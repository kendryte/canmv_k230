from model_cleanup import deinit_with_retry
# demo_dynamic_gesture.py - Dynamic hand gesture recognition

import gc
import time
import ulab.numpy as np
import nncase_runtime as nn
import aicube
import image
import config
import i18n
import app_visual as visual
from media.sensor import *
from media.display import Display
from app_contract import Application
from libs.AIBase import AIBase
from libs.AI2D import Ai2d
from model_cleanup import deinit_model
from media.media import ALIGN_UP
from libs.Utils import *

GESTURE_KMODEL = config.KMODEL_DIR + "gesture.kmodel"
GESTURE_LABELS = ["hand"]
GESTURE_ANCHORS = [26, 27, 53, 52, 75, 71, 80, 99, 106, 82,
                   99, 134, 140, 113, 161, 172, 245, 276]
GESTURE_STRIDES = [8, 16, 32]

# direction indicator icon files (ARGB8888 raw bins, u8)
BIN_SHANG = config.UTILS_DIR + "shang.bin"   # 216h x 150w
BIN_XIA   = config.UTILS_DIR + "xia.bin"     # 216h x 150w
BIN_ZUO   = config.UTILS_DIR + "zuo.bin"     # 150w x 216h
BIN_YOU   = config.UTILS_DIR + "you.bin"     # 150w x 216h

CJK_FONT = "/sdcard/res/font/AlibabaPuHuiTi-3-45-Light.ttf"

# state enum
TRIGGER = 0
UP      = 2
DOWN    = 3
LEFT    = 4
RIGHT   = 5
MIDDLE  = 1


def _score_at(scores, index):
    """Read one accumulated model score without allocating a frame closure."""
    try:
        return float(scores[index]) if index < len(scores) else 0.0
    except Exception:
        return 0.0


def _confirmed(scores, index, frame_count, high_score,
               high_frames=2, low_score=0.3, low_frames=3):
    score = _score_at(scores, index)
    return (score >= high_score and frame_count >= high_frames) or \
           (score >= low_score and frame_count >= low_frames)


class _HandDetModel(AIBase):
    def __init__(self, rgb_size, disp_size, conf_thr=0.2, nms_thr=0.5):
        try:
            km = config.KMODEL_DIR + "hand_det.kmodel"
            super().__init__(km, [512, 512], rgb_size, 0)
            self.confidence_threshold = conf_thr
            self.nms_threshold = nms_thr
            self.labels = GESTURE_LABELS
            self.model_input_size = [512, 512]
            self.strides = GESTURE_STRIDES
            self.anchors = GESTURE_ANCHORS
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

    def config_preprocess(self, input_size=None):
        s = input_size if input_size else self.rgb888p_size
        top, bottom, left, right, _ = center_pad_param(
            self.rgb888p_size, self.model_input_size)
        self.ai2d.pad([0, 0, 0, 0, top, bottom, left, right], 0,
                      [114, 114, 114])
        self.ai2d.resize(nn.interp_method.tf_bilinear,
                         nn.interp_mode.half_pixel)
        self.ai2d.build([1, 3, s[1], s[0]],
                        [1, 3, self.model_input_size[1], self.model_input_size[0]])

    def postprocess(self, results):
        return aicube.anchorbasedet_post_process(
            results[0], results[1], results[2], self.model_input_size,
            self.rgb888p_size, self.strides, len(self.labels),
            self.confidence_threshold, self.nms_threshold,
            self.anchors, False)


class _HandKPModel(AIBase):
    def __init__(self, rgb_size, disp_size):
        try:
            km = config.KMODEL_DIR + "handkp_det.kmodel"
            super().__init__(km, [256, 256], rgb_size, 0)
            self.model_input_size = [256, 256]
            self.rgb888p_size = [ALIGN_UP(rgb_size[0], 16), rgb_size[1]]
            self.display_size = [ALIGN_UP(disp_size[0], 16), disp_size[1]]
            self.crop_params = []
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
        self.ai2d.resize(nn.interp_method.tf_bilinear,
                         nn.interp_mode.half_pixel)
        self.ai2d.build([1, 3, s[1], s[0]],
                        [1, 3, self.model_input_size[1], self.model_input_size[0]])

    def postprocess(self, results):
        r = results[0].reshape(results[0].shape[0] * results[0].shape[1])
        res = np.zeros(r.shape, dtype=np.int16)
        res[0::2] = r[0::2] * self.crop_params[2] + self.crop_params[0]
        res[1::2] = r[1::2] * self.crop_params[3] + self.crop_params[1]
        gesture = self._classify_gesture(res)
        # Keep keypoints in Sensor coordinates. The dynamic-state direction
        # angle must not change when Display uses a different aspect ratio.
        return res, gesture

    def _vector_angle(self, v1, v2):
        v1_x, v1_y = float(v1[0]), float(v1[1])
        v2_x, v2_y = float(v2[0]), float(v2[1])
        v1_n = np.sqrt(v1_x * v1_x + v1_y * v1_y)
        v2_n = np.sqrt(v2_x * v2_x + v2_y * v2_y)
        denominator = v1_n * v2_n
        if denominator <= 0.000001:
            return 65535.0
        dot = v1_x * v2_x + v1_y * v2_y
        cos_a = dot / denominator
        cos_a = max(-1.0, min(1.0, cos_a))
        return np.acos(cos_a) * 180 / np.pi

    def _classify_gesture(self, r):
        angles = []
        for i in range(5):
            a = self._vector_angle(
                [r[0] - r[i * 8 + 4], r[1] - r[i * 8 + 5]],
                [r[i * 8 + 6] - r[i * 8 + 8], r[i * 8 + 7] - r[i * 8 + 9]])
            angles.append(a)
        thr_a, thr_t, thr_s = 65.0, 53.0, 49.0
        if 65535.0 not in angles:
            a = angles
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


class _GestureModel(AIBase):
    def __init__(self, rgb_size, disp_size):
        try:
            super().__init__(GESTURE_KMODEL, [224, 224], rgb_size, 0)
            self.model_input_size = [224, 224]
            self.rgb888p_size = [ALIGN_UP(rgb_size[0], 16), rgb_size[1]]
            self.display_size = [ALIGN_UP(disp_size[0], 16), disp_size[1]]
            self.ai2d_resize = Ai2d(0)
            self.ai2d_resize.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT,
                                             nn.ai2d_format.NCHW_FMT,
                                             np.uint8, np.uint8)
            self.ai2d_crop = Ai2d(0)
            self.ai2d_crop.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT,
                                           nn.ai2d_format.NCHW_FMT,
                                           np.uint8, np.uint8)
            self.resize_shape = 256
            self.mean_vals = np.array([0.485, 0.456, 0.406]).reshape((3, 1, 1))
            self.std_vals = np.array([0.229, 0.224, 0.225]).reshape((3, 1, 1))
            self.first_data = None
            self.input_tensors = []
            self.max_hist_len = 20
        except BaseException:
            # The caller cannot own this model until construction returns.
            try:
                self.deinit()
            except Exception as error:
                print("model constructor cleanup failed:", error)
            raise

    def config_preprocess(self, input_size=None):
        s = input_size if input_size else self.rgb888p_size
        cp = self._get_crop_param()
        self.ai2d_resize.resize(nn.interp_method.tf_bilinear,
                                nn.interp_mode.half_pixel)
        self.ai2d_resize.build([1, 3, s[1], s[0]],
                               [1, 3, cp[1], cp[0]])
        self.ai2d_crop.crop(cp[2], cp[3], cp[4], cp[5])
        self.ai2d_crop.build([1, 3, cp[1], cp[0]],
                             [1, 3, self.model_input_size[1], self.model_input_size[0]])
        input_shapes = [
            [1, 3, 224, 224], [1, 3, 56, 56], [1, 4, 28, 28],
            [1, 4, 28, 28], [1, 8, 14, 14], [1, 8, 14, 14],
            [1, 8, 14, 14], [1, 12, 14, 14], [1, 12, 14, 14],
            [1, 20, 7, 7], [1, 20, 7, 7]]
        self.first_data = np.ones(input_shapes[0], dtype=np.float)
        for i in range(min(11, self.get_kmodel_inputs_num())):
            self.input_tensors.append(nn.from_numpy(
                np.zeros(input_shapes[i], dtype=np.float)))

    def _get_crop_param(self):
        ori_w = self.rgb888p_size[0]
        ori_h = self.rgb888p_size[1]
        width = self.model_input_size[0]
        height = self.model_input_size[1]
        ratio_w = float(self.resize_shape) / ori_w
        ratio_h = float(self.resize_shape) / ori_h
        ratio = ratio_h if ratio_w < ratio_h else ratio_w
        new_w = int(ratio * ori_w)
        new_h = int(ratio * ori_h)
        top = int((new_h - height) / 2)
        left = int((new_w - width) / 2)
        return new_w, new_h, left, top, width, height

    def run(self, input_np, his_logit, history):
        rs = self.ai2d_resize.run(input_np)
        cr = self.ai2d_crop.run(rs.to_numpy())
        out = cr.to_numpy()
        self.first_data[0] = out[0].copy()
        self.first_data[0] = ((self.first_data[0] * 1.0 / 255)
                              - self.mean_vals) / self.std_vals
        self._replace_input_tensor(0, self.first_data)
        outputs = self.inference(self.input_tensors)
        num = min(self.get_kmodel_outputs_num(), len(self.input_tensors))
        for i in range(1, num):
            self._replace_input_tensor(i, outputs[i])
        return self._postprocess(outputs, his_logit, history)

    def _replace_input_tensor(self, index, data):
        new_tensor = nn.from_numpy(data)
        previous = self.input_tensors[index]
        self.input_tensors[index] = new_tensor
        if previous is not None:
            previous.release()

    def _postprocess(self, results, his_logit, history):
        his_logit.append(results[0])
        avg = sum(np.array(his_logit))
        # gesture.kmodel outputs class scores as [1, class_count].  Keep the
        # scores one-dimensional here so callers can index them by class id.
        # The reference demo performs the same operation in draw_result via
        # avg_logit[0].
        scores = avg[0]
        idx_ = int(np.argmax(scores))
        idx = self._filter(idx_, history)
        # Do not clear accumulated scores merely because the temporal filter
        # retained the preceding class.  Dynamic output can fluctuate for a
        # frame while a gesture is in progress; draw_result resets the window
        # when the filtered class is genuinely invalid for the current state.
        return idx, scores

    def _filter(self, pred, history):
        if pred in (0, 1, 3, 4, 6, 7, 8, 9, 14, 19, 20, 21, 22, 23, 24):
            pred = history[-1]
        if pred == 0:
            pred = 2
        if pred != history[-1] and len(history) >= 2:
            if history[-1] != history[-2]:
                pred = history[-1]
        history.append(pred)
        if len(history) > self.max_hist_len:
            history[:] = history[-self.max_hist_len:]
        return history[-1]

    def deinit(self):
        if getattr(self, "_deinited", False):
            return
        self.first_data = None
        deinit_model(self, ("ai2d_resize", "ai2d_crop"), ("input_tensors",))
        self._deinited = True


class DynamicGestureDemo(Application):
    name = "动态手势"
    model_path = config.KMODEL_DIR + "hand_det.kmodel"
    rgb_size = [1280, 720]
    required_files = [
        config.KMODEL_DIR + "hand_det.kmodel",
        config.KMODEL_DIR + "handkp_det.kmodel",
        GESTURE_KMODEL,
        BIN_SHANG, BIN_XIA, BIN_ZUO, BIN_YOU,
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
        self._ai_img = None
        self._osd_img = None
        self._video_bound = False
        self.cur_state = TRIGGER
        self.pre_state = TRIGGER
        self.draw_state = TRIGGER
        self.vec_flag = []
        self.his_logit = []
        self.history = [2]
        self.s_start = time.time_ns()
        self.m_start = None
        self._direction_labels = ({
            UP: "向上", RIGHT: "向右", DOWN: "向下",
            LEFT: "向左", MIDDLE: "中间"} if i18n.is_chinese() else {
            UP: "UP", RIGHT: "RIGHT", DOWN: "DOWN",
            LEFT: "LEFT", MIDDLE: "CENTER"})

        # Roll back partially-created sub-models on failure: a create() error
        # means runner never calls close(), so any KPU/AI2D already allocated
        # here must be released before re-raising.
        self.hand_det = None
        self.hand_kp = None
        self.gesture = None
        try:
            self.hand_det = _HandDetModel(self.rgb_size, self.display_size)
            self.hand_det.config_preprocess()
            self.hand_kp = _HandKPModel(self.rgb_size, self.display_size)
            self.gesture = _GestureModel(self.rgb_size, self.display_size)
            self.gesture.config_preprocess()

            # load direction indicator overlays
            self._load_bins()
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
                print("DynamicGestureDemo: video layer disable failed:", e)
            self._video_bound = False
        if sensor is not None:
            try:
                sensor.stop()
            except Exception as e:
                print("DynamicGestureDemo: sensor stop failed:", e)

    def _release_owned_resources(self):
        self._osd_img = None

    def _load_bins(self):
        self._icons = {}
        for key, path, h, w in [
            ("up", BIN_SHANG, 216, 150),
            ("down", BIN_XIA, 216, 150),
            ("left", BIN_ZUO, 150, 216),
            ("right", BIN_YOU, 150, 216),
        ]:
            try:
                data = np.fromfile(path, dtype=np.uint8)
                self._icons[key] = data.reshape((h, w, 4))
            except Exception as e:
                print("Failed to load", path, ":", e)
                self._icons[key] = np.zeros((h, w, 4), dtype=np.uint8)

    def run(self, input_np):
        if self.cur_state == TRIGGER:
            dets = self.hand_det.run(input_np)
            boxes = []
            gesture_res = []
            for det in dets:
                x1, y1, x2, y2 = det[2], det[3], det[4], det[5]
                w, h = int(x2 - x1), int(y2 - y1)
                if h < 0.1 * self.rgb_size[1]:
                    continue
                if w < 0.25 * self.rgb_size[0] and \
                   (x1 < 0.03 * self.rgb_size[0] or x2 > 0.97 * self.rgb_size[0]):
                    continue
                if w < 0.15 * self.rgb_size[0] and \
                   (x1 < 0.01 * self.rgb_size[0] or x2 > 0.99 * self.rgb_size[0]):
                    continue
                self.hand_kp.config_preprocess(det)
                kp, gesture = self.hand_kp.run(input_np)
                boxes.append(det)
                gesture_res.append((kp, gesture))
            return boxes, gesture_res
        else:
            idx, avg = self.gesture.run(input_np, self.his_logit, self.history)
            return idx, avg

    def draw_result(self, img, result):
        cw, ch = img.width(), img.height()
        count = 0
        osd_np = img.to_numpy_ref()

        if self.cur_state == TRIGGER:
            dets, gesture_res = result
            for det, (kp, gesture) in zip(dets, gesture_res):
                x1, y1, x2, y2 = det[2], det[3], det[4], det[5]
                box_x = int(x1 * self.display_size[0] // self.rgb_size[0])
                box_y = int(y1 * self.display_size[1] // self.rgb_size[1])
                box_w = int((x2 - x1) * self.display_size[0] //
                            self.rgb_size[0])
                box_h = int((y2 - y1) * self.display_size[1] //
                            self.rgb_size[1])
                visual.draw_detection(
                    img, box_x, box_y, box_w, box_h,
                    label=gesture.upper() if gesture else "HAND",
                    color=visual.VIOLET)
                if gesture in ("five", "yeah"):
                    vx = kp[24] - kp[0]
                    vy = kp[25] - kp[1]
                    angle = self.hand_kp._vector_angle([vx, vy], [1.0, 0.0])
                    if vy > 0:
                        angle = 360 - angle
                    if 70.0 <= angle < 110.0:
                        if self.pre_state not in (UP, MIDDLE):
                            self.vec_flag.append(self.pre_state)
                        if len(self.vec_flag) > 10 or \
                           self.pre_state in (UP, MIDDLE, TRIGGER):
                            self._paste_icon(osd_np, self._icons["up"], cw, ch)
                            self.cur_state = UP
                    elif 110.0 <= angle < 225.0:
                        if self.pre_state != RIGHT:
                            self.vec_flag.append(self.pre_state)
                        if len(self.vec_flag) > 10 or \
                           self.pre_state in (RIGHT, TRIGGER):
                            self._paste_icon(osd_np, self._icons["right"], cw, ch)
                            self.cur_state = RIGHT
                    elif 225.0 <= angle < 315.0:
                        if self.pre_state != DOWN:
                            self.vec_flag.append(self.pre_state)
                        if len(self.vec_flag) > 10 or \
                           self.pre_state in (DOWN, TRIGGER):
                            self._paste_icon(osd_np, self._icons["down"], cw, ch)
                            self.cur_state = DOWN
                    else:
                        if self.pre_state != LEFT:
                            self.vec_flag.append(self.pre_state)
                        if len(self.vec_flag) > 10 or \
                           self.pre_state in (LEFT, TRIGGER):
                            self._paste_icon(osd_np, self._icons["left"], cw, ch)
                            self.cur_state = LEFT
                    self.m_start = time.time_ns()
                count += 1
            self.his_logit.clear()
        else:
            idx, avg = result
            frame_count = len(self.his_logit)

            if self.cur_state == UP:
                self._paste_icon(osd_np, self._icons["up"], cw, ch)
                if idx in (15, 10):
                    self.vec_flag.clear()
                    if _confirmed(avg, idx, frame_count, 0.7,
                                  high_frames=2, low_frames=4):
                        self.s_start = time.time_ns()
                        self.cur_state = TRIGGER
                        self.draw_state = DOWN
                        self.history = [2]
                    self.pre_state = UP
                elif idx in (25, 26):
                    self.vec_flag.clear()
                    if _confirmed(avg, idx, frame_count, 0.4):
                        self.s_start = time.time_ns()
                        self.cur_state = TRIGGER
                        self.draw_state = MIDDLE
                        self.history = [2]
                    self.pre_state = MIDDLE
                else:
                    self.his_logit.clear()
            elif self.cur_state == RIGHT:
                self._paste_icon(osd_np, self._icons["right"], cw, ch)
                if idx in (16, 11):
                    self.vec_flag.clear()
                    if _confirmed(avg, idx, frame_count, 0.4):
                        self.s_start = time.time_ns()
                        self.cur_state = TRIGGER
                        # The reference model reports the movement opposite
                        # to the initial pointing direction.
                        self.draw_state = LEFT
                        self.history = [2]
                    self.pre_state = RIGHT
                else:
                    self.his_logit.clear()
            elif self.cur_state == DOWN:
                self._paste_icon(osd_np, self._icons["down"], cw, ch)
                if idx in (18, 13):
                    self.vec_flag.clear()
                    if _confirmed(avg, idx, frame_count, 0.4):
                        self.s_start = time.time_ns()
                        self.cur_state = TRIGGER
                        self.draw_state = UP
                        self.history = [2]
                    self.pre_state = DOWN
                else:
                    self.his_logit.clear()
            elif self.cur_state == LEFT:
                self._paste_icon(osd_np, self._icons["left"], cw, ch)
                if idx in (17, 12):
                    self.vec_flag.clear()
                    if _confirmed(avg, idx, frame_count, 0.4):
                        self.s_start = time.time_ns()
                        self.cur_state = TRIGGER
                        self.draw_state = RIGHT
                        self.history = [2]
                    self.pre_state = LEFT
                else:
                    self.his_logit.clear()

            if self.cur_state != TRIGGER:
                el = round((time.time_ns() - self.m_start) / 1000000)
                if el > 2000:
                    self.cur_state = TRIGGER
                    self.pre_state = TRIGGER
            count = 1

        # draw result arrow directly on the OSD image
        elapsed = round((time.time_ns() - self.s_start) / 1000000)
        if elapsed < 1000:
            if self.draw_state == UP:
                visual.draw_arrow(img, cw // 2, ch // 2, cw // 2,
                                  ch // 2 - 60, visual.VIOLET,
                                  size=26, thickness=8)
            elif self.draw_state == RIGHT:
                visual.draw_arrow(img, cw // 2, ch // 2, cw // 2 + 60,
                                  ch // 2, visual.VIOLET,
                                  size=26, thickness=8)
            elif self.draw_state == DOWN:
                visual.draw_arrow(img, cw // 2, ch // 2, cw // 2,
                                  ch // 2 + 60, visual.VIOLET,
                                  size=26, thickness=8)
            elif self.draw_state == LEFT:
                visual.draw_arrow(img, cw // 2, ch // 2, cw // 2 - 60,
                                  ch // 2, visual.VIOLET,
                                  size=26, thickness=8)
            elif self.draw_state == MIDDLE:
                img.draw_circle(cw // 2, ch // 2, 55,
                                color=visual.SHADOW, fill=True)
                img.draw_circle(cw // 2, ch // 2, 48,
                                color=visual.VIOLET, fill=True)
            label = self._direction_labels.get(self.draw_state, "")
            if label:
                visual.draw_badge(
                    img, label, cw // 2 - 40, ch // 2 + 68,
                    color=visual.VIOLET, font_size=24, font=CJK_FONT)
        else:
            self.draw_state = TRIGGER

        visual.draw_mode_badge(img, "GESTURE CONTROL", visual.VIOLET)
        return count

    def _paste_icon(self, draw_np, icon, cw, ch):
        ih, iw = icon.shape[0], icon.shape[1]
        h = min(ih, ch // 2)
        w = min(iw, cw // 2)
        draw_np[:h, :w, :] = icon[:h, :w, :]

    def deinit(self):
        try:
            deinit_with_retry(self.hand_det)
        except Exception as error:
            print("Gesture hand_det cleanup failed:", error)
        try:
            deinit_with_retry(self.hand_kp)
        except Exception as error:
            print("Gesture hand_kp cleanup failed:", error)
        try:
            deinit_with_retry(self.gesture)
        except Exception as error:
            print("Gesture gesture cleanup failed:", error)
        gc.collect()
