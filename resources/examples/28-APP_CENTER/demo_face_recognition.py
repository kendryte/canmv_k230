# demo_face_recognition.py - Live lite face recognition application

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
    "zh_CN": {"loaded": "已加载 %d 张人脸", "empty": "数据库为空，请先注册"},
    "en_US": {"loaded": "Loaded %d faces", "empty": "Database is empty; enroll a face first"},
}


def _t(key, *values):
    value = _TEXT[i18n.language()].get(key, key)
    return value % values if values else value


class FaceRecognitionDemo(Application):
    name = "人脸识别"
    model_path = demo_common.FACE_DET_KMODEL
    embedding_model = config.KMODEL_DIR + "face_recognition_mobile.kmodel"
    database_dir = config.UTILS_DIR + "db/"
    required_files = [demo_common.FACE_ANCHOR_FILE, embedding_model]

    rgb_size = [640, 360]
    SENSOR_ID = 2
    SENSOR_FPS = 60
    DISPLAY_CHANNEL = CAM_CHN_ID_0
    AI_CHANNEL = CAM_CHN_ID_2
    DISPLAY_FORMAT = Sensor.YUV420SP
    AI_FORMAT = Sensor.RGBP888
    VIDEO_LAYER = Display.LAYER_VIDEO1
    RECOGNITION_THRESHOLD = 0.75

    def __init__(self):
        Application.__init__(self)
        self.rgb_size = [ALIGN_UP(self.rgb_size[0], 16), self.rgb_size[1]]
        self.display_size = [ALIGN_UP(config.CAM_WIN_W, 16),
                             config.CAM_WIN_H]
        self.sensor = None
        self._ai_img = None
        self._osd_img = None
        self._video_bound = False
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
        registered = self._database.load()
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
        if registered:
            self._set_status(_t("loaded", registered),
                             config.THEME_GREEN)
        else:
            self._set_status(_t("empty"), config.THEME_ORANGE)

    def run_once(self):
        self._ai_img = self.sensor.snapshot(chn=self.AI_CHANNEL)
        input_np = self._ai_img.to_numpy_ref()
        dets, landmarks = self._detector.run(input_np)
        face_count = len(dets) if dets is not None else 0
        results = []

        for landmark in landmarks:
            if self.stop_req:
                break
            if not self._database.features:
                results.append(("unknown", 0.0))
                continue
            try:
                self._embedding.config_preprocess(landmark)
                feature = self._embedding.run(input_np)
                results.append(self._database.search(
                    feature, self.RECOGNITION_THRESHOLD))
            except Exception as error:
                print("FaceRecognitionDemo: recognition failed:", error)
                results.append(("unknown", 0.0))

        self._osd_img.clear()
        self._draw_results(dets, results)
        self.display.show(self._osd_img)
        return face_count

    def _draw_results(self, dets, results):
        if dets is None:
            return
        for index, det in enumerate(dets):
            name, score = results[index] if index < len(results) \
                else ("unknown", 0.0)
            known = name != "unknown"
            color = (255, 48, 209, 88) if known \
                else (255, 255, 69, 58)
            x = int(round(det[0])) * self.display_size[0] // self.rgb_size[0]
            y = int(round(det[1])) * self.display_size[1] // self.rgb_size[1]
            w = int(round(det[2])) * self.display_size[0] // self.rgb_size[0]
            h = int(round(det[3])) * self.display_size[1] // self.rgb_size[1]
            visual.draw_detection(
                self._osd_img, x, y, w, h,
                label=name if known else "UNKNOWN",
                score=score if known else None, color=color)

    @staticmethod
    def _set_status(text, color):
        config.demo_status_text = text
        config.demo_status_color = color

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
                print("FaceRecognitionDemo: video disable failed:", error)
            self._video_bound = False
        if sensor is not None:
            try:
                sensor.stop()
            except Exception as error:
                print("FaceRecognitionDemo: sensor stop failed:", error)

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
