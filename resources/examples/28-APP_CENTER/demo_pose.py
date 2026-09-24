# demos_pose.py - Person pose estimation demo

import nncase_runtime as nn
import ulab.numpy as np
import image
import aidemo
import config
import app_visual as visual
from media.sensor import *
from media.display import Display
from media.media import ALIGN_UP
from app_contract import Application
from libs.AIBase import AIBase
from libs.AI2D import Ai2d
from libs.Utils import *


class PoseEstimationDemo(Application, AIBase):
    name = "姿态估计"
    model_path = config.KMODEL_DIR + "yolov8n-pose.kmodel"
    model_size = [320, 320]
    rgb_size   = [320, 320]

    SENSOR_ID = 2
    SENSOR_FPS = 60
    DISPLAY_CHANNEL = CAM_CHN_ID_0
    AI_CHANNEL = CAM_CHN_ID_2
    DISPLAY_FORMAT = Sensor.YUV420SP
    AI_FORMAT = Sensor.RGBP888
    VIDEO_LAYER = Display.LAYER_VIDEO1

    SKELETON = [
        (16, 14), (14, 12), (17, 15), (15, 13), (12, 13),
        (6, 12), (7, 13), (6, 7), (6, 8), (7, 9),
        (8, 10), (9, 11), (2, 3), (1, 2), (1, 3),
        (2, 4), (3, 5), (4, 6), (5, 7)
    ]
    LIMB_COLORS = [
        (255, 51, 153, 255), (255, 51, 153, 255), (255, 51, 153, 255),
        (255, 51, 153, 255), (255, 255, 51, 255), (255, 255, 51, 255),
        (255, 255, 51, 255), (255, 255, 128, 0), (255, 255, 128, 0),
        (255, 255, 128, 0), (255, 255, 128, 0), (255, 255, 128, 0),
        (255, 0, 255, 0), (255, 0, 255, 0), (255, 0, 255, 0),
        (255, 0, 255, 0), (255, 0, 255, 0), (255, 0, 255, 0),
        (255, 0, 255, 0)
    ]
    KP_COLORS = [
        (255, 0, 255, 0), (255, 0, 255, 0), (255, 0, 255, 0),
        (255, 0, 255, 0), (255, 0, 255, 0), (255, 255, 128, 0),
        (255, 255, 128, 0), (255, 255, 128, 0), (255, 255, 128, 0),
        (255, 255, 128, 0), (255, 255, 128, 0), (255, 51, 153, 255),
        (255, 51, 153, 255), (255, 51, 153, 255), (255, 51, 153, 255),
        (255, 51, 153, 255), (255, 51, 153, 255)
    ]

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
            self.confidence_threshold = 0.2
            self.nms_threshold = 0.5
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
                print("PoseEstimationDemo: video layer disable failed:", e)
            self._video_bound = False
        if sensor is not None:
            try:
                sensor.stop()
            except Exception as e:
                print("PoseEstimationDemo: sensor stop failed:", e)

    def _release_owned_resources(self):
        self._osd_img = None

    def config_preprocess(self, input_size=None):
        ai_input = input_size if input_size else self.rgb_size
        top, bottom, left, right, _ = center_pad_param(self.rgb_size,
                                                       self.model_size)
        self.ai2d.pad([0, 0, 0, 0, top, bottom, left, right], 0, [0, 0, 0])
        self.ai2d.resize(nn.interp_method.tf_bilinear,
                         nn.interp_mode.half_pixel)
        self.ai2d.build([1, 3, ai_input[1], ai_input[0]],
                        [1, 3, self.model_size[1], self.model_size[0]])

    def preprocess(self, input_np):
        return [nn.from_numpy(input_np)]

    def postprocess(self, results):
        return aidemo.person_kp_postprocess(
            results[0], [self.rgb_size[1], self.rgb_size[0]],
            self.model_size, self.confidence_threshold, self.nms_threshold
        )

    def draw_result(self, img, res):
        count = 0
        if not res or not res[0]:
            return 0
        kpses = res[1]
        for i in range(len(res[0])):
            for k in range(17 + 2):
                if k < 17:
                    kps_x = round(kpses[i][k][0])
                    kps_y = round(kpses[i][k][1])
                    kps_s = kpses[i][k][2]
                    x1 = int(float(kps_x) * self.display_size[0] // self.rgb_size[0])
                    y1 = int(float(kps_y) * self.display_size[1] // self.rgb_size[1])
                    if kps_s > 0:
                        visual.draw_keypoint(img, x1, y1,
                                             self.KP_COLORS[k], radius=4)
                ske = self.SKELETON[k]
                pos1_x = round(kpses[i][ske[0] - 1][0])
                pos1_y = round(kpses[i][ske[0] - 1][1])
                pos1_s = kpses[i][ske[0] - 1][2]
                pos2_x = round(kpses[i][ske[1] - 1][0])
                pos2_y = round(kpses[i][ske[1] - 1][1])
                pos2_s = kpses[i][ske[1] - 1][2]
                if pos1_s > 0.0 and pos2_s > 0.0:
                    px1 = int(float(pos1_x) * self.display_size[0] // self.rgb_size[0])
                    py1 = int(float(pos1_y) * self.display_size[1] // self.rgb_size[1])
                    px2 = int(float(pos2_x) * self.display_size[0] // self.rgb_size[0])
                    py2 = int(float(pos2_y) * self.display_size[1] // self.rgb_size[1])
                    visual.draw_skeleton_line(
                        img, px1, py1, px2, py2,
                        self.LIMB_COLORS[k], thickness=3)
            count += 1
        if count:
            visual.draw_mode_badge(img, "POSE TRACKING", visual.CYAN)
        return count
