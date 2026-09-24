from model_cleanup import deinit_with_retry
# demo_hand_keypoint_class.py - Hand keypoint & gesture recognition demo

import gc
import image
import ulab.numpy as np
import nncase_runtime as nn
import aicube
import config
import app_visual as visual
from media.sensor import *
from media.display import Display
from app_contract import Application
from libs.AIBase import AIBase
from libs.AI2D import Ai2d
from media.media import ALIGN_UP
from libs.Utils import *


class _HandDetModel(AIBase):
    def __init__(self, kmodel_path, labels, model_input_size, anchors,
                 conf_thr, nms_thr, strides, rgb_size, disp_size):
        try:
            super().__init__(kmodel_path, model_input_size, rgb_size, 0)
            self.labels = labels
            self.model_input_size = model_input_size
            self.confidence_threshold = conf_thr
            self.nms_threshold = nms_thr
            self.anchors = anchors
            self.strides = strides
            self.rgb888p_size = [ALIGN_UP(rgb_size[0], 16), rgb_size[1]]
            self.display_size = [ALIGN_UP(disp_size[0], 16), disp_size[1]]
            self.ai2d = Ai2d(0)
            self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT, nn.ai2d_format.NCHW_FMT, np.uint8, np.uint8)
        except BaseException:
            # The caller cannot own this model until construction returns.
            try:
                self.deinit()
            except Exception as error:
                print("model constructor cleanup failed:", error)
            raise

    def config_preprocess(self, input_size=None):
        s = input_size if input_size else self.rgb888p_size
        top, bottom, left, right, _ = center_pad_param(self.rgb888p_size, self.model_input_size)
        self.ai2d.pad([0, 0, 0, 0, top, bottom, left, right], 0, [114, 114, 114])
        self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
        self.ai2d.build([1, 3, s[1], s[0]], [1, 3, self.model_input_size[1], self.model_input_size[0]])

    def postprocess(self, results):
        dets = aicube.anchorbasedet_post_process(
            results[0], results[1], results[2], self.model_input_size,
            self.rgb888p_size, self.strides, len(self.labels),
            self.confidence_threshold, self.nms_threshold, self.anchors, False
        )
        return dets


class _HandKPModel(AIBase):
    def __init__(self, kmodel_path, model_input_size, rgb_size, disp_size):
        try:
            super().__init__(kmodel_path, model_input_size, rgb_size, 0)
            self.model_input_size = model_input_size
            self.rgb888p_size = [ALIGN_UP(rgb_size[0], 16), rgb_size[1]]
            self.display_size = [ALIGN_UP(disp_size[0], 16), disp_size[1]]
            self.crop_params = []
            self.ai2d = Ai2d(0)
            self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT, nn.ai2d_format.NCHW_FMT, np.uint8, np.uint8)
        except BaseException:
            # The caller cannot own this model until construction returns.
            try:
                self.deinit()
            except Exception as error:
                print("model constructor cleanup failed:", error)
            raise

    def get_crop_param(self, det_box):
        x1, y1, x2, y2 = det_box[2], det_box[3], det_box[4], det_box[5]
        w, h = int(x2 - x1), int(y2 - y1)
        length = max(w, h) / 2
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        ratio_num = 1.26 * length
        x1_kp = int(max(0, cx - ratio_num))
        y1_kp = int(max(0, cy - ratio_num))
        x2_kp = int(min(self.rgb888p_size[0] - 1, cx + ratio_num))
        y2_kp = int(min(self.rgb888p_size[1] - 1, cy + ratio_num))
        w_kp = int(x2_kp - x1_kp + 1)
        h_kp = int(y2_kp - y1_kp + 1)
        return [x1_kp, y1_kp, w_kp, h_kp]

    def config_preprocess(self, det, input_size=None):
        s = input_size if input_size else self.rgb888p_size
        self.crop_params = self.get_crop_param(det)
        self.ai2d.crop(self.crop_params[0], self.crop_params[1],
                       self.crop_params[2], self.crop_params[3])
        self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
        self.ai2d.build([1, 3, s[1], s[0]], [1, 3, self.model_input_size[1], self.model_input_size[0]])

    def postprocess(self, results):
        r = results[0].reshape(results[0].shape[0] * results[0].shape[1])
        results_show = np.zeros(r.shape, dtype=np.int16)
        results_show[0::2] = r[0::2] * self.crop_params[2] + self.crop_params[0]
        results_show[1::2] = r[1::2] * self.crop_params[3] + self.crop_params[1]
        gesture = self._classify_gesture(results_show)
        results_show[0::2] = results_show[0::2] * (self.display_size[0] / self.rgb888p_size[0])
        results_show[1::2] = results_show[1::2] * (self.display_size[1] / self.rgb888p_size[1])
        return results_show, gesture

    def _vector_angle(self, v1, v2):
        # Convert int16 keypoints before multiplication to avoid overflow.
        # Coincident/noisy keypoints can also form a zero-length vector; that
        # frame is not classifiable and must not terminate the application.
        v1_x, v1_y = float(v1[0]), float(v1[1])
        v2_x, v2_y = float(v2[0]), float(v2[1])
        v1_norm = np.sqrt(v1_x * v1_x + v1_y * v1_y)
        v2_norm = np.sqrt(v2_x * v2_x + v2_y * v2_y)
        denominator = v1_norm * v2_norm
        if denominator <= 0.000001:
            return 65535.0
        dot = v1_x * v2_x + v1_y * v2_y
        cos_a = dot / denominator
        # Floating-point rounding can put cosine just outside [-1, 1].
        cos_a = max(-1.0, min(1.0, cos_a))
        angle = np.acos(cos_a) * 180 / np.pi
        return angle

    def _classify_gesture(self, r):
        angle_list = []
        for i in range(5):
            a = self._vector_angle(
                [r[0] - r[i * 8 + 4], r[1] - r[i * 8 + 5]],
                [r[i * 8 + 6] - r[i * 8 + 8], r[i * 8 + 7] - r[i * 8 + 9]]
            )
            angle_list.append(a)
        thr_a, thr_t, thr_s = 65.0, 53.0, 49.0
        if 65535.0 not in angle_list:
            a = angle_list
            if a[0] > thr_t and a[1] > thr_a and a[2] > thr_a and a[3] > thr_a and a[4] > thr_a:
                return "fist"
            elif a[0] < thr_s and a[1] < thr_s and a[2] < thr_s and a[3] < thr_s and a[4] < thr_s:
                return "five"
            elif a[0] < thr_s and a[1] < thr_s and a[2] > thr_a and a[3] > thr_a and a[4] > thr_a:
                return "gun"
            elif a[0] < thr_s and a[1] < thr_s and a[2] > thr_a and a[3] > thr_a and a[4] < thr_s:
                return "love"
            elif a[0] > 5 and a[1] < thr_s and a[2] > thr_a and a[3] > thr_a and a[4] > thr_a:
                return "one"
            elif a[0] < thr_s and a[1] > thr_a and a[2] > thr_a and a[3] > thr_a and a[4] < thr_s:
                return "six"
            elif a[0] > thr_t and a[1] < thr_s and a[2] < thr_s and a[3] < thr_s and a[4] > thr_a:
                return "three"
            elif a[0] < thr_s and a[1] > thr_a and a[2] > thr_a and a[3] > thr_a and a[4] > thr_a:
                return "thumbUp"
            elif a[0] > thr_t and a[1] < thr_s and a[2] < thr_s and a[3] > thr_a and a[4] > thr_a:
                return "yeah"
        return None


class HandKeyPointClassDemo(Application):
    name = "手势识别"
    rgb_size = [1280, 720]
    required_files = [
        config.KMODEL_DIR + "hand_det.kmodel",
        config.KMODEL_DIR + "handkp_det.kmodel",
    ]

    SENSOR_ID = 2
    SENSOR_FPS = 60
    DISPLAY_CHANNEL = CAM_CHN_ID_0
    AI_CHANNEL = CAM_CHN_ID_2
    DISPLAY_FORMAT = Sensor.YUV420SP
    AI_FORMAT = Sensor.RGBP888
    VIDEO_LAYER = Display.LAYER_VIDEO1

    FINGER_COLORS = [
        (255, 255, 0, 0), (255, 255, 0, 255), (255, 255, 255, 0),
        (255, 0, 255, 0), (255, 0, 0, 255)
    ]

    def __init__(self):
        self.rgb_size = [ALIGN_UP(self.rgb_size[0], 16), self.rgb_size[1]]
        self.display_size = [ALIGN_UP(config.CAM_WIN_W, 16), config.CAM_WIN_H]
        Application.__init__(self)
        self.sensor = None
        self._osd_img = None
        self._ai_img = None
        self._video_bound = False
        labels = ["hand"]
        anchors = [26, 27, 53, 52, 75, 71, 80, 99, 106, 82, 99, 134,
                   140, 113, 161, 172, 245, 276]

        # Roll back partially-created sub-models on failure: a create() error
        # means runner never calls close(), so any KPU/AI2D already allocated
        # here must be released before re-raising.
        self.hand_det = None
        self.hand_kp = None
        try:
            self.hand_det = _HandDetModel(config.KMODEL_DIR + "hand_det.kmodel",
                                           labels, [512, 512], anchors,
                                           0.2, 0.5, [8, 16, 32],
                                           self.rgb_size, self.display_size)
            self.hand_det.config_preprocess()
            self.hand_kp = _HandKPModel(config.KMODEL_DIR + "handkp_det.kmodel",
                                         [256, 256], self.rgb_size, self.display_size)
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
                print("HandKeyPointClassDemo: video layer disable failed:", e)
            self._video_bound = False
        if sensor is not None:
            try:
                sensor.stop()
            except Exception as e:
                print("HandKeyPointClassDemo: sensor stop failed:", e)

    def _release_owned_resources(self):
        self._osd_img = None

    def _skip_hand(self, det_box):
        x1, y1, x2, y2 = det_box[2], det_box[3], det_box[4], det_box[5]
        w, h = int(x2 - x1), int(y2 - y1)
        if h < 0.1 * self.rgb_size[1]:
            return True
        if w < 0.25 * self.rgb_size[0] and (x1 < 0.03 * self.rgb_size[0] or x2 > 0.97 * self.rgb_size[0]):
            return True
        if w < 0.15 * self.rgb_size[0] and (x1 < 0.01 * self.rgb_size[0] or x2 > 0.99 * self.rgb_size[0]):
            return True
        return False

    def run(self, input_np):
        det_boxes = self.hand_det.run(input_np)
        boxes = []
        gesture_res = []
        for det_box in det_boxes:
            if self._skip_hand(det_box):
                continue
            self.hand_kp.config_preprocess(det_box)
            results_show, gesture = self.hand_kp.run(input_np)
            gesture_res.append((results_show, gesture))
            boxes.append(det_box)
        return boxes, gesture_res

    def draw_result(self, img, result):
        dets, gesture_res = result
        count = 0
        if dets:
            for k in range(len(dets)):
                det_box = dets[k]
                if self._skip_hand(det_box):
                    continue
                x1, y1, x2, y2 = det_box[2], det_box[3], det_box[4], det_box[5]
                w_det = int(float(x2 - x1) * self.display_size[0] // self.rgb_size[0])
                h_det = int(float(y2 - y1) * self.display_size[1] // self.rgb_size[1])
                x_det = int(x1 * self.display_size[0] // self.rgb_size[0])
                y_det = int(y1 * self.display_size[1] // self.rgb_size[1])
                gesture_str = gesture_res[k][1]
                visual.draw_detection(
                    img, x_det, y_det, w_det, h_det,
                    label=gesture_str.upper() if gesture_str else "HAND",
                    color=visual.GREEN)

                r = gesture_res[k][0]
                n = len(r) // 2
                for i in range(n):
                    visual.draw_keypoint(img, r[i * 2], r[i * 2 + 1],
                                         color=visual.GREEN, radius=2)

                for i in range(5):
                    j = i * 8
                    color = self.FINGER_COLORS[i]
                    visual.draw_skeleton_line(
                        img, r[0], r[1], r[j + 2], r[j + 3],
                        color=color, thickness=3)
                    visual.draw_skeleton_line(
                        img, r[j + 2], r[j + 3], r[j + 4], r[j + 5],
                        color=color, thickness=3)
                    visual.draw_skeleton_line(
                        img, r[j + 4], r[j + 5], r[j + 6], r[j + 7],
                        color=color, thickness=3)
                    visual.draw_skeleton_line(
                        img, r[j + 6], r[j + 7], r[j + 8], r[j + 9],
                        color=color, thickness=3)
                count += 1
        if count:
            visual.draw_mode_badge(img, "HAND SKELETON", visual.GREEN)
        return count

    def deinit(self):
        for model in (self.hand_det, self.hand_kp):
            if model is None:
                continue
            try:
                deinit_with_retry(model)
            except Exception as e:
                print("HandKeyPointClassDemo: model deinit failed:", e)
        gc.collect()
