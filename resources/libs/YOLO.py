from libs.AIBase import AIBase
from libs.AI2D import Ai2d
from libs.Utils import *
import os
import ujson
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
import aidemo

class _YOLOBase(AIBase):
    """Share segmentation image caching and cleanup across YOLO wrappers."""
    def _get_mask_image(self):
        """Get or create the cached video segmentation image.

        Returns:
            image.Image: ARGB8888 image referencing the current masks buffer.

        Notes:
            The image shares mask storage; later postprocessing updates its pixels.
            The cached image is replaced when the mask array changes.
        """
        if (getattr(self, "_mask_image", None) is None or
                getattr(self, "_mask_image_data", None) is not self.masks):
            self._mask_image = image.Image(
                self.display_size[0], self.display_size[1], image.ARGB8888,
                alloc=image.ALLOC_REF, data=self.masks)
            self._mask_image_data = self.masks
        return self._mask_image

    def deinit(self):
        """Release inference resources and cached segmentation image references.

        Returns:
            None.

        Raises:
            Exception: An error propagated from AIBase.deinit().
        """
        try:
            AIBase.deinit(self)
        finally:
            self._mask_image = None
            self._mask_image_data = None


class YOLOv5(_YOLOBase):
    """Run YOLOv5 classification, detection or instance segmentation."""
    def __init__(self,task_type="detect",mode="video",kmodel_path="",labels=[],rgb888p_size=[320,320],model_input_size=[320,320],display_size=[1920,1080],conf_thresh=0.5,nms_thresh=0.45,mask_thresh=0.5,max_boxes_num=50,debug_mode=0):
        """Initialize the YOLOv5 model and task-specific resources.

        Args:
            task_type (str): Task name supported by this YOLO version.
            mode (str): Processing mode, 'image' or 'video'.
            kmodel_path (str): Path to the kmodel file.
            labels (list): Class names in model class-index order.
            rgb888p_size (list or None): RGB planar input [width, height], in pixels.
            model_input_size (list or None): Model input [width, height], in pixels.
            display_size (list or None): Display [width, height], in pixels.
            conf_thresh (float): Confidence threshold for accepting predictions.
            nms_thresh (float): Intersection-over-union threshold for non-maximum suppression.
            mask_thresh (float): Threshold for segmentation masks.
            max_boxes_num (int): Maximum detections for postprocessors that accept a box limit.
            debug_mode (int): Enable timing output when greater than zero.

        Raises:
            ValueError: The mode is unsupported.
            Exception: The task_type is unsupported.

        Notes:
            Call config_preprocess() before run(), then deinit() when finished.
            Model output layout must match the selected task and YOLO version.
        """
        try:
            if mode not in ("video", "image"):
                raise ValueError("Invalid mode")
            if task_type not in ["classify","detect","segment"]:
                raise Exception("Please select the correct task_type parameter, including 'classify', 'detect', 'segment'.")
            super().__init__(kmodel_path,model_input_size,rgb888p_size,debug_mode)
            self.task_type=task_type
            self.mode=mode
            self.kmodel_path=kmodel_path
            self.labels=labels
            self.class_num=len(labels)
            if mode=="video":
                self.rgb888p_size=[ALIGN_UP(rgb888p_size[0],16),rgb888p_size[1]]
            else:
                self.rgb888p_size=[rgb888p_size[0],rgb888p_size[1]]
            self.model_input_size=model_input_size
            self.display_size=[ALIGN_UP(display_size[0],16),display_size[1]]

            self.conf_thresh=conf_thresh
            self.nms_thresh=nms_thresh
            self.mask_thresh=mask_thresh
            self.max_boxes_num=max_boxes_num
            self.debug_mode=debug_mode

            self.scale=1.0
            self.colors=get_colors(len(self.labels))
            self.masks=None
            if self.task_type=="segment":
                if self.mode=="image":
                    self.masks=np.zeros((1,self.rgb888p_size[1],self.rgb888p_size[0],4),dtype=np.uint8)
                elif self.mode=="video":
                    self.masks=np.zeros((1,self.display_size[1],self.display_size[0],4),dtype=np.uint8)
            # Ai2d实例，用于实现模型预处理
            self.ai2d=Ai2d(self.debug_mode)
            # 设置Ai2d的输入输出格式和类型
            self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT,nn.ai2d_format.NCHW_FMT,np.uint8, np.uint8)
            self._active_input_size = list(self.rgb888p_size)
        except BaseException:
            try:
                self.deinit()
            except Exception as error:
                print("YOLO constructor cleanup failed:", error)
            raise

    # 配置预处理操作，这里使用了resize，Ai2d支持crop/shift/pad/resize/affine，具体代码请打开/sdcard/app/libs/AI2D.py查看
    def config_preprocess(self,input_image_size=None):
        """Build preprocessing for the selected task and input dimensions.

        Args:
            input_image_size (list or None): Input [width, height]; None uses rgb888p_size.

        Returns:
            None.

        Notes:
            Classification uses a centered square crop. Other tasks use
            aspect-preserving padding. Successful builds update the active input
            size used by postprocessing; image segmentation also resizes masks.
        """
        with ScopedTiming("set preprocess config",self.debug_mode > 0):
            # 初始化ai2d预处理配置，默认为sensor给到AI的尺寸，您可以通过设置input_image_size自行修改输入尺寸
            ai2d_input_size=input_image_size if input_image_size else self.rgb888p_size
            new_input_size = [ai2d_input_size[0], ai2d_input_size[1]]
            new_masks = self.masks
            if (self.task_type == "segment" and self.mode == "image" and
                    new_input_size != self._active_input_size):
                new_masks = np.zeros((1, ai2d_input_size[1], ai2d_input_size[0], 4), dtype=np.uint8)
            if self.task_type=="classify":
                top,left,m=center_crop_param(ai2d_input_size)
                self.ai2d.crop(left,top,m,m)
            elif self.task_type=="detect":
                # 计算padding参数
                top,bottom,left,right,self.scale=letterbox_pad_param(ai2d_input_size,self.model_input_size)
                # 配置padding预处理
                self.ai2d.pad([0,0,0,0,top,bottom,left,right], 0, [128,128,128])
            elif self.task_type=="segment":
                top,bottom,left,right,scale=letterbox_pad_param(ai2d_input_size,self.model_input_size)
                self.ai2d.pad([0,0,0,0,top,bottom,left,right], 0, [128,128,128])
            self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
            # build参数包含输入shape和输出shape
            self.ai2d.build([1,3,ai2d_input_size[1],ai2d_input_size[0]],[1,3,self.model_input_size[1],self.model_input_size[0]])
            self._active_input_size = new_input_size
            self.masks = new_masks

    def postprocess(self,results):
        """Decode model outputs for the configured YOLO task.

        Args:
            results (list): Model output ndarrays in output index order.

        Returns:
            tuple or list: Classification returns (class_index, score), with
            (-1, 0.0) below threshold. Other tasks return the matching aidemo
            postprocessor result, consumed directly by draw_result().

        Notes:
            Detection/segmentation results contain boxes, class IDs and scores.
            Coordinates target the display in video mode and active input size
            in image mode. Segmentation also overwrites the reusable masks array.
        """
        with ScopedTiming("postprocess",self.debug_mode > 0):
            if self.task_type=="classify":
                softmax_res=softmax(results[0][0])
                res_idx=np.argmax(softmax_res)
                cls_res=(-1,0.0)
                # 如果类别分数大于阈值，返回当前类别和分数
                if softmax_res[res_idx]>self.conf_thresh:
                    cls_res=(res_idx,softmax_res[res_idx])
                return cls_res
            elif self.task_type=="detect":
                if self.mode=="image":
                    det_res = aidemo.yolov5_det_postprocess(results[0][0],[self._active_input_size[1],self._active_input_size[0]],[self.model_input_size[1],self.model_input_size[0]],[self._active_input_size[1],self._active_input_size[0]],len(self.labels),self.conf_thresh,self.nms_thresh,self.max_boxes_num)
                elif self.mode=="video":
                    det_res = aidemo.yolov5_det_postprocess(results[0][0],[self._active_input_size[1],self._active_input_size[0]],[self.model_input_size[1],self.model_input_size[0]],[self.display_size[1],self.display_size[0]],len(self.labels),self.conf_thresh,self.nms_thresh,self.max_boxes_num)
                return det_res
            elif self.task_type=="segment":
                if self.mode=="image":
                    seg_res = aidemo.yolov5_seg_postprocess(results[0][0],results[1][0],[self._active_input_size[1],self._active_input_size[0]],[self.model_input_size[1],self.model_input_size[0]],[self._active_input_size[1],self._active_input_size[0]],len(self.labels),self.conf_thresh,self.nms_thresh,self.mask_thresh,self.masks)
                elif self.mode=="video":
                    seg_res = aidemo.yolov5_seg_postprocess(results[0][0],results[1][0],[self._active_input_size[1],self._active_input_size[0]],[self.model_input_size[1],self.model_input_size[0]],[self.display_size[1],self.display_size[0]],len(self.labels),self.conf_thresh,self.nms_thresh,self.mask_thresh,self.masks)
                return seg_res

    def draw_result(self,res,img):
        """Render task results for video display or IDE image output.

        Args:
            res (object): Result returned by this task's postprocess() method.
            img (image.Image): Drawing target; use the mode-appropriate pixel format.

        Returns:
            None.

        Notes:
            Video mode clears and updates the supplied OSD image. Image mode
            compresses the rendered image for the IDE; segmentation renders a
            separate image from the mask buffer.
        """
        with ScopedTiming("draw result",self.debug_mode > 0):
            if self.mode=="video":
                if self.task_type=="classify":
                    ids,score=res[0],res[1]
                    if ids!=-1:
                        img.clear()
                        mes=self.labels[ids]+" {0:.3f}".format(score)
                        img.draw_string_advanced(5,5,32,mes,color=(0,255,0))
                    else:
                        img.clear()
                elif self.task_type=="detect":
                    if res:
                        img.clear()
                        for i in range(len(res[0])):
                            x, y, w, h = map(lambda x: int(round(x, 0)), res[0][i])
                            img.draw_rectangle(x,y, w, h, color=self.colors[res[1][i]],thickness=4)
                            img.draw_string_advanced( x , y-50,32," " + self.labels[res[1][i]] + " {0:.3f}".format(res[2][i]), color=self.colors[res[1][i]])
                    else:
                        img.clear()
                elif self.task_type=="segment":
                    if res[0]:
                        img.clear()
                        mask_img=self._get_mask_image()
                        img.copy_from(mask_img)
                        dets,ids,scores = res[0],res[1],res[2]
                        for i, det in enumerate(dets):
                            x1, y1, w, h = map(lambda x: int(round(x, 0)), det)
                            img.draw_string_advanced(x1,y1-50,32, " " + self.labels[int(ids[i])] + " {0:.3f}".format(scores[i]) , color=self.colors[int(ids[i])])
                    else:
                        img.clear()
                else:
                    pass
            elif self.mode=="image":
                if self.task_type=="classify":
                    ids,score=res[0],res[1]
                    if ids!=-1:
                        mes=self.labels[ids]+" {0:.3f}".format(score)
                        img.draw_string_advanced(5,5,32,mes,color=(0,255,0))
                    img.compress_for_ide()
                elif self.task_type=="detect":
                    if res:
                        for i in range(len(res[0])):
                            x, y, w, h = map(lambda x: int(round(x, 0)), res[0][i])
                            img.draw_rectangle(x,y, w, h, color=self.colors[res[1][i]],thickness=4)
                            img.draw_string_advanced( x , y-50,32," " + self.labels[res[1][i]] + " {0:.3f}".format(res[2][i]) , color=self.colors[res[1][i]])
                    img.compress_for_ide()
                elif self.task_type=="segment":
                    if res[0]:
                        mask_rgb=self.masks[0,:,:,1:4]
                        mask_img=image.Image(self._active_input_size[0], self._active_input_size[1], image.RGB888,alloc=image.ALLOC_REF,data=mask_rgb.copy())
                        dets,ids,scores = res[0],res[1],res[2]
                        for i, det in enumerate(dets):
                            x, y, w, h = map(lambda x: int(round(x, 0)), det)
                            mask_img.draw_string_advanced(x,y-50,32, " " + self.labels[int(ids[i])] + " {0:.3f}".format(scores[i]) , color=self.colors[int(ids[i])])
                        mask_img.compress_for_ide()
                else:
                    pass


class YOLOv8(_YOLOBase):
    """Run YOLOv8 classification, detection, segmentation, pose or OBB tasks."""
    def __init__(self,task_type="detect",mode="video",kmodel_path="",labels=[],rgb888p_size=[320,320],model_input_size=[320,320],display_size=[1920,1080],conf_thresh=0.5,nms_thresh=0.45,mask_thresh=0.5,kp_num=17,kp_dim=3,max_boxes_num=50,debug_mode=0):
        """Initialize the YOLOv8 model and task-specific resources.

        Args:
            task_type (str): Task name supported by this YOLO version.
            mode (str): Processing mode, 'image' or 'video'.
            kmodel_path (str): Path to the kmodel file.
            labels (list): Class names in model class-index order.
            rgb888p_size (list or None): RGB planar input [width, height], in pixels.
            model_input_size (list or None): Model input [width, height], in pixels.
            display_size (list or None): Display [width, height], in pixels.
            conf_thresh (float): Confidence threshold for accepting predictions.
            nms_thresh (float): Intersection-over-union threshold for non-maximum suppression.
            mask_thresh (float): Threshold for segmentation masks.
            kp_num (int): Number of keypoints per detected instance.
            kp_dim (int): Number of values per keypoint in the model output.
            max_boxes_num (int): Maximum detections for postprocessors that accept a box limit.
            debug_mode (int): Enable timing output when greater than zero.

        Raises:
            ValueError: The mode is unsupported.
            Exception: The task_type is unsupported.

        Notes:
            Call config_preprocess() before run(), then deinit() when finished.
            Model output layout must match the selected task and YOLO version.
        """
        try:
            if mode not in ("video", "image"):
                raise ValueError("Invalid mode")
            if task_type not in ["classify","detect","segment","obb","pose"]:
                raise Exception("Please select the correct task_type parameter, including 'classify', 'detect', 'segment','obb','pose'.")
            super().__init__(kmodel_path,model_input_size,rgb888p_size,debug_mode)
            self.task_type=task_type
            self.mode=mode
            self.kmodel_path=kmodel_path
            self.labels=labels
            self.class_num=len(labels)
            if mode=="video":
                self.rgb888p_size=[ALIGN_UP(rgb888p_size[0],16),rgb888p_size[1]]
            else:
                self.rgb888p_size=[rgb888p_size[0],rgb888p_size[1]]
            self.model_input_size=model_input_size
            self.display_size=[ALIGN_UP(display_size[0],16),display_size[1]]

            self.conf_thresh=conf_thresh
            self.nms_thresh=nms_thresh
            self.mask_thresh=mask_thresh
            self.kp_num=kp_num
            self.kp_dim=kp_dim
            self.max_boxes_num=max_boxes_num
            self.debug_mode=debug_mode

            self.scale=1.0
            self.colors=get_colors(len(self.labels))
            self.kp_colors=get_colors(self.kp_num)
            self.masks=None
            if self.task_type=="segment":
                if self.mode=="image":
                    self.masks=np.zeros((1,self.rgb888p_size[1],self.rgb888p_size[0],4),dtype=np.uint8)
                elif self.mode=="video":
                    self.masks=np.zeros((1,self.display_size[1],self.display_size[0],4),dtype=np.uint8)
            # Ai2d实例，用于实现模型预处理
            self.ai2d=Ai2d(self.debug_mode)
            # 设置Ai2d的输入输出格式和类型
            self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT,nn.ai2d_format.NCHW_FMT,np.uint8, np.uint8)
            self._active_input_size = list(self.rgb888p_size)
        except BaseException:
            try:
                self.deinit()
            except Exception as error:
                print("YOLO constructor cleanup failed:", error)
            raise

    # 配置预处理操作，这里使用了resize，Ai2d支持crop/shift/pad/resize/affine，具体代码请打开/sdcard/app/libs/AI2D.py查看
    def config_preprocess(self,input_image_size=None):
        """Build preprocessing for the selected task and input dimensions.

        Args:
            input_image_size (list or None): Input [width, height]; None uses rgb888p_size.

        Returns:
            None.

        Notes:
            Classification uses a centered square crop. Other tasks use
            aspect-preserving padding. Successful builds update the active input
            size used by postprocessing; image segmentation also resizes masks.
        """
        with ScopedTiming("set preprocess config",self.debug_mode > 0):
            # 初始化ai2d预处理配置，默认为sensor给到AI的尺寸，您可以通过设置input_image_size自行修改输入尺寸
            ai2d_input_size=input_image_size if input_image_size else self.rgb888p_size
            new_input_size = [ai2d_input_size[0], ai2d_input_size[1]]
            new_masks = self.masks
            if (self.task_type == "segment" and self.mode == "image" and
                    new_input_size != self._active_input_size):
                new_masks = np.zeros((1, ai2d_input_size[1], ai2d_input_size[0], 4), dtype=np.uint8)
            if self.task_type=="classify":
                top,left,m=center_crop_param(ai2d_input_size)
                self.ai2d.crop(left,top,m,m)
            elif self.task_type=="detect":
                # 计算padding参数
                top,bottom,left,right,self.scale=letterbox_pad_param(ai2d_input_size,self.model_input_size)
                # 配置padding预处理
                self.ai2d.pad([0,0,0,0,top,bottom,left,right], 0, [128,128,128])
            elif self.task_type=="segment":
                top,bottom,left,right,scale=letterbox_pad_param(ai2d_input_size,self.model_input_size)
                self.ai2d.pad([0,0,0,0,top,bottom,left,right], 0, [128,128,128])
            elif self.task_type=="obb":
                # 计算padding参数
                top,bottom,left,right,self.scale=letterbox_pad_param(ai2d_input_size,self.model_input_size)
                # 配置padding预处理
                self.ai2d.pad([0,0,0,0,top,bottom,left,right], 0, [128,128,128])
            elif self.task_type=="pose":
                top,bottom,left,right,self.scale=letterbox_pad_param(ai2d_input_size,self.model_input_size)
                self.ai2d.pad([0,0,0,0,top,bottom,left,right], 0, [128,128,128])
            self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
            # build参数包含输入shape和输出shape
            self.ai2d.build([1,3,ai2d_input_size[1],ai2d_input_size[0]],[1,3,self.model_input_size[1],self.model_input_size[0]])
            self._active_input_size = new_input_size
            self.masks = new_masks

    def postprocess(self,results):
        """Decode model outputs for the configured YOLO task.

        Args:
            results (list): Model output ndarrays in output index order.

        Returns:
            tuple or list: Classification returns (class_index, score), with
            (-1, 0.0) below threshold. Other tasks return the matching aidemo
            postprocessor result, consumed directly by draw_result().

        Notes:
            Detection/segmentation results contain boxes, class IDs and scores.
            Coordinates target the display in video mode and active input size
            in image mode. Segmentation also overwrites the reusable masks array.
        """
        with ScopedTiming("postprocess",self.debug_mode > 0):
            if self.task_type=="classify":
                scores=results[0][0]
                max_score=np.max(scores)
                res_idx=np.argmax(scores)
                cls_res=(-1,0.0)
                # 如果类别分数大于阈值，返回当前类别和分数
                if max_score>self.conf_thresh:
                    cls_res=(res_idx,max_score)
                return cls_res
            elif self.task_type=="detect":
                new_result=results[0][0].transpose()
                if self.mode=="image":
                    det_res = aidemo.yolov8_det_postprocess(new_result.copy(),[self._active_input_size[1],self._active_input_size[0]],[self.model_input_size[1],self.model_input_size[0]],[self._active_input_size[1],self._active_input_size[0]],len(self.labels),self.conf_thresh,self.nms_thresh,self.max_boxes_num)
                elif self.mode=="video":
                    det_res = aidemo.yolov8_det_postprocess(new_result.copy(),[self._active_input_size[1],self._active_input_size[0]],[self.model_input_size[1],self.model_input_size[0]],[self.display_size[1],self.display_size[0]],len(self.labels),self.conf_thresh,self.nms_thresh,self.max_boxes_num)
                return det_res
            elif self.task_type=="segment":
                new_result=results[0][0].transpose()
                if self.mode=="image":
                    seg_res = aidemo.yolov8_seg_postprocess(new_result.copy(),results[1][0],[self._active_input_size[1],self._active_input_size[0]],[self.model_input_size[1],self.model_input_size[0]],[self._active_input_size[1],self._active_input_size[0]],len(self.labels),self.conf_thresh,self.nms_thresh,self.mask_thresh,self.masks)
                elif self.mode=="video":
                    seg_res = aidemo.yolov8_seg_postprocess(new_result.copy(),results[1][0],[self._active_input_size[1],self._active_input_size[0]],[self.model_input_size[1],self.model_input_size[0]],[self.display_size[1],self.display_size[0]],len(self.labels),self.conf_thresh,self.nms_thresh,self.mask_thresh,self.masks)
                return seg_res
            elif self.task_type=="obb":
                new_result=results[0][0].transpose()
                if self.mode=="image":
                    obb_res = aidemo.yolo_obb_postprocess(new_result.copy(),[self._active_input_size[1],self._active_input_size[0]],[self.model_input_size[1],self.model_input_size[0]],[self._active_input_size[1],self._active_input_size[0]],len(self.labels),self.conf_thresh,self.nms_thresh,self.max_boxes_num)
                elif self.mode=="video":
                    obb_res = aidemo.yolo_obb_postprocess(new_result.copy(),[self._active_input_size[1],self._active_input_size[0]],[self.model_input_size[1],self.model_input_size[0]],[self.display_size[1],self.display_size[0]],len(self.labels),self.conf_thresh,self.nms_thresh,self.max_boxes_num)
                return obb_res
            elif self.task_type=="pose":
                new_result=results[0][0].transpose()
                if self.mode=="image":
                    pose_res = aidemo.yolov8_pose_postprocess(new_result.copy(),[self._active_input_size[1],self._active_input_size[0]],[self.model_input_size[1],self.model_input_size[0]],[self._active_input_size[1],self._active_input_size[0]],len(self.labels),self.kp_num,self.kp_dim,self.conf_thresh,self.nms_thresh,self.max_boxes_num)
                elif self.mode=="video":
                    pose_res = aidemo.yolov8_pose_postprocess(new_result.copy(),[self._active_input_size[1],self._active_input_size[0]],[self.model_input_size[1],self.model_input_size[0]],[self.display_size[1],self.display_size[0]],len(self.labels),self.kp_num,self.kp_dim,self.conf_thresh,self.nms_thresh,self.max_boxes_num)
                return pose_res

    def draw_result(self,res,img):
        """Render task results for video display or IDE image output.

        Args:
            res (object): Result returned by this task's postprocess() method.
            img (image.Image): Drawing target; use the mode-appropriate pixel format.

        Returns:
            None.

        Notes:
            Video mode clears and updates the supplied OSD image. Image mode
            compresses the rendered image for the IDE; segmentation renders a
            separate image from the mask buffer.
        """
        with ScopedTiming("draw result",self.debug_mode > 0):
            if self.mode=="video":
                if self.task_type=="classify":
                    ids,score=res[0],res[1]
                    if ids!=-1:
                        img.clear()
                        mes=self.labels[ids]+" {0:.3f}".format(score)
                        img.draw_string_advanced(5,5,32,mes,color=(0,255,0))
                    else:
                        img.clear()
                elif self.task_type=="detect":
                    if res:
                        img.clear()
                        for i in range(len(res[0])):
                            x, y, w, h = map(lambda x: int(round(x, 0)), res[0][i])
                            img.draw_rectangle(x,y, w, h, color=self.colors[res[1][i]],thickness=4)
                            img.draw_string_advanced( x , y-50,32," " + self.labels[res[1][i]] + " {0:.3f}".format(res[2][i]) , color=self.colors[res[1][i]])
                    else:
                        img.clear()
                elif self.task_type=="segment":
                    if res[0]:
                        img.clear()
                        mask_img=self._get_mask_image()
                        img.copy_from(mask_img)
                        dets,ids,scores = res[0],res[1],res[2]
                        for i, det in enumerate(dets):
                            x1, y1, w, h = map(lambda x: int(round(x, 0)), det)
                            img.draw_string_advanced(x1,y1-50,32, " " + self.labels[int(ids[i])] + " {0:.3f}".format(scores[i]) , color=self.colors[int(ids[i])])
                    else:
                        img.clear()
                elif self.task_type=="obb":
                    if res:
                        img.clear()
                        for i in range(len(res[0])):
                            x1, y1, x2,y2,x3,y3,x4,y4 = map(lambda x: int(round(x, 0)), res[0][i])
                            img.draw_line(int(x1),int(y1),int(x2),int(y2),color=self.colors[res[1][i]],thickness=4)
                            img.draw_line(int(x2),int(y2),int(x3),int(y3),color=self.colors[res[1][i]],thickness=4)
                            img.draw_line(int(x3),int(y3),int(x4),int(y4),color=self.colors[res[1][i]],thickness=4)
                            img.draw_line(int(x4),int(y4),int(x1),int(y1),color=self.colors[res[1][i]],thickness=4)
                            img.draw_string_advanced(x1, y1,24,str(res[1][i]) , color=self.colors[res[1][i]])
                    else:
                        img.clear()
                elif self.task_type=="pose":
                    if res:
                        img.clear()
                        for i in range(len(res[0])):
                            for k in range(self.kp_num):
                                x=res[3][i][k*self.kp_dim+0]
                                y=res[3][i][k*self.kp_dim+1]
                                img.draw_circle(int(x),int(y),5,self.kp_colors[k],fill=True)
                                x_, y_, w_, h_ = map(lambda x: int(round(x, 0)), res[0][i])
                                img.draw_rectangle(x_,y_, w_, h_, color=self.colors[res[1][i]],thickness=4)
                                img.draw_string_advanced( x_ , y_-50,32," " + self.labels[res[1][i]] + " {0:.3f}".format(res[2][i]) , color=self.colors[res[1][i]])
                    else:
                        img.clear()
                else:
                    pass
            elif self.mode=="image":
                if self.task_type=="classify":
                    ids,score=res[0],res[1]
                    if ids!=-1:
                        mes=self.labels[ids]+" {0:.3f}".format(score)
                        img.draw_string_advanced(5,5,32,mes,color=(0,255,0))
                    img.compress_for_ide()
                elif self.task_type=="detect":
                    if res:
                        for i in range(len(res[0])):
                            x, y, w, h = map(lambda x: int(round(x, 0)), res[0][i])
                            img.draw_rectangle(x,y, w, h, color=self.colors[res[1][i]],thickness=4)
                            img.draw_string_advanced( x , y-50,32," " + self.labels[res[1][i]] + " {0:.3f}".format(res[2][i]) , color=self.colors[res[1][i]])
                    img.compress_for_ide()
                elif self.task_type=="segment":
                    if res[0]:
                        mask_rgb=self.masks[0,:,:,1:4]
                        mask_img=image.Image(self._active_input_size[0], self._active_input_size[1], image.RGB888,alloc=image.ALLOC_REF,data=mask_rgb.copy())
                        dets,ids,scores = res[0],res[1],res[2]
                        for i, det in enumerate(dets):
                            x, y, w, h = map(lambda x: int(round(x, 0)), det)
                            mask_img.draw_string_advanced(x,y-50,32, " " + self.labels[int(ids[i])] + " {0:.3f}".format(scores[i]) , color=self.colors[int(ids[i])])
                        mask_img.compress_for_ide()
                elif self.task_type=="obb":
                    if res:
                        for i in range(len(res[0])):
                            x1, y1, x2,y2,x3,y3,x4,y4 = map(lambda x: int(round(x, 0)), res[0][i])
                            img.draw_line(int(x1),int(y1),int(x2),int(y2),color=self.colors[res[1][i]],thickness=4)
                            img.draw_line(int(x2),int(y2),int(x3),int(y3),color=self.colors[res[1][i]],thickness=4)
                            img.draw_line(int(x3),int(y3),int(x4),int(y4),color=self.colors[res[1][i]],thickness=4)
                            img.draw_line(int(x4),int(y4),int(x1),int(y1),color=self.colors[res[1][i]],thickness=4)
                            img.draw_string_advanced(x1, y1,24,str(res[1][i]) , color=self.colors[res[1][i]])
                    img.compress_for_ide()
                elif self.task_type=="pose":
                    if res:
                        for i in range(len(res[0])):
                            for k in range(self.kp_num):
                                x=res[3][i][k*self.kp_dim+0]
                                y=res[3][i][k*self.kp_dim+1]
                                img.draw_circle(int(x),int(y),5,self.kp_colors[k],fill=True)
                                x_, y_, w_, h_ = map(lambda x: int(round(x, 0)), res[0][i])
                                img.draw_rectangle(x_,y_, w_, h_, color=self.colors[res[1][i]],thickness=4)
                                img.draw_string_advanced( x_ , y_-50,32," " + self.labels[res[1][i]] + " {0:.3f}".format(res[2][i]) , color=self.colors[res[1][i]])
                    img.compress_for_ide()
                else:
                    pass


class YOLO11(_YOLOBase):
    """Run YOLO11 classification, detection, segmentation, pose or OBB tasks."""
    def __init__(self,task_type="detect",mode="video",kmodel_path="",labels=[],rgb888p_size=[320,320],model_input_size=[320,320],display_size=[1920,1080],conf_thresh=0.5,nms_thresh=0.45,mask_thresh=0.5,kp_num=17,kp_dim=3,max_boxes_num=50,debug_mode=0):
        """Initialize the YOLO11 model and task-specific resources.

        Args:
            task_type (str): Task name supported by this YOLO version.
            mode (str): Processing mode, 'image' or 'video'.
            kmodel_path (str): Path to the kmodel file.
            labels (list): Class names in model class-index order.
            rgb888p_size (list or None): RGB planar input [width, height], in pixels.
            model_input_size (list or None): Model input [width, height], in pixels.
            display_size (list or None): Display [width, height], in pixels.
            conf_thresh (float): Confidence threshold for accepting predictions.
            nms_thresh (float): Intersection-over-union threshold for non-maximum suppression.
            mask_thresh (float): Threshold for segmentation masks.
            kp_num (int): Number of keypoints per detected instance.
            kp_dim (int): Number of values per keypoint in the model output.
            max_boxes_num (int): Maximum detections for postprocessors that accept a box limit.
            debug_mode (int): Enable timing output when greater than zero.

        Raises:
            ValueError: The mode is unsupported.
            Exception: The task_type is unsupported.

        Notes:
            Call config_preprocess() before run(), then deinit() when finished.
            Model output layout must match the selected task and YOLO version.
        """
        try:
            if mode not in ("video", "image"):
                raise ValueError("Invalid mode")
            if task_type not in ["classify","detect","segment","obb","pose"]:
                raise Exception("Please select the correct task_type parameter, including 'classify', 'detect', 'segment','obb','pose'.")
            super().__init__(kmodel_path,model_input_size,rgb888p_size,debug_mode)
            self.task_type=task_type
            self.mode=mode
            self.kmodel_path=kmodel_path
            self.labels=labels
            self.class_num=len(labels)
            if mode=="video":
                self.rgb888p_size=[ALIGN_UP(rgb888p_size[0],16),rgb888p_size[1]]
            else:
                self.rgb888p_size=[rgb888p_size[0],rgb888p_size[1]]
            self.model_input_size=model_input_size
            self.display_size=[ALIGN_UP(display_size[0],16),display_size[1]]

            self.conf_thresh=conf_thresh
            self.nms_thresh=nms_thresh
            self.mask_thresh=mask_thresh
            self.kp_num=kp_num
            self.kp_dim=kp_dim
            self.max_boxes_num=max_boxes_num
            self.debug_mode=debug_mode

            self.scale=1.0
            self.colors=get_colors(len(self.labels))
            self.kp_colors=get_colors(self.kp_num)
            self.masks=None
            if self.task_type=="segment":
                if self.mode=="image":
                    self.masks=np.zeros((1,self.rgb888p_size[1],self.rgb888p_size[0],4),dtype=np.uint8)
                elif self.mode=="video":
                    self.masks=np.zeros((1,self.display_size[1],self.display_size[0],4),dtype=np.uint8)
            # Ai2d实例，用于实现模型预处理
            self.ai2d=Ai2d(self.debug_mode)
            # 设置Ai2d的输入输出格式和类型
            self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT,nn.ai2d_format.NCHW_FMT,np.uint8, np.uint8)
            self._active_input_size = list(self.rgb888p_size)
        except BaseException:
            try:
                self.deinit()
            except Exception as error:
                print("YOLO constructor cleanup failed:", error)
            raise

    # 配置预处理操作，这里使用了resize，Ai2d支持crop/shift/pad/resize/affine，具体代码请打开/sdcard/app/libs/AI2D.py查看
    def config_preprocess(self,input_image_size=None):
        """Build preprocessing for the selected task and input dimensions.

        Args:
            input_image_size (list or None): Input [width, height]; None uses rgb888p_size.

        Returns:
            None.

        Notes:
            Classification uses a centered square crop. Other tasks use
            aspect-preserving padding. Successful builds update the active input
            size used by postprocessing; image segmentation also resizes masks.
        """
        with ScopedTiming("set preprocess config",self.debug_mode > 0):
            # 初始化ai2d预处理配置，默认为sensor给到AI的尺寸，您可以通过设置input_image_size自行修改输入尺寸
            ai2d_input_size=input_image_size if input_image_size else self.rgb888p_size
            new_input_size = [ai2d_input_size[0], ai2d_input_size[1]]
            new_masks = self.masks
            if (self.task_type == "segment" and self.mode == "image" and
                    new_input_size != self._active_input_size):
                new_masks = np.zeros((1, ai2d_input_size[1], ai2d_input_size[0], 4), dtype=np.uint8)
            if self.task_type=="classify":
                top,left,m=center_crop_param(ai2d_input_size)
                self.ai2d.crop(left,top,m,m)
            elif self.task_type=="detect":
                # 计算padding参数
                top,bottom,left,right,self.scale=letterbox_pad_param(ai2d_input_size,self.model_input_size)
                # 配置padding预处理
                self.ai2d.pad([0,0,0,0,top,bottom,left,right], 0, [128,128,128])
            elif self.task_type=="segment":
                top,bottom,left,right,scale=letterbox_pad_param(ai2d_input_size,self.model_input_size)
                self.ai2d.pad([0,0,0,0,top,bottom,left,right], 0, [128,128,128])
            elif self.task_type=="obb":
                # 计算padding参数
                top,bottom,left,right,self.scale=letterbox_pad_param(ai2d_input_size,self.model_input_size)
                # 配置padding预处理
                self.ai2d.pad([0,0,0,0,top,bottom,left,right], 0, [128,128,128])
            elif self.task_type=="pose":
                top,bottom,left,right,self.scale=letterbox_pad_param(ai2d_input_size,self.model_input_size)
                self.ai2d.pad([0,0,0,0,top,bottom,left,right], 0, [128,128,128])
            self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
            # build参数包含输入shape和输出shape
            self.ai2d.build([1,3,ai2d_input_size[1],ai2d_input_size[0]],[1,3,self.model_input_size[1],self.model_input_size[0]])
            self._active_input_size = new_input_size
            self.masks = new_masks

    def postprocess(self,results):
        """Decode model outputs for the configured YOLO task.

        Args:
            results (list): Model output ndarrays in output index order.

        Returns:
            tuple or list: Classification returns (class_index, score), with
            (-1, 0.0) below threshold. Other tasks return the matching aidemo
            postprocessor result, consumed directly by draw_result().

        Notes:
            Detection/segmentation results contain boxes, class IDs and scores.
            Coordinates target the display in video mode and active input size
            in image mode. Segmentation also overwrites the reusable masks array.
        """
        with ScopedTiming("postprocess",self.debug_mode > 0):
            if self.task_type=="classify":
                scores=results[0][0]
                max_score=np.max(scores)
                res_idx=np.argmax(scores)
                cls_res=(-1,0.0)
                # 如果类别分数大于阈值，返回当前类别和分数
                if max_score>self.conf_thresh:
                    cls_res=(res_idx,max_score)
                return cls_res
            elif self.task_type=="detect":
                new_result=results[0][0].transpose()
                if self.mode=="image":
                    det_res = aidemo.yolov8_det_postprocess(new_result.copy(),[self._active_input_size[1],self._active_input_size[0]],[self.model_input_size[1],self.model_input_size[0]],[self._active_input_size[1],self._active_input_size[0]],len(self.labels),self.conf_thresh,self.nms_thresh,self.max_boxes_num)
                elif self.mode=="video":
                    det_res = aidemo.yolov8_det_postprocess(new_result.copy(),[self._active_input_size[1],self._active_input_size[0]],[self.model_input_size[1],self.model_input_size[0]],[self.display_size[1],self.display_size[0]],len(self.labels),self.conf_thresh,self.nms_thresh,self.max_boxes_num)
                return det_res
            elif self.task_type=="segment":
                new_result=results[0][0].transpose()
                if self.mode=="image":
                    seg_res = aidemo.yolov8_seg_postprocess(new_result.copy(),results[1][0],[self._active_input_size[1],self._active_input_size[0]],[self.model_input_size[1],self.model_input_size[0]],[self._active_input_size[1],self._active_input_size[0]],len(self.labels),self.conf_thresh,self.nms_thresh,self.mask_thresh,self.masks)
                elif self.mode=="video":
                    seg_res = aidemo.yolov8_seg_postprocess(new_result.copy(),results[1][0],[self._active_input_size[1],self._active_input_size[0]],[self.model_input_size[1],self.model_input_size[0]],[self.display_size[1],self.display_size[0]],len(self.labels),self.conf_thresh,self.nms_thresh,self.mask_thresh,self.masks)
                return seg_res
            elif self.task_type=="obb":
                new_result=results[0][0].transpose()
                if self.mode=="image":
                    obb_res = aidemo.yolo_obb_postprocess(new_result.copy(),[self._active_input_size[1],self._active_input_size[0]],[self.model_input_size[1],self.model_input_size[0]],[self._active_input_size[1],self._active_input_size[0]],len(self.labels),self.conf_thresh,self.nms_thresh,self.max_boxes_num)
                elif self.mode=="video":
                    obb_res = aidemo.yolo_obb_postprocess(new_result.copy(),[self._active_input_size[1],self._active_input_size[0]],[self.model_input_size[1],self.model_input_size[0]],[self.display_size[1],self.display_size[0]],len(self.labels),self.conf_thresh,self.nms_thresh,self.max_boxes_num)
                return obb_res
            elif self.task_type=="pose":
                new_result=results[0][0].transpose()
                if self.mode=="image":
                    pose_res = aidemo.yolov8_pose_postprocess(new_result.copy(),[self._active_input_size[1],self._active_input_size[0]],[self.model_input_size[1],self.model_input_size[0]],[self._active_input_size[1],self._active_input_size[0]],len(self.labels),self.kp_num,self.kp_dim,self.conf_thresh,self.nms_thresh,self.max_boxes_num)
                elif self.mode=="video":
                    pose_res = aidemo.yolov8_pose_postprocess(new_result.copy(),[self._active_input_size[1],self._active_input_size[0]],[self.model_input_size[1],self.model_input_size[0]],[self.display_size[1],self.display_size[0]],len(self.labels),self.kp_num,self.kp_dim,self.conf_thresh,self.nms_thresh,self.max_boxes_num)
                return pose_res


    def draw_result(self,res,img):
        """Render task results for video display or IDE image output.

        Args:
            res (object): Result returned by this task's postprocess() method.
            img (image.Image): Drawing target; use the mode-appropriate pixel format.

        Returns:
            None.

        Notes:
            Video mode clears and updates the supplied OSD image. Image mode
            compresses the rendered image for the IDE; segmentation renders a
            separate image from the mask buffer.
        """
        with ScopedTiming("draw result",self.debug_mode > 0):
            if self.mode=="video":
                if self.task_type=="classify":
                    ids,score=res[0],res[1]
                    if ids!=-1:
                        img.clear()
                        mes=self.labels[ids]+" {0:.3f}".format(score)
                        img.draw_string_advanced(5,5,32,mes,color=(0,255,0))
                    else:
                        img.clear()
                elif self.task_type=="detect":
                    if res:
                        img.clear()
                        for i in range(len(res[0])):
                            x, y, w, h = map(lambda x: int(round(x, 0)), res[0][i])
                            img.draw_rectangle(x,y, w, h, color=self.colors[res[1][i]],thickness=4)
                            img.draw_string_advanced( x , y-50,32," " + self.labels[res[1][i]] + " {0:.3f}".format(res[2][i]) , color=self.colors[res[1][i]])
                    else:
                        img.clear()
                elif self.task_type=="segment":
                    if res[0]:
                        img.clear()
                        mask_img=self._get_mask_image()
                        img.copy_from(mask_img)
                        dets,ids,scores = res[0],res[1],res[2]
                        for i, det in enumerate(dets):
                            x1, y1, w, h = map(lambda x: int(round(x, 0)), det)
                            img.draw_string_advanced(x1,y1-50,32, " " + self.labels[int(ids[i])] + " {0:.3f}".format(scores[i]) , color=self.colors[int(ids[i])])
                    else:
                        img.clear()
                elif self.task_type=="obb":
                    if res:
                        img.clear()
                        for i in range(len(res[0])):
                            x1, y1, x2,y2,x3,y3,x4,y4 = map(lambda x: int(round(x, 0)), res[0][i])
                            img.draw_line(int(x1),int(y1),int(x2),int(y2),color=self.colors[res[1][i]],thickness=4)
                            img.draw_line(int(x2),int(y2),int(x3),int(y3),color=self.colors[res[1][i]],thickness=4)
                            img.draw_line(int(x3),int(y3),int(x4),int(y4),color=self.colors[res[1][i]],thickness=4)
                            img.draw_line(int(x4),int(y4),int(x1),int(y1),color=self.colors[res[1][i]],thickness=4)
                            img.draw_string_advanced(x1, y1,24,str(res[1][i]) , color=self.colors[res[1][i]])
                    else:
                        img.clear()
                elif self.task_type=="pose":
                    if res:
                        img.clear()
                        for i in range(len(res[0])):
                            for k in range(self.kp_num):
                                x=res[3][i][k*self.kp_dim+0]
                                y=res[3][i][k*self.kp_dim+1]
                                img.draw_circle(int(x),int(y),5,self.kp_colors[k],fill=True)
                                x_, y_, w_, h_ = map(lambda x: int(round(x, 0)), res[0][i])
                                img.draw_rectangle(x_,y_, w_, h_, color=self.colors[res[1][i]],thickness=4)
                                img.draw_string_advanced( x_ , y_-50,32," " + self.labels[res[1][i]] + " {0:.3f}".format(res[2][i]) , color=self.colors[res[1][i]])
                    else:
                        img.clear()
                else:
                    pass
            elif self.mode=="image":
                if self.task_type=="classify":
                    ids,score=res[0],res[1]
                    if ids!=-1:
                        mes=self.labels[ids]+" {0:.3f}".format(score)
                        img.draw_string_advanced(5,5,32,mes,color=(0,255,0))
                    img.compress_for_ide()
                elif self.task_type=="detect":
                    if res:
                        for i in range(len(res[0])):
                            x, y, w, h = map(lambda x: int(round(x, 0)), res[0][i])
                            img.draw_rectangle(x,y, w, h, color=self.colors[res[1][i]],thickness=4)
                            img.draw_string_advanced( x , y-50,32," " + self.labels[res[1][i]] + " {0:.3f}".format(res[2][i]) , color=self.colors[res[1][i]])
                    img.compress_for_ide()
                elif self.task_type=="segment":
                    if res[0]:
                        mask_rgb=self.masks[0,:,:,1:4]
                        mask_img=image.Image(self._active_input_size[0], self._active_input_size[1], image.RGB888,alloc=image.ALLOC_REF,data=mask_rgb.copy())
                        dets,ids,scores = res[0],res[1],res[2]
                        for i, det in enumerate(dets):
                            x, y, w, h = map(lambda x: int(round(x, 0)), det)
                            mask_img.draw_string_advanced(x,y-50,32, " " + self.labels[int(ids[i])] + " {0:.3f}".format(scores[i]) , color=self.colors[int(ids[i])])
                        mask_img.compress_for_ide()
                elif self.task_type=="obb":
                    if res:
                        for i in range(len(res[0])):
                            x1, y1, x2,y2,x3,y3,x4,y4 = map(lambda x: int(round(x, 0)), res[0][i])
                            img.draw_line(int(x1),int(y1),int(x2),int(y2),color=self.colors[res[1][i]],thickness=4)
                            img.draw_line(int(x2),int(y2),int(x3),int(y3),color=self.colors[res[1][i]],thickness=4)
                            img.draw_line(int(x3),int(y3),int(x4),int(y4),color=self.colors[res[1][i]],thickness=4)
                            img.draw_line(int(x4),int(y4),int(x1),int(y1),color=self.colors[res[1][i]],thickness=4)
                            img.draw_string_advanced(x1, y1,24,str(res[1][i]) , color=self.colors[res[1][i]])
                    img.compress_for_ide()
                elif self.task_type=="pose":
                    if res:
                        for i in range(len(res[0])):
                            for k in range(self.kp_num):
                                x=res[3][i][k*self.kp_dim+0]
                                y=res[3][i][k*self.kp_dim+1]
                                img.draw_circle(int(x),int(y),5,self.kp_colors[k],fill=True)
                                x_, y_, w_, h_ = map(lambda x: int(round(x, 0)), res[0][i])
                                img.draw_rectangle(x_,y_, w_, h_, color=self.colors[res[1][i]],thickness=4)
                                img.draw_string_advanced( x_ , y_-50,32," " + self.labels[res[1][i]] + " {0:.3f}".format(res[2][i]) , color=self.colors[res[1][i]])
                    img.compress_for_ide()
                else:
                    pass

class YOLO26(_YOLOBase):
    """Run YOLO26 classification, detection, segmentation, pose or OBB tasks."""
    def __init__(self,task_type="detect",mode="video",kmodel_path="",labels=[],rgb888p_size=[320,320],model_input_size=[320,320],display_size=[1920,1080],conf_thresh=0.5,mask_thresh=0.5,kp_num=17,kp_dim=3,max_boxes_num=50,debug_mode=0):
        """Initialize the YOLO26 model and task-specific resources.

        Args:
            task_type (str): Task name supported by this YOLO version.
            mode (str): Processing mode, 'image' or 'video'.
            kmodel_path (str): Path to the kmodel file.
            labels (list): Class names in model class-index order.
            rgb888p_size (list or None): RGB planar input [width, height], in pixels.
            model_input_size (list or None): Model input [width, height], in pixels.
            display_size (list or None): Display [width, height], in pixels.
            conf_thresh (float): Confidence threshold for accepting predictions.
            mask_thresh (float): Threshold for segmentation masks.
            kp_num (int): Number of keypoints per detected instance.
            kp_dim (int): Number of values per keypoint in the model output.
            max_boxes_num (int): Maximum detections for postprocessors that accept a box limit.
            debug_mode (int): Enable timing output when greater than zero.

        Raises:
            ValueError: The mode is unsupported.
            Exception: The task_type is unsupported.

        Notes:
            Call config_preprocess() before run(), then deinit() when finished.
            Model output layout must match the selected task and YOLO version.
        """
        try:
            if mode not in ("video", "image"):
                raise ValueError("Invalid mode")
            if task_type not in ["classify","detect","segment","obb","pose"]:
                raise Exception("Please select the correct task_type parameter, including 'classify', 'detect', 'segment','obb','pose'.")
            super().__init__(kmodel_path,model_input_size,rgb888p_size,debug_mode)
            self.task_type=task_type
            self.mode=mode
            self.kmodel_path=kmodel_path
            self.labels=labels
            self.class_num=len(labels)
            if mode=="video":
                self.rgb888p_size=[ALIGN_UP(rgb888p_size[0],16),rgb888p_size[1]]
            else:
                self.rgb888p_size=[rgb888p_size[0],rgb888p_size[1]]
            self.model_input_size=model_input_size
            self.display_size=[ALIGN_UP(display_size[0],16),display_size[1]]

            self.conf_thresh=conf_thresh
            self.mask_thresh=mask_thresh
            self.kp_num=kp_num
            self.kp_dim=kp_dim
            self.max_boxes_num=max_boxes_num
            self.debug_mode=debug_mode

            self.scale=1.0
            self.colors=get_colors(len(self.labels))
            self.kp_colors=get_colors(self.kp_num)
            self.masks=None
            if self.task_type=="segment":
                if self.mode=="image":
                    self.masks=np.zeros((1,self.rgb888p_size[1],self.rgb888p_size[0],4),dtype=np.uint8)
                elif self.mode=="video":
                    self.masks=np.zeros((1,self.display_size[1],self.display_size[0],4),dtype=np.uint8)
            # Ai2d实例，用于实现模型预处理
            self.ai2d=Ai2d(self.debug_mode)
            # 设置Ai2d的输入输出格式和类型
            self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT,nn.ai2d_format.NCHW_FMT,np.uint8, np.uint8)
            self._active_input_size = list(self.rgb888p_size)
        except BaseException:
            try:
                self.deinit()
            except Exception as error:
                print("YOLO constructor cleanup failed:", error)
            raise

    # 配置预处理操作，这里使用了resize，Ai2d支持crop/shift/pad/resize/affine，具体代码请打开/sdcard/app/libs/AI2D.py查看
    def config_preprocess(self,input_image_size=None):
        """Build preprocessing for the selected task and input dimensions.

        Args:
            input_image_size (list or None): Input [width, height]; None uses rgb888p_size.

        Returns:
            None.

        Notes:
            Classification uses a centered square crop. Other tasks use
            aspect-preserving padding. Successful builds update the active input
            size used by postprocessing; image segmentation also resizes masks.
        """
        with ScopedTiming("set preprocess config",self.debug_mode > 0):
            # 初始化ai2d预处理配置，默认为sensor给到AI的尺寸，您可以通过设置input_image_size自行修改输入尺寸
            ai2d_input_size=input_image_size if input_image_size else self.rgb888p_size
            new_input_size = [ai2d_input_size[0], ai2d_input_size[1]]
            new_masks = self.masks
            if (self.task_type == "segment" and self.mode == "image" and
                    new_input_size != self._active_input_size):
                new_masks = np.zeros((1, ai2d_input_size[1], ai2d_input_size[0], 4), dtype=np.uint8)
            if self.task_type=="classify":
                top,left,m=center_crop_param(ai2d_input_size)
                self.ai2d.crop(left,top,m,m)
            elif self.task_type=="detect":
                # 计算padding参数
                top,bottom,left,right,self.scale=letterbox_pad_param(ai2d_input_size,self.model_input_size)
                # 配置padding预处理
                self.ai2d.pad([0,0,0,0,top,bottom,left,right], 0, [128,128,128])
            elif self.task_type=="segment":
                top,bottom,left,right,scale=letterbox_pad_param(ai2d_input_size,self.model_input_size)
                self.ai2d.pad([0,0,0,0,top,bottom,left,right], 0, [128,128,128])
            elif self.task_type=="obb":
                # 计算padding参数
                top,bottom,left,right,self.scale=letterbox_pad_param(ai2d_input_size,self.model_input_size)
                # 配置padding预处理
                self.ai2d.pad([0,0,0,0,top,bottom,left,right], 0, [128,128,128])
            elif self.task_type=="pose":
                top,bottom,left,right,scale=letterbox_pad_param(ai2d_input_size,self.model_input_size)
                self.ai2d.pad([0,0,0,0,top,bottom,left,right], 0, [128,128,128])
            self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
            # build参数包含输入shape和输出shape
            self.ai2d.build([1,3,ai2d_input_size[1],ai2d_input_size[0]],[1,3,self.model_input_size[1],self.model_input_size[0]])
            self._active_input_size = new_input_size
            self.masks = new_masks

    def postprocess(self,results):
        """Decode model outputs for the configured YOLO task.

        Args:
            results (list): Model output ndarrays in output index order.

        Returns:
            tuple or list: Classification returns (class_index, score), with
            (-1, 0.0) below threshold. Other tasks return the matching aidemo
            postprocessor result, consumed directly by draw_result().

        Notes:
            Detection/segmentation results contain boxes, class IDs and scores.
            Coordinates target the display in video mode and active input size
            in image mode. Segmentation also overwrites the reusable masks array.
        """
        with ScopedTiming("postprocess",self.debug_mode > 0):
            if self.task_type=="classify":
                scores=results[0][0]
                max_score=np.max(scores)
                res_idx=np.argmax(scores)
                cls_res=(-1,0.0)
                # 如果类别分数大于阈值，返回当前类别和分数
                if max_score>self.conf_thresh:
                    cls_res=(res_idx,max_score)
                return cls_res
            elif self.task_type=="detect":
                if self.mode=="image":
                    det_res = aidemo.yolo26_det_postprocess(results[0][0],[self._active_input_size[1],self._active_input_size[0]],[self.model_input_size[1],self.model_input_size[0]],[self._active_input_size[1],self._active_input_size[0]],len(self.labels),self.conf_thresh,self.max_boxes_num)
                elif self.mode=="video":
                    det_res = aidemo.yolo26_det_postprocess(results[0][0],[self._active_input_size[1],self._active_input_size[0]],[self.model_input_size[1],self.model_input_size[0]],[self.display_size[1],self.display_size[0]],len(self.labels),self.conf_thresh,self.max_boxes_num)
                return det_res
            elif self.task_type=="segment":
                if self.mode=="image":
                    seg_res = aidemo.yolo26_seg_postprocess(results[0][0],results[1][0],[self._active_input_size[1],self._active_input_size[0]],[self.model_input_size[1],self.model_input_size[0]],[self._active_input_size[1],self._active_input_size[0]],len(self.labels),self.conf_thresh,self.mask_thresh,self.masks)
                elif self.mode=="video":
                    seg_res = aidemo.yolo26_seg_postprocess(results[0][0],results[1][0],[self._active_input_size[1],self._active_input_size[0]],[self.model_input_size[1],self.model_input_size[0]],[self.display_size[1],self.display_size[0]],len(self.labels),self.conf_thresh,self.mask_thresh,self.masks)
                return seg_res
            elif self.task_type=="obb":
                if self.mode=="image":
                    obb_res = aidemo.yolo26_obb_postprocess(results[0][0],[self._active_input_size[1],self._active_input_size[0]],[self.model_input_size[1],self.model_input_size[0]],[self._active_input_size[1],self._active_input_size[0]],len(self.labels),self.conf_thresh,self.max_boxes_num)
                elif self.mode=="video":
                    obb_res = aidemo.yolo26_obb_postprocess(results[0][0],[self._active_input_size[1],self._active_input_size[0]],[self.model_input_size[1],self.model_input_size[0]],[self.display_size[1],self.display_size[0]],len(self.labels),self.conf_thresh,self.max_boxes_num)
                return obb_res
            elif self.task_type=="pose":
                if self.mode=="image":
                    pose_res = aidemo.yolo26_pose_postprocess(results[0][0],[self._active_input_size[1],self._active_input_size[0]],[self.model_input_size[1],self.model_input_size[0]],[self._active_input_size[1],self._active_input_size[0]],len(self.labels),self.kp_num,self.kp_dim,self.conf_thresh,self.max_boxes_num)
                elif self.mode=="video":
                    pose_res = aidemo.yolo26_pose_postprocess(results[0][0],[self._active_input_size[1],self._active_input_size[0]],[self.model_input_size[1],self.model_input_size[0]],[self.display_size[1],self.display_size[0]],len(self.labels),self.kp_num,self.kp_dim,self.conf_thresh,self.max_boxes_num)
                return pose_res

    def draw_result(self,res,img):
        """Render task results for video display or IDE image output.

        Args:
            res (object): Result returned by this task's postprocess() method.
            img (image.Image): Drawing target; use the mode-appropriate pixel format.

        Returns:
            None.

        Notes:
            Video mode clears and updates the supplied OSD image. Image mode
            compresses the rendered image for the IDE; segmentation renders a
            separate image from the mask buffer.
        """
        with ScopedTiming("draw result",self.debug_mode > 0):
            if self.mode=="video":
                if self.task_type=="classify":
                    ids,score=res[0],res[1]
                    if ids!=-1:
                        img.clear()
                        mes=self.labels[ids]+" {0:.3f}".format(score)
                        img.draw_string_advanced(5,5,32,mes,color=(0,255,0))
                    else:
                        img.clear()
                elif self.task_type=="detect":
                    if res:
                        img.clear()
                        for i in range(len(res[0])):
                            x, y, w, h = map(lambda x: int(round(x, 0)), res[0][i])
                            img.draw_rectangle(x,y, w, h, color=self.colors[res[1][i]],thickness=4)
                            img.draw_string_advanced( x , y-50,32," " + self.labels[res[1][i]] + " {0:.3f}".format(res[2][i]) , color=self.colors[res[1][i]])
                    else:
                        img.clear()
                elif self.task_type=="segment":
                    if res[0]:
                        img.clear()
                        mask_img=self._get_mask_image()
                        img.copy_from(mask_img)
                        dets,ids,scores = res[0],res[1],res[2]
                        for i, det in enumerate(dets):
                            x1, y1, w, h = map(lambda x: int(round(x, 0)), det)
                            img.draw_string_advanced(x1,y1-50,32, " " + self.labels[int(ids[i])] + " {0:.3f}".format(scores[i]) , color=self.colors[int(ids[i])])
                    else:
                        img.clear()
                elif self.task_type=="obb":
                    if res:
                        img.clear()
                        for i in range(len(res[0])):
                            x1, y1, x2,y2,x3,y3,x4,y4 = map(lambda x: int(round(x, 0)), res[0][i])
                            img.draw_line(int(x1),int(y1),int(x2),int(y2),color=self.colors[res[1][i]],thickness=4)
                            img.draw_line(int(x2),int(y2),int(x3),int(y3),color=self.colors[res[1][i]],thickness=4)
                            img.draw_line(int(x3),int(y3),int(x4),int(y4),color=self.colors[res[1][i]],thickness=4)
                            img.draw_line(int(x4),int(y4),int(x1),int(y1),color=self.colors[res[1][i]],thickness=4)
                            img.draw_string_advanced(x1, y1,24,str(res[1][i]) , color=self.colors[res[1][i]])
                    else:
                        img.clear()
                elif self.task_type=="pose":
                    if res:
                        img.clear()
                        for i in range(len(res[0])):
                            for k in range(self.kp_num):
                                x=res[3][i][k*self.kp_dim+0]
                                y=res[3][i][k*self.kp_dim+1]
                                img.draw_circle(int(x),int(y),5,self.kp_colors[k],fill=True)
                                x_, y_, w_, h_ = map(lambda x: int(round(x, 0)), res[0][i])
                                img.draw_rectangle(x_,y_, w_, h_, color=self.colors[res[1][i]],thickness=4)
                                img.draw_string_advanced( x_ , y_-50,32," " + self.labels[res[1][i]] + " {0:.3f}".format(res[2][i]) , color=self.colors[res[1][i]])
                    else:
                        img.clear()
                else:
                    pass
            elif self.mode=="image":
                if self.task_type=="classify":
                    ids,score=res[0],res[1]
                    if ids!=-1:
                        mes=self.labels[ids]+" {0:.3f}".format(score)
                        img.draw_string_advanced(5,5,32,mes,color=(0,255,0))
                    img.compress_for_ide()
                elif self.task_type=="detect":
                    if res:
                        for i in range(len(res[0])):
                            x, y, w, h = map(lambda x: int(round(x, 0)), res[0][i])
                            img.draw_rectangle(x,y, w, h, color=self.colors[res[1][i]],thickness=4)
                            img.draw_string_advanced( x , y-50,32," " + self.labels[res[1][i]] + " {0:.3f}".format(res[2][i]) , color=self.colors[res[1][i]])
                    img.compress_for_ide()
                elif self.task_type=="segment":
                    if res[0]:
                        mask_rgb=self.masks[0,:,:,1:4]
                        mask_img=image.Image(self._active_input_size[0], self._active_input_size[1], image.RGB888,alloc=image.ALLOC_REF,data=mask_rgb.copy())
                        dets,ids,scores = res[0],res[1],res[2]
                        for i, det in enumerate(dets):
                            x, y, w, h = map(lambda x: int(round(x, 0)), det)
                            mask_img.draw_string_advanced(x,y-50,32, " " + self.labels[int(ids[i])] + " {0:.3f}".format(scores[i]) , color=self.colors[int(ids[i])])
                        mask_img.compress_for_ide()
                elif self.task_type=="obb":
                    if res:
                        for i in range(len(res[0])):
                            x1, y1, x2,y2,x3,y3,x4,y4 = map(lambda x: int(round(x, 0)), res[0][i])
                            img.draw_line(int(x1),int(y1),int(x2),int(y2),color=self.colors[res[1][i]],thickness=4)
                            img.draw_line(int(x2),int(y2),int(x3),int(y3),color=self.colors[res[1][i]],thickness=4)
                            img.draw_line(int(x3),int(y3),int(x4),int(y4),color=self.colors[res[1][i]],thickness=4)
                            img.draw_line(int(x4),int(y4),int(x1),int(y1),color=self.colors[res[1][i]],thickness=4)
                            img.draw_string_advanced(x1, y1,24,str(res[1][i]) , color=self.colors[res[1][i]])
                    img.compress_for_ide()
                elif self.task_type=="pose":
                    if res:
                        for i in range(len(res[0])):
                            for k in range(self.kp_num):
                                x=res[3][i][k*self.kp_dim+0]
                                y=res[3][i][k*self.kp_dim+1]
                                img.draw_circle(int(x),int(y),5,self.kp_colors[k],fill=True)
                                x_, y_, w_, h_ = map(lambda x: int(round(x, 0)), res[0][i])
                                img.draw_rectangle(x_,y_, w_, h_, color=self.colors[res[1][i]],thickness=4)
                                img.draw_string_advanced( x_ , y_-50,32," " + self.labels[res[1][i]] + " {0:.3f}".format(res[2][i]) , color=self.colors[res[1][i]])
                    img.compress_for_ide()
                else:
                    pass
