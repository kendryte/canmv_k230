# demo_face_detect.py - Face detection demo

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


class FaceDetectionDemo(Application, AIBase):
    name = "人脸检测"
    model_path = demo_common.FACE_DET_KMODEL
    model_size = [320, 320]
    rgb_size   = [640, 360]
    required_files = [demo_common.FACE_ANCHOR_FILE]

    SENSOR_ID = 2
    SENSOR_FPS = 60
    DISPLAY_CHANNEL = CAM_CHN_ID_0
    AI_CHANNEL = CAM_CHN_ID_2
    DISPLAY_FORMAT = Sensor.YUV420SP
    AI_FORMAT = Sensor.RGBP888
    VIDEO_LAYER = Display.LAYER_VIDEO1

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
            self.confidence_threshold = 0.5
            self.nms_threshold = 0.2
            self.anchors = demo_common.load_face_anchors()
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
                print("FaceDetectionDemo: video layer disable failed:", e)
            self._video_bound = False
        if sensor is not None:
            try:
                sensor.stop()
            except Exception as e:
                print("FaceDetectionDemo: sensor stop failed:", e)

    def _release_owned_resources(self):
        self._osd_img = None

    def config_preprocess(self, input_size=None):
        ai_input = input_size if input_size else self.rgb_size
        top, bottom, left, right, _ = letterbox_pad_param(self.rgb_size, self.model_size)
        self.ai2d.pad([0, 0, 0, 0, top, bottom, left, right], 0, [104, 117, 123])
        self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
        self.ai2d.build([1, 3, ai_input[1], ai_input[0]],
                        [1, 3, self.model_size[1], self.model_size[0]])

    def postprocess(self, results):
        res = aidemo.face_det_post_process(self.confidence_threshold, self.nms_threshold,
                                            self.model_size[0], self.anchors, self.rgb_size, results)
        return res[0] if len(res) else []

    def draw_result(self, img, dets):
        if dets:
            for det in dets:
                x = int(round(det[0])) * self.display_size[0] // self.rgb_size[0]
                y = int(round(det[1])) * self.display_size[1] // self.rgb_size[1]
                w = int(round(det[2])) * self.display_size[0] // self.rgb_size[0]
                h = int(round(det[3])) * self.display_size[1] // self.rgb_size[1]
                visual.draw_detection(img, x, y, w, h,
                                      label="FACE", color=visual.CYAN)
            return len(dets)
        return 0
