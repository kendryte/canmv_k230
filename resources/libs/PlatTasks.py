from libs.AIBase import AIBase
from libs.AI2D import Ai2d
from libs.Utils import *
import os,sys,ujson,gc,math
from media.media import *
import nncase_runtime as nn
import ulab.numpy as np
import image
import aicube
import ujson

# 自定义分类任务类
class ClassificationApp(AIBase):
    """Wrap platform single-label classification models."""
    def __init__(self,mode,kmodel_path,labels,model_input_size=[224,224],confidence_threshold=0.7,rgb888p_size=[224,224],display_size=[800,480],debug_mode=0):
        """Initialize the ClassificationApp model and preprocessing resources.

        Args:
            mode (str): Processing mode, 'image' or 'video'.
            kmodel_path (str): Path to the kmodel file.
            labels (list): Class names in model class-index order.
            model_input_size (list or None): Model input [width, height], in pixels.
            confidence_threshold (float): Task-specific classification or similarity threshold.
            rgb888p_size (list or None): RGB planar input [width, height], in pixels.
            display_size (list or None): Display [width, height], in pixels.
            debug_mode (int): Enable timing output when greater than zero.

        Raises:
            ValueError: The processing mode is unsupported.

        Notes:
            Call config_preprocess() before inference and deinit() when finished.
            Dimensions use [width, height]; video input widths are aligned to 16.
        """
        try:
            if mode not in ["video","image"]:
                print("Please select the correct inference mode, including 'video', 'image'.")
                raise ValueError("Invalid mode")
            else:
                self.mode=mode
            super().__init__(kmodel_path,model_input_size,rgb888p_size,debug_mode)
            self.kmodel_path=kmodel_path
            # 分类标签
            self.labels=labels
            self.num_classes=len(self.labels)
            # 模型输入分辨率
            self.model_input_size=model_input_size
            # 分类阈值
            self.confidence_threshold=confidence_threshold
            self.mode=mode
            if self.mode=="video":
                # sensor给到AI的图像分辨率,宽16字节对齐
                self.rgb888p_size=[ALIGN_UP(rgb888p_size[0],16),rgb888p_size[1]]
            else:
                self.rgb888p_size=[rgb888p_size[0],rgb888p_size[1]]
            if self.mode=="video":
                # 显示分辨率，宽16字节对齐
                self.display_size=[ALIGN_UP(display_size[0],16),display_size[1]]
            else:
                self.display_size=[display_size[0],display_size[1]]
            self.debug_mode=debug_mode
            self.cur_result={"label":"","score":0.0}
            # Ai2d实例，用于实现模型预处理
            self.ai2d=Ai2d(debug_mode)
            # 设置Ai2d的输入输出格式和类型
            self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT,nn.ai2d_format.NCHW_FMT,np.uint8, np.uint8)
        except BaseException:
            try:
                self.deinit()
            except Exception as error:
                print("task constructor cleanup failed:", error)
            raise


    # 配置预处理操作，这里使用了resize，Ai2d支持crop/shift/pad/resize/affine，具体代码请打开/sdcard/app/libs/AI2D.py查看
    def config_preprocess(self,input_image_size=None):
        """Build preprocessing for the supplied image dimensions.

        Args:
            input_image_size (list or None): Input [width, height]; None uses rgb888p_size.

        Returns:
            None.

        Notes:
            Resize the input to the model input dimensions.
            None selects the configured rgb888p_size.
        """
        with ScopedTiming("set preprocess config",self.debug_mode > 0):
            # 初始化ai2d预处理配置，默认为sensor给到AI的尺寸，您可以通过设置input_image_size自行修改输入尺寸
            ai2d_input_size=input_image_size if input_image_size else self.rgb888p_size
            self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
            # build参数包含输入shape和输出shape
            self.ai2d.build([1,3,ai2d_input_size[1],ai2d_input_size[0]],[1,3,self.model_input_size[1],self.model_input_size[0]])

    # 自定义当前任务的后处理，results是模型输出的array列表
    def postprocess(self,results):
        """Decode a single-label classification result.

        Args:
            results (list): Model output ndarrays in output index order.

        Returns:
            dict: {'label': class name, 'score': confidence}.

        Notes:
            Models with more than two labels use softmax; binary models use
            a single sigmoid logit and require two labels.
        """
        with ScopedTiming("postprocess",self.debug_mode > 0):
            self.cur_result={"label":"","score":0.0}
            if self.num_classes>2:
                softmax_res=softmax(results[0][0])
                res_idx=np.argmax(softmax_res)
                # 如果类别分数大于阈值，返回当前类别和分数
                if softmax_res[res_idx]>self.confidence_threshold:
                    self.cur_result["label"]=self.labels[res_idx]
                    self.cur_result["score"]=softmax_res[res_idx]
            else:
                sigmoid_res=sigmoid(results[0][0][0])
                if sigmoid_res>self.confidence_threshold:
                    self.cur_result["label"]=self.labels[1]
                    self.cur_result["score"]=sigmoid_res
                else:
                    self.cur_result["label"]=self.labels[0]
                    self.cur_result["score"]=1.0-sigmoid_res
            return self.cur_result

    # 将结果绘制到屏幕上
    def draw_result(self,draw_img,res):
        """Draw the task result on the configured output image.

        Args:
            draw_img (image.Image): Drawing target for the configured mode.
            res (object): Result returned by this task's postprocess() method.

        Returns:
            None.

        Notes:
            Video mode clears the target before drawing.
        """
        with ScopedTiming("draw result",self.debug_mode > 0):
            if self.mode=="video":
                draw_img.clear()
            if res["label"]!="":
                draw_img.draw_string_advanced(5,5,32,res["label"]+" "+str(round(res["score"],3)),color=(0,255,0))

    def get_cur_result(self):
        """Get the current task result without copying it.

        Returns:
            dict: {'label': class name, 'score': confidence}.

        Notes:
            The returned dict is shared with the application. Copy any data that
            must remain independent of later processing or caller mutation.
        """
        return self.cur_result

    def deinit(self):
        """Release inference resources and reset retained task results.

        Returns:
            None.

        Raises:
            Exception: An error propagated from AIBase.deinit().

        Notes:
            Replaces the current result without clearing a dict held by a caller.
        """
        try:
            AIBase.deinit(self)
        finally:
            # Replace references without mutating results retained by callers.
            self.cur_result = {'label': '', 'score': 0.0}


class DetectionApp(AIBase):
    """Wrap platform anchor-based, anchor-free and GFL detection models."""
    def __init__(self,mode,kmodel_path,labels,model_input_size=[640,640],anchors=[10,13,16,30,33,23,30,61,62,45,59,119,116,90,156,198,373,326],model_type="AnchorBaseDet",confidence_threshold=0.5,nms_threshold=0.25,rgb888p_size=[1280,720],display_size=[1920,1080],debug_mode=0):
        """Initialize the DetectionApp model and preprocessing resources.

        Args:
            mode (str): Processing mode, 'image' or 'video'.
            kmodel_path (str): Path to the kmodel file.
            labels (list): Class names in model class-index order.
            model_input_size (list or None): Model input [width, height], in pixels.
            anchors (list): Anchor dimensions; AnchorBaseDet requires 18 values.
            model_type (str): 'AnchorBaseDet', 'AnchorFreeDet', or 'GFLDet'.
            confidence_threshold (float): Task-specific classification or similarity threshold.
            nms_threshold (float): Intersection-over-union threshold for non-maximum suppression.
            rgb888p_size (list or None): RGB planar input [width, height], in pixels.
            display_size (list or None): Display [width, height], in pixels.
            debug_mode (int): Enable timing output when greater than zero.

        Raises:
            ValueError: The processing mode is unsupported. AnchorBaseDet also
            requires exactly 18 anchor values.

        Notes:
            Call config_preprocess() before inference and deinit() when finished.
            Dimensions use [width, height]; video input widths are aligned to 16.
        """
        try:
            if mode not in ["video","image"]:
                print("Please select the correct inference mode, including 'video', 'image'.")
                raise ValueError("Invalid mode")
            else:
                self.mode=mode
            super().__init__(kmodel_path,model_input_size,rgb888p_size,debug_mode)
            # kmodel路径
            self.kmodel_path=kmodel_path
            # 类别标签
            self.labels=labels
            self.num_classes=len(self.labels)
            # 模型输入分辨率
            self.model_input_size=model_input_size
            # 检测任务的锚框
            if model_type == "AnchorBaseDet" and len(anchors) != 18:
                raise ValueError("AnchorBaseDet requires 18 anchor values")
            self.anchors=anchors
            # 模型类型，支持"AnchorBaseDet","AnchorFreeDet","GFLDet"三种模型
            self.model_type=model_type
            # 检测框类别置信度阈值
            self.confidence_threshold=confidence_threshold
            # 检测框NMS筛选阈值
            self.nms_threshold=nms_threshold
            # NMS选项，如果为True做类间NMS,如果为False做类内NMS
            self.nms_option=False
            # 输出特征图的降采样倍数
            self.strides=[8,16,32]
            if self.mode=="video":
                # sensor给到AI的图像分辨率,宽16字节对齐
                self.rgb888p_size=[ALIGN_UP(rgb888p_size[0],16),rgb888p_size[1]]
            else:
                self.rgb888p_size=[rgb888p_size[0],rgb888p_size[1]]
            if self.mode=="video":
                # 显示分辨率，宽16字节对齐
                self.display_size=[ALIGN_UP(display_size[0],16),display_size[1]]
            else:
                self.display_size=[display_size[0],display_size[1]]
            # 调试模式
            self.debug_mode=debug_mode
            # 检测框预置颜色值
            self.color_four=get_colors(len(self.labels))
            self.cur_result={"boxes":[],"scores":[], "idx":[]}
            # Ai2d实例，用于实现模型预处理
            self.ai2d=Ai2d(debug_mode)
            # 设置Ai2d的输入输出格式和类型
            self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT,nn.ai2d_format.NCHW_FMT,np.uint8, np.uint8)
        except BaseException:
            try:
                self.deinit()
            except Exception as error:
                print("task constructor cleanup failed:", error)
            raise

    # 配置预处理操作，这里使用了pad和resize，Ai2d支持crop/shift/pad/resize/affine，具体代码请打开/sdcard/app/libs/AI2D.py查看
    def config_preprocess(self,input_image_size=None):
        """Build preprocessing for the supplied image dimensions.

        Args:
            input_image_size (list or None): Input [width, height]; None uses rgb888p_size.

        Returns:
            None.

        Notes:
            Resize with centered padding filled with 114.
            None selects the configured rgb888p_size.
        """
        with ScopedTiming("set preprocess config",self.debug_mode > 0):
            # 初始化ai2d预处理配置，默认为sensor给到AI的尺寸，您可以通过设置input_image_size自行修改输入尺寸
            ai2d_input_size=input_image_size if input_image_size else self.rgb888p_size
            # 计算padding参数
            top,bottom,left,right,_=center_pad_param(ai2d_input_size,self.model_input_size)
            # 配置padding预处理
            self.ai2d.pad([0,0,0,0,top,bottom,left,right], 0, [114,114,114])
            # 配置resize预处理
            self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
            # build预处理过程，参数为输入tensor的shape和输出tensor的shape
            self.ai2d.build([1,3,ai2d_input_size[1],ai2d_input_size[0]],[1,3,self.model_input_size[1],self.model_input_size[0]])

    # 自定义当前任务的后处理,这里调用了aicube模块的后处理接口
    def postprocess(self,results):
        """Decode detection outputs through the selected aicube postprocessor.

        Args:
            results (list): Model output ndarrays in output index order.

        Returns:
            dict: 'boxes' contains input-space [x1, y1, x2, y2] boxes;
            'scores' and 'idx' contain matching confidences and class indices.
        """
        with ScopedTiming("postprocess",self.debug_mode > 0):
            self.cur_result={"boxes":[],"scores":[], "idx":[]}
            # AnchorBaseDet模型的后处理
            if self.model_type == "AnchorBaseDet":
                det_boxes = aicube.anchorbasedet_post_process( results[0], results[1], results[2], self.model_input_size, self.rgb888p_size, self.strides, self.num_classes, self.confidence_threshold, self.nms_threshold, self.anchors, self.nms_option)
            # GFLDet模型的后处理
            elif self.model_type == "GFLDet":
                det_boxes = aicube.gfldet_post_process( results[0], results[1], results[2], self.model_input_size, self.rgb888p_size, self.strides,self.num_classes, self.confidence_threshold, self.nms_threshold, self.nms_option)
            # AnchorFreeDet模型的后处理
            elif self.model_type=="AnchorFreeDet":
                det_boxes = aicube.anchorfreedet_post_process( results[0], results[1], results[2], self.model_input_size, self.rgb888p_size, self.strides, self.num_classes, self.confidence_threshold, self.nms_threshold, self.nms_option)
            else:
                det_boxes=None
            
            if det_boxes:
                det_boxes=np.ndarray(det_boxes)
                self.cur_result["boxes"]=np.ndarray(det_boxes[:,2:6],dtype=np.int16)
                self.cur_result["scores"]=det_boxes[:,1]
                self.cur_result["idx"]=np.ndarray(det_boxes[:,0],dtype=np.int16)
            return self.cur_result

    # 将结果绘制到屏幕上
    def draw_result(self,draw_img,res):
        """Draw the task result on the configured output image.

        Args:
            draw_img (image.Image): Drawing target for the configured mode.
            res (object): Result returned by this task's postprocess() method.

        Returns:
            None.

        Notes:
            Video mode clears the target before drawing.
        """
        with ScopedTiming("draw osd",self.debug_mode > 0):
            if self.mode=="video":
                draw_img.clear()
            if res["boxes"]:
                for i in range(len(res["boxes"])):
                    x=int(res["boxes"][i][0] * self.display_size[0] // self.rgb888p_size[0])
                    y=int(res["boxes"][i][1] * self.display_size[1] // self.rgb888p_size[1])
                    w = int(float(res["boxes"][i][2] - res["boxes"][i][0]) * self.display_size[0] // self.rgb888p_size[0])
                    h = int(float(res["boxes"][i][3] - res["boxes"][i][1]) * self.display_size[1] // self.rgb888p_size[1])
                    draw_img.draw_rectangle(x , y , w , h , color=self.color_four[res["idx"][i]])
                    draw_img.draw_string_advanced(x, y-50,24, self.labels[res["idx"][i]] + " " + str(round(res["scores"][i],2)) , color=self.color_four[res["idx"][i]])

    def get_cur_result(self):
        """Get the current task result without copying it.

        Returns:
            dict: 'boxes' contains input-space [x1, y1, x2, y2] boxes;
            'scores' and 'idx' contain matching confidences and class indices.

        Notes:
            The returned dict is shared with the application. Copy any data that
            must remain independent of later processing or caller mutation.
        """
        return self.cur_result

    def deinit(self):
        """Release inference resources and reset retained task results.

        Returns:
            None.

        Raises:
            Exception: An error propagated from AIBase.deinit().

        Notes:
            Replaces the current result without clearing a dict held by a caller.
        """
        try:
            AIBase.deinit(self)
        finally:
            # Replace references without mutating results retained by callers.
            self.cur_result = {'boxes': [], 'scores': [], 'idx': []}

class SegmentationApp(AIBase):
    """Wrap platform semantic segmentation models."""
    def __init__(self,mode,kmodel_path,labels,model_input_size=[320,320],rgb888p_size=[320,320],display_size=[1920,1080],debug_mode=0):
        """Initialize the SegmentationApp model and preprocessing resources.

        Args:
            mode (str): Processing mode, 'image' or 'video'.
            kmodel_path (str): Path to the kmodel file.
            labels (list): Class names in model class-index order.
            model_input_size (list or None): Model input [width, height], in pixels.
            rgb888p_size (list or None): RGB planar input [width, height], in pixels.
            display_size (list or None): Display [width, height], in pixels.
            debug_mode (int): Enable timing output when greater than zero.

        Raises:
            ValueError: The processing mode is unsupported.

        Notes:
            Call config_preprocess() before inference and deinit() when finished.
            Dimensions use [width, height]; video input widths are aligned to 16.
        """
        try:
            if mode not in ["video","image"]:
                print("Please select the correct inference mode, including 'video', 'image'.")
                raise ValueError("Invalid mode")
            else:
                self.mode=mode
            super().__init__(kmodel_path,model_input_size,rgb888p_size,debug_mode)
            # kmodel路径
            self.kmodel_path=kmodel_path
            self.labels=labels
            # 分割类别数
            self.num_classes=len(self.labels)
            # 模型输入分辨率
            self.model_input_size=model_input_size
            if self.mode=="video":
                # sensor给到AI的图像分辨率,宽16字节对齐
                self.rgb888p_size=[ALIGN_UP(rgb888p_size[0],16),rgb888p_size[1]]
            else:
                self.rgb888p_size=[rgb888p_size[0],rgb888p_size[1]]
            if self.mode=="video":
                # 显示分辨率，宽16字节对齐
                self.display_size=[ALIGN_UP(display_size[0],16),display_size[1]]
            else:
                self.display_size=[display_size[0],display_size[1]]
            self.cur_result={"mask":None}
            # debug_mode模式
            self.debug_mode=debug_mode
            # Ai2d实例，用于实现模型预处理
            self.ai2d=Ai2d(debug_mode)
            # 设置Ai2d的输入输出格式和类型
            self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT,nn.ai2d_format.NCHW_FMT,np.uint8, np.uint8)
        except BaseException:
            try:
                self.deinit()
            except Exception as error:
                print("task constructor cleanup failed:", error)
            raise

    # 配置预处理操作，这里使用了resize，Ai2d支持crop/shift/pad/resize/affine，具体代码请打开/sdcard/app/libs/AI2D.py查看
    def config_preprocess(self,input_image_size=None):
        """Build preprocessing for the supplied image dimensions.

        Args:
            input_image_size (list or None): Input [width, height]; None uses rgb888p_size.

        Returns:
            None.

        Notes:
            Resize the input to the model input dimensions.
            None selects the configured rgb888p_size.
        """
        with ScopedTiming("set preprocess config",self.debug_mode > 0):
            # 初始化ai2d预处理配置，默认为sensor给到AI的尺寸，您可以通过设置input_image_size自行修改输入尺寸
            ai2d_input_size=input_image_size if input_image_size else self.rgb888p_size
            self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
            # build预处理过程，参数为输入tensor的shape和输出tensor的shape
            self.ai2d.build([1,3,ai2d_input_size[1],ai2d_input_size[0]],[1,3,self.model_input_size[1],self.model_input_size[0]])

    # 自定义当前任务的后处理
    def postprocess(self,input_np):
        """Convert the stored segmentation output into a mask image.

        Args:
            input_np (object): Reserved compatibility argument; unused.

        Returns:
            dict: {'mask': image.Image} with an ARGB8888 video mask or RGB888 image mask.

        Notes:
            The input_np argument is retained for compatibility and ignored;
            this method reads self.results[0]. The returned dict is also cur_result.
        """
        with ScopedTiming("postprocess",self.debug_mode > 0):
            self.cur_result["mask"]=None
            # 这里使用了aicube封装的接口seg_post_process做后处理，返回一个和display_size相同分辨率的mask图
            mask = aicube.seg_post_process(self.results[0], self.num_classes, [self.model_input_size[1],self.model_input_size[0]], [self.display_size[1],self.display_size[0]])
            # 在mask数据上创建osd图像并返回
            if self.mode=="video":
                self.cur_result["mask"] = image.Image(self.display_size[0], self.display_size[1], image.ARGB8888,alloc=image.ALLOC_REF,data=mask)
            else:
                self.cur_result["mask"] = image.Image(self.display_size[0], self.display_size[1], image.RGB888,alloc=image.ALLOC_REF,data=mask[:,:,1:4].copy())
            return self.cur_result

    # 绘制分割结果，将创建的mask图像copy到osd_img上
    def draw_result(self,osd_img,res):
        """Draw the task result on the configured output image.

        Args:
            osd_img (image.Image): OSD drawing target for video mode.
            res (object): Result returned by this task's postprocess() method.

        Returns:
            None.

        Notes:
            Video mode clears and copies the mask into osd_img.
            Image mode performs no drawing.
        """
        with ScopedTiming("draw osd",self.debug_mode > 0):
            if self.mode=="video":
                osd_img.clear()
            if res["mask"]:
                if self.mode=="video":
                    res["mask"].copy_to(osd_img)
                
    def get_cur_result(self):
        """Get the current task result without copying it.

        Returns:
            dict: {'mask': image.Image} with an ARGB8888 video mask or RGB888 image mask.

        Notes:
            The returned dict is shared with the application. Copy any data that
            must remain independent of later processing or caller mutation.
        """
        return self.cur_result

    def deinit(self):
        """Release inference resources and reset retained task results.

        Returns:
            None.

        Raises:
            Exception: An error propagated from AIBase.deinit().

        Notes:
            Replaces the current result without clearing a dict held by a caller.
        """
        try:
            AIBase.deinit(self)
        finally:
            # Replace references without mutating results retained by callers.
            self.cur_result = {'mask': None}


class OCRDetectionApp(AIBase):
    """Detect text quadrilaterals and produce cropped text images."""
    def __init__(self,mode,kmodel_path,model_input_size,mask_threshold=0.5,box_threshold=0.5,rgb888p_size=[1280,720],display_size=[1920,1080],debug_mode=0):
        """Initialize the OCRDetectionApp model and preprocessing resources.

        Args:
            mode (str): Processing mode, 'image' or 'video'.
            kmodel_path (str): Path to the kmodel file.
            model_input_size (list or None): Model input [width, height], in pixels.
            mask_threshold (float): OCR text-region mask threshold.
            box_threshold (float): OCR text-box confidence threshold.
            rgb888p_size (list or None): RGB planar input [width, height], in pixels.
            display_size (list or None): Display [width, height], in pixels.
            debug_mode (int): Enable timing output when greater than zero.

        Raises:
            ValueError: The processing mode is unsupported.

        Notes:
            Call config_preprocess() before inference and deinit() when finished.
            Dimensions use [width, height]; video input widths are aligned to 16.
        """
        try:
            if mode not in ["video","image"]:
                print("Please select the correct inference mode, including 'video', 'image'.")
                raise ValueError("Invalid mode")
            else:
                self.mode=mode
            super().__init__(kmodel_path,model_input_size,rgb888p_size,debug_mode)
            # kmodel路径
            self.kmodel_path=kmodel_path
            # OCR检测模型输入分辨率[width,height]
            self.model_input_size=model_input_size
            # ocr检测输出feature map二值化阈值
            self.mask_threshold=mask_threshold
            # 检测框分数阈值
            self.box_threshold=box_threshold
            if self.mode=="video":
                # sensor给到AI的图像分辨率,宽16字节对齐
                self.rgb888p_size=[ALIGN_UP(rgb888p_size[0],16),rgb888p_size[1]]
            else:
                self.rgb888p_size=[rgb888p_size[0],rgb888p_size[1]]
            if self.mode=="video":
                # 显示分辨率，宽16字节对齐
                self.display_size=[ALIGN_UP(display_size[0],16),display_size[1]]
            else:
                self.display_size=[display_size[0],display_size[1]]
            self.cur_result={"boxes":[],"crop_images":[]}
            # debug模式
            self.debug_mode=debug_mode
            # Ai2d实例，用于实现模型预处理
            self.ai2d=Ai2d(debug_mode)
            # 设置Ai2d的输入输出格式和类型
            self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT,nn.ai2d_format.NCHW_FMT,np.uint8, np.uint8)
        except BaseException:
            try:
                self.deinit()
            except Exception as error:
                print("task constructor cleanup failed:", error)
            raise

    # 配置预处理操作，这里使用了pad和resize，Ai2d支持crop/shift/pad/resize/affine，具体代码请打开/sdcard/app/libs/AI2D.py查看
    def config_preprocess(self,input_image_size=None):
        """Build preprocessing for the supplied image dimensions.

        Args:
            input_image_size (list or None): Input [width, height]; None uses rgb888p_size.

        Returns:
            None.

        Notes:
            Resize with top-left letterbox padding filled with 114.
            None selects the configured rgb888p_size.
        """
        with ScopedTiming("set preprocess config",self.debug_mode > 0):
            # 初始化ai2d预处理配置，默认为sensor给到AI的尺寸，您可以通过设置input_image_size自行修改输入尺寸
            ai2d_input_size=input_image_size if input_image_size else self.rgb888p_size
            # 计算padding参数
            top,bottom,left,right,_=letterbox_pad_param(ai2d_input_size,self.model_input_size)
            # 配置padding预处理
            self.ai2d.pad([0,0,0,0,top,bottom,left,right], 0, [114,114,114])
            # 设置resize预处理
            self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
            # build预处理过程，参数为输入tensor的shape和输出tensor的shape
            self.ai2d.build([1,3,ai2d_input_size[1],ai2d_input_size[0]],[1,3,self.model_input_size[1],self.model_input_size[0]])

    # 自定义当前任务的后处理
    def postprocess(self,results):
        """Decode text regions and crop them from the current input image.

        Args:
            results (list): Model output ndarrays in output index order.

        Returns:
            dict: 'boxes' contains eight-coordinate input-space quadrilaterals;
            'crop_images' contains corresponding cropped HWC arrays.

        Notes:
            Requires cur_img from the same inference. Cropping uses a contiguous
            HWC copy of that image.
        """
        with ScopedTiming("postprocess",self.debug_mode > 0):
            # chw2hwc
            hwc_array=chw2hwc(self.cur_img)
            # det_boxes结构为[[crop_array_nhwc,[p1_x,p1_y,p2_x,p2_y,p3_x,p3_y,p4_x,p4_y]],...]，crop_array_nhwc是切割的检测框数据，后八个数据表示检测框的左上，右上，右下，左下的坐标
            det_boxes = aicube.ocr_post_process(results[0][:,:,:,0].reshape(-1), hwc_array.reshape(-1),self.model_input_size,self.rgb888p_size, self.mask_threshold, self.box_threshold)
            # 只取坐标值
            self.cur_result={"boxes":[],"crop_images":[]}
            for det_box in det_boxes:
                self.cur_result["crop_images"].append(det_box[0])
                self.cur_result["boxes"].append(det_box[1])
            return self.cur_result

    # 绘制推理结果
    def draw_result(self,osd_img,res):
        """Draw the task result on the configured output image.

        Args:
            osd_img (image.Image): OSD drawing target for video mode.
            res (object): Reserved compatibility argument; unused.

        Returns:
            None.

        Notes:
            The res argument is retained for compatibility; drawing reads
            self.cur_result. Input-space boxes are scaled to display dimensions.
        """
        if self.mode=="video":
            osd_img.clear()
        # 一次绘制四条边，得到文本检测的四边形，坐标需要从原图分辨率转换成显示分辨率
        for i in range(len(self.cur_result["boxes"])):
            for j in range(4):
                x1=self.cur_result["boxes"][i][2*j]*self.display_size[0]//self.rgb888p_size[0]
                y1=self.cur_result["boxes"][i][2*j+1]*self.display_size[1]//self.rgb888p_size[1]
                x2=self.cur_result["boxes"][i][(2*j+2)%8]*self.display_size[0]//self.rgb888p_size[0]
                y2=self.cur_result["boxes"][i][(2*j+3)%8]*self.display_size[1]//self.rgb888p_size[1]
                osd_img.draw_line(int(x1),int(y1),int(x2),int(y2),color=(255,255,0,0),thickness=4)

    def get_cur_result(self):
        """Get the current task result without copying it.

        Returns:
            dict: 'boxes' contains eight-coordinate input-space quadrilaterals;
            'crop_images' contains corresponding cropped HWC arrays.

        Notes:
            The returned dict is shared with the application. Copy any data that
            must remain independent of later processing or caller mutation.
        """
        return self.cur_result

    def deinit(self):
        """Release inference resources and reset retained task results.

        Returns:
            None.

        Raises:
            Exception: An error propagated from AIBase.deinit().

        Notes:
            Replaces the current result without clearing a dict held by a caller.
        """
        try:
            AIBase.deinit(self)
        finally:
            # Replace references without mutating results retained by callers.
            self.cur_result = {'boxes': [], 'crop_images': []}

class OCRRecognitionApp(AIBase):
    """Decode text recognition models with greedy CTC decoding."""
    def __init__(self,mode,kmodel_path,model_input_size,ocr_dict,rgb888p_size=[1280,720],display_size=[1920,1080],debug_mode=0):
        """Initialize the OCRRecognitionApp model and preprocessing resources.

        Args:
            mode (str): Processing mode, 'image' or 'video'.
            kmodel_path (str): Path to the kmodel file.
            model_input_size (list or None): Model input [width, height], in pixels.
            ocr_dict (list): Index-to-character table; the last index is the CTC blank.
            rgb888p_size (list or None): RGB planar input [width, height], in pixels.
            display_size (list or None): Display [width, height], in pixels.
            debug_mode (int): Enable timing output when greater than zero.

        Raises:
            ValueError: The processing mode is unsupported.

        Notes:
            Call config_preprocess() before inference and deinit() when finished.
            Dimensions use [width, height]; video input widths are aligned to 16.
        """
        try:
            if mode not in ["video","image"]:
                print("Please select the correct inference mode, including 'video', 'image'.")
                raise ValueError("Invalid mode")
            else:
                self.mode=mode
            super().__init__(kmodel_path,model_input_size,rgb888p_size,debug_mode)
            # kmodel路径
            self.kmodel_path=kmodel_path
            # OCR检测模型输入分辨率[width,height]
            self.model_input_size=model_input_size
            self.ocr_dict=ocr_dict
            if self.mode=="video":
                # sensor给到AI的图像分辨率,宽16字节对齐
                self.rgb888p_size=[ALIGN_UP(rgb888p_size[0],16),rgb888p_size[1]]
            else:
                self.rgb888p_size=[rgb888p_size[0],rgb888p_size[1]]
            if self.mode=="video":
                # 显示分辨率，宽16字节对齐
                self.display_size=[ALIGN_UP(display_size[0],16),display_size[1]]
            else:
                self.display_size=[display_size[0],display_size[1]]
            self.cur_result={"text":""}
            # debug模式
            self.debug_mode=debug_mode
            # Ai2d实例，用于实现模型预处理
            self.ai2d=Ai2d(debug_mode)
            # 设置Ai2d的输入输出格式和类型
            self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT,nn.ai2d_format.NCHW_FMT,np.uint8, np.uint8)
        except BaseException:
            try:
                self.deinit()
            except Exception as error:
                print("task constructor cleanup failed:", error)
            raise

    # 配置预处理操作，这里使用了pad和resize，Ai2d支持crop/shift/pad/resize/affine，具体代码请打开/sdcard/app/libs/AI2D.py查看
    def config_preprocess(self,input_image_size=None):
        """Build preprocessing for the supplied image dimensions.

        Args:
            input_image_size (list or None): Input [width, height]; None uses rgb888p_size.

        Returns:
            None.

        Notes:
            Resize with top-left letterbox padding filled with zero.
            None selects the configured rgb888p_size.
        """
        with ScopedTiming("set preprocess config",self.debug_mode > 0):
            # 初始化ai2d预处理配置，默认为sensor给到AI的尺寸，您可以通过设置input_image_size自行修改输入尺寸
            ai2d_input_size=input_image_size if input_image_size else self.rgb888p_size
            # 计算padding参数
            top,bottom,left,right,_=letterbox_pad_param(ai2d_input_size,self.model_input_size)
            # 配置padding预处理
            self.ai2d.pad([0,0,0,0,top,bottom,left,right], 0, [0,0,0])
            # 设置resize预处理
            self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
            # build预处理过程，参数为输入tensor的shape和输出tensor的shape
            self.ai2d.build([1,3,ai2d_input_size[1],ai2d_input_size[0]],[1,3,self.model_input_size[1],self.model_input_size[0]])

    # 自定义当前任务的后处理
    def postprocess(self,results):
        """Greedily decode CTC output, removing blanks and adjacent repeats.

        Args:
            results (list): Model output ndarrays in output index order.

        Returns:
            dict: {'text': recognized string}.

        Notes:
            The last ocr_dict entry is treated as the blank token.
        """
        with ScopedTiming("postprocess",self.debug_mode > 0):
            self.cur_result["text"]=""
            chars = []
            preds = np.argmax(results[0], axis=2).reshape((-1))
            for i in range(len(preds)):
                if preds[i] != (len(self.ocr_dict) - 1) and (not (i > 0 and preds[i - 1] == preds[i])):
                    chars.append(self.ocr_dict[preds[i]])
            self.cur_result["text"] = "".join(chars)
            return self.cur_result

    # 打印推理结果
    def print_result(self,osd_img,res):
        """Print recognized text and clear the OSD in video mode.

        Args:
            osd_img (image.Image): OSD drawing target for video mode.
            res (object): Result returned by this task's postprocess() method.

        Returns:
            None.
        """
        if self.mode=="video":
            osd_img.clear()
        print("text:",res["text"])
        
    # 绘制推理结果
    def draw_result(self,osd_img,det_boxes,ocr_texts):
        """Draw corresponding text boxes and recognized strings.

        Args:
            osd_img (image.Image): OSD drawing target for video mode.
            det_boxes (list): OCR quadrilaterals, each containing eight input-space coordinates.
            ocr_texts (list): Recognized strings corresponding to det_boxes.

        Returns:
            None.

        Notes:
            Video mode clears the target before drawing.
        """
        if self.mode=="video":
            osd_img.clear()
        for i in range(len(det_boxes)):
            # 一次绘制四条边，得到文本检测的四边形，坐标需要从原图分辨率转换成显示分辨率
            for j in range(4):
                x1=det_boxes[i][2*j]*self.display_size[0]//self.rgb888p_size[0]
                y1=det_boxes[i][2*j+1]*self.display_size[1]//self.rgb888p_size[1]
                x2=det_boxes[i][(2*j+2)%8]*self.display_size[0]//self.rgb888p_size[0]
                y2=det_boxes[i][(2*j+3)%8]*self.display_size[1]//self.rgb888p_size[1]
                osd_img.draw_line(int(x1),int(y1),int(x2),int(y2),color=(255,255,0,0),thickness=4)
            osd_img.draw_string_advanced(int(x1),int(y1),24,ocr_texts[i],color=(0,0,255))

    def get_cur_result(self):
        """Get the current task result without copying it.

        Returns:
            dict: {'text': recognized string}.

        Notes:
            The returned dict is shared with the application. Copy any data that
            must remain independent of later processing or caller mutation.
        """
        return self.cur_result

    def deinit(self):
        """Release inference resources and reset retained task results.

        Returns:
            None.

        Raises:
            Exception: An error propagated from AIBase.deinit().

        Notes:
            Replaces the current result without clearing a dict held by a caller.
        """
        try:
            AIBase.deinit(self)
        finally:
            # Replace references without mutating results retained by callers.
            self.cur_result = {'text': ''}

class MetricLearningApp(AIBase):
    """Compare query embeddings against in-memory reference images."""
    def __init__(self,mode,kmodel_path,model_input_size=[224,224],confidence_threshold=0.5,rgb888p_size=[224,224],display_size=[1920,1080],debug_mode=0):
        """Initialize the MetricLearningApp model and preprocessing resources.

        Args:
            mode (str): Processing mode, 'image' or 'video'.
            kmodel_path (str): Path to the kmodel file.
            model_input_size (list or None): Model input [width, height], in pixels.
            confidence_threshold (float): Task-specific classification or similarity threshold.
            rgb888p_size (list or None): RGB planar input [width, height], in pixels.
            display_size (list or None): Display [width, height], in pixels.
            debug_mode (int): Enable timing output when greater than zero.

        Raises:
            ValueError: The processing mode is unsupported.

        Notes:
            Call config_preprocess() before inference and deinit() when finished.
            Dimensions use [width, height]; video input widths are aligned to 16.
        """
        try:
            if mode not in ["video","image"]:
                print("Please select the correct inference mode, including 'video', 'image'.")
                raise ValueError("Invalid mode")
            else:
                self.mode=mode
            super().__init__(kmodel_path,model_input_size,rgb888p_size,debug_mode)
            # kmodel路径
            self.kmodel_path=kmodel_path
            # 模型输入分辨率
            self.model_input_size=model_input_size
            self.confidence_threshold=confidence_threshold
            if self.mode=="video":
                # sensor给到AI的图像分辨率,宽16字节对齐
                self.rgb888p_size=[ALIGN_UP(rgb888p_size[0],16),rgb888p_size[1]]
            else:
                self.rgb888p_size=[rgb888p_size[0],rgb888p_size[1]]
            if self.mode=="video":
                # 显示分辨率，宽16字节对齐
                self.display_size=[ALIGN_UP(display_size[0],16),display_size[1]]
            else:
                self.display_size=[display_size[0],display_size[1]]
            self.cur_result={"label":"","score":0.0}
            # debug模式
            self.debug_mode=debug_mode
            # 模型输出列表
            self.results=[]
            # features库
            self.embeddings=[]
            # features对应的标签
            self.embeddings_labels=[]
            # Ai2d实例，用于实现模型预处理
            self.ai2d=Ai2d(debug_mode)
            # 设置Ai2d的输入输出格式和类型
            self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT,nn.ai2d_format.NCHW_FMT,np.uint8, np.uint8)
        except BaseException:
            try:
                self.deinit()
            except Exception as error:
                print("task constructor cleanup failed:", error)
            raise

    # 配置预处理操作，这里使用了resize，Ai2d支持crop/shift/pad/resize/affine，具体代码请打开/sdcard/app/libs/AI2D.py查看
    def config_preprocess(self,input_image_size=None):
        """Build preprocessing for the supplied image dimensions.

        Args:
            input_image_size (list or None): Input [width, height]; None uses rgb888p_size.

        Returns:
            None.

        Notes:
            Resize the input to the model input dimensions.
            None selects the configured rgb888p_size.
        """
        with ScopedTiming("set preprocess config",self.debug_mode > 0):
            # 初始化ai2d预处理配置
            ai2d_input_size=input_image_size if input_image_size else self.rgb888p_size
            # 设置resize预处理
            self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
            # build预处理过程，参数为输入tensor的shape和输出tensor的shape
            self.ai2d.build([1,3,ai2d_input_size[1],ai2d_input_size[0]],[1,3,self.model_input_size[1],self.model_input_size[0]])
            self._preprocess_size = (ai2d_input_size[0], ai2d_input_size[1])

    # 加载图片，将图片特征化后存入特征向量库
    def load_image(self,image_path,label):
        """Extract and store a labeled reference embedding from an image.

        Args:
            image_path (str): Path to the reference image.
            label (str): Label to associate with the reference embedding.

        Returns:
            None.

        Notes:
            Temporarily rebuilds preprocessing for the reference image and
            restores the preceding configuration afterwards. References remain
            in memory until removed by the caller or deinit(); no count limit
            or persistence is imposed.
        """
        previous_size = getattr(self, "_preprocess_size", self.rgb888p_size)
        try:
            img, _ = read_image(image_path)
            self.config_preprocess([img.shape[2], img.shape[1]])
            tensor = self.preprocess(img)
            results = self.inference(tensor)
            self.embeddings.append(results[0][0])
            try:
                self.embeddings_labels.append(label)
            except BaseException:
                self.embeddings.pop()
                raise
        except BaseException:
            try:
                self.config_preprocess(previous_size)
            except Exception as error:
                print("metric preprocessing rollback failed:", error)
            raise
        else:
            self.config_preprocess(previous_size)
        finally:
            gc.collect()

    # 自学习任务推理流程
    def postprocess(self,results):
        """Match the output embedding to stored references.

        Args:
            results (list): Model output ndarrays in output index order.

        Returns:
            dict: {'label': matched label, 'score': cosine similarity};
            unmatched queries produce an empty label and zero score.
        """
        with ScopedTiming("postprocess",self.debug_mode > 0):
            self.cur_result={"label":"","score":0.0}
            if len(self.embeddings)>0:
                # 计算特征向量和向量库中所有向量的最大相似度和相似向量的索引
                idx,score=self.compute_similar(results[0][0])
                gc.collect()
                # 返回分类标签和分数
                if idx >= 0 and len(self.embeddings_labels)>0 and score>self.confidence_threshold:
                    self.cur_result["label"]=self.embeddings_labels[idx]
                    self.cur_result["score"]=score
                return self.cur_result
            else:
                return self.cur_result

    # 绘制分类结果
    def draw_result(self,osd_img,res):
        """Draw the task result on the configured output image.

        Args:
            osd_img (image.Image): OSD drawing target for video mode.
            res (object): Result returned by this task's postprocess() method.

        Returns:
            None.

        Notes:
            Video mode clears the target before drawing.
        """
        with ScopedTiming("draw osd",self.debug_mode > 0):
            if self.mode=="video":
                osd_img.clear()
            if res["label"]!="":
                osd_img.draw_string_advanced(5,5,32,res["label"]+" "+str(round(res["score"],3)),color=(255,0,255,0))

    # 计算参数向量和向量库所有向量的相似度，并返回最大相似索引和对应的相似度分数
    def compute_similar(self,embedding):
        """Find the reference embedding with maximum cosine similarity.

        Args:
            embedding (ulab.numpy.ndarray): Query feature vector with the reference embedding shape.

        Returns:
            tuple: (reference_index, similarity), or (-1, 0.0) when there
            are no references, the query norm is zero, or all references are zero.

        Notes:
            Zero-norm references are excluded. Reference vectors must have the
            same feature length as the query.
        """
        if not self.embeddings:
            return -1, 0.0
        output = np.linalg.norm(embedding)
        if output == 0:
            return -1, 0.0
        # Build once per comparison: callers may modify embeddings in place.
        matrix = np.array(self.embeddings, dtype=np.float)
        embed_lib = np.linalg.norm(matrix, axis=1)
        dot_products = np.dot(matrix, embedding)
        if np.min(embed_lib) > 0:
            similarities = dot_products / (embed_lib * output)
        else:
            similarities = dot_products / ((embed_lib + (embed_lib == 0)) * output)
            valid = False
            for index in range(len(embed_lib)):
                if embed_lib[index] == 0:
                    similarities[index] = -float("inf")
                else:
                    valid = True
            if not valid:
                return -1, 0.0
        most_similar_index = np.argmax(similarities)
        return most_similar_index, similarities[most_similar_index]

    def get_cur_result(self):
        """Get the current task result without copying it.

        Returns:
            dict: {'label': matched label, 'score': cosine similarity};
            unmatched queries produce an empty label and zero score.

        Notes:
            The returned dict is shared with the application. Copy any data that
            must remain independent of later processing or caller mutation.
        """
        return self.cur_result

    def deinit(self):
        """Release inference resources and reset retained task results.

        Returns:
            None.

        Raises:
            Exception: An error propagated from AIBase.deinit().

        Notes:
            Replaces the current result without clearing a dict held by a caller.
            Also drops reference embeddings and their labels.
        """
        try:
            AIBase.deinit(self)
        finally:
            # Replace references without mutating results retained by callers.
            self.cur_result = {'label': '', 'score': 0.0}
            self.embeddings = []
            self.embeddings_labels = []

class MultiLabelClassificationApp(AIBase):
    """Wrap platform classification models with independent label scores."""
    def __init__(self,mode,kmodel_path,labels,model_input_size=[224,224],confidence_threshold=0.5,rgb888p_size=[224,224],display_size=[1920,1080],debug_mode=0):
        """Initialize the MultiLabelClassificationApp model and preprocessing resources.

        Args:
            mode (str): Processing mode, 'image' or 'video'.
            kmodel_path (str): Path to the kmodel file.
            labels (list): Class names in model class-index order.
            model_input_size (list or None): Model input [width, height], in pixels.
            confidence_threshold (float): Task-specific classification or similarity threshold.
            rgb888p_size (list or None): RGB planar input [width, height], in pixels.
            display_size (list or None): Display [width, height], in pixels.
            debug_mode (int): Enable timing output when greater than zero.

        Raises:
            ValueError: The processing mode is unsupported.

        Notes:
            Call config_preprocess() before inference and deinit() when finished.
            Dimensions use [width, height]; video input widths are aligned to 16.
        """
        try:
            if mode not in ["video","image"]:
                print("Please select the correct inference mode, including 'video', 'image'.")
                raise ValueError("Invalid mode")
            else:
                self.mode=mode
            super().__init__(kmodel_path,model_input_size,rgb888p_size,debug_mode)
            self.kmodel_path=kmodel_path
            # 分类标签
            self.labels=labels
            self.num_classes=len(self.labels)
            # 模型输入分辨率
            self.model_input_size=model_input_size
            # 分类阈值
            self.confidence_threshold=confidence_threshold
            if self.mode=="video":
                # sensor给到AI的图像分辨率,宽16字节对齐
                self.rgb888p_size=[ALIGN_UP(rgb888p_size[0],16),rgb888p_size[1]]
            else:
                self.rgb888p_size=[rgb888p_size[0],rgb888p_size[1]]
            if self.mode=="video":
                # 显示分辨率，宽16字节对齐
                self.display_size=[ALIGN_UP(display_size[0],16),display_size[1]]
            else:
                self.display_size=[display_size[0],display_size[1]]
            self.cur_result={"labels":[],"scores":[]}
            self.debug_mode=debug_mode
            # Ai2d实例，用于实现模型预处理
            self.ai2d=Ai2d(debug_mode)
            # 设置Ai2d的输入输出格式和类型
            self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT,nn.ai2d_format.NCHW_FMT,np.uint8, np.uint8)
        except BaseException:
            try:
                self.deinit()
            except Exception as error:
                print("task constructor cleanup failed:", error)
            raise

    # 配置预处理操作，这里使用了resize，Ai2d支持crop/shift/pad/resize/affine，具体代码请打开/sdcard/app/libs/AI2D.py查看
    def config_preprocess(self,input_image_size=None):
        """Build preprocessing for the supplied image dimensions.

        Args:
            input_image_size (list or None): Input [width, height]; None uses rgb888p_size.

        Returns:
            None.

        Notes:
            Resize the input to the model input dimensions.
            None selects the configured rgb888p_size.
        """
        with ScopedTiming("set preprocess config",self.debug_mode > 0):
            # 初始化ai2d预处理配置，默认为sensor给到AI的尺寸，您可以通过设置input_image_size自行修改输入尺寸
            ai2d_input_size=input_image_size if input_image_size else self.rgb888p_size
            # 配置resize预处理
            self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
            # build预处理过程，参数为输入tensor的shape和输出tensor的shape
            self.ai2d.build([1,3,ai2d_input_size[1],ai2d_input_size[0]],[1,3,self.model_input_size[1],self.model_input_size[0]])

    # 自定义当前任务的后处理
    def postprocess(self,results):
        """Select labels whose sigmoid scores exceed the threshold.

        Args:
            results (list): Model output ndarrays in output index order.

        Returns:
            dict: 'labels' and 'scores' contain accepted labels and their scores.
        """
        with ScopedTiming("postprocess",self.debug_mode > 0):
            self.cur_result={"labels":[],"scores":[]}
            # 依次计算所有类别中的所属类别，对每一个类别做二分类
            for i in range(len(self.labels)):
                score=sigmoid(results[0][0][i])
                if score>self.confidence_threshold:
                   self.cur_result["labels"].append(self.labels[i])
                   self.cur_result["scores"].append(score)
            return self.cur_result

    # 将结果绘制到屏幕上
    def draw_result(self,osd_img,res):
        """Draw the task result on the configured output image.

        Args:
            osd_img (image.Image): OSD drawing target for video mode.
            res (object): Result returned by this task's postprocess() method.

        Returns:
            None.

        Notes:
            Video mode clears the target before drawing.
        """
        with ScopedTiming("draw osd",self.debug_mode > 0):
            if self.mode=="video":
                osd_img.clear()
            for i in range(len(res["labels"])):
                osd_img.draw_string_advanced(10,i*30,24,res["labels"][i]+" "+str(round(res["scores"][i],3)),color=(255,0,255,0))

    def get_cur_result(self):
        """Get the current task result without copying it.

        Returns:
            dict: 'labels' and 'scores' contain accepted labels and their scores.

        Notes:
            The returned dict is shared with the application. Copy any data that
            must remain independent of later processing or caller mutation.
        """
        return self.cur_result

    def deinit(self):
        """Release inference resources and reset retained task results.

        Returns:
            None.

        Raises:
            Exception: An error propagated from AIBase.deinit().

        Notes:
            Replaces the current result without clearing a dict held by a caller.
        """
        try:
            AIBase.deinit(self)
        finally:
            # Replace references without mutating results retained by callers.
            self.cur_result = {'labels': [], 'scores': []}
