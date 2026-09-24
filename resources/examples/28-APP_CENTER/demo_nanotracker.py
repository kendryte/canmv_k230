from model_cleanup import deinit_with_retry
# demo_nanotracker.py - Interactive independent NanoTracker application

import gc
import math
import time

import aidemo
import image
import nncase_runtime as nn
import ulab.numpy as np

import app_visual as visual
import config
import i18n
from app_contract import Application
from libs.AIBase import AIBase
from libs.AI2D import Ai2d
from model_cleanup import deinit_model
from media.display import Display
from media.media import ALIGN_UP
from media.sensor import *


_TEXT = {
    "zh_CN": {
        "action": "暂停画面", "ready": "点击暂停后拖动选择目标",
        "freezing": "正在冻结画面...", "initializing": "正在初始化目标...",
        "select": "拖动矩形选择跟踪目标", "small": "选框太小，请重新拖动",
        "selected": "已选择目标，点击开始跟踪", "select_first": "请先拖动矩形选择目标",
        "invalid_frame": "冻结帧无效，请重新选择", "tracking": "跟踪中",
        "lost": "目标丢失，请重新选框", "losing": "目标暂时丢失",
    },
    "en_US": {
        "action": "Pause frame", "ready": "Pause, then drag to select a target",
        "freezing": "Freezing frame...", "initializing": "Initializing target...",
        "select": "Drag a rectangle around the target", "small": "Selection is too small; try again",
        "selected": "Target selected; start tracking", "select_first": "Select a target rectangle first",
        "invalid_frame": "Frozen frame is invalid; select again", "tracking": "Tracking",
        "lost": "Target lost; select again", "losing": "Target temporarily lost",
    },
}


def _t(key):
    return _TEXT[i18n.language()].get(key, key)


class _NanoBackbone(AIBase):
    """One NanoTracker backbone owned exclusively by this application."""

    CONTEXT_AMOUNT = 0.5

    def __init__(self, model_path, model_size, rgb_size, search_ratio=1.0):
        try:
            AIBase.__init__(self, model_path, model_size, rgb_size, 0)
            self.model_size = model_size
            self.rgb_size = rgb_size
            self.search_ratio = search_ratio
            self.ai2d_crop = Ai2d(0)
            self.ai2d_crop.set_ai2d_dtype(
                nn.ai2d_format.NCHW_FMT, nn.ai2d_format.NCHW_FMT,
                np.uint8, np.uint8)
            self.ai2d_pad = Ai2d(0)
            self.ai2d_pad.set_ai2d_dtype(
                nn.ai2d_format.NCHW_FMT, nn.ai2d_format.NCHW_FMT,
                np.uint8, np.uint8)
            self._active_ai2d = None
            self.scale_z = None
            self._deinited = False
        except BaseException:
            # The caller cannot own this model until construction returns.
            try:
                self.deinit()
            except Exception as error:
                print("model constructor cleanup failed:", error)
            raise

    def config_preprocess(self, center_xy_wh):
        cx = float(center_xy_wh[0])
        cy = float(center_xy_wh[1])
        target_w = max(2.0, float(center_xy_wh[2]))
        target_h = max(2.0, float(center_xy_wh[3]))
        context = self.CONTEXT_AMOUNT * (target_w + target_h)
        side = int(round(math.sqrt(
            (target_w + context) * (target_h + context)) *
            self.search_ratio))
        side = max(2, side)
        # Pass the exact source-to-model scale used by this crop to the native
        # decoder. Recomputing it after separately rounding the template side
        # causes small position/size oscillations, especially for small ROIs.
        self.scale_z = float(self.model_size[0]) / float(side)

        x0 = int(math.floor(cx - (side + 1) / 2.0 + 0.5))
        y0 = int(math.floor(cy - (side + 1) / 2.0 + 0.5))
        x1 = x0 + side
        y1 = y0 + side
        src_w, src_h = self.rgb_size

        pad_left = max(0, -x0)
        pad_top = max(0, -y0)
        pad_right = max(0, x1 - src_w)
        pad_bottom = max(0, y1 - src_h)

        if not (pad_left or pad_top or pad_right or pad_bottom):
            ai2d = self.ai2d_crop
            ai2d.crop(x0, y0, side, side)
            ai2d.resize(nn.interp_method.tf_bilinear,
                        nn.interp_mode.half_pixel)
        else:
            crop_x = max(0, x0)
            crop_y = max(0, y0)
            crop_w = min(src_w, x1) - crop_x
            crop_h = min(src_h, y1) - crop_y
            if crop_w < 1 or crop_h < 1:
                raise ValueError("target crop is outside the image")

            out_w, out_h = self.model_size
            scaled_left = int(round(pad_left * out_w / side))
            scaled_right = int(round(pad_right * out_w / side))
            scaled_top = int(round(pad_top * out_h / side))
            scaled_bottom = int(round(pad_bottom * out_h / side))
            # Rounding must not consume the complete model image.
            scaled_left = min(scaled_left, out_w - 1)
            scaled_right = min(scaled_right,
                               out_w - scaled_left - 1)
            scaled_top = min(scaled_top, out_h - 1)
            scaled_bottom = min(scaled_bottom,
                                out_h - scaled_top - 1)

            ai2d = self.ai2d_pad
            ai2d.crop(crop_x, crop_y, crop_w, crop_h)
            ai2d.resize(nn.interp_method.tf_bilinear,
                        nn.interp_mode.half_pixel)
            ai2d.pad([0, 0, 0, 0,
                      scaled_top, scaled_bottom,
                      scaled_left, scaled_right],
                     0, [114, 114, 114])

        ai2d.build([1, 3, src_h, src_w],
                   [1, 3, self.model_size[1], self.model_size[0]])
        self._active_ai2d = ai2d

    def preprocess(self, input_np):
        if self._active_ai2d is None:
            raise RuntimeError("NanoTracker crop is not configured")
        return [self._active_ai2d.run(input_np)]

    def postprocess(self, results):
        return results[0]

    def deinit(self):
        if getattr(self, "_deinited", False):
            return
        self._active_ai2d = None
        deinit_model(self, ("ai2d_crop", "ai2d_pad"))
        self._deinited = True


class _NanoTrackerHead(AIBase):
    """NanoTracker head model and firmware postprocess wrapper."""

    CONTEXT_AMOUNT = 0.5

    def __init__(self, model_path, rgb_size, crop_size, threshold):
        try:
            AIBase.__init__(self, model_path, None, rgb_size, 0)
            self.rgb_size = rgb_size
            self.crop_size = crop_size
            self.threshold = threshold
            self._deinited = False
        except BaseException:
            # The caller cannot own this model until construction returns.
            try:
                self.deinit()
            except Exception as error:
                print("model constructor cleanup failed:", error)
            raise

    def run(self, template_feature, search_feature, center_xy_wh,
            scale_z=None):
        tensors = []
        try:
            tensors.append(nn.from_numpy(template_feature))
            tensors.append(nn.from_numpy(search_feature))
            results = self.inference(tensors)
        finally:
            for tensor in tensors:
                tensor.release()
        if scale_z is None:
            return aidemo.nanotracker_postprocess(
                results[0], results[1],
                [self.rgb_size[1], self.rgb_size[0]],
                self.threshold, center_xy_wh,
                self.crop_size, self.CONTEXT_AMOUNT)
        return aidemo.nanotracker_postprocess(
            results[0], results[1],
            [self.rgb_size[1], self.rgb_size[0]],
            self.threshold, center_xy_wh,
            self.crop_size, self.CONTEXT_AMOUNT, float(scale_z))

    def deinit(self):
        if getattr(self, "_deinited", False):
            return
        AIBase.deinit(self)
        self._deinited = True


class NanoTrackerDemo(Application):
    """User-selected single-object tracking with fully owned resources."""

    name = "单目标跟踪"
    template_model_path = config.KMODEL_DIR + "cropped_test127.kmodel"
    search_model_path = \
        config.KMODEL_DIR + "nanotrack_backbone_sim.kmodel"
    head_model_path = \
        config.KMODEL_DIR + "nanotracker_head_calib_k230.kmodel"
    model_path = template_model_path
    required_files = [search_model_path, head_model_path]

    # UI metadata only. Sensor/model/image ownership remains in this class.
    ui_action_label = "暂停画面"
    ui_roi_select = True

    rgb_size = [640, 360]
    template_size = [127, 127]
    search_size = [255, 255]
    threshold = 0.1
    min_target_size = 12
    max_lost_frames = 12
    visual_center_alpha = 0.45
    visual_size_alpha = 0.30
    visual_snap_ratio = 0.25

    # This Sensor profile belongs only to this application. SENSOR_FPS is an
    # editable hint and is intentionally not passed to Sensor().
    SENSOR_ID = 2
    SENSOR_FPS = 60
    DISPLAY_CHANNEL = CAM_CHN_ID_0
    AI_CHANNEL = CAM_CHN_ID_2
    DISPLAY_FORMAT = Sensor.YUV420SP
    AI_FORMAT = Sensor.RGBP888
    VIDEO_LAYER = Display.LAYER_VIDEO1

    PREVIEW = "preview"
    FREEZING = "freezing"
    SELECTING = "selecting"
    INITIALIZING = "initializing"
    TRACKING = "tracking"
    LOST = "lost"

    @classmethod
    def localized_ui(cls):
        return {"action_label": _t("action")}

    def __init__(self):
        Application.__init__(self)
        self._strings = _TEXT[i18n.language()]
        self.rgb_size = [ALIGN_UP(self.rgb_size[0], 16), self.rgb_size[1]]
        self.display_size = [ALIGN_UP(config.CAM_WIN_W, 16),
                             config.CAM_WIN_H]
        self.sensor = None
        self._video_bound = False
        self._ai_img = None
        self._frozen_ai_img = None
        self._osd_img = None
        self._state = self.PREVIEW
        self._command = None
        self._pending_screen_roi = None
        self._selected_center = None
        self._center_xy_wh = None
        self._template_feature = None
        self._search_feature = None
        self._last_box = None
        self._visual_center = None
        self._lost_frames = 0
        self._models_deinited = False
        self._tracking_status = None

        self._template_model = None
        self._search_model = None
        self._head_model = None
        try:
            self._template_model = _NanoBackbone(
                self.template_model_path, self.template_size,
                self.rgb_size, 1.0)
            self._search_model = _NanoBackbone(
                self.search_model_path, self.search_size,
                self.rgb_size,
                float(self.search_size[0]) / self.template_size[0])
            self._head_model = _NanoTrackerHead(
                self.head_model_path, self.rgb_size,
                self.template_size[0], self.threshold)
        except Exception:
            self.deinit()
            raise

    def _msg(self, key):
        return self._strings.get(key, key)

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
        if self.stop_req:
            return
        self.start()
        self._opened = True
        self._set_status(self._msg("ready"), config.THEME_GREEN)

    def request_action(self):
        """LVGL-thread entry: submit a scalar command, never touch resources."""
        if self.stop_req or self._command is not None:
            return
        state = self._state
        if state in (self.PREVIEW, self.TRACKING, self.LOST):
            self._command = "pause"
            self._set_status(self._msg("freezing"), config.THEME_ORANGE)
        elif state == self.SELECTING:
            self._command = "start"
            self._set_status(self._msg("initializing"), config.THEME_ORANGE)

    def submit_roi(self, x, y, w, h):
        """LVGL-thread entry: copy only the final screen-space rectangle."""
        if self.stop_req or self._state != self.SELECTING:
            return
        self._pending_screen_roi = (int(x), int(y), int(w), int(h))

    def run_once(self):
        command = self._command
        self._command = None

        if command == "pause":
            self._freeze_for_selection()
            return None

        if self._state == self.SELECTING:
            self._consume_pending_roi()
            if command == "start":
                self._start_tracking()
            else:
                time.sleep_ms(20)
            return None

        if self._state in (self.PREVIEW, self.FREEZING,
                           self.INITIALIZING, self.LOST):
            time.sleep_ms(20)
            return None

        if self._state != self.TRACKING:
            return None

        self._ai_img = self.sensor.snapshot(chn=self.AI_CHANNEL)
        input_np = self._ai_img.to_numpy_ref()
        self._search_model.config_preprocess(self._center_xy_wh)
        self._search_feature = self._search_model.run(input_np)
        result = self._head_model.run(
            self._template_feature, self._search_feature,
            self._center_xy_wh, self._search_model.scale_z)
        return self._handle_tracking_result(result)

    def _freeze_for_selection(self):
        self._state = self.FREEZING
        self._pending_screen_roi = None
        self._selected_center = None
        self._template_feature = None
        self._search_feature = None
        self._last_box = None
        self._visual_center = None
        self._lost_frames = 0
        self._tracking_status = None
        self._ai_img = None
        self._osd_img = None
        if self.display is not None:
            self.display.clear()
        gc.collect()

        # Keep this exact frame until the template feature is extracted. The
        # temporary HWC/scaled images exist only during this one pause action.
        frozen = self.sensor.snapshot(chn=self.AI_CHANNEL)
        self._frozen_ai_img = frozen
        chw = frozen.to_numpy_ref()
        pixels = self.rgb_size[0] * self.rgb_size[1]
        hwc = chw.reshape((3, pixels)).transpose().copy().reshape(
            (self.rgb_size[1], self.rgb_size[0], 3))
        native_img = image.Image(self.rgb_size[0], self.rgb_size[1],
                                 image.RGB888, alloc=image.ALLOC_REF,
                                 data=hwc)
        frozen_display = native_img.to_rgb888(
            x_size=self.display_size[0], y_size=self.display_size[1])
        self.display.show(frozen_display)
        frozen_display = None
        native_img = None
        hwc = None
        chw = None
        gc.collect()

        self._state = self.SELECTING
        self._send_ui_mode("select")
        self._set_status(self._msg("select"), config.THEME_ORANGE)

    def _consume_pending_roi(self):
        roi = self._pending_screen_roi
        if roi is None:
            return
        self._pending_screen_roi = None
        x, y, w, h = roi
        if w <= 0 or h <= 0:
            self._selected_center = None
            self._set_status(self._msg("small"), config.THEME_RED)
            return

        display_w, display_h = self.display_size
        ai_w, ai_h = self.rgb_size
        x1 = max(0, min(display_w - 1, x))
        y1 = max(0, min(display_h - 1, y))
        x2 = max(x1 + 1, min(display_w, x + w))
        y2 = max(y1 + 1, min(display_h, y + h))
        ai_x1 = int(round(x1 * ai_w / display_w))
        ai_y1 = int(round(y1 * ai_h / display_h))
        ai_x2 = int(round(x2 * ai_w / display_w))
        ai_y2 = int(round(y2 * ai_h / display_h))
        target_w = max(1, ai_x2 - ai_x1)
        target_h = max(1, ai_y2 - ai_y1)
        if target_w < self.min_target_size or \
                target_h < self.min_target_size:
            self._selected_center = None
            self._set_status(self._msg("small"), config.THEME_RED)
            return

        self._selected_center = [
            ai_x1 + target_w / 2.0,
            ai_y1 + target_h / 2.0,
            float(target_w), float(target_h)]
        self._set_status(self._msg("selected"), config.THEME_GREEN)

    def _start_tracking(self):
        self._consume_pending_roi()
        if self._selected_center is None:
            self._set_status(self._msg("select_first"), config.THEME_RED)
            return
        if self._frozen_ai_img is None:
            self._set_status(self._msg("invalid_frame"), config.THEME_RED)
            return

        self._state = self.INITIALIZING
        center = list(self._selected_center)
        self._template_model.config_preprocess(center)
        feature = self._template_model.run(
            self._frozen_ai_img.to_numpy_ref())
        self._template_feature = feature.copy()
        self._center_xy_wh = center
        self._visual_center = None
        self._frozen_ai_img = None
        self._selected_center = None
        self._ai_img = None

        # OSD0 currently contains an opaque RGB freeze frame. Disable it before
        # configuring the same layer as the transparent ARGB tracking overlay.
        self.display.clear()
        gc.collect()
        self._osd_img = image.Image(self.display_size[0],
                                    self.display_size[1],
                                    image.ARGB8888)
        self._osd_img.clear()
        self.display.show(self._osd_img)
        self._state = self.TRACKING
        self._send_ui_mode("tracking")
        self._set_tracking_status(self._msg("tracking"), config.THEME_GREEN)

    def _handle_tracking_result(self, result):
        box = result[0] if result and len(result) > 0 else None
        center = result[1] if result and len(result) > 1 else None
        state_valid = center is not None and len(center) >= 4 and \
            center[2] > 1 and center[3] > 1
        valid = box is not None and state_valid and \
            len(box) >= 5 and \
            box[2] > 1 and box[3] > 1

        if state_valid:
            # The native wrapper returns the continuous tracker state even when
            # a low-confidence frame suppresses the visible detection box.
            self._center_xy_wh = [float(center[0]), float(center[1]),
                                  float(center[2]), float(center[3])]
            visual_center = self._smooth_visual_center(
                self._center_xy_wh)
        else:
            visual_center = None

        self._osd_img.clear()
        if valid:
            self._last_box = box
            self._lost_frames = 0
            score = float(box[4])
            cx, cy, target_w, target_h = visual_center
            scale_x = float(self.display_size[0]) / self.rgb_size[0]
            scale_y = float(self.display_size[1]) / self.rgb_size[1]
            # Keep subpixel tracker precision until the final OSD conversion;
            # the old integer box path quantized coordinates twice.
            x1 = int(round((cx - target_w * 0.5) * scale_x))
            y1 = int(round((cy - target_h * 0.5) * scale_y))
            x2 = int(round((cx + target_w * 0.5) * scale_x))
            y2 = int(round((cy + target_h * 0.5) * scale_y))
            x = max(0, min(self.display_size[0] - 1, x1))
            y = max(0, min(self.display_size[1] - 1, y1))
            x2 = max(x + 1, min(self.display_size[0], x2))
            y2 = max(y + 1, min(self.display_size[1], y2))
            w = x2 - x
            h = y2 - y
            visual.draw_detection(self._osd_img, x, y, w, h,
                                  label="TRACK", score=score,
                                  color=visual.CYAN)
            self._set_tracking_status(self._msg("tracking"),
                                      config.THEME_GREEN)
            count = 1
        else:
            self._lost_frames += 1
            count = 0
            if self._lost_frames >= self.max_lost_frames:
                self._state = self.LOST
                self._send_ui_mode("lost")
                self._set_tracking_status(
                    self._msg("lost"), config.THEME_RED)
            else:
                self._set_tracking_status(
                    self._msg("losing"), config.THEME_ORANGE)

        self.display.show(self._osd_img)
        return count

    def _smooth_visual_center(self, center):
        """Smooth only the OSD box; never feed this state back to tracking."""
        target = [float(center[0]), float(center[1]),
                  float(center[2]), float(center[3])]
        previous = self._visual_center
        if previous is None:
            self._visual_center = target
            return target

        move_x = target[0] - previous[0]
        move_y = target[1] - previous[1]
        size_change = max(abs(target[2] - previous[2]),
                          abs(target[3] - previous[3]))
        snap_distance = max(8.0, max(target[2], target[3]) *
                            self.visual_snap_ratio)
        if move_x * move_x + move_y * move_y > \
                snap_distance * snap_distance or \
                size_change > snap_distance:
            smoothed = target
        else:
            center_alpha = self.visual_center_alpha
            size_alpha = self.visual_size_alpha
            smoothed = [
                previous[0] + move_x * center_alpha,
                previous[1] + move_y * center_alpha,
                previous[2] + (target[2] - previous[2]) * size_alpha,
                previous[3] + (target[3] - previous[3]) * size_alpha]
        self._visual_center = smoothed
        return smoothed

    def _set_tracking_status(self, text, color):
        value = (text, color)
        if value == self._tracking_status:
            return
        self._tracking_status = value
        self._set_status(text, color)

    @staticmethod
    def _set_status(text, color):
        config.demo_status_text = text
        config.demo_status_color = color

    @staticmethod
    def _send_ui_mode(mode):
        config.demo_ui_request = ("roi_mode", mode)

    def stop(self):
        Application.stop(self)
        self._command = None
        self._pending_screen_roi = None
        sensor = self.sensor
        self.sensor = None
        self._ai_img = None
        self._frozen_ai_img = None
        if self.display is not None:
            self.display.clear()
        if self._video_bound:
            try:
                Display.disable_layer(self.VIDEO_LAYER)
            except Exception as error:
                print("NanoTrackerDemo: video disable failed:", error)
            self._video_bound = False
        if sensor is not None:
            try:
                sensor.stop()
            except Exception as error:
                print("NanoTrackerDemo: sensor stop failed:", error)

    def deinit(self):
        if self._models_deinited:
            return
        self._models_deinited = True
        for model_name in ("_head_model", "_search_model",
                           "_template_model"):
            model = getattr(self, model_name, None)
            setattr(self, model_name, None)
            if model is not None:
                try:
                    deinit_with_retry(model)
                except Exception as error:
                    print("NanoTrackerDemo: model deinit failed:", error)

    def _release_owned_resources(self):
        self._osd_img = None
        self._template_feature = None
        self._search_feature = None
        self._last_box = None
        self._visual_center = None
        self._center_xy_wh = None
