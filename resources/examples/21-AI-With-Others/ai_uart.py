"""
Script: ai_uart.py
脚本名称：ai_uart.py

Description:
    This script performs real-time object detection using a YOLOv8 model on an embedded system.
    It captures video frames from a sensor, performs inference, displays detection results,
    and sends labels over UART.

    The model input is resized and padded using Ai2d utilities. Results are post-processed
    with NMS and confidence filtering. The script supports multiple display modes such as HDMI and LCD.

脚本说明：
    本脚本在嵌入式系统上使用 YOLOv8 模型进行实时目标检测。
    它从摄像头获取图像帧，执行模型推理，绘制检测结果，并通过串口发送识别标签。

    使用 Ai2d 工具对模型输入进行缩放和填充，后处理包括 NMS 和置信度过滤。
    支持多种显示模式，如 HDMI 和 LCD。

Author: Canaan Developer
作者：Canaan 开发者
"""

from libs.PipeLine import PipeLine
from libs.AIBase import AIBase
from libs.AI2D import Ai2d
from libs.Utils import *
import os, sys, ujson, gc, math
from media.media import *
import nncase_runtime as nn
import ulab.numpy as np
import image
import aidemo
from machine import UART
from machine import FPIOA
import time

# Custom YOLOv8 object detection class
class ObjectDetectionApp(AIBase):
    def __init__(self, kmodel_path, labels, model_input_size, max_boxes_num, confidence_threshold=0.5, nms_threshold=0.2, rgb888p_size=[224,224], display_size=[1920,1080], debug_mode=0):
        """
        Initialize object detection system.

        Parameters:
        - kmodel_path: Path to YOLOv8 KModel.
        - labels: List of class labels.
        - model_input_size: Model input resolution.
        - max_boxes_num: Max detection results to keep.
        - confidence_threshold: Detection score threshold.
        - nms_threshold: Non-max suppression threshold.
        - rgb888p_size: Camera input size (aligned to 16-width).
        - display_size: Output display size.
        - debug_mode: Enable debug timing logs.
        """
        super().__init__(kmodel_path, model_input_size, rgb888p_size, debug_mode)
        self.kmodel_path = kmodel_path
        self.labels = labels
        self.model_input_size = model_input_size
        self.confidence_threshold = confidence_threshold
        self.nms_threshold = nms_threshold
        self.max_boxes_num = max_boxes_num

        # Align width to multiple of 16 for hardware compatibility
        self.rgb888p_size = [ALIGN_UP(rgb888p_size[0], 16), rgb888p_size[1]]
        self.display_size = [ALIGN_UP(display_size[0], 16), display_size[1]]
        self.debug_mode = debug_mode

        # Predefined colors for each class
        self.color_four = get_colors(len(self.labels))

        # Input scaling factors
        self.x_factor = float(self.rgb888p_size[0]) / self.model_input_size[0]
        self.y_factor = float(self.rgb888p_size[1]) / self.model_input_size[1]

        # Ai2d instance for preprocessing
        self.ai2d = Ai2d(debug_mode)
        self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT, nn.ai2d_format.NCHW_FMT, np.uint8, np.uint8)

        # Configure UART pins using FPIOA
        self.fpioa = FPIOA()
        self.fpioa.set_function(3, self.fpioa.UART1_TXD, ie=1, oe=1)
        self.fpioa.set_function(4, self.fpioa.UART1_RXD, ie=1, oe=1)

        # Initialize UART1
        self.uart = UART(UART.UART1, baudrate=115200, bits=UART.EIGHTBITS, parity=UART.PARITY_NONE, stop=UART.STOPBITS_ONE)

    def config_preprocess(self, input_image_size=None):
        """
        Configure pre-processing: padding and resizing using Ai2d.
        """
        with ScopedTiming("set preprocess config", self.debug_mode > 0):
            ai2d_input_size = input_image_size if input_image_size else self.rgb888p_size
            top, bottom, left, right, self.scale = letterbox_pad_param(self.rgb888p_size, self.model_input_size)
            self.ai2d.pad([0,0,0,0,top,bottom,left,right], 0, [128,128,128])
            self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
            self.ai2d.build(
                [1, 3, ai2d_input_size[1], ai2d_input_size[0]],
                [1, 3, self.model_input_size[1], self.model_input_size[0]]
            )

    def preprocess(self, input_np):
        """
        Prepare numpy image for inference.
        """
        with ScopedTiming("preprocess", self.debug_mode > 0):
            return [nn.from_numpy(input_np)]

    def postprocess(self, results):
        """
        Apply YOLOv8 post-processing including NMS and thresholding.
        """
        with ScopedTiming("postprocess", self.debug_mode > 0):
            new_result = results[0][0].transpose()
            det_res = aidemo.yolov8_det_postprocess(
                new_result.copy(),
                [self.rgb888p_size[1], self.rgb888p_size[0]],
                [self.model_input_size[1], self.model_input_size[0]],
                [self.display_size[1], self.display_size[0]],
                len(self.labels),
                self.confidence_threshold,
                self.nms_threshold,
                self.max_boxes_num
            )
            return det_res

    def draw_result(self, pl, dets):
        """
        Draw detection results and send label info via UART.
        """
        with ScopedTiming("display_draw", self.debug_mode > 0):
            if dets:
                pl.osd_img.clear()
                for i in range(len(dets[0])):
                    x, y, w, h = map(lambda x: int(round(x, 0)), dets[0][i])
                    pl.osd_img.draw_rectangle(x, y, w, h, color=self.color_four[dets[1][i]], thickness=4)
                    pl.osd_img.draw_string_advanced(
                        x, y - 50, 32,
                        " " + self.labels[dets[1][i]] + " " + str(round(dets[2][i], 2)),
                        color=self.color_four[dets[1][i]]
                    )
                    # Send detected label over UART
                    uart_write_res = self.labels[dets[1][i]] + " "
                    self.uart.write(uart_write_res.encode("utf-8"))
            else:
                pl.osd_img.clear()

if __name__ == "__main__":
    # auto按开发板选择默认驱动；可手动覆盖为hdmi/lcd/st7701等模式
    display_mode="auto"
    # None使用SDK默认分辨率；更换屏幕时可指定[640, 480]等尺寸
    display_size=None
    rgb888p_size = [224, 224]
    kmodel_path = "/sdcard/examples/kmodel/yolov8n_224.kmodel"

    # Class labels for COCO dataset
    labels = ["person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
              "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat",
              "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack",
              "umbrella", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball",
              "kite", "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket",
              "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
              "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
              "couch", "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote",
              "keyboard", "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator", "book",
              "clock", "vase", "scissors", "teddy bear", "hair drier", "toothbrush"]

    confidence_threshold = 0.3
    nms_threshold = 0.4
    max_boxes_num = 30

    # Initialize the PipeLine. rgb888p_size is the AI input resolution and display_size is the display resolution
    pl = PipeLine(rgb888p_size=rgb888p_size, display_mode=display_mode, display_size=display_size)
    # Create the PipeLine. Pass sensor_id to select a camera when needed, for example pl.create(sensor_id=2)
    pl.create()
    display_size = pl.get_display_size()

    # Initialize detection app
    ob_det = ObjectDetectionApp(
        kmodel_path,
        labels=labels,
        model_input_size=[224, 224],
        max_boxes_num=max_boxes_num,
        confidence_threshold=confidence_threshold,
        nms_threshold=nms_threshold,
        rgb888p_size=rgb888p_size,
        display_size=display_size,
        debug_mode=0
    )
    ob_det.config_preprocess()

    # Real-time processing loop
    while True:
        with ScopedTiming("total", 1):
            img = pl.get_frame()                         # Capture frame
            res = ob_det.run(img)                        # Run inference
            ob_det.draw_result(pl, res)                  # Draw results
            pl.show_image()                              # Display results
            gc.collect()                                 # Free memory

    ob_det.deinit()
    pl.destroy()
