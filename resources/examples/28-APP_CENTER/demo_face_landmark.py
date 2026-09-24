from model_cleanup import deinit_with_retry
# demo_face_landmark.py - Face landmark demo (106-point)

import gc
import ulab.numpy as np
import nncase_runtime as nn
import image
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


class _FaceLandmarkModel(AIBase):
    def __init__(self, kmodel_path, model_input_size, rgb_size, disp_size):
        try:
            super().__init__(kmodel_path, model_input_size, rgb_size, 0)
            self.model_input_size = model_input_size
            self.rgb888p_size = [ALIGN_UP(rgb_size[0], 16), rgb_size[1]]
            self.display_size = [ALIGN_UP(disp_size[0], 16), disp_size[1]]
            self.matrix_dst = None
            self.ai2d = Ai2d(0)
            self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT, nn.ai2d_format.NCHW_FMT, np.uint8, np.uint8)
        except BaseException:
            # The caller cannot own this model until construction returns.
            try:
                self.deinit()
            except Exception as error:
                print("model constructor cleanup failed:", error)
            raise

    def get_affine_matrix(self, bbox):
        x1, y1, w, h = map(lambda v: int(round(v, 0)), bbox[:4])
        scale_ratio = self.model_input_size[0] / (max(w, h) * 1.5)
        cx = (x1 + w / 2) * scale_ratio
        cy = (y1 + h / 2) * scale_ratio
        half = self.model_input_size[0] / 2
        m = np.zeros((2, 3), dtype=np.float)
        m[0, 0] = scale_ratio; m[0, 1] = 0; m[0, 2] = half - cx
        m[1, 0] = 0; m[1, 1] = scale_ratio; m[1, 2] = half - cy
        return m

    def config_preprocess(self, det, input_size=None):
        s = input_size if input_size else self.rgb888p_size
        self.matrix_dst = self.get_affine_matrix(det)
        am = [self.matrix_dst[0][0], self.matrix_dst[0][1], self.matrix_dst[0][2],
              self.matrix_dst[1][0], self.matrix_dst[1][1], self.matrix_dst[1][2]]
        self.ai2d.affine(nn.interp_method.cv2_bilinear, 0, 0, 127, 1, am)
        self.ai2d.build([1, 3, s[1], s[0]], [1, 3, self.model_input_size[1], self.model_input_size[0]])

    def postprocess(self, results):
        pred = results[0].flatten()
        half = self.model_input_size[0] // 2
        for i in range(len(pred)):
            pred[i] += (pred[i] + 1) * half
        inv = aidemo.invert_affine_transform(self.matrix_dst).flatten()
        n = len(pred) // 2
        for k in range(n):
            ox, oy = pred[k * 2], pred[k * 2 + 1]
            pred[k * 2]     = ox * inv[0] + oy * inv[1] + inv[2]
            pred[k * 2 + 1] = ox * inv[3] + oy * inv[4] + inv[5]
        return pred


class FaceLandmarkDemo(Application):
    name = "人脸关键点"
    model_path = demo_common.FACE_DET_KMODEL
    rgb_size = [1280, 720]
    required_files = [
        demo_common.FACE_ANCHOR_FILE,
        config.KMODEL_DIR + "face_landmark.kmodel",
    ]

    SENSOR_ID = 2
    SENSOR_FPS = 60
    DISPLAY_CHANNEL = CAM_CHN_ID_0
    AI_CHANNEL = CAM_CHN_ID_2
    DISPLAY_FORMAT = Sensor.YUV420SP
    AI_FORMAT = Sensor.RGBP888
    VIDEO_LAYER = Display.LAYER_VIDEO1

    DICT_KP_SEQ = [
        [43, 44, 45, 47, 46, 50, 51, 49, 48],
        [97, 98, 99, 100, 101, 105, 104, 103, 102],
        [35, 36, 33, 37, 39, 42, 40, 41],
        [89, 90, 87, 91, 93, 96, 94, 95],
        [34, 88],
        [72, 73, 74, 86],
        [77, 78, 79, 80, 85, 84, 83],
        [52, 55, 56, 53, 59, 58, 61, 68, 67, 71, 63, 64],
        [65, 54, 60, 57, 69, 70, 62, 66],
        [1, 9, 10, 11, 12, 13, 14, 15, 16, 2, 3, 4, 5, 6, 7, 8, 0, 24, 23, 22, 21, 20, 19, 18, 32, 31, 30, 29, 28, 27, 26, 25, 17]
    ]
    COLOR_LIST = [
        (255, 0, 255, 0), (255, 0, 255, 0), (255, 255, 0, 255), (255, 255, 0, 255),
        (255, 255, 0, 0), (255, 255, 170, 0), (255, 255, 255, 0), (255, 0, 255, 255),
        (255, 255, 220, 50), (255, 30, 30, 255)
    ]

    def __init__(self):
        self.rgb_size = [ALIGN_UP(self.rgb_size[0], 16), self.rgb_size[1]]
        self.display_size = [ALIGN_UP(config.CAM_WIN_W, 16), config.CAM_WIN_H]
        Application.__init__(self)
        self.sensor = None
        self._ai_img = None
        self._osd_img = None
        self._video_bound = False
        # Roll back partially-created sub-models on failure: a create() error
        # means runner never calls close(), so any KPU/AI2D already allocated
        # here must be released before re-raising.
        self.face_det = None
        self.face_landmark = None
        try:
            self.face_det = demo_common.FaceDetSubModel(self.rgb_size,
                                                        self.display_size)
            self.face_det.config_preprocess()
            self.face_landmark = _FaceLandmarkModel(
                config.KMODEL_DIR + "face_landmark.kmodel", [192, 192],
                self.rgb_size, self.display_size)
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
        self._osd_img = image.Image(self.display_size[0], self.display_size[1], image.ARGB8888)
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
                print("FaceLandmarkDemo: video layer disable failed:", e)
            self._video_bound = False
        if sensor is not None:
            try:
                sensor.stop()
            except Exception as e:
                print("FaceLandmarkDemo: sensor stop failed:", e)

    def _release_owned_resources(self):
        self._osd_img = None

    def run(self, input_np):
        det_boxes = self.face_det.run(input_np)
        landmark_res = []
        for det_box in det_boxes:
            self.face_landmark.config_preprocess(det_box)
            res = self.face_landmark.run(input_np)
            landmark_res.append(res)
        return det_boxes, landmark_res

    def draw_result(self, img, result):
        dets, landmark_res = result
        count = len(dets) if dets else 0
        if landmark_res:
            osd_np = img.to_numpy_ref()
            for pred in landmark_res:
                for sub_idx in range(len(self.DICT_KP_SEQ)):
                    sub_part = self.DICT_KP_SEQ[sub_idx]
                    pts = []
                    for kp_idx in range(len(sub_part)):
                        real = sub_part[kp_idx]
                        x = int(pred[real * 2] * self.display_size[0] // self.rgb_size[0])
                        y = int(pred[real * 2 + 1] * self.display_size[1] // self.rgb_size[1])
                        pts.append((x, y))
                    if sub_idx in (9, 6):
                        color = np.array(self.COLOR_LIST[sub_idx], dtype=np.uint8)
                        aidemo.polylines(osd_np, np.array(pts), False, color, 5, 8, 0)
                    elif sub_idx == 4:
                        for px, py in pts:
                            visual.draw_keypoint(
                                img, px, py, self.COLOR_LIST[sub_idx],
                                radius=2)
                    else:
                        color = np.array(self.COLOR_LIST[sub_idx], dtype=np.uint8)
                        aidemo.contours(osd_np, np.array(pts), -1, color, 2, 8)
            visual.draw_mode_badge(img, "106 LANDMARKS", visual.CYAN)
        return count

    def deinit(self):
        for model in (self.face_det, self.face_landmark):
            if model is None:
                continue
            try:
                deinit_with_retry(model)
            except Exception as e:
                print("FaceLandmarkDemo: model deinit failed:", e)
        gc.collect()
