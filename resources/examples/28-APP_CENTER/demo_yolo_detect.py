# demo_yolo_detect.py - YOLOv8 object detection demo

import nncase_runtime as nn
import ulab.numpy as np
import image
import aidemo
import config
import app_visual as visual
import demo_common
from media.sensor import *
from media.display import Display
from media.media import ALIGN_UP
from app_contract import Application
from libs.AIBase import AIBase
from libs.AI2D import Ai2d
from libs.Utils import *


class YOLODetectionDemo(Application, AIBase):
    name = "物体检测"
    model_path = config.KMODEL_DIR + "yolov8n_224.kmodel"
    model_size = [224, 224]
    # The AI channel already matches the model.  Avoid capturing 640x480 and
    # resizing it back to 224x224 on every frame.
    rgb_size   = [224, 224]

    SENSOR_ID = 2
    SENSOR_FPS = 60
    DISPLAY_CHANNEL = CAM_CHN_ID_0
    AI_CHANNEL = CAM_CHN_ID_2
    DISPLAY_FORMAT = Sensor.YUV420SP
    AI_FORMAT = Sensor.RGBP888
    VIDEO_LAYER = Display.LAYER_VIDEO1

    LABELS = demo_common.COCO_LABELS

    def __init__(self):
        try:
            self.rgb_size = [ALIGN_UP(self.rgb_size[0], 16), self.rgb_size[1]]
            self.display_size = [ALIGN_UP(config.CAM_WIN_W, 16), config.CAM_WIN_H]
            Application.__init__(self)
            AIBase.__init__(self, self.model_path, self.model_size,
                            self.rgb_size, 0)
            self.ai2d = Ai2d(0)
            self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT,
                                     nn.ai2d_format.NCHW_FMT,
                                     np.uint8, np.uint8)
            self.sensor = None
            self._ai_img = None
            self._osd_img = None
            self._video_bound = False
            self.confidence_threshold = 0.3
            self.nms_threshold = 0.4
            self.max_boxes = 30
            self.colors = get_colors(len(self.LABELS))
        except BaseException:
            # The caller cannot own this model until construction returns.
            try:
                self.deinit()
            except Exception as error:
                print("model constructor cleanup failed:", error)
            raise

    def open(self):
        if self._opened or self.stop_req:
            return
        sensor = Sensor(id=self.SENSOR_ID)
        self.sensor = sensor
        sensor.reset()
        sensor.set_framesize(w=self.display_size[0], h=self.display_size[1],
                             chn=self.DISPLAY_CHANNEL)
        sensor.set_pixformat(self.DISPLAY_FORMAT, chn=self.DISPLAY_CHANNEL)
        sensor.set_framesize(w=self.rgb_size[0], h=self.rgb_size[1],
                             chn=self.AI_CHANNEL)
        sensor.set_pixformat(self.AI_FORMAT, chn=self.AI_CHANNEL)
        Display.bind_layer(**sensor.bind_info(
            x=config.CAM_WIN_X, y=config.CAM_WIN_Y,
            chn=self.DISPLAY_CHANNEL), layer=self.VIDEO_LAYER)
        self._video_bound = True
        sensor.run()
        self._osd_img = image.Image(self.display_size[0],
                                    self.display_size[1], image.ARGB8888)
        self.config_preprocess()
        if self.stop_req:
            return
        self.start()
        self._opened = True

    def run_once(self):
        self._ai_img = self.sensor.snapshot(chn=self.AI_CHANNEL)
        result = AIBase.run(self, self._ai_img.to_numpy_ref())
        self._osd_img.clear()
        count = self.draw_result(self._osd_img, result)
        self.display.show(self._osd_img)
        return count if count else 0

    def stop(self):
        Application.stop(self)
        sensor = self.sensor
        self.sensor = None
        self._ai_img = None
        if self.display is not None:
            self.display.clear()
        if self._video_bound:
            try:
                Display.disable_layer(self.VIDEO_LAYER)
            except Exception as e:
                print("YOLODetectionDemo: video layer disable failed:", e)
            self._video_bound = False
        if sensor is not None:
            try:
                sensor.stop()
            except Exception as e:
                print("YOLODetectionDemo: sensor stop failed:", e)

    def _release_owned_resources(self):
        self._osd_img = None

    def config_preprocess(self, input_size=None):
        ai_input = input_size if input_size else self.rgb_size
        top, bottom, left, right, self.scale = letterbox_pad_param(self.rgb_size, self.model_size)
        self.ai2d.pad([0, 0, 0, 0, top, bottom, left, right], 0, [128, 128, 128])
        self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
        self.ai2d.build([1, 3, ai_input[1], ai_input[0]],
                        [1, 3, self.model_size[1], self.model_size[0]])

    def preprocess(self, input_np):
        # Sensor output already has the model's NCHW size and format.
        return [nn.from_numpy(input_np)]

    def postprocess(self, results):
        new_result = results[0][0].transpose()
        det_res = aidemo.yolov8_det_postprocess(
            new_result.copy(),
            [self.rgb_size[1], self.rgb_size[0]],
            [self.model_size[1], self.model_size[0]],
            [self.display_size[1], self.display_size[0]],
            len(self.LABELS), self.confidence_threshold,
            self.nms_threshold, self.max_boxes
        )
        return det_res

    def draw_result(self, img, dets):
        count = 0
        if dets and len(dets) >= 3 and dets[0]:
            for i in range(len(dets[0])):
                x, y, w, h = map(lambda v: int(round(v, 0)), dets[0][i])
                cls_id = int(dets[1][i])
                conf   = round(dets[2][i], 2)
                color  = self.colors[cls_id % len(self.colors)]
                visual.draw_detection(
                    img, x, y, w, h, label=self.LABELS[cls_id],
                    score=conf, color=color)
                count += 1
        return count
