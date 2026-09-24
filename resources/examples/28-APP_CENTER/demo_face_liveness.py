from model_cleanup import deinit_with_retry
# demo_face_liveness.py - Face liveness detection (real vs spoof)

import gc
import image
import ulab.numpy as np
import nncase_runtime as nn
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


class _FaceLivenessModel(AIBase):
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

    def config_preprocess(self, box, input_size=None):
        s = input_size if input_size else self.rgb888p_size
        crop_w = int(box[2]) + 224
        crop_h = int(box[3]) + 192
        crop_x = int(box[0]) - crop_w // 2
        crop_y = int(box[1]) - crop_h // 2
        crop_x = max(0, crop_x)
        crop_y = max(0, crop_y)
        if crop_x + crop_w > s[0]:
            crop_w = s[0] - crop_x
        if crop_y + crop_h > s[1]:
            crop_h = s[1] - crop_y
        if crop_w <= 0 or crop_h <= 0:
            crop_w, crop_h = s[0], s[1]
        self.ai2d.crop(crop_x, crop_y, crop_w, crop_h)
        self.ai2d.resize(nn.interp_method.tf_bilinear,
                         nn.interp_mode.half_pixel)
        top, bottom, left, right, _ = letterbox_pad_param(
            [crop_w, crop_h], self.model_input_size)
        self.ai2d.pad([0, 0, 0, 0, top, bottom, left, right], 0,
                      [128, 128, 128])
        self.ai2d.build([1, 3, s[1], s[0]],
                        [1, 3, self.model_input_size[1], self.model_input_size[0]])

    def postprocess(self, results):
        return results[0][0]


class FaceLivenessDemo(Application):
    name = "活体检测"
    model_path = demo_common.FACE_DET_KMODEL
    rgb_size = [1280, 720]
    required_files = [
        demo_common.FACE_ANCHOR_FILE,
        config.KMODEL_DIR + "face_liveness_rgb.kmodel",
    ]

    SENSOR_ID = 2
    SENSOR_FPS = 60
    DISPLAY_CHANNEL = CAM_CHN_ID_0
    AI_CHANNEL = CAM_CHN_ID_2
    DISPLAY_FORMAT = Sensor.YUV420SP
    AI_FORMAT = Sensor.RGBP888
    VIDEO_LAYER = Display.LAYER_VIDEO1

    def __init__(self, liveness_threshold=0.5):
        self.rgb_size = [ALIGN_UP(self.rgb_size[0], 16), self.rgb_size[1]]
        self.display_size = [ALIGN_UP(config.CAM_WIN_W, 16), config.CAM_WIN_H]
        Application.__init__(self)
        self.sensor = None
        self._osd_img = None
        self._ai_img = None
        self._video_bound = False
        self.liveness_threshold = liveness_threshold
        # looser thresholds to catch more faces before classifying
        # Roll back partially-created sub-models on failure: a create() error
        # means runner never calls close(), so any KPU/AI2D already allocated
        # here must be released before re-raising.
        self.face_det = None
        self.face_live = None
        try:
            self.face_det = demo_common.FaceDetSubModel(
                self.rgb_size, self.display_size,
                conf_thr=0.25, nms_thr=0.3)
            self.face_det.config_preprocess()
            self.face_live = _FaceLivenessModel(
                config.KMODEL_DIR + "face_liveness_rgb.kmodel",
                [112, 112], self.rgb_size, self.display_size)
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
                print("FaceLivenessDemo: video layer disable failed:", e)
            self._video_bound = False
        if sensor is not None:
            try:
                sensor.stop()
            except Exception as e:
                print("FaceLivenessDemo: sensor stop failed:", e)

    def _release_owned_resources(self):
        self._osd_img = None

    def run(self, input_np):
        det_boxes = self.face_det.run(input_np)
        live_res = []
        for box in det_boxes:
            self.face_live.config_preprocess(box)
            scores = self.face_live.run(input_np)
            if scores[1] > self.liveness_threshold:
                live_res.append(True)
            else:
                live_res.append(False)
        return det_boxes, live_res

    def draw_result(self, img, result):
        dets, live_res = result
        count = len(dets) if dets else 0
        if dets:
            for i, det in enumerate(dets):
                x1, y1, w, h = map(lambda v: int(round(v, 0)), det[:4])
                x1 = x1 * self.display_size[0] // self.rgb_size[0]
                y1 = y1 * self.display_size[1] // self.rgb_size[1]
                w  = w  * self.display_size[0] // self.rgb_size[0]
                h  = h  * self.display_size[1] // self.rgb_size[1]
                label = "live" if live_res[i] else "spoof"
                color = visual.GREEN if live_res[i] else visual.RED
                visual.draw_detection(
                    img, x1, y1, int(w), int(h),
                    label=label.upper(), color=color, font_size=22)
        return count

    def deinit(self):
        for model in (self.face_det, self.face_live):
            if model is None:
                continue
            try:
                deinit_with_retry(model)
            except Exception as e:
                print("FaceLivenessDemo: model deinit failed:", e)
        gc.collect()
