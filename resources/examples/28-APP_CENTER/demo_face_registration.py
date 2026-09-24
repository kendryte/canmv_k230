# demo_face_registration.py - Interactive lite face registration application

import gc
import time

import image
import config
import i18n
import app_visual as visual
import demo_common
from media.sensor import *
from media.display import Display
from media.media import ALIGN_UP
from app_contract import Application
from face_lite import FaceDetectorLite, FaceEmbeddingLite, FaceFeatureDatabase


_TEXT = {
    "zh_CN": {
        "action": "注册人脸", "database": "注册人员", "name_title": "输入注册姓名",
        "ready": "点击按钮开始注册", "name_first": "请先输入姓名",
        "detecting": "正在检测人脸...", "saving": "正在保存...", "cancelled": "已取消",
        "querying": "正在查询注册人员...", "clearing": "正在清空人脸数据库...",
        "cleared": "已清空 %d 位注册人员", "found": "已查询到 %d 位注册人员",
        "db_failed": "数据库操作失败", "registered": "已注册: %s",
        "save_failed": "保存失败: %s", "enter_name": "请输入注册姓名",
        "feature_failed": "人脸特征提取失败", "no_face": "未检测到人脸",
        "one_face": "画面中只能有一张人脸",
    },
    "en_US": {
        "action": "Enroll face", "database": "Registered Faces",
        "name_title": "Enter registration name", "ready": "Tap Enroll to capture",
        "name_first": "Enter a name first", "detecting": "Detecting face...",
        "saving": "Saving...", "cancelled": "Cancelled",
        "querying": "Loading registered faces...", "clearing": "Clearing face database...",
        "cleared": "Cleared %d registered faces", "found": "Found %d registered faces",
        "db_failed": "Database operation failed", "registered": "Enrolled: %s",
        "save_failed": "Save failed: %s", "enter_name": "Enter a registration name",
        "feature_failed": "Face feature extraction failed", "no_face": "No face detected",
        "one_face": "Only one face is allowed",
    },
}


def _t(key, *values):
    value = _TEXT[i18n.language()].get(key, key)
    return value % values if values else value


class FaceRegistrationDemo(Application):
    name = "人脸注册"
    model_path = demo_common.FACE_DET_KMODEL
    embedding_model = config.KMODEL_DIR + "face_recognition_mobile.kmodel"
    database_dir = config.UTILS_DIR + "db/"
    required_files = [demo_common.FACE_ANCHOR_FILE, embedding_model]

    # Used by runner/overlay to add the registration control and name dialog.
    ui_action_label = "注册人脸"
    ui_name_input = True
    ui_database = True
    ui_database_title = "Registered Faces"

    rgb_size = [640, 360]
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
                "name_placeholder": "Name",
                "database_title": _t("database")}

    def __init__(self):
        Application.__init__(self)
        self.rgb_size = [ALIGN_UP(self.rgb_size[0], 16), self.rgb_size[1]]
        self.display_size = [ALIGN_UP(config.CAM_WIN_W, 16),
                             config.CAM_WIN_H]
        self.sensor = None
        self._ai_img = None
        self._osd_img = None
        self._video_bound = False
        self._capture_requested = False
        self._pending_feature = None
        self._submitted_name = None
        self._database_command = None
        self._detector = None
        self._embedding = None
        self._database = FaceFeatureDatabase(self.database_dir)

        try:
            anchors = demo_common.load_face_anchors()
            self._detector = FaceDetectorLite(
                self.model_path, self.rgb_size, anchors)
            self._embedding = FaceEmbeddingLite(
                self.embedding_model, self.rgb_size)
            self._detector.config_preprocess()
        except Exception:
            self.deinit()
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
        self.start()
        self._opened = True
        self._set_status(_t("ready"), config.THEME_GREEN)

    def request_action(self):
        """Called by the LVGL thread; only update atomic Python state."""
        if self.stop_req or self._database_command is not None:
            return
        if self._pending_feature is not None:
            self._set_status(_t("name_first"), config.THEME_ORANGE)
            return
        if not self._capture_requested:
            self._capture_requested = True
            self._set_status(_t("detecting"), config.THEME_ORANGE)

    def submit_name(self, name):
        """Called by the LVGL thread; filesystem work remains in run_once()."""
        if self._pending_feature is None:
            return
        self._submitted_name = name
        if name:
            self._set_status(_t("saving"), config.THEME_ORANGE)
        else:
            self._set_status(_t("cancelled"), config.THEME_ORANGE)

    def request_database_query(self):
        """LVGL-thread entry: submit a query command only."""
        if not self.stop_req and self._database_command is None and \
                not self._capture_requested and \
                self._pending_feature is None:
            self._database_command = "query"
            self._set_status(_t("querying"), config.THEME_ORANGE)
            return True
        return False

    def request_database_clear(self):
        """LVGL-thread entry: submit a destructive command after UI confirm."""
        if not self.stop_req and self._database_command is None and \
                not self._capture_requested and \
                self._pending_feature is None:
            self._database_command = "clear"
            self._set_status(_t("clearing"), config.THEME_ORANGE)
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
                self._set_status(_t("cleared", removed),
                                 config.THEME_GREEN)
            rows = self._database.list_names()
            if command == "query":
                self._set_status(_t("found", len(rows)),
                                 config.THEME_GREEN)
            config.demo_ui_request = ("database_rows", rows)
        except Exception as error:
            print("FaceRegistrationDemo: database command failed:", error)
            self._set_status(_t("db_failed"), config.THEME_RED)
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
            self._set_status(_t("registered", saved_name), config.THEME_GREEN)
        except Exception as error:
            print("FaceRegistrationDemo: save failed:", error)
            # Keep the reason visible on the device as well as the serial log;
            # this is especially useful for SD-card and invalid-name errors.
            reason = str(error)
            if len(reason) > 32:
                reason = reason[:32]
            self._set_status(_t("save_failed", reason), config.THEME_RED)
        return True

    def run_once(self):
        self._process_database_command()
        if self._save_submitted_feature():
            self._resume_live_preview()

        # OSD0 keeps the captured RGB frame while the name keyboard is open.
        # Do not acquire or infer another frame until save/cancel completes.
        if self._pending_feature is not None:
            time.sleep_ms(20)
            return None

        self._ai_img = self.sensor.snapshot(chn=self.AI_CHANNEL)
        input_np = self._ai_img.to_numpy_ref()
        dets, landmarks = self._detector.run(input_np)
        face_count = len(dets) if dets is not None else 0

        if self._capture_requested:
            self._capture_requested = False
            if face_count == 1 and len(landmarks) == 1:
                try:
                    self._embedding.config_preprocess(landmarks[0])
                    feature = self._embedding.run(input_np)
                    self._pending_feature = feature.copy()
                    self._show_frozen_frame(self._ai_img, dets[0])
                    self._ai_img = None
                    config.demo_ui_request = "face_name"
                    self._set_status(_t("enter_name"), config.THEME_ORANGE)
                except Exception as error:
                    print("FaceRegistrationDemo: feature failed:", error)
                    self._pending_feature = None
                    if self._osd_img is None:
                        self._resume_live_preview()
                    self._set_status(_t("feature_failed"), config.THEME_RED)
            elif face_count == 0:
                self._set_status(_t("no_face"), config.THEME_RED)
            else:
                self._set_status(_t("one_face"), config.THEME_RED)

        if self._pending_feature is not None:
            return None
        self._osd_img.clear()
        self._draw_faces(dets, face_count == 1)
        self.display.show(self._osd_img)
        return face_count

    def _display_box(self, det):
        raw_x = int(round(det[0])) * self.display_size[0] // self.rgb_size[0]
        raw_y = int(round(det[1])) * self.display_size[1] // self.rgb_size[1]
        raw_w = int(round(det[2])) * self.display_size[0] // self.rgb_size[0]
        raw_h = int(round(det[3])) * self.display_size[1] // self.rgb_size[1]
        x = max(0, min(self.display_size[0] - 2, raw_x))
        y = max(0, min(self.display_size[1] - 2, raw_y))
        x2 = max(x + 1, min(self.display_size[0], raw_x + raw_w))
        y2 = max(y + 1, min(self.display_size[1], raw_y + raw_h))
        return x, y, x2 - x, y2 - y

    def _show_frozen_frame(self, captured_img, det):
        """Show the exact registered frame as an opaque full-screen OSD0."""
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

        x, y, width, height = self._display_box(det)
        frozen_display.draw_rectangle(
            x, y, width, height, color=(0, 0, 0), thickness=7)
        frozen_display.draw_rectangle(
            x, y, width, height, color=(48, 209, 88), thickness=3)
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

    def _draw_faces(self, dets, single_face):
        if dets is None:
            return
        color = (255, 48, 209, 88) if single_face \
            else (255, 255, 159, 10)
        for det in dets:
            x, y, w, h = self._display_box(det)
            visual.draw_detection(
                self._osd_img, x, y, w, h,
                label="READY" if single_face else "ONE FACE ONLY",
                color=color)

    @staticmethod
    def _set_status(text, color):
        config.demo_status_text = text
        config.demo_status_color = color

    def stop(self):
        Application.stop(self)
        self._capture_requested = False
        if self._database_command == "clear":
            self._process_database_command()
        self._database_command = None
        # A user may confirm the keyboard and immediately leave the app before
        # the next frame begins.  Persist that already-submitted registration
        # before releasing the pending feature.
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
                print("FaceRegistrationDemo: video disable failed:", error)
            self._video_bound = False
        if sensor is not None:
            try:
                sensor.stop()
            except Exception as error:
                print("FaceRegistrationDemo: sensor stop failed:", error)

    def deinit(self):
        detector = self._detector
        embedding = self._embedding
        self._detector = None
        self._embedding = None
        if detector is not None:
            detector.deinit()
        if embedding is not None:
            embedding.deinit()

    def _release_owned_resources(self):
        self._osd_img = None
        self._database = None
