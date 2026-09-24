# demo_yolo_license_plate.py - YOLO-pose license plate detection demo

import nncase_runtime as nn
import ulab.numpy as np
import image
import aidemo
import config
import i18n
import app_visual as visual
import demo_common
from media.sensor import *
from media.display import Display
from media.media import ALIGN_UP
from app_contract import Application
from libs.AIBase import AIBase
from libs.AI2D import Ai2d
from libs.Utils import *


class YoloLicenceDetectionDemo(Application, AIBase):
    """Independent four-keypoint plate detector based on 05-AI-Demo."""

    name = "YOLO车牌检测"
    model_path = config.KMODEL_DIR + "yolo_license_plate_det.kmodel"
    model_size = [640, 640]
    rgb_size = [640, 360]

    CONFIDENCE_THRESHOLD = 0.25
    NMS_THRESHOLD = 0.45
    MAX_BOXES = 10

    # This Sensor profile belongs only to this application. SENSOR_FPS is kept
    # as an editable hint and is intentionally not passed to Sensor().
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
            self.display_size = [ALIGN_UP(config.CAM_WIN_W, 16),
                                 config.CAM_WIN_H]
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
            # Resolve the display label once, not once per detection/frame.
            self._plate_label = "车牌" if i18n.is_chinese() else "PLATE"
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
        sensor.set_framesize(w=self.display_size[0],
                             h=self.display_size[1],
                             chn=self.DISPLAY_CHANNEL)
        sensor.set_pixformat(self.DISPLAY_FORMAT,
                             chn=self.DISPLAY_CHANNEL)
        sensor.set_framesize(w=self.rgb_size[0], h=self.rgb_size[1],
                             chn=self.AI_CHANNEL)
        sensor.set_pixformat(self.AI_FORMAT, chn=self.AI_CHANNEL)
        Display.bind_layer(**sensor.bind_info(
            x=config.CAM_WIN_X, y=config.CAM_WIN_Y,
            chn=self.DISPLAY_CHANNEL), layer=self.VIDEO_LAYER)
        self._video_bound = True
        sensor.run()

        self._osd_img = image.Image(self.display_size[0],
                                    self.display_size[1],
                                    image.ARGB8888)
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
        return count

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
            except Exception as error:
                print("YoloLicenceDetectionDemo: video disable failed:",
                      error)
            self._video_bound = False
        if sensor is not None:
            try:
                sensor.stop()
            except Exception as error:
                print("YoloLicenceDetectionDemo: sensor stop failed:",
                      error)

    def _release_owned_resources(self):
        self._osd_img = None

    def config_preprocess(self, input_size=None):
        ai_input = input_size if input_size else self.rgb_size
        top, bottom, left, right, _ = letterbox_pad_param(
            self.rgb_size, self.model_size)
        self.ai2d.pad([0, 0, 0, 0, top, bottom, left, right],
                      0, [128, 128, 128])
        self.ai2d.resize(nn.interp_method.tf_bilinear,
                         nn.interp_mode.half_pixel)
        self.ai2d.build([1, 3, ai_input[1], ai_input[0]],
                        [1, 3, self.model_size[1], self.model_size[0]])

    def postprocess(self, results):
        new_result = results[0][0].transpose()
        return aidemo.yolo_license_plate_det_postprocess(
            new_result.copy(),
            [self.rgb_size[1], self.rgb_size[0]],
            [self.model_size[1], self.model_size[0]],
            [self.display_size[1], self.display_size[0]],
            self.CONFIDENCE_THRESHOLD, self.NMS_THRESHOLD,
            self.MAX_BOXES)

    def draw_result(self, img, dets):
        if not dets or dets[0] is None:
            return 0
        keypoints = dets[0]
        boxes = dets[1]
        scores = dets[2]
        count = len(keypoints)

        for index in range(count):
            source_points = keypoints[index]
            points = []
            for point_index in range(4):
                px = source_points[point_index * 2] * \
                    self.display_size[0] / self.rgb_size[0]
                py = source_points[point_index * 2 + 1] * \
                    self.display_size[1] / self.rgb_size[1]
                points.append((int(round(px, 0)), int(round(py, 0))))

            source_box = boxes[index]
            x = int(round(source_box[0] * self.display_size[0] /
                          self.rgb_size[0], 0))
            y = int(round(source_box[1] * self.display_size[1] /
                          self.rgb_size[1], 0))
            w = int(round(source_box[2] * self.display_size[0] /
                          self.rgb_size[0], 0))
            h = int(round(source_box[3] * self.display_size[1] /
                          self.rgb_size[1], 0))
            score = scores[index] if index < len(scores) else None

            visual.draw_detection(
                img, x, y, w, h, label=self._plate_label, score=score,
                color=visual.BLUE, font=demo_common.CJK_FONT)
            visual.draw_polygon(img, points, color=visual.ORANGE)
        return count
