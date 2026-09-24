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

# 自定义跌倒检测类，继承自AIBase基类
class FallDetectionApp(AIBase):
    def __init__(self, kmodel_path, model_input_size, labels, anchors, confidence_threshold=0.2, nms_threshold=0.5, nms_option=False, strides=[8,16,32], rgb888p_size=[224,224], display_size=[1920,1080], debug_mode=0):
        super().__init__(kmodel_path, model_input_size, rgb888p_size, debug_mode)  # 调用基类的构造函数
        self.kmodel_path = kmodel_path                      # 模型文件路径
        self.model_input_size = model_input_size            # 模型输入分辨率
        self.labels = labels                                # 分类标签
        self.anchors = anchors                              # 锚点数据，用于跌倒检测
        self.strides = strides                              # 步长设置
        self.confidence_threshold = confidence_threshold    # 置信度阈值
        self.nms_threshold = nms_threshold                  # NMS（非极大值抑制）阈值
        self.nms_option = nms_option                        # NMS选项
        self.rgb888p_size = [ALIGN_UP(rgb888p_size[0], 16), rgb888p_size[1]]  # sensor给到AI的图像分辨率，并对宽度进行16的对齐
        self.display_size = [ALIGN_UP(display_size[0], 16), display_size[1]]  # 显示分辨率，并对宽度进行16的对齐
        self.debug_mode = debug_mode                                          # 是否开启调试模式
        self.color = [(255,0, 0, 255), (255,0, 255, 0), (255,255,0, 0), (255,255,0, 255)]  # 用于绘制不同类别的颜色
        # Ai2d实例，用于实现模型预处理
        self.ai2d = Ai2d(debug_mode)
        # 设置Ai2d的输入输出格式和类型
        self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT, nn.ai2d_format.NCHW_FMT, np.uint8, np.uint8)

    # 配置预处理操作，这里使用了pad和resize，Ai2d支持crop/shift/pad/resize/affine，具体代码请打开/sdcard/app/libs/AI2D.py查看
    def config_preprocess(self, input_image_size=None):
        with ScopedTiming("set preprocess config", self.debug_mode > 0):                    # 计时器，如果debug_mode大于0则开启
            ai2d_input_size = input_image_size if input_image_size else self.rgb888p_size   # 初始化ai2d预处理配置，默认为sensor给到AI的尺寸，可以通过设置input_image_size自行修改输入尺寸
            top, bottom, left, right,_ = center_pad_param(self.rgb888p_size,self.model_input_size)
            self.ai2d.pad([0, 0, 0, 0, top, bottom, left, right], 0, [0,0,0])               # 填充边缘
            self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)       # 缩放图像
            self.ai2d.build([1,3,ai2d_input_size[1],ai2d_input_size[0]],[1,3,self.model_input_size[1],self.model_input_size[0]])  # 构建预处理流程

    # 自定义当前任务的后处理，results是模型输出array的列表，这里使用了aicube库的anchorbasedet_post_process接口
    def postprocess(self, results):
        with ScopedTiming("postprocess", self.debug_mode > 0):
            dets = aicube.anchorbasedet_post_process(results[0], results[1], results[2], self.model_input_size, self.rgb888p_size, self.strides, len(self.labels), self.confidence_threshold, self.nms_threshold, self.anchors, self.nms_option)
            return dets

    # 绘制检测结果到画面上
    def draw_result(self, pl, dets):
        with ScopedTiming("display_draw", self.debug_mode > 0):
            if dets:
                pl.osd_img.clear()  # 清除OSD图像
                for det_box in dets:
                    # 计算显示分辨率下的坐标
                    x1, y1, x2, y2 = det_box[2], det_box[3], det_box[4], det_box[5]
                    w = (x2 - x1) * self.display_size[0] // self.rgb888p_size[0]
                    h = (y2 - y1) * self.display_size[1] // self.rgb888p_size[1]
                    x1 = int(x1 * self.display_size[0] // self.rgb888p_size[0])
                    y1 = int(y1 * self.display_size[1] // self.rgb888p_size[1])
                    x2 = int(x2 * self.display_size[0] // self.rgb888p_size[0])
                    y2 = int(y2 * self.display_size[1] // self.rgb888p_size[1])
                    # 绘制矩形框和类别标签
                    pl.osd_img.draw_rectangle(x1, y1, int(w), int(h), color=self.color[det_box[0]], thickness=2)
                    pl.osd_img.draw_string_advanced(x1, y1-50, 32," " + self.labels[det_box[0]] + " " + str(round(det_box[1],2)), color=self.color[det_box[0]])
            else:
                pl.osd_img.clear()

if __name__ == "__main__":
    # auto按开发板选择默认驱动；可手动改为hdmi/lcd/st7701/nt35516等模式
    display_mode="auto"
    # None使用SDK默认分辨率；更换屏幕规格时手动指定，如[640, 480]
    display_size=None
    # k230保持不变，k230d可调整为[640,360]
    rgb888p_size = [1280, 720]
    # 设置模型路径和其他参数
    kmodel_path = "/sdcard/examples/kmodel/yolov5n-falldown.kmodel"
    confidence_threshold = 0.3
    nms_threshold = 0.45
    labels = ["Fall","NoFall"]  # 模型输出类别名称
    anchors = [10, 13, 16, 30, 33, 23, 30, 61, 62, 45, 59, 119, 116, 90, 156, 198, 373, 326]  # anchor设置

    # 初始化PipeLine，rgb888p_size为传给AI的图像分辨率，display_size为显示分辨率
    pl = PipeLine(rgb888p_size=rgb888p_size, display_mode=display_mode, display_size=display_size)
    # 创建PipeLine，可按需传入sensor_id选择摄像头，例如pl.create(sensor_id=2)
    pl.create()
    display_size=pl.get_display_size()
    # 初始化自定义跌倒检测实例
    fall_det = FallDetectionApp(kmodel_path, model_input_size=[640, 640], labels=labels, anchors=anchors, confidence_threshold=confidence_threshold, nms_threshold=nms_threshold, nms_option=False, strides=[8,16,32], rgb888p_size=rgb888p_size, display_size=display_size, debug_mode=0)
    fall_det.config_preprocess()
    while True:
        with ScopedTiming("total",1):
            img = pl.get_frame()                        # 获取当前帧数据
            res = fall_det.run(img)                     # 推理当前帧
            fall_det.draw_result(pl, res)               # 绘制结果到PipeLine的osd图像
            pl.show_image()                             # 显示当前的绘制结果
            gc.collect()                                # 垃圾回收
    fall_det.deinit()                                   # 反初始化
    pl.destroy()                                        # 销毁PipeLine实例
