from model_cleanup import deinit_with_retry
# demo_face_parse.py - Face parsing demo (face region segmentation)

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


class _FaceParseModel(AIBase):
    def __init__(self, kmodel_path, model_input_size, rgb_size, disp_size):
        try:
            super().__init__(kmodel_path, model_input_size, rgb_size, 0)
            self.model_input_size = model_input_size
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

    def get_affine_matrix(self, bbox):
        x1, y1, w, h = map(lambda x: int(round(x, 0)), bbox[:4])
        if w <= 0 or h <= 0:
            return [1.0, 0, 0, 0, 1.0, 0]
        edge_size = self.model_input_size[1]
        trans_distance = edge_size / 2.0
        center_x = x1 + w / 2.0
        center_y = y1 + h / 2.0
        maximum_edge = 2.7 * (h if h > w else w)
        scale = edge_size * 2.0 / maximum_edge
        cx = trans_distance - scale * center_x
        cy = trans_distance - scale * center_y
        return [scale, 0, cx, 0, scale, cy]

    def config_preprocess(self, det, input_size=None):
        s = input_size if input_size else self.rgb888p_size
        matrix_dst = self.get_affine_matrix(det)
        self.ai2d.affine(nn.interp_method.cv2_bilinear, 0, 0, 127, 1, matrix_dst)
        self.ai2d.build([1, 3, s[1], s[0]], [1, 3, self.model_input_size[1], self.model_input_size[0]])

    def postprocess(self, results):
        return results[0]


class FaceParseDemo(Application):
    name = "人脸解析"
    model_path = demo_common.FACE_DET_KMODEL
    rgb_size = [1280, 720]
    required_files = [
        demo_common.FACE_ANCHOR_FILE,
        config.KMODEL_DIR + "face_parse.kmodel",
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
        # Reused per-frame parse buffer (see draw_result); allocated in open().
        self._draw_np = None
        self._draw_img = None
        self._video_bound = False
        self.parse_input_size = [320, 320]
        # Roll back partially-created sub-models on failure: a create() error
        # means runner never calls close(), so any KPU/AI2D already allocated
        # here must be released before re-raising.
        self.face_det = None
        self.face_parse = None
        try:
            self.face_det = demo_common.FaceDetSubModel(self.rgb_size,
                                                        self.display_size)
            self.face_det.config_preprocess()
            self.face_parse = _FaceParseModel(
                config.KMODEL_DIR + "face_parse.kmodel",
                self.parse_input_size, self.rgb_size, self.display_size)
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
        # Preallocate the parse compositing buffer once and reuse it every
        # frame instead of allocating a full-screen ARGB buffer per frame.
        self._draw_np = np.zeros(
            (self.display_size[1], self.display_size[0], 4), dtype=np.uint8)
        self._draw_img = image.Image(
            self.display_size[0], self.display_size[1],
            image.ARGB8888, alloc=image.ALLOC_REF, data=self._draw_np)
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
                print("FaceParseDemo: video layer disable failed:", e)
            self._video_bound = False
        if sensor is not None:
            try:
                sensor.stop()
            except Exception as e:
                print("FaceParseDemo: sensor stop failed:", e)

    def _release_owned_resources(self):
        self._osd_img = None
        self._draw_img = None
        self._draw_np = None

    def run(self, input_np):
        det_boxes = self.face_det.run(input_np)
        parse_res = []
        for det in det_boxes:
            self.face_parse.config_preprocess(det)
            res = self.face_parse.run(input_np)
            parse_res.append(res)
        return det_boxes, parse_res

    def draw_result(self, img, result):
        dets, parse_res = result
        count = len(dets) if dets else 0
        if dets:
            draw_np = self._draw_np
            draw_img = self._draw_img
            # Clear the reused buffer (also resets alpha) before compositing.
            draw_img.clear()
            for i, det in enumerate(dets):
                aidemo.face_parse_post_process(
                    draw_np, self.rgb_size, self.display_size,
                    self.parse_input_size[0], det.tolist(), parse_res[i]
                )
            draw_img.copy_to(img)
            visual.draw_mode_badge(img, "FACE PARSING", visual.VIOLET)
        return count

    def deinit(self):
        for model in (self.face_det, self.face_parse):
            if model is None:
                continue
            try:
                deinit_with_retry(model)
            except Exception as e:
                print("FaceParseDemo: model deinit failed:", e)
        gc.collect()
