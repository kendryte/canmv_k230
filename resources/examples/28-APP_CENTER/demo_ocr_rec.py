from model_cleanup import deinit_with_retry
# demo_ocr_rec.py - OCR detection & recognition demo

import gc
import image
import ulab.numpy as np
import nncase_runtime as nn
import aicube
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

OCR_FONT = demo_common.CJK_FONT


class _OCRDetModel(AIBase):
    def __init__(self, kmodel_path, model_input_size, mask_thr, box_thr,
                 rgb_size, disp_size):
        try:
            super().__init__(kmodel_path, model_input_size, rgb_size, 0)
            self.model_input_size = model_input_size
            self.mask_threshold = mask_thr
            self.box_threshold = box_thr
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

    def _chw2hwc(self, features):
        s = (features.shape[0], features.shape[1], features.shape[2])
        c_hw = features.reshape((s[0], s[1] * s[2]))
        hw_c = c_hw.transpose()
        new_array = hw_c.copy()
        hwc = new_array.reshape((s[1], s[2], s[0]))
        del c_hw, hw_c, new_array
        return hwc

    def config_preprocess(self, input_size=None):
        s = input_size if input_size else self.rgb888p_size
        top, bottom, left, right, _ = letterbox_pad_param(self.rgb888p_size, self.model_input_size)
        self.ai2d.pad([0, 0, 0, 0, top, bottom, left, right], 0, [0, 0, 0])
        self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
        self.ai2d.build([1, 3, s[1], s[0]], [1, 3, self.model_input_size[1], self.model_input_size[0]])

    def postprocess(self, results):
        hwc_array = self._chw2hwc(self.cur_img)
        det_boxes = aicube.ocr_post_process(
            results[0][:, :, :, 0].reshape(-1), hwc_array.reshape(-1),
            self.model_input_size, self.rgb888p_size,
            self.mask_threshold, self.box_threshold
        )
        return det_boxes


class _OCRRecModel(AIBase):
    def __init__(self, kmodel_path, model_input_size, dict_path, rgb_size, disp_size):
        try:
            super().__init__(kmodel_path, model_input_size, rgb_size, 0)
            self.model_input_size = model_input_size
            self.rgb888p_size = [ALIGN_UP(rgb_size[0], 16), rgb_size[1]]
            self.display_size = [ALIGN_UP(disp_size[0], 16), disp_size[1]]
            self.dict_word = None
            self._read_dict(dict_path)
            self.ai2d = Ai2d(0)
            self.ai2d.set_ai2d_dtype(nn.ai2d_format.RGB_packed, nn.ai2d_format.NCHW_FMT, np.uint8, np.uint8)
        except BaseException:
            # The caller cannot own this model until construction returns.
            try:
                self.deinit()
            except Exception as error:
                print("model constructor cleanup failed:", error)
            raise

    def _read_dict(self, dict_path):
        if dict_path:
            with open(dict_path, 'r') as f:
                line_one = f.read(100000)
                line_list = line_one.split("\r\n")
            self.dict_word = {num: char.replace("\r", "").replace("\n", "")
                              for num, char in enumerate(line_list)}

    def config_preprocess(self, input_image_size=None, input_np=None):
        s = input_image_size if input_image_size else self.rgb888p_size
        top, bottom, left, right, _ = letterbox_pad_param(s, self.model_input_size)
        self.ai2d.pad([0, 0, 0, 0, top, bottom, left, right], 0, [0, 0, 0])
        self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
        self.ai2d.build(
            [input_np.shape[0], input_np.shape[1], input_np.shape[2], input_np.shape[3]],
            [1, 3, self.model_input_size[1], self.model_input_size[0]]
        )

    def postprocess(self, results):
        preds = np.argmax(results[0], axis=2).reshape((-1))
        output_txt = ""
        for i in range(len(preds)):
            if preds[i] != (len(self.dict_word) - 1) and \
               (not (i > 0 and preds[i - 1] == preds[i])):
                output_txt += self.dict_word[preds[i]]
        return output_txt


class OCRDetRecDemo(Application):
    name = "OCR 识别"
    rgb_size = [640, 360]
    required_files = [
        config.KMODEL_DIR + "ocr_det_int16.kmodel",
        config.KMODEL_DIR + "ocr_rec_int16.kmodel",
        config.UTILS_DIR + "dict.txt",
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
        dict_path = config.UTILS_DIR + "dict.txt"

        # Roll back partially-created sub-models on failure: a create() error
        # means runner never calls close(), so any KPU/AI2D already allocated
        # here must be released before re-raising.
        self.ocr_det = None
        self.ocr_rec = None
        try:
            self.ocr_det = _OCRDetModel(
                config.KMODEL_DIR + "ocr_det_int16.kmodel",
                [640, 640], 0.25, 0.3, self.rgb_size, self.display_size
            )
            self.ocr_det.config_preprocess()
            self.ocr_rec = _OCRRecModel(
                config.KMODEL_DIR + "ocr_rec_int16.kmodel",
                [512, 32], dict_path, self.rgb_size, self.display_size
            )
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
                print("OCRDetRecDemo: video layer disable failed:", e)
            self._video_bound = False
        if sensor is not None:
            try:
                sensor.stop()
            except Exception as e:
                print("OCRDetRecDemo: sensor stop failed:", e)

    def _release_owned_resources(self):
        self._osd_img = None

    def run(self, input_np):
        det_res = self.ocr_det.run(input_np)
        boxes = []
        ocr_res = []
        for det in det_res:
            self.ocr_rec.config_preprocess(
                input_image_size=[det[0].shape[2], det[0].shape[1]],
                input_np=det[0]
            )
            ocr_str = self.ocr_rec.run(det[0])
            ocr_res.append(ocr_str)
            boxes.append(det[1])
        # single collect after the loop: a full gc per box is very slow
        if det_res:
            gc.collect()
        return boxes, ocr_res

    def draw_result(self, img, result):
        det_res, rec_res = result
        count = len(det_res) if det_res else 0
        if det_res:
            for j in range(len(det_res)):
                points = []
                for i in range(4):
                    x = det_res[j][i * 2] / self.rgb_size[0] * \
                        self.display_size[0]
                    y = det_res[j][i * 2 + 1] / self.rgb_size[1] * \
                        self.display_size[1]
                    points.append((int(x), int(y)))
                label = rec_res[j] if j < len(rec_res) else "TEXT"
                visual.draw_polygon(
                    img, points, label=label, color=visual.BLUE,
                    font_size=20, font=OCR_FONT)
        return count

    def deinit(self):
        for model in (self.ocr_det, self.ocr_rec):
            if model is None:
                continue
            try:
                deinit_with_retry(model)
            except Exception as e:
                print("OCRDetRecDemo: model deinit failed:", e)
        gc.collect()
