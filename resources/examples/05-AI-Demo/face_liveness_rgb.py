from libs.PipeLine import PipeLine
from libs.AIBase import AIBase
from libs.AI2D import Ai2d
from libs.Utils import *
import os,sys,ujson,gc,math
from media.media import *
import nncase_runtime as nn
import ulab.numpy as np
import image
import aidemo

# 自定义人脸检测任务类
class FaceDetApp(AIBase):
    def __init__(self,kmodel_path,model_input_size,anchors,confidence_threshold=0.25,nms_threshold=0.3,rgb888p_size=[1920,1080],display_size=[1920,1080],debug_mode=0):
        super().__init__(kmodel_path,model_input_size,rgb888p_size,debug_mode)
        # kmodel路径
        self.kmodel_path=kmodel_path
        # 检测模型输入分辨率
        self.model_input_size=model_input_size
        # 置信度阈值
        self.confidence_threshold=confidence_threshold
        # nms阈值
        self.nms_threshold=nms_threshold
        self.anchors=anchors
        # sensor给到AI的图像分辨率，宽16字节对齐
        self.rgb888p_size=[ALIGN_UP(rgb888p_size[0],16),rgb888p_size[1]]
        # 视频输出VO分辨率，宽16字节对齐
        self.display_size=[ALIGN_UP(display_size[0],16),display_size[1]]
        # debug模式
        self.debug_mode=debug_mode
        # 实例化Ai2d，用于实现模型预处理
        self.ai2d=Ai2d(debug_mode)
        # 设置Ai2d的输入输出格式和类型
        self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT,nn.ai2d_format.NCHW_FMT,np.uint8, np.uint8)

    # 配置预处理操作，这里使用了pad和resize，Ai2d支持crop/shift/pad/resize/affine，具体代码请打开/sdcard/app/libs/AI2D.py查看
    def config_preprocess(self,input_image_size=None):
        with ScopedTiming("set preprocess config",self.debug_mode > 0):
            # 初始化ai2d预处理配置，默认为sensor给到AI的尺寸，可以通过设置input_image_size自行修改输入尺寸
            ai2d_input_size=input_image_size if input_image_size else self.rgb888p_size
            top, bottom, left, right,_ =letterbox_pad_param(self.rgb888p_size,self.model_input_size)
            self.ai2d.pad([0, 0, 0, 0, top, bottom, left, right], 0, [104, 117, 123])  # 填充边缘
            # 设置resize预处理
            self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
            # 构建预处理流程,参数为预处理输入tensor的shape和预处理输出的tensor的shape
            self.ai2d.build([1,3,ai2d_input_size[1],ai2d_input_size[0]],[1,3,self.model_input_size[1],self.model_input_size[0]])

    # 自定义后处理，results是模型输出的array列表，这里使用了aidemo库的face_det_post_process接口
    def postprocess(self,results):
        with ScopedTiming("postprocess",self.debug_mode > 0):
            res = aidemo.face_det_post_process(self.confidence_threshold,self.nms_threshold,self.model_input_size[0],self.anchors,self.rgb888p_size,results)
            if len(res)==0:
                return res,res
            else:
                return res[0],res[1]

# 自定义活体检测
class FaceLivenessApp(AIBase):
    def __init__(self,kmodel_path,model_input_size,rgb888p_size=[1920,1080],display_size=[1920,1080],debug_mode=0):
        super().__init__(kmodel_path,model_input_size,rgb888p_size,debug_mode)
        # kmodel路径
        self.kmodel_path=kmodel_path
        # 检测模型输入分辨率
        self.model_input_size=model_input_size
        # sensor给到AI的图像分辨率，宽16字节对齐
        self.rgb888p_size=[ALIGN_UP(rgb888p_size[0],16),rgb888p_size[1]]
        # 视频输出VO分辨率，宽16字节对齐
        self.display_size=[ALIGN_UP(display_size[0],16),display_size[1]]
        # debug模式
        self.debug_mode=debug_mode
        self.ai2d=Ai2d(debug_mode)
        self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT,nn.ai2d_format.NCHW_FMT,np.uint8, np.uint8)

    # 配置预处理操作，这里使用了affine，Ai2d支持crop/shift/pad/resize/affine，具体代码请打开/sdcard/app/libs/AI2D.py查看
    def config_preprocess(self,box,input_image_size=None):
        with ScopedTiming("set preprocess config",self.debug_mode > 0):
            ai2d_input_size=input_image_size if input_image_size else self.rgb888p_size
            # 扩展 box 的宽高
            crop_w = int(box[2]) + 224
            crop_h = int(box[3]) + 192
            # 左上角起点
            crop_x = int(box[0]) - crop_w // 2
            crop_y = int(box[1]) - crop_h // 2
            # 限制起点不小于 0
            crop_x = max(0, crop_x)
            crop_y = max(0, crop_y)
            # 限制宽高不越界
            if crop_x + crop_w > ai2d_input_size[0]:
               crop_w = ai2d_input_size[0] - crop_x
            if crop_y + crop_h > ai2d_input_size[1]:
               crop_h = ai2d_input_size[1] - crop_y
            self.ai2d.crop(crop_x,crop_y,crop_w,crop_h)
            self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
            top,bottom,left,right,self.scale=letterbox_pad_param([crop_w,crop_h],self.model_input_size)
            # 配置padding预处理
            self.ai2d.pad([0,0,0,0,top,bottom,left,right], 0, [128,128,128])
            # 构建预处理流程,参数为预处理输入tensor的shape和预处理输出的tensor的shape
            self.ai2d.build([1,3,ai2d_input_size[1],ai2d_input_size[0]],[1,3,self.model_input_size[1],self.model_input_size[0]])

    # 自定义后处理
    def postprocess(self,results):
        with ScopedTiming("postprocess",self.debug_mode > 0):
            return results[0][0]


# 人脸活体任务类
class FaceLiveness:
    def __init__(self,face_det_kmodel,face_live_kmodel,det_input_size,live_input_size,anchors,confidence_threshold=0.25,nms_threshold=0.3,face_liveness_threshold=0.75,rgb888p_size=[1280,720],display_size=[1920,1080],debug_mode=0):
        # 人脸检测模型路径
        self.face_det_kmodel=face_det_kmodel
        # 人脸识别模型路径
        self.face_live_kmodel=face_live_kmodel
        # 人脸检测模型输入分辨率
        self.det_input_size=det_input_size
        # 人脸识别模型输入分辨率
        self.live_input_size=live_input_size
        # anchors
        self.anchors=anchors
        # 置信度阈值
        self.confidence_threshold=confidence_threshold
        # nms阈值
        self.nms_threshold=nms_threshold
        self.face_liveness_threshold=face_liveness_threshold
        # sensor给到AI的图像分辨率，宽16字节对齐
        self.rgb888p_size=[ALIGN_UP(rgb888p_size[0],16),rgb888p_size[1]]
        # 视频输出VO分辨率，宽16字节对齐
        self.display_size=[ALIGN_UP(display_size[0],16),display_size[1]]
        # debug_mode模式
        self.debug_mode=debug_mode
        self.face_det=FaceDetApp(self.face_det_kmodel,model_input_size=self.det_input_size,anchors=self.anchors,confidence_threshold=self.confidence_threshold,nms_threshold=self.nms_threshold,rgb888p_size=self.rgb888p_size,display_size=self.display_size,debug_mode=0)
        self.face_live=FaceLivenessApp(self.face_live_kmodel,model_input_size=self.live_input_size,rgb888p_size=self.rgb888p_size,display_size=self.display_size)
        self.face_det.config_preprocess()

    # run函数
    def run(self,input_np):
        # 执行人脸检测
        det_boxes,landms=self.face_det.run(input_np)
        live_res = []
        for box in det_boxes:
            self.face_live.config_preprocess(box)
            res=self.face_live.run(input_np)
            if res[1]>self.face_liveness_threshold:
                live_res.append("真人")
            else:
                live_res.append("非真人")
        return det_boxes,live_res

    # 绘制识别结果
    def draw_result(self,pl,dets,live_results):
        pl.osd_img.clear()
        if dets:
            for i,det in enumerate(dets):
                # （1）画人脸框
                x1, y1, w, h = map(lambda x: int(round(x, 0)), det[:4])
                x1 = x1 * self.display_size[0]//self.rgb888p_size[0]
                y1 = y1 * self.display_size[1]//self.rgb888p_size[1]
                w =  w * self.display_size[0]//self.rgb888p_size[0]
                h = h * self.display_size[1]//self.rgb888p_size[1]
                # （2）写人脸活体结果
                live_text = live_results[i]
                if live_text=="真人":
                    pl.osd_img.draw_string_advanced(x1,y1,32,live_text,color=(0, 255, 0))
                    pl.osd_img.draw_rectangle(x1,y1, w, h, color=(0, 255, 0), thickness = 4)
                else:
                    pl.osd_img.draw_string_advanced(x1,y1,32,live_text,color=(255, 0, 0))
                    pl.osd_img.draw_rectangle(x1,y1, w, h, color=(255,0, 0), thickness = 4)


if __name__=="__main__":
    # auto按开发板选择默认驱动；可手动改为hdmi/lcd/st7701/nt35516等模式
    display_mode="auto"
    # None使用SDK默认分辨率；更换屏幕规格时手动指定，如[640, 480]
    display_size=None
    # k230保持不变，k230d可调整为[640,360]
    rgb888p_size = [640, 360]
    # 人脸检测模型路径
    face_det_kmodel_path="/sdcard/examples/kmodel/face_detection_320.kmodel"
    # 人脸活体模型路径
    face_live_kmodel_path="/sdcard/examples/kmodel/face_liveness_rgb.kmodel"
    # 其它参数
    anchors_path="/sdcard/examples/utils/prior_data_320.bin"
    face_det_input_size=[320,320]
    face_live_input_size=[112,112]
    confidence_threshold=0.5
    nms_threshold=0.2
    anchor_len=4200
    det_dim=4
    anchors = np.fromfile(anchors_path, dtype=np.float)
    anchors = anchors.reshape((anchor_len,det_dim))
    face_liveness_threshold = 0.5        # 人脸活体阈值

    # 初始化PipeLine，rgb888p_size为传给AI的图像分辨率，display_size为显示分辨率
    pl=PipeLine(rgb888p_size=rgb888p_size,display_mode=display_mode, display_size=display_size)
    # 创建PipeLine，可按需传入sensor_id选择摄像头，例如pl.create(sensor_id=2)
    pl.create()
    display_size=pl.get_display_size()
    fl=FaceLiveness(face_det_kmodel_path,face_live_kmodel_path,det_input_size=face_det_input_size,live_input_size=face_live_input_size,anchors=anchors,confidence_threshold=confidence_threshold,nms_threshold=nms_threshold,face_liveness_threshold=face_liveness_threshold,rgb888p_size=rgb888p_size,display_size=display_size)
    while True:
        with ScopedTiming("total", 1):
            img=pl.get_frame()                      # 获取当前帧
            det_boxes,live_res=fl.run(img)          # 推理当前帧
            fl.draw_result(pl,det_boxes,live_res)   # 绘制推理结果
            pl.show_image()                         # 展示推理效果
            gc.collect()
    fr.face_det.deinit()
    fr.face_live.deinit()
    pl.destroy()
