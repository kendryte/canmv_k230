from model_cleanup import deinit_with_retry
# demo_self_learning.py - Independent interactive self-learning classifier

import gc
import os
import time

import image
import nncase_runtime as nn
import ulab.numpy as np

import app_visual as visual
import config
import i18n
from app_contract import Application
from libs.AIBase import AIBase
from libs.AI2D import Ai2d
from media.display import Display
from media.media import ALIGN_UP
from media.sensor import *


CJK_FONT = "/sdcard/res/font/AlibabaPuHuiTi-3-45-Light.ttf"

_TEXT = {
    "zh_CN": {
        "action": "捕获并注册", "name_title": "输入类别名称", "database": "注册类别",
        "ready": "将物体放入框内，可识别或注册", "name_first": "请先输入类别名称",
        "capturing": "正在捕获框内物体...", "saving": "正在保存类别...",
        "cancelled": "已取消注册", "querying": "正在查询注册类别...",
        "clearing": "正在清空自学习数据库...", "cleared": "已清空 %d 个学习样本",
        "found": "已查询到 %d 个注册类别", "db_failed": "数据库操作失败",
        "registered": "已注册类别: %s", "save_failed": "保存失败: %s",
        "loaded": "已加载 %d 个学习样本", "captured": "已捕获，请输入类别名称",
        "feature_failed": "特征捕获失败", "recognized": "识别结果: %s",
        "unknown": "未识别，可点击按钮注册", "empty": "暂无类别，请捕获并注册",
        "captured_badge": "已捕获，等待命名", "pending_badge": "待注册物体",
    },
    "en_US": {
        "action": "Capture & enroll", "name_title": "Enter category name",
        "database": "Registered Categories", "ready": "Place an object in the frame to classify or enroll",
        "name_first": "Enter a category name first", "capturing": "Capturing object...",
        "saving": "Saving category...", "cancelled": "Enrollment cancelled",
        "querying": "Loading registered categories...", "clearing": "Clearing self-learning database...",
        "cleared": "Cleared %d learned samples", "found": "Found %d registered categories",
        "db_failed": "Database operation failed", "registered": "Category enrolled: %s",
        "save_failed": "Save failed: %s", "loaded": "Loaded %d learned samples",
        "captured": "Captured; enter a category name", "feature_failed": "Feature capture failed",
        "recognized": "Result: %s", "unknown": "Unknown; tap Capture to enroll",
        "empty": "No categories; capture one to enroll", "captured_badge": "CAPTURED",
        "pending_badge": "NOT ENROLLED",
    },
}


def _t(key, *values):
    value = _TEXT[i18n.language()].get(key, key)
    return value % values if values else value


class _SelfLearningModel(AIBase):
    """Feature extractor owned only by the self-learning application."""

    def __init__(self, model_path, rgb_size, roi):
        try:
            self.model_size = [224, 224]
            self.rgb_size = rgb_size
            self.roi = roi
            AIBase.__init__(self, model_path, self.model_size, rgb_size, 0)
            self.ai2d = Ai2d(0)
            self.ai2d.set_ai2d_dtype(
                nn.ai2d_format.NCHW_FMT, nn.ai2d_format.NCHW_FMT,
                np.uint8, np.uint8)
            self._deinited = False
        except BaseException:
            # The caller cannot own this model until construction returns.
            try:
                self.deinit()
            except Exception as error:
                print("model constructor cleanup failed:", error)
            raise

    def config_preprocess(self):
        x, y, width, height = self.roi
        self.ai2d.crop(x, y, width, height)
        self.ai2d.resize(nn.interp_method.tf_bilinear,
                         nn.interp_mode.half_pixel)
        self.ai2d.build([1, 3, self.rgb_size[1], self.rgb_size[0]],
                        [1, 3, self.model_size[1], self.model_size[0]])

    def postprocess(self, results):
        return results[0][0]

    def deinit(self):
        if getattr(self, "_deinited", False):
            return
        AIBase.deinit(self)
        self._deinited = True


class _SelfLearningDatabase:
    """Persistent multi-sample category database local to this application."""

    INVALID_FILENAME_CHARS = '/\\:*?"<>|'

    def __init__(self, directory, threshold=0.5, max_features=200):
        self.directory = directory if directory.endswith('/') \
            else directory + '/'
        self.threshold = threshold
        self.max_features = max_features
        self.feature_size = 0
        self.labels = []
        self.features = []
        self._ensure_directory()

    def _ensure_directory(self):
        try:
            os.stat(self.directory)
        except OSError:
            os.mkdir(self.directory[:-1])

    @classmethod
    def sanitize_name(cls, name):
        name = name.strip()
        chars = []
        for char in name:
            if char in cls.INVALID_FILENAME_CHARS or ord(char) < 32:
                chars.append('_')
            else:
                chars.append(char)
        safe = ''.join(chars).strip(' .')
        if len(safe) > 24:
            safe = safe[:24]
        if not safe:
            raise ValueError('invalid category name')
        return safe

    @staticmethod
    def _normalize(feature):
        norm = np.linalg.norm(feature)
        if norm <= 0:
            raise ValueError('empty feature')
        return feature / norm

    @staticmethod
    def _label_from_filename(filename):
        stem = filename[:-4]
        split = stem.rfind('_')
        if split <= 0:
            return stem
        try:
            int(stem[split + 1:])
            return stem[:split]
        except Exception:
            return stem

    def load(self, feature_size):
        self.feature_size = int(feature_size)
        self.labels = []
        self.features = []
        try:
            files = os.listdir(self.directory)
        except OSError:
            return 0
        files.sort()
        for filename in files:
            if not filename.endswith('.bin'):
                continue
            if len(self.features) >= self.max_features:
                break
            try:
                with open(self.directory + filename, 'rb') as file:
                    feature = np.frombuffer(file.read(), dtype=np.float)
                if len(feature) != self.feature_size:
                    print('SelfLearning: skip invalid feature', filename)
                    continue
                self.features.append(self._normalize(feature))
                self.labels.append(self._label_from_filename(filename))
            except Exception as error:
                print('SelfLearning: load failed %s: %s' %
                      (filename, error))
        print('SelfLearning: loaded %d sample(s)' % len(self.features))
        return len(self.features)

    def _next_path(self, safe_name):
        for index in range(1000):
            path = self.directory + safe_name + '_%03d.bin' % index
            try:
                os.stat(path)
            except OSError:
                return path
        raise ValueError('too many samples for category')

    def save(self, name, feature):
        if len(self.features) >= self.max_features:
            raise ValueError('feature database is full')
        if feature is None:
            raise ValueError('invalid feature')
        if self.feature_size <= 0:
            self.feature_size = len(feature)
        if len(feature) != self.feature_size:
            raise ValueError('invalid feature size')

        safe_name = self.sanitize_name(name)
        normalized = self._normalize(feature)
        path = self._next_path(safe_name)
        data = feature.tobytes()
        with open(path, 'wb') as file:
            file.write(data)
        if os.stat(path)[6] != len(data):
            raise OSError('feature write size mismatch')
        sync = getattr(os, 'sync', None)
        if sync:
            try:
                sync()
            except Exception as error:
                print('SelfLearning: sync warning:', error)

        self.labels.append(safe_name)
        self.features.append(normalized)
        print('SelfLearning: saved %s to %s' % (safe_name, path))
        return safe_name

    def list_categories(self):
        """Return sorted (category, sample_count) rows for the query UI."""
        counts = {}
        if self.feature_size > 0:
            labels = self.labels
        else:
            labels = []
            try:
                files = os.listdir(self.directory)
            except OSError:
                files = []
            for filename in files:
                if filename.endswith('.bin'):
                    labels.append(self._label_from_filename(filename))
        for label in labels:
            counts[label] = counts.get(label, 0) + 1
        names = list(counts.keys())
        names.sort()
        return [(name, counts[name]) for name in names]

    def clear(self):
        """Delete all persisted samples and reset the memory search index."""
        removed = 0
        failed = 0
        try:
            files = os.listdir(self.directory)
        except OSError:
            files = []
        for filename in files:
            if not filename.endswith('.bin'):
                continue
            try:
                os.remove(self.directory + filename)
                removed += 1
            except OSError as error:
                failed += 1
                print('SelfLearning: remove failed %s: %s' %
                      (filename, error))
        self.labels = []
        self.features = []
        sync = getattr(os, 'sync', None)
        if sync:
            try:
                sync()
            except Exception as error:
                print('SelfLearning: sync warning:', error)
        if failed:
            raise OSError('failed to remove %d sample(s)' % failed)
        print('SelfLearning: removed %d sample(s)' % removed)
        return removed

    def search(self, feature):
        if not self.features:
            return 'unknown', 0.0
        norm = np.linalg.norm(feature)
        if norm <= 0:
            return 'unknown', 0.0
        best_index = -1
        best_score = -1.0
        for index in range(len(self.features)):
            score = float(np.dot(feature, self.features[index]) / norm)
            if score > best_score:
                best_index = index
                best_score = score
        if best_index < 0 or best_score < self.threshold:
            return 'unknown', best_score
        return self.labels[best_index], best_score


class SelfLearningDemo(Application):
    name = "自学习分类"
    model_path = config.KMODEL_DIR + "recognition.kmodel"
    database_dir = config.UTILS_DIR + "self_learning/"

    ui_action_label = "捕获并注册"
    ui_name_input = True
    ui_name_title = "输入类别名称"
    ui_name_placeholder = "Enter category name"
    ui_database = True
    ui_database_title = "Registered Categories"

    rgb_size = [640, 360]
    model_size = [224, 224]
    recognition_threshold = 0.5
    max_features = 200

    SENSOR_ID = 2
    SENSOR_FPS = 60
    DISPLAY_CHANNEL = CAM_CHN_ID_0
    AI_CHANNEL = CAM_CHN_ID_2
    DISPLAY_FORMAT = Sensor.YUV420SP
    AI_FORMAT = Sensor.RGBP888
    VIDEO_LAYER = Display.LAYER_VIDEO1

    @classmethod
    def localized_ui(cls):
        return {"action_label": _t("action"),
                "name_title": _t("name_title"),
                "name_placeholder": "Enter category name",
                "database_title": _t("database")}

    def __init__(self):
        Application.__init__(self)
        self._strings = _TEXT[i18n.language()]
        self.rgb_size = [ALIGN_UP(self.rgb_size[0], 16), self.rgb_size[1]]
        self.display_size = [ALIGN_UP(config.CAM_WIN_W, 16),
                             config.CAM_WIN_H]
        roi_size = min(240, self.rgb_size[1] - 32,
                       self.rgb_size[0] - 32)
        roi_size = max(64, roi_size)
        self.roi = [(self.rgb_size[0] - roi_size) // 2,
                    (self.rgb_size[1] - roi_size) // 2,
                    roi_size, roi_size]

        self.sensor = None
        self._video_bound = False
        self._ai_img = None
        self._osd_img = None
        self._capture_requested = False
        self._pending_feature = None
        self._submitted_name = None
        self._database_command = None
        self._database_loaded = False
        self._last_status = None
        self._status_hold_frames = 0
        self._model = None
        self._database = _SelfLearningDatabase(
            self.database_dir, self.recognition_threshold,
            self.max_features)

        try:
            self._model = _SelfLearningModel(
                self.model_path, self.rgb_size, self.roi)
            self._model.config_preprocess()
        except Exception:
            self.deinit()
            raise

    def _msg(self, key, *values):
        value = self._strings.get(key, key)
        return value % values if values else value

    def open(self):
        if self._opened or self.stop_req:
            return
        sensor = Sensor(id=self.SENSOR_ID)
        self.sensor = sensor
        sensor.reset()
        sensor.set_framesize(w=self.display_size[0], h=self.display_size[1],
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
                                    self.display_size[1], image.ARGB8888)
        self.start()
        self._opened = True
        self._set_status(self._msg("ready"), config.THEME_GREEN)

    def request_action(self):
        """LVGL thread entry: request one feature capture only."""
        if self.stop_req or self._database_command is not None:
            return
        if self._pending_feature is not None:
            self._set_status(self._msg("name_first"), config.THEME_ORANGE)
            return
        if not self._capture_requested:
            self._capture_requested = True
            self._set_status(self._msg("capturing"), config.THEME_ORANGE)

    def submit_name(self, name):
        """LVGL thread entry: defer SD-card access to the worker thread."""
        if self._pending_feature is None:
            return
        self._submitted_name = name
        if name:
            self._set_status(self._msg("saving"), config.THEME_ORANGE)
        else:
            self._set_status(self._msg("cancelled"),
                             config.THEME_ORANGE, 20)

    def request_database_query(self):
        """LVGL-thread entry: submit a query command only."""
        if not self.stop_req and self._database_command is None and \
                not self._capture_requested and \
                self._pending_feature is None:
            self._database_command = "query"
            self._set_status(self._msg("querying"), config.THEME_ORANGE)
            return True
        return False

    def request_database_clear(self):
        """LVGL-thread entry: submit clear after LVGL confirmation."""
        if not self.stop_req and self._database_command is None and \
                not self._capture_requested and \
                self._pending_feature is None:
            self._database_command = "clear"
            self._set_status(self._msg("clearing"),
                             config.THEME_ORANGE)
            return True
        return False

    def _process_database_command(self):
        command = self._database_command
        if command is None:
            return
        self._database_command = None
        try:
            if command == "clear":
                removed = self._database.clear()
                self._database_loaded = False
                self._set_status(self._msg("cleared", removed),
                                 config.THEME_GREEN, 30)
            rows = self._database.list_categories()
            if command == "query":
                self._set_status(self._msg("found", len(rows)),
                                 config.THEME_GREEN, 20)
            config.demo_ui_request = ("database_rows", rows)
        except Exception as error:
            if command == "clear":
                self._database_loaded = False
            print("SelfLearningDemo: database command failed:", error)
            self._set_status(self._msg("db_failed"), config.THEME_RED, 40)
            config.demo_ui_request = ("database_error", str(error))

    def _save_submitted_feature(self):
        name = self._submitted_name
        if name is None:
            return False
        self._submitted_name = None
        feature = self._pending_feature
        self._pending_feature = None
        if not name or feature is None:
            return True
        try:
            saved_name = self._database.save(name, feature)
            self._set_status(self._msg("registered", saved_name),
                             config.THEME_GREEN, 30)
        except Exception as error:
            print("SelfLearningDemo: save failed:", error)
            reason = str(error)
            if len(reason) > 30:
                reason = reason[:30]
            self._set_status(self._msg("save_failed", reason),
                             config.THEME_RED, 40)
        return True

    def run_once(self):
        self._process_database_command()
        if self._save_submitted_feature():
            self._resume_live_preview()

        # OSD0 contains the opaque captured frame while the LVGL keyboard is
        # open. Do not acquire or infer another frame until the user saves or
        # cancels, so the displayed object and registered feature stay exact.
        if self._pending_feature is not None:
            time.sleep_ms(20)
            return None

        self._ai_img = self.sensor.snapshot(chn=self.AI_CHANNEL)
        feature = self._model.run(self._ai_img.to_numpy_ref())
        if not self._database_loaded:
            count = self._database.load(len(feature))
            self._database_loaded = True
            if count:
                self._set_status(self._msg("loaded", count),
                                 config.THEME_GREEN, 20)

        if self._capture_requested:
            self._capture_requested = False
            try:
                self._pending_feature = feature.copy()
                self._show_frozen_frame(self._ai_img)
                self._ai_img = None
                config.demo_ui_request = "name_input"
                self._set_status(self._msg("captured"),
                                 config.THEME_ORANGE)
            except Exception as error:
                print("SelfLearningDemo: capture failed:", error)
                self._pending_feature = None
                self._resume_live_preview()
                self._set_status(self._msg("feature_failed"),
                                 config.THEME_RED)

        if self._pending_feature is not None:
            return None
        label, score = self._database.search(feature)
        known = label != 'unknown'
        self._osd_img.clear()
        self._draw_result(label, score, known)
        self.display.show(self._osd_img)

        if self._status_hold_frames > 0:
            self._status_hold_frames -= 1
        elif self._pending_feature is None and self._submitted_name is None:
            if known:
                self._set_status(self._msg("recognized", label),
                                 config.THEME_GREEN)
            elif self._database.features:
                self._set_status(self._msg("unknown"),
                                 config.THEME_ORANGE)
            else:
                self._set_status(self._msg("empty"),
                                 config.THEME_ORANGE)
        return 1 if known else 0

    def _display_roi(self):
        x, y, width, height = self.roi
        draw_x = int(round(x * self.display_size[0] / self.rgb_size[0]))
        draw_y = int(round(y * self.display_size[1] / self.rgb_size[1]))
        draw_w = int(round(width * self.display_size[0] /
                           self.rgb_size[0]))
        draw_h = int(round(height * self.display_size[1] /
                           self.rgb_size[1]))
        return draw_x, draw_y, draw_w, draw_h

    def _show_frozen_frame(self, captured_img):
        """Show the captured AI frame as one opaque, full-screen OSD0 image."""
        self.display.clear()
        self._osd_img = None
        gc.collect()

        chw = captured_img.to_numpy_ref()
        pixels = self.rgb_size[0] * self.rgb_size[1]
        hwc = chw.reshape((3, pixels)).transpose().copy().reshape(
            (self.rgb_size[1], self.rgb_size[0], 3))
        native_img = image.Image(self.rgb_size[0], self.rgb_size[1],
                                 image.RGB888, alloc=image.ALLOC_REF,
                                 data=hwc)
        frozen_display = native_img.to_rgb888(
            x_size=self.display_size[0], y_size=self.display_size[1])

        x, y, width, height = self._display_roi()
        frozen_display.draw_rectangle(
            x, y, width, height, color=(0, 0, 0), thickness=7)
        frozen_display.draw_rectangle(
            x, y, width, height, color=(255, 159, 10), thickness=3)
        self.display.show(frozen_display)

        frozen_display = None
        native_img = None
        hwc = None
        chw = None
        gc.collect()

    def _resume_live_preview(self):
        """Replace the opaque freeze frame with a transparent OSD0 canvas."""
        if self.display is None or self.stop_req:
            return
        self.display.clear()
        gc.collect()
        self._osd_img = image.Image(self.display_size[0],
                                    self.display_size[1], image.ARGB8888)

    def _draw_result(self, label, score, known):
        draw_x, draw_y, draw_w, draw_h = self._display_roi()
        if self._pending_feature is not None:
            text = self._msg("captured_badge")
            color = visual.ORANGE
            draw_score = None
        elif known:
            text = label
            color = visual.GREEN
            draw_score = score
        elif self._database.features:
            text = "UNKNOWN"
            color = visual.RED
            draw_score = None
        else:
            text = self._msg("pending_badge")
            color = visual.CYAN
            draw_score = None
        visual.draw_detection(
            self._osd_img, draw_x, draw_y, draw_w, draw_h,
            label=text, score=draw_score, color=color,
            font_size=22, font=CJK_FONT)

    def _set_status(self, text, color, hold_frames=0):
        if hold_frames > self._status_hold_frames:
            self._status_hold_frames = hold_frames
        value = (text, color)
        if value == self._last_status:
            return
        self._last_status = value
        config.demo_status_text = text
        config.demo_status_color = color

    def stop(self):
        Application.stop(self)
        self._capture_requested = False
        if self._database_command == "clear":
            self._process_database_command()
        self._database_command = None
        self._save_submitted_feature()
        self._pending_feature = None
        self._submitted_name = None
        sensor = self.sensor
        self.sensor = None
        self._ai_img = None
        if self.display is not None:
            self.display.clear()
        if self._video_bound:
            try:
                Display.disable_layer(self.VIDEO_LAYER)
            except Exception as error:
                print("SelfLearningDemo: video disable failed:", error)
            self._video_bound = False
        if sensor is not None:
            try:
                sensor.stop()
            except Exception as error:
                print("SelfLearningDemo: sensor stop failed:", error)

    def deinit(self):
        model = self._model
        self._model = None
        if model is not None:
            deinit_with_retry(model)

    def _release_owned_resources(self):
        self._osd_img = None
        self._database = None
