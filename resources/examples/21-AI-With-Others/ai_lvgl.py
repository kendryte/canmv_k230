"""
Script: ai_lvgl.py
脚本名称：ai_lvgl.py

Description:
    This script integrates object detection and face detection with LVGL-based GUI control
    on an embedded system. It initializes media inputs and display outputs, executes AI inference
    using YOLOv8 and face detection models, and displays results across different overlay layers.

    It leverages Ai2d for input preprocessing (resize, padding), supports confidence and NMS
    filtering in post-processing, and manages real-time user interaction via LVGL touch input.
    Each detection task runs in its own thread for improved responsiveness.

脚本说明：
    本脚本在嵌入式系统上结合 LVGL 图形界面实现目标检测与人脸检测功能。
    初始化摄像头和显示输出，通过 YOLOv8 和人脸检测模型进行推理，
    并将检测结果绘制到不同的图层显示。

    使用 Ai2d 工具进行模型输入图像的预处理（缩放与填充），
    后处理包括置信度和非极大值抑制（NMS）过滤。
    支持 LVGL 触摸输入交互，检测任务各在线程中独立运行，提升系统响应能力。

Author: Canaan Developer
作者：Canaan 开发者
"""


from libs.PipeLine import PipeLine
from libs.AIBase import AIBase
from libs.AI2D import Ai2d
from libs.Utils import *
import nncase_runtime as nn
import ulab.numpy as np
import aidemo
from media.display import *
from media.media import *
from media.sensor import *
import time, os, sys, gc
import lvgl as lv
from machine import TOUCH
from machine import RTC
import _thread

DISPLAY_WIDTH = ALIGN_UP(800, 16)
DISPLAY_HEIGHT = 480

sensor = None
rgb888p_size=[1280,720]
display_size = [800, 480]
cur_state=0
cur_frame=None
osd_img=None

scr = None
sensor_img=None
obj = None
_x = 0
objs = []

# 自定义YOLOv8检测类
class ObjectDetectionApp(AIBase):
    def __init__(self,kmodel_path,labels,model_input_size,max_boxes_num,confidence_threshold=0.5,nms_threshold=0.2,rgb888p_size=[224,224],display_size=[1920,1080],debug_mode=0):
        super().__init__(kmodel_path,model_input_size,rgb888p_size,debug_mode)
        self.kmodel_path=kmodel_path
        self.labels=labels
        self.model_input_size=model_input_size
        self.confidence_threshold=confidence_threshold
        self.nms_threshold=nms_threshold
        self.max_boxes_num=max_boxes_num
        self.rgb888p_size=[ALIGN_UP(rgb888p_size[0],16),rgb888p_size[1]]
        self.display_size=[ALIGN_UP(display_size[0],16),display_size[1]]
        self.debug_mode=debug_mode
        self.color_four=get_colors(len(self.labels))
        self.x_factor = float(self.rgb888p_size[0])/self.model_input_size[0]
        self.y_factor = float(self.rgb888p_size[1])/self.model_input_size[1]
        self.ai2d=Ai2d(debug_mode)
        self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT,nn.ai2d_format.NCHW_FMT,np.uint8, np.uint8)

    # 配置预处理操作，这里使用了resize，Ai2d支持crop/shift/pad/resize/affine，具体代码请打开/sdcard/app/libs/AI2D.py查看
    def config_preprocess(self,input_image_size=None):
        with ScopedTiming("set preprocess config",self.debug_mode > 0):
            ai2d_input_size=input_image_size if input_image_size else self.rgb888p_size
            top,bottom,left,right,self.scale=letterbox_pad_param(self.rgb888p_size,self.model_input_size)
            self.ai2d.pad([0,0,0,0,top,bottom,left,right], 0, [128,128,128])
            self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
            self.ai2d.build([1,3,ai2d_input_size[1],ai2d_input_size[0]],[1,3,self.model_input_size[1],self.model_input_size[0]])

    def postprocess(self,results):
        with ScopedTiming("postprocess",self.debug_mode > 0):
            new_result=results[0][0].transpose()
            det_res = aidemo.yolov8_det_postprocess(new_result.copy(),[self.rgb888p_size[1],self.rgb888p_size[0]],[self.model_input_size[1],self.model_input_size[0]],[self.display_size[1],self.display_size[0]],len(self.labels),self.confidence_threshold,self.nms_threshold,self.max_boxes_num)
            return det_res

    def draw_result(self,osd_img,dets):
        with ScopedTiming("display_draw",self.debug_mode >0):
            if dets:
                for i in range(len(dets[0])):
                    x, y, w, h = map(lambda x: int(round(x, 0)), dets[0][i])
                    osd_img.draw_rectangle(x,y, w, h, color=self.color_four[dets[1][i]],thickness=4)
                    osd_img.draw_string_advanced(x, y-50,32," " + self.labels[dets[1][i]] + " " + str(round(dets[2][i],2)) , color=self.color_four[dets[1][i]])

    def deinit(self):
        del self.kpu
        del self.ai2d
        self.tensors.clear()
        del self.tensors
        gc.collect()
        time.sleep_ms(50)


# 自定义人脸检测类，继承自AIBase基类
class FaceDetectionApp(AIBase):
    def __init__(self, kmodel_path, model_input_size, anchors, confidence_threshold=0.5, nms_threshold=0.2, rgb888p_size=[224,224], display_size=[1920,1080], debug_mode=0):
        super().__init__(kmodel_path, model_input_size, rgb888p_size, debug_mode)  # 调用基类的构造函数
        self.kmodel_path = kmodel_path  # 模型文件路径
        self.model_input_size = model_input_size  # 模型输入分辨率
        self.confidence_threshold = confidence_threshold  # 置信度阈值
        self.nms_threshold = nms_threshold  # NMS（非极大值抑制）阈值
        self.anchors = anchors  # 锚点数据，用于目标检测
        self.rgb888p_size = [ALIGN_UP(rgb888p_size[0], 16), rgb888p_size[1]]  # sensor给到AI的图像分辨率，并对宽度进行16的对齐
        self.display_size = [ALIGN_UP(display_size[0], 16), display_size[1]]  # 显示分辨率，并对宽度进行16的对齐
        self.debug_mode = debug_mode  # 是否开启调试模式
        self.ai2d = Ai2d(debug_mode)  # 实例化Ai2d，用于实现模型预处理
        self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT, nn.ai2d_format.NCHW_FMT, np.uint8, np.uint8)  # 设置Ai2d的输入输出格式和类型

    # 配置预处理操作，这里使用了pad和resize，Ai2d支持crop/shift/pad/resize/affine，具体代码请打开/sdcard/app/libs/AI2D.py查看
    def config_preprocess(self, input_image_size=None):
        with ScopedTiming("set preprocess config", self.debug_mode > 0):  # 计时器，如果debug_mode大于0则开启
            ai2d_input_size = input_image_size if input_image_size else self.rgb888p_size  # 初始化ai2d预处理配置，默认为sensor给到AI的尺寸，可以通过设置input_image_size自行修改输入尺寸
            top, bottom, left, right,_ = letterbox_pad_param(self.rgb888p_size,self.model_input_size)
            self.ai2d.pad([0, 0, 0, 0, top, bottom, left, right], 0, [104, 117, 123])  # 填充边缘
            self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)  # 缩放图像
            self.ai2d.build([1,3,ai2d_input_size[1],ai2d_input_size[0]],[1,3,self.model_input_size[1],self.model_input_size[0]])  # 构建预处理流程

    # 自定义当前任务的后处理，results是模型输出array列表，这里使用了aidemo库的face_det_post_process接口
    def postprocess(self, results):
        with ScopedTiming("postprocess", self.debug_mode > 0):
            post_ret = aidemo.face_det_post_process(self.confidence_threshold, self.nms_threshold, self.model_input_size[1], self.anchors, self.rgb888p_size, results)
            if len(post_ret) == 0:
                return post_ret
            else:
                return post_ret[0]

    # 绘制检测结果到画面上
    def draw_result(self, osd_img, dets):
        with ScopedTiming("display_draw", self.debug_mode > 0):
            if dets:
                for det in dets:
                    # 将检测框的坐标转换为显示分辨率下的坐标
                    x, y, w, h = map(lambda x: int(round(x, 0)), det[:4])
                    x = x * self.display_size[0] // self.rgb888p_size[0]
                    y = y * self.display_size[1] // self.rgb888p_size[1]
                    w = w * self.display_size[0] // self.rgb888p_size[0]
                    h = h * self.display_size[1] // self.rgb888p_size[1]
                    osd_img.draw_rectangle(x, y, w, h, color=(255, 255, 0, 255), thickness=2)

    def deinit(self):
        del self.kpu
        del self.ai2d
        self.tensors.clear()
        del self.tensors
        gc.collect()
        time.sleep_ms(50)


def face_det_thread():
    global sensor,osd_img,rgb888p_size,display_size,cur_state
    # 设置模型路径和其他参数
    kmodel_path = "/sdcard/examples/kmodel/face_detection_320.kmodel"
    # 其它参数
    confidence_threshold = 0.5
    nms_threshold = 0.2
    anchor_len = 4200
    det_dim = 4
    anchors_path = "/sdcard/examples/utils/prior_data_320.bin"
    anchors = np.fromfile(anchors_path, dtype=np.float)
    anchors = anchors.reshape((anchor_len, det_dim))
    face_det = FaceDetectionApp(kmodel_path, model_input_size=[320, 320], anchors=anchors, confidence_threshold=confidence_threshold, nms_threshold=nms_threshold, rgb888p_size=rgb888p_size, display_size=display_size, debug_mode=0)
    face_det.config_preprocess()  # 配置预处理
    while True:
        with ScopedTiming("total", 2):
            if cur_state==2:
                img_0=sensor.snapshot(chn=CAM_CHN_ID_0)
                img_2 = sensor.snapshot(chn = CAM_CHN_ID_2)
                img_np =img_2.to_numpy_ref()
                res = face_det.run(img_np)         # 推理当前帧
                face_det.draw_result(img_0, res)   # 绘制结果
                Display.show_image(img_0, 0, 0, Display.LAYER_OSD1)
            else:
                break
        gc.collect()
    face_det.deinit()


def yolov8_det_thread():
    global sensor,osd_img,rgb888p_size,display_size,cur_state
    kmodel_path="/sdcard/examples/kmodel/yolov8n_224.kmodel"
    labels = ["person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat", "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch", "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase", "scissors", "teddy bear", "hair drier", "toothbrush"]
    confidence_threshold = 0.3
    nms_threshold = 0.4
    ob_det=ObjectDetectionApp(kmodel_path,labels=labels,model_input_size=[224,224],max_boxes_num=50,confidence_threshold=confidence_threshold,nms_threshold=nms_threshold,rgb888p_size=rgb888p_size,display_size=display_size,debug_mode=0)
    ob_det.config_preprocess()
    while True:
        with ScopedTiming("total", 1):
            if cur_state==1:
                img_0=sensor.snapshot(chn=CAM_CHN_ID_0)
                img_2 = sensor.snapshot(chn = CAM_CHN_ID_2)
                img_np =img_2.to_numpy_ref()
                det_res = ob_det.run(img_np)
                ob_det.draw_result(img_0, det_res)
                Display.show_image(img_0, 0, 0, Display.LAYER_OSD1)
            else:
                break
        gc.collect()
    ob_det.deinit()

def media_init():
    global sensor,osd_img,rgb888p_size,display_size
    Display.init(Display.ST7701, width = DISPLAY_WIDTH, height = DISPLAY_HEIGHT, to_ide = True, osd_num=2)
    sensor = Sensor(fps=30)
    sensor.reset()
    sensor.set_framesize(w = 800, h = 480,chn=CAM_CHN_ID_0)
    sensor.set_pixformat(Sensor.RGB888)
    sensor.set_framesize(w = rgb888p_size[0], h = rgb888p_size[1], chn=CAM_CHN_ID_2)
    sensor.set_pixformat(Sensor.RGBP888, chn=CAM_CHN_ID_2)

    sensor.run()

def media_deinit():
    global sensor
    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    sensor.stop()
    Display.deinit()
    time.sleep_ms(50)

def disp_drv_flush_cb(disp_drv, area, color):
    global disp_img1, disp_img2
    if disp_drv.flush_is_last() == True:
        if disp_img1.virtaddr() == uctypes.addressof(color.__dereference__()):
            disp_img2.bytearray()[:]=bytearray(0)
            Display.show_image(disp_img1,layer=Display.LAYER_OSD2)
        else:
            disp_img1.bytearray()[:]=bytearray(0)
            Display.show_image(disp_img2,layer=Display.LAYER_OSD2)
        time.sleep(0.01)
    disp_drv.flush_ready()


class touch_screen():
    def __init__(self):
        self.x = 0
        self.y = 0
        self.state = lv.INDEV_STATE.RELEASED
        self.indev_drv = lv.indev_create()
        self.indev_drv.set_type(lv.INDEV_TYPE.POINTER)
        self.indev_drv.set_read_cb(self.callback)
        self.touch = TOUCH(0)

    def callback(self, driver, data):
        x, y, state = self.x, self.y, lv.INDEV_STATE.RELEASED
        tp = self.touch.read(1)
        if tp != (): #发生触摸事件
            for i in range(len(tp)):
                 pass
        if len(tp):
            x, y, event = tp[0].x, tp[0].y, tp[0].event
            if event == 2 or event == 3:
                state = lv.INDEV_STATE.PRESSED
        data.point = lv.point_t({'x': x, 'y': y})
        data.state = state

def lvgl_init():
    global disp_img1, disp_img2
    lv.init()
    disp_drv = lv.disp_create(DISPLAY_WIDTH, DISPLAY_HEIGHT)
    disp_drv.set_flush_cb(disp_drv_flush_cb)
    disp_drv.set_color_format(lv.COLOR_FORMAT.ARGB8888)
    disp_img1 = image.Image(display_size[0], display_size[1], image.BGRA8888)
    disp_img2 = image.Image(display_size[0], display_size[1], image.BGRA8888)
    disp_img1.clear()
    disp_img2.clear()
    disp_drv.set_draw_buffers(disp_img1.bytearray(), disp_img2.bytearray(), disp_img1.size(), lv.DISP_RENDER_MODE.FULL)
    tp = touch_screen()

def lvgl_deinit():
    global disp_img1, disp_img2,camera_stop
    disp_img1.clear()
    disp_img2.clear()
    lv.deinit()
    del disp_img1
    del disp_img2

def btn_clicked_face_det(event):
    global cur_state
    if cur_state==2:
        return
    cur_state=2
    time.sleep_ms(100)
    _thread.start_new_thread(face_det_thread,())

def btn_clicked_yolo_det(event):
    global cur_state
    if cur_state==1:
        return
    cur_state=1
    time.sleep_ms(100)
    _thread.start_new_thread(yolov8_det_thread,())

def user_gui_init():
    global scr, obj,sensor_img
    res_path = "/sdcard/examples/15-LVGL/data/"
    font_simsun_16_cjk = lv.font_load("A:" + res_path + "font/lv_font_simsun_16_cjk.fnt")

    scr = lv.scr_act()

    # 设置屏幕背景完全透明
    lv.scr_act().set_style_bg_opa(lv.OPA.TRANSP, lv.PART.MAIN)

    # 创建一个半透明的侧边栏
    label = lv.obj(lv.layer_sys())
    label.set_size(100, 480)
    label.set_pos(700, 0)
    label.set_style_bg_color(lv.color_hex(0x000000), lv.PART.MAIN)
    label.set_style_bg_opa(50, lv.PART.MAIN)
    label.set_style_border_width(0, lv.PART.MAIN)

    # yolov8检测按钮
    btn1 = lv.btn(lv.layer_sys())
    btn1.set_size(90, 45)
    btn1.set_pos(705, 20)
    btn1.set_style_radius(20, lv.PART.MAIN)
    btn1.set_style_bg_color(lv.color_hex(0x0000FF), lv.PART.MAIN)
    btn1.set_style_bg_opa(255, lv.PART.MAIN)  # 不透明背景
    btn1.add_event(btn_clicked_yolo_det, lv.EVENT.CLICKED, None)
    label1 = lv.label(btn1)
    label1.set_style_text_font(font_simsun_16_cjk, 0)
    label1.set_text("YOLOv8")

    # 人脸检测按钮
    btn2 = lv.btn(lv.layer_sys())
    btn2.set_size(90, 45)
    btn2.set_pos(705, 75)
    btn2.set_style_radius(20, lv.PART.MAIN)
    btn2.set_style_bg_color(lv.color_hex(0x0000FF), lv.PART.MAIN)
    btn2.set_style_bg_opa(255, lv.PART.MAIN)  # 不透明背景
    btn2.add_event(btn_clicked_face_det, lv.EVENT.CLICKED, None)
    label2 = lv.label(btn2)
    label2.set_style_text_font(font_simsun_16_cjk, 0)
    label2.set_text("Face")

    lv.scr_load(scr)

media_init()
lvgl_init()
user_gui_init()
try:
    while True:
        time.sleep_ms(lv.task_handler())
except BaseException as e:
    import sys
    sys.print_exception(e)
    cur_state=0
    time.sleep_ms(100)
lvgl_deinit()
media_deinit()
gc.collect()
