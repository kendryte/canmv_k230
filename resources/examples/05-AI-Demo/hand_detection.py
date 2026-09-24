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

# 自定义手掌检测类，继承自AIBase基类
class HandDetectionApp(AIBase):
    def __init__(self, kmodel_path, model_input_size, labels, anchors, confidence_threshold=0.2, nms_threshold=0.5, nms_option=False, strides=[8,16,32], rgb888p_size=[224,224], display_size=[1920,1080], debug_mode=0):
        super().__init__(kmodel_path, model_input_size, rgb888p_size, debug_mode)  # 调用基类的构造函数，初始化模型文件路径、模型输入分辨率、RGB图像分辨率和调试模式
        self.kmodel_path = kmodel_path  # 模型文件路径
        self.model_input_size = model_input_size  # 模型输入分辨率
        self.labels = labels  # 模型输出的类别标签列表
        self.anchors = anchors  # 用于目标检测的锚点尺寸列表
        self.strides = strides  # 特征下采样倍数
        self.confidence_threshold = confidence_threshold  # 置信度阈值，用于过滤低置信度的检测结果
        self.nms_threshold = nms_threshold  # NMS（非极大值抑制）阈值，用于去除重叠的检测框
        self.nms_option = nms_option  # NMS选项，可能影响NMS的具体实现
        self.rgb888p_size = [ALIGN_UP(rgb888p_size[0], 16), rgb888p_size[1]]  # sensor给到AI的图像分辨率，对齐到最近的16的倍数
        self.display_size = [ALIGN_UP(display_size[0], 16), display_size[1]]  # 显示分辨率，对齐到最近的16的倍数
        self.debug_mode = debug_mode  # 调试模式，用于输出调试信息
        self.ai2d = Ai2d(debug_mode)  # 实例化Ai2d类，用于实现模型预处理
        # 设置Ai2d的输入输出格式和类型，这里使用NCHW格式，数据类型为uint8
        self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT, nn.ai2d_format.NCHW_FMT, np.uint8, np.uint8)

    # 配置预处理操作，这里使用了pad和resize
    def config_preprocess(self, input_image_size=None):
        with ScopedTiming("set preprocess config", self.debug_mode > 0):  # 使用ScopedTiming装饰器来测量预处理配置的时间
            # 初始化ai2d预处理配置，默认为sensor给到AI的尺寸，可以通过设置input_image_size自行修改输入尺寸
            ai2d_input_size = input_image_size if input_image_size else self.rgb888p_size
            # 计算padding参数并应用pad操作，以确保输入图像尺寸与模型输入尺寸匹配
            top, bottom, left, right,_ = center_pad_param(self.rgb888p_size, self.model_input_size)
            self.ai2d.pad([0, 0, 0, 0, top, bottom, left, right], 0, [0, 0, 0])
            # 使用双线性插值进行resize操作，调整图像尺寸以符合模型输入要求
            self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
            # 构建预处理流程
            self.ai2d.build([1,3,ai2d_input_size[1],ai2d_input_size[0]],[1,3,self.model_input_size[1],self.model_input_size[0]])

    # 自定义当前任务的后处理，用于处理模型输出结果
    def postprocess(self, results):
        with ScopedTiming("postprocess", self.debug_mode > 0):  # 使用ScopedTiming装饰器来测量后处理的时间
            # 使用aicube库的函数进行后处理，得到最终的检测结果
            dets = aicube.anchorbasedet_post_process(results[0], results[1], results[2], self.model_input_size, self.rgb888p_size, self.strides, len(self.labels), self.confidence_threshold, self.nms_threshold, self.anchors, self.nms_option)
            return dets

    # 绘制检测结果到屏幕上
    def draw_result(self, pl, dets):
        with ScopedTiming("display_draw", self.debug_mode > 0):  # 使用ScopedTiming装饰器来测量绘制结果的时间
            if dets:  # 如果存在检测结果
                pl.osd_img.clear()  # 清除屏幕上的旧内容
                for det_box in dets:  # 遍历每个检测框
                    # 根据模型输出计算检测框的像素坐标，并调整大小以适应显示分辨率
                    x1, y1, x2, y2 = det_box[2], det_box[3], det_box[4], det_box[5]
                    w = float(x2 - x1) * self.display_size[0] // self.rgb888p_size[0]
                    h = float(y2 - y1) * self.display_size[1] // self.rgb888p_size[1]
                    x1 = int(x1 * self.display_size[0] // self.rgb888p_size[0])
                    y1 = int(y1 * self.display_size[1] // self.rgb888p_size[1])
                    x2 = int(x2 * self.display_size[0] // self.rgb888p_size[0])
                    y2 = int(y2 * self.display_size[1] // self.rgb888p_size[1])
                    # 过滤掉太小或者位置不合理的检测框
                    if (h < (0.1 * self.display_size[0])):
                        continue
                    if (w < (0.25 * self.display_size[0]) and ((x1 < (0.03 * self.display_size[0])) or (x2 > (0.97 * self.display_size[0])))):
                        continue
                    if (w < (0.15 * self.display_size[0]) and ((x1 < (0.01 * self.display_size[0])) or (x2 > (0.99 * self.display_size[0])))):
                        continue
                    # 绘制矩形框和类别标签
                    pl.osd_img.draw_rectangle(x1, y1, int(w), int(h), color=(255, 0, 255, 0), thickness=2)
                    pl.osd_img.draw_string_advanced(x1, y1-50,32, " " + self.labels[det_box[0]] + " " + str(round(det_box[1], 2)), color=(255, 0, 255, 0))
            else:
                pl.osd_img.clear()  # 如果没有检测结果，清空屏幕

if __name__=="__main__":
    # auto按开发板选择默认驱动；可手动改为hdmi/lcd/st7701/nt35516等模式
    display_mode="auto"
    # None使用SDK默认分辨率；更换屏幕规格时手动指定，如[640, 480]
    display_size=None
    # k230保持不变，k230d可调整为[640,360]
    rgb888p_size = [1280, 720]
    # 模型路径
    kmodel_path="/sdcard/examples/kmodel/hand_det.kmodel"
    # 其它参数设置
    confidence_threshold = 0.2
    nms_threshold = 0.5
    labels = ["hand"]
    anchors = [26,27, 53,52, 75,71, 80,99, 106,82, 99,134, 140,113, 161,172, 245,276]   #anchor设置

    # 初始化PipeLine，rgb888p_size为传给AI的图像分辨率，display_size为显示分辨率
    pl=PipeLine(rgb888p_size=rgb888p_size,display_mode=display_mode, display_size=display_size)
    # 创建PipeLine，可按需传入sensor_id选择摄像头，例如pl.create(sensor_id=2)
    pl.create()
    display_size=pl.get_display_size()
    # 初始化自定义手掌检测实例
    hand_det=HandDetectionApp(kmodel_path,model_input_size=[512,512],labels=labels,anchors=anchors,confidence_threshold=confidence_threshold,nms_threshold=nms_threshold,nms_option=False,strides=[8,16,32],rgb888p_size=rgb888p_size,display_size=display_size,debug_mode=0)
    hand_det.config_preprocess()
    while True:
        with ScopedTiming("total",1):
            img=pl.get_frame()                      # 获取当前帧数据
            res=hand_det.run(img)                   # 推理当前帧
            hand_det.draw_result(pl,res)            # 绘制结果到PipeLine的osd图像
            pl.show_image()                         # 显示当前的绘制结果
            gc.collect()                            # 垃圾回收
    hand_det.deinit()                               # 反初始化
    pl.destroy()                                    # 销毁PipeLine实例

