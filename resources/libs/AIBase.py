from libs.PipeLine import ScopedTiming
import os
import ujson
from media.sensor import *
from media.display import *
from media.media import *
from time import *
import nncase_runtime as nn
import ulab.numpy as np
import time
import utime
import image
import random
import gc
import sys

# AIBase类别主要抽象的是AI任务推理流程
class AIBase:
    """Base class for the preprocess, inference and postprocess lifecycle."""
    def __init__(self,kmodel_path,model_input_size=None,rgb888p_size=None,debug_mode=0):
        # kmodel路径
        """Load the model and initialize inference state.

        Args:
            kmodel_path (str): Path to the kmodel file.
            model_input_size (list or None): Model input [width, height], in pixels.
            rgb888p_size (list or None): RGB planar input [width, height], in pixels.
            debug_mode (int): Enable timing output when greater than zero.

        Notes:
            Subclasses configure preprocessing and implement postprocess().
            Call deinit() to release native resources when the application ends.
        """
        self.kmodel_path=kmodel_path
        # 模型输入分辨率
        self.model_input_size=model_input_size
        # sensor给到AI的图像分辨率
        self.rgb888p_size=rgb888p_size
        # 调试模式
        self.debug_mode=debug_mode
        # kpu对象
        self.kpu = None
        self.cur_img = None
        self.tensors = []
        self.results = []
        try:
            self.kpu = nn.kpu()
            self.kpu.load_kmodel(self.kmodel_path)
        except BaseException:
            try:
                AIBase.deinit(self)
            except Exception as error:
                print("model load cleanup failed:", error)
            raise

    def get_kmodel_inputs_num(self):
        """Get the loaded model's input count.

        Returns:
            int: Number of model inputs.
        """
        return self.kpu.inputs_size()
    
    def get_kmodel_outputs_num(self):
        """Get the loaded model's output count.

        Returns:
            int: Number of model outputs.
        """
        return self.kpu.outputs_size()
    
    def preprocess(self,input_np):
        """Run the configured AI2D preprocessing stage.

        Args:
            input_np (ulab.numpy.ndarray): Input array matching the configured shape and dtype.

        Returns:
            list: One AI2D-owned output tensor, reused by later preprocessing calls.

        Notes:
            Override this hook for models requiring different input preparation.
        """
        with ScopedTiming("preprocess",self.debug_mode > 0):
            return [self.ai2d.run(input_np)]

    def inference(self,tensors):
        """Run inference and copy model outputs to ndarrays.

        Args:
            tensors (list): Input tensors in model input order; ownership stays with the caller.

        Returns:
            list: Reused result list containing independently copied output arrays.

        Notes:
            The list is cleared by the next inference call. Retain individual
            arrays or copy the list when keeping results across calls.
            Temporary native output tensors are released after conversion.
        """
        with ScopedTiming("set input",self.debug_mode > 0):
            self.results.clear()
            for i in range(self.kpu.inputs_size()):
                # 将ai2d的输出tensor绑定为kmodel的输入数据
                self.kpu.set_input_tensor(i, tensors[i])
        with ScopedTiming("kpu run",self.debug_mode > 0):
            # 运行kmodel做推理
            self.kpu.run()
        with ScopedTiming("get output",self.debug_mode > 0):
            # 获取kmodel的推理输出tensor,输出可能为多个，因此返回的是一个列表
            for i in range(self.kpu.outputs_size()):
                output_data = self.kpu.get_output_tensor(i)
                try:
                    result = output_data.to_numpy()
                    self.results.append(result)
                finally:
                    release = getattr(output_data, "release", None)
                    if callable(release):
                        try:
                            release()
                        except Exception:
                            pass
                    output_data = None
            return self.results

    # 基类后处理接口
    def postprocess(self,results):
        """Provide the subclass hook for interpreting model outputs.

        Args:
            results (list): Model output ndarrays in output index order.

        Returns:
            None: The base implementation does not decode outputs.
        """
        return

    # kmodel运行pipe，包括预处理+推理+后处理，后处理在单独的任务类中实现
    def run(self,input_np):
        """Run preprocessing, inference and task-specific postprocessing.

        Args:
            input_np (ulab.numpy.ndarray): Input array matching the configured shape and dtype.

        Returns:
            object: The value returned by the subclass postprocess() method.

        Notes:
            The input is retained as cur_img. Keep borrowed frame storage valid
            until processing has completed.

            Input tensor ownership differs per task. Vision tasks return an
            Ai2d-owned tensor that Ai2d keeps alive and reuses, so dropping the
            list is harmless. Audio tasks such as KWS build their inputs with
            nn.from_numpy() inside preprocess(), which makes self.tensors the
            only owner. The previous inputs are therefore released only after
            inference() has bound the new ones, never while the interpreter is
            still holding them.
        """
        self.cur_img=input_np
        previous_tensors=self.tensors
        self.tensors=self.preprocess(input_np)
        self.results=self.inference(self.tensors)
        if previous_tensors is not self.tensors:
            previous_tensors.clear()
        return self.postprocess(self.results)

    # AIBase销毁函数
    def deinit(self):
        """Release model, preprocessing and retained inference resources.

        Returns:
            None.

        Raises:
            Exception: The first resource cleanup error, after other cleanup attempts.

        Notes:
            Successful cleanup is safe to repeat. Failed native resources remain
            referenced for a later cleanup attempt. This also runs garbage
            collection and requests runtime memory-pool shrinking.
        """
        if getattr(self, "_deinitialized", False):
            return
        with ScopedTiming("deinit",getattr(self, "debug_mode", 0) > 0):
            self.cur_img = None

            if hasattr(self, "masks"):
                self.masks = None

            # The interpreter keeps references to its bound input/output
            # tensors. Drop it before releasing those tensors, whoever owns
            # them: vision tasks bind Ai2d-owned inputs that outlive the list,
            # but audio tasks such as KWS bind nn.from_numpy() tensors whose
            # only owner is self.tensors. Clearing the list first would free an
            # input the interpreter is still bound to.
            kpu = getattr(self, "kpu", None)
            self.kpu = None
            cleanup_error = None
            if kpu is not None:
                try:
                    kpu.release()
                except Exception as error:
                    self.kpu = kpu
                    cleanup_error = error

            if hasattr(self, "tensors"):
                self.tensors.clear()
                self.tensors = []
            if hasattr(self, "results"):
                self.results.clear()
                self.results = []

            ai2d = getattr(self, "ai2d", None)
            self.ai2d = None
            if ai2d is not None:
                try:
                    deinit = getattr(ai2d, "deinit", None)
                    if callable(deinit):
                        deinit()
                except Exception as error:
                    self.ai2d = ai2d
                    if cleanup_error is None:
                        cleanup_error = error
            try:
                gc.collect()
                nn.shrink_memory_pool()
                gc.collect()
            except Exception as error:
                if cleanup_error is None:
                    cleanup_error = error
            time.sleep_ms(100)
            if cleanup_error is not None:
                raise cleanup_error
            self._deinitialized = True
