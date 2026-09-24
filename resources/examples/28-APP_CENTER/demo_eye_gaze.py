from model_cleanup import deinit_with_retry
# demo_eye_gaze.py - Eye gaze estimation (face detection + gaze direction arrow)

import gc
import math
import image
import ulab.numpy as np
import nncase_runtime as nn
import aidemo
import config
import app_visual as visual
import demo_common
from media.sensor import *
from media.display import Display
from app_contract import Application
from libs.AIBase import AIBase
from libs.AI2D import Ai2d
from media.media import ALIGN_UP
from libs.Utils import *


class _EyeGazeModel(AIBase):
    def __init__(self, kmodel_path, model_input_size, rgb_size, disp_size):
        try:
            super().__init__(kmodel_path, model_input_size, rgb_size, 0)
            self.model_input_size = model_input_size
            self.rgb888p_size = [ALIGN_UP(rgb_size[0], 16), rgb_size[1]]
            self.display_size = [ALIGN_UP(disp_size[0], 16), disp_size[1]]
            self.ai2d = Ai2d(0)
            self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT,
                                     nn.ai2d_format.NCHW_FMT,
                                     np.uint8, np.uint8)
        except BaseException:
            # The caller cannot own this model until construction returns.
            try:
                self.deinit()
            except Exception as error:
                print("model constructor cleanup failed:", error)
            raise

    def config_preprocess(self, det, input_size=None):
        s = input_size if input_size else self.rgb888p_size
        x, y, w, h = map(lambda v: int(round(v, 0)), det[:4])
        if w <= 0 or h <= 0:
            x, y, w, h = 0, 0, s[0], s[1]
        self.ai2d.crop(x, y, w, h)
        self.ai2d.resize(nn.interp_method.tf_bilinear,
                         nn.interp_mode.half_pixel)
        self.ai2d.build([1, 3, s[1], s[0]],
                        [1, 3, self.model_input_size[1], self.model_input_size[0]])

    def postprocess(self, results):
        pitch, yaw = aidemo.eye_gaze_post_process(results)
        return pitch, yaw


class EyeGazeDemo(Application):
    name = "视线估计"
    model_path = demo_common.FACE_DET_KMODEL
    rgb_size = [1280, 720]
    required_files = [
        demo_common.FACE_ANCHOR_FILE,
        config.KMODEL_DIR + "eye_gaze.kmodel",
    ]

    SENSOR_ID = 2
    SENSOR_FPS = 60
    DISPLAY_CHANNEL = CAM_CHN_ID_0
    AI_CHANNEL = CAM_CHN_ID_2
    DISPLAY_FORMAT = Sensor.YUV420SP
    AI_FORMAT = Sensor.RGBP888
    VIDEO_LAYER = Display.LAYER_VIDEO1

    def __init__(self):
        self.rgb_size = [ALIGN_UP(self.rgb_size[0], 16), self.rgb_size[1]]
        self.display_size = [ALIGN_UP(config.CAM_WIN_W, 16), config.CAM_WIN_H]
        Application.__init__(self)
        self.sensor = None
        self._osd_img = None
        self._ai_img = None
        self._video_bound = False
        # Roll back partially-created sub-models on failure: a create() error
        # means runner never calls close(), so any KPU/AI2D already allocated
        # here must be released before re-raising.
        self.face_det = None
        self.eye_gaze = None
        try:
            self.face_det = demo_common.FaceDetSubModel(
                self.rgb_size, self.display_size,
                conf_thr=0.5, nms_thr=0.2)
            self.face_det.config_preprocess()
            self.eye_gaze = _EyeGazeModel(
                config.KMODEL_DIR + "eye_gaze.kmodel",
                [448, 448], self.rgb_size, self.display_size)
        except Exception:
            self.deinit()
            raise

    def open(self):
        if self._opened or self.stop_req:
            return
        sensor = Sensor(id=self.SENSOR_ID)
        self.sensor = sensor
        sensor.reset()
        sensor.set_framesize(w=self.display_size[0], h=self.display_size[1], chn=self.DISPLAY_CHANNEL)
        sensor.set_pixformat(self.DISPLAY_FORMAT, chn=self.DISPLAY_CHANNEL)
        sensor.set_framesize(w=self.rgb_size[0], h=self.rgb_size[1], chn=self.AI_CHANNEL)
        sensor.set_pixformat(self.AI_FORMAT, chn=self.AI_CHANNEL)
        Display.bind_layer(**sensor.bind_info(
            x=config.CAM_WIN_X, y=config.CAM_WIN_Y,
            chn=self.DISPLAY_CHANNEL), layer=self.VIDEO_LAYER)
        self._video_bound = True
        sensor.run()
        self._osd_img = image.Image(
            self.display_size[0], self.display_size[1], image.ARGB8888)
        if self.stop_req:
            return
        self.start()
        self._opened = True

    def run_once(self):
        self._ai_img = self.sensor.snapshot(chn=self.AI_CHANNEL)
        result = self.run(self._ai_img.to_numpy_ref())
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
                print("EyeGazeDemo: video layer disable failed:", e)
            self._video_bound = False
        if sensor is not None:
            try:
                sensor.stop()
            except Exception as e:
                print("EyeGazeDemo: sensor stop failed:", e)

    def _release_owned_resources(self):
        self._osd_img = None

    def run(self, input_np):
        det_boxes = self.face_det.run(input_np)
        gaze_res = []
        for det_box in det_boxes:
            self.eye_gaze.config_preprocess(det_box)
            pitch, yaw = self.eye_gaze.run(input_np)
            gaze_res.append((pitch, yaw))
        return det_boxes, gaze_res

    def draw_result(self, img, result):
        dets, gaze_res = result
        count = len(dets) if dets else 0
        if not dets:
            return 0
        length_R = self.display_size[0] / 2
        for det, (pitch, yaw) in zip(dets, gaze_res):
            x, y, w, h = map(lambda v: int(round(v, 0)), det[:4])
            x = x * self.display_size[0] // self.rgb_size[0]
            y = y * self.display_size[1] // self.rgb_size[1]
            w = w * self.display_size[0] // self.rgb_size[0]
            h = h * self.display_size[1] // self.rgb_size[1]

            visual.draw_detection(img, x, y, int(w), int(h),
                                  label="GAZE", color=visual.CYAN)

            cx = x + w / 2.0
            cy = y + h / 2.0
            dx = -length_R * math.sin(pitch) * math.cos(yaw)
            dy = -length_R * math.sin(yaw)
            tx = int(cx + dx)
            ty = int(cy + dy)
            visual.draw_arrow(img, cx, cy, tx, ty,
                              color=visual.ORANGE, size=26, thickness=4)

        return count

    def deinit(self):
        for model in (self.face_det, self.eye_gaze):
            if model is None:
                continue
            try:
                deinit_with_retry(model)
            except Exception as e:
                print("EyeGazeDemo: model deinit failed:", e)
        gc.collect()
