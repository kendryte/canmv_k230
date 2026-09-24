from libs.PipeLine import PipeLine
from libs.AIBase import AIBase
from libs.AI2D import Ai2d
from libs.Utils import *
import os,sys,ujson,gc,math
from media.media import *
import nncase_runtime as nn
import ulab.numpy as np
import image
import aicube

# 自定义手掌检测任务类
class HandDetApp(AIBase):
    def __init__(self,kmodel_path,model_input_size,anchors,confidence_threshold=0.2,nms_threshold=0.5,nms_option=False, strides=[8,16,32],rgb888p_size=[1920,1080],display_size=[1920,1080],debug_mode=0):
        super().__init__(kmodel_path,model_input_size,rgb888p_size,debug_mode)
        # kmodel路径
        self.kmodel_path=kmodel_path
        # 检测模型输入分辨率
        self.model_input_size=model_input_size
        # 置信度阈值
        self.confidence_threshold=confidence_threshold
        # nms阈值
        self.nms_threshold=nms_threshold
        # 锚框,目标检测任务使用
        self.anchors=anchors
        # 特征下采样倍数
        self.strides = strides
        # NMS选项，如果为True做类间NMS,如果为False做类内NMS
        self.nms_option = nms_option
        # sensor给到AI的图像分辨率，宽16字节对齐
        self.rgb888p_size=[ALIGN_UP(rgb888p_size[0],16),rgb888p_size[1]]
        # 视频输出VO分辨率，宽16字节对齐
        self.display_size=[ALIGN_UP(display_size[0],16),display_size[1]]
        # debug模式
        self.debug_mode=debug_mode
        # Ai2d实例用于实现预处理
        self.ai2d=Ai2d(debug_mode)
        # 设置ai2d的输入输出的格式和数据类型
        self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT,nn.ai2d_format.NCHW_FMT,np.uint8, np.uint8)

    # 配置预处理操作，这里使用了pad和resize，Ai2d支持crop/shift/pad/resize/affine，具体代码请打开/sdcard/app/libs/AI2D.py查看
    def config_preprocess(self,input_image_size=None):
        with ScopedTiming("set preprocess config",self.debug_mode > 0):
            # 初始化ai2d预处理配置，默认为sensor给到AI的尺寸，可以通过设置input_image_size自行修改输入尺寸
            ai2d_input_size = input_image_size if input_image_size else self.rgb888p_size
            # 计算padding参数并应用pad操作，以确保输入图像尺寸与模型输入尺寸匹配
            top, bottom, left, right, _ =center_pad_param(self.rgb888p_size, self.model_input_size) 
            self.ai2d.pad([0, 0, 0, 0, top, bottom, left, right], 0, [114, 114, 114])
            # 使用双线性插值进行resize操作，调整图像尺寸以符合模型输入要求
            self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
            # 构建预处理流程,参数为预处理输入tensor的shape和预处理输出的tensor的shape
            self.ai2d.build([1,3,ai2d_input_size[1],ai2d_input_size[0]],[1,3,self.model_input_size[1],self.model_input_size[0]])

    # 自定义当前任务的后处理，用于处理模型输出结果，这里使用了aicube库的anchorbasedet_post_process接口
    def postprocess(self,results):
        with ScopedTiming("postprocess",self.debug_mode > 0):
            dets = aicube.anchorbasedet_post_process(results[0], results[1], results[2], self.model_input_size, self.rgb888p_size, self.strides,1, self.confidence_threshold, self.nms_threshold, self.anchors, self.nms_option)
            # 返回手掌检测结果
            return dets

# 自定义手势识别任务类
class HandRecognitionApp(AIBase):
    def __init__(self,kmodel_path,model_input_size,labels,rgb888p_size=[1920,1080],display_size=[1920,1080],debug_mode=0):
        super().__init__(kmodel_path,model_input_size,rgb888p_size,debug_mode)
        # kmodel路径
        self.kmodel_path=kmodel_path
        # 检测模型输入分辨率
        self.model_input_size=model_input_size
        self.labels=labels
        # sensor给到AI的图像分辨率，宽16字节对齐
        self.rgb888p_size=[ALIGN_UP(rgb888p_size[0],16),rgb888p_size[1]]
        # 视频输出VO分辨率，宽16字节对齐
        self.display_size=[ALIGN_UP(display_size[0],16),display_size[1]]
        self.crop_params=[]
        # debug模式
        self.debug_mode=debug_mode
        # Ai2d实例用于实现预处理
        self.ai2d=Ai2d(debug_mode)
        # 设置ai2d的输入输出的格式和数据类型
        self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT,nn.ai2d_format.NCHW_FMT,np.uint8, np.uint8)

    # 配置预处理操作，这里使用了crop和resize，Ai2d支持crop/shift/pad/resize/affine，具体代码请打开/sdcard/app/libs/AI2D.py查看
    def config_preprocess(self,det,input_image_size=None):
        with ScopedTiming("set preprocess config",self.debug_mode > 0):
            ai2d_input_size=input_image_size if input_image_size else self.rgb888p_size
            self.crop_params = self.get_crop_param(det)
            self.ai2d.crop(self.crop_params[0],self.crop_params[1],self.crop_params[2],self.crop_params[3])
            self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
            self.ai2d.build([1,3,ai2d_input_size[1],ai2d_input_size[0]],[1,3,self.model_input_size[1],self.model_input_size[0]])

    # 自定义后处理，results是模型输出的array列表
    def postprocess(self,results):
        with ScopedTiming("postprocess",self.debug_mode > 0):
            result=results[0].reshape(results[0].shape[0]*results[0].shape[1])
            x_softmax = self.softmax(result)
            idx = np.argmax(x_softmax)
            text = " " + self.labels[idx] + ": " + str(round(x_softmax[idx],2))
            return text

    # 计算crop参数
    def get_crop_param(self,det_box):
        x1, y1, x2, y2 = det_box[2],det_box[3],det_box[4],det_box[5]
        w,h= int(x2 - x1),int(y2 - y1)
        w_det = int(float(x2 - x1) * self.display_size[0] // self.rgb888p_size[0])
        h_det = int(float(y2 - y1) * self.display_size[1] // self.rgb888p_size[1])
        x_det = int(x1*self.display_size[0] // self.rgb888p_size[0])
        y_det = int(y1*self.display_size[1] // self.rgb888p_size[1])
        length = max(w, h)/2
        cx = (x1+x2)/2
        cy = (y1+y2)/2
        ratio_num = 1.26*length
        x1_kp = int(max(0,cx-ratio_num))
        y1_kp = int(max(0,cy-ratio_num))
        x2_kp = int(min(self.rgb888p_size[0]-1, cx+ratio_num))
        y2_kp = int(min(self.rgb888p_size[1]-1, cy+ratio_num))
        w_kp = int(x2_kp - x1_kp + 1)
        h_kp = int(y2_kp - y1_kp + 1)
        return [x1_kp, y1_kp, w_kp, h_kp]

    # softmax实现
    def softmax(self,x):
        x -= np.max(x)
        x = np.exp(x) / np.sum(np.exp(x))
        return x

class HandRecognition:
    def __init__(self,hand_det_kmodel,hand_kp_kmodel,det_input_size,kp_input_size,labels,anchors,confidence_threshold=0.25,nms_threshold=0.3,nms_option=False,strides=[8,16,32],rgb888p_size=[1280,720],display_size=[1920,1080],debug_mode=0):
        # 手掌检测模型路径
        self.hand_det_kmodel=hand_det_kmodel
        # 手掌关键点模型路径
        self.hand_kp_kmodel=hand_kp_kmodel
        # 手掌检测模型输入分辨率
        self.det_input_size=det_input_size
        # 手掌关键点模型输入分辨率
        self.kp_input_size=kp_input_size
        self.labels=labels
        # anchors
        self.anchors=anchors
        # 置信度阈值
        self.confidence_threshold=confidence_threshold
        # nms阈值
        self.nms_threshold=nms_threshold
        # nms选项
        self.nms_option=nms_option
        # 特征图针对输出的下采样倍数
        self.strides=strides
        # sensor给到AI的图像分辨率，宽16字节对齐
        self.rgb888p_size=[ALIGN_UP(rgb888p_size[0],16),rgb888p_size[1]]
        # 视频输出VO分辨率，宽16字节对齐
        self.display_size=[ALIGN_UP(display_size[0],16),display_size[1]]
        # debug_mode模式
        self.debug_mode=debug_mode
        self.hand_det=HandDetApp(self.hand_det_kmodel,model_input_size=self.det_input_size,anchors=self.anchors,confidence_threshold=self.confidence_threshold,nms_threshold=self.nms_threshold,nms_option=self.nms_option,strides=self.strides,rgb888p_size=self.rgb888p_size,display_size=self.display_size,debug_mode=0)
        self.hand_rec=HandRecognitionApp(self.hand_kp_kmodel,model_input_size=self.kp_input_size,labels=self.labels,rgb888p_size=self.rgb888p_size,display_size=self.display_size)
        self.hand_det.config_preprocess()

    # run函数
    def run(self,input_np):
        # 执行手掌检测
        det_boxes=self.hand_det.run(input_np)
        hand_rec_res=[]
        hand_det_res=[]
        for det_box in det_boxes:
            # 对检测到的每一个手掌执行手势识别
            x1, y1, x2, y2 = det_box[2],det_box[3],det_box[4],det_box[5]
            w,h= int(x2 - x1),int(y2 - y1)
            if (h<(0.1*self.rgb888p_size[1])):
                continue
            if (w<(0.25*self.rgb888p_size[0]) and ((x1<(0.03*self.rgb888p_size[0])) or (x2>(0.97*self.rgb888p_size[0])))):
                continue
            if (w<(0.15*self.rgb888p_size[0]) and ((x1<(0.01*self.rgb888p_size[0])) or (x2>(0.99*self.rgb888p_size[0])))):
                continue
            self.hand_rec.config_preprocess(det_box)
            text=self.hand_rec.run(input_np)
            hand_det_res.append(det_box)
            hand_rec_res.append(text)
        return hand_det_res,hand_rec_res

    # 绘制效果，绘制识别结果和检测框
    def draw_result(self,pl,hand_det_res,hand_rec_res):
        pl.osd_img.clear()
        if hand_det_res:
            for k in range(len(hand_det_res)):
                det_box=hand_det_res[k]
                x1, y1, x2, y2 = det_box[2],det_box[3],det_box[4],det_box[5]
                w,h= int(x2 - x1),int(y2 - y1)
                w_det = int(float(x2 - x1) * self.display_size[0] // self.rgb888p_size[0])
                h_det = int(float(y2 - y1) * self.display_size[1] // self.rgb888p_size[1])
                x_det = int(x1*self.display_size[0] // self.rgb888p_size[0])
                y_det = int(y1*self.display_size[1] // self.rgb888p_size[1])
                pl.osd_img.draw_rectangle(x_det, y_det, w_det, h_det, color=(255, 0, 255, 0), thickness = 2)
                pl.osd_img.draw_string_advanced( x_det, y_det-50, 32,hand_rec_res[k], color=(255,0, 255, 0))


if __name__=="__main__":
    # auto按开发板选择默认驱动；可手动改为hdmi/lcd/st7701/nt35516等模式
    display_mode="auto"
    # None使用SDK默认分辨率；更换屏幕规格时手动指定，如[640, 480]
    display_size=None
    # k230保持不变，k230d可调整为[640,360]
    rgb888p_size = [1280, 720]
    # 手掌检测模型路径
    hand_det_kmodel_path="/sdcard/examples/kmodel/hand_det.kmodel"
    # 手势识别模型路径
    hand_rec_kmodel_path="/sdcard/examples/kmodel/hand_reco.kmodel"
    # 其它参数
    anchors_path="/sdcard/examples/utils/prior_data_320.bin"
    hand_det_input_size=[512,512]
    hand_rec_input_size=[224,224]
    confidence_threshold=0.2
    nms_threshold=0.5
    labels=["gun","other","yeah","five"]
    anchors = [26,27, 53,52, 75,71, 80,99, 106,82, 99,134, 140,113, 161,172, 245,276]

    # 初始化PipeLine，rgb888p_size为传给AI的图像分辨率，display_size为显示分辨率
    pl=PipeLine(rgb888p_size=rgb888p_size,display_mode=display_mode, display_size=display_size)
    # 创建PipeLine，可按需传入sensor_id选择摄像头，例如pl.create(sensor_id=2)
    pl.create()
    display_size=pl.get_display_size()
    hr=HandRecognition(hand_det_kmodel_path,hand_rec_kmodel_path,det_input_size=hand_det_input_size,kp_input_size=hand_rec_input_size,labels=labels,anchors=anchors,confidence_threshold=confidence_threshold,nms_threshold=nms_threshold,nms_option=False,strides=[8,16,32],rgb888p_size=rgb888p_size,display_size=display_size)
    while True:
        with ScopedTiming("total",1):
            img=pl.get_frame()                              # 获取当前帧
            hand_det_res,hand_rec_res=hr.run(img)           # 推理当前帧
            hr.draw_result(pl,hand_det_res,hand_rec_res)    # 绘制推理结果
            pl.show_image()                                 # 展示推理结果
            gc.collect()
    hr.hand_det.deinit()
    hr.hand_rec.deinit()
    pl.destroy()

