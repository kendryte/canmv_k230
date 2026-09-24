from model_cleanup import deinit_with_retry
# demo_license_plate.py - License plate detection & recognition demo

import gc
import image
import ulab.numpy as np
import nncase_runtime as nn
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


class _LicenceDetModel(AIBase):
    def __init__(self, kmodel_path, model_input_size, conf_thr, nms_thr,
                 rgb_size, disp_size):
        try:
            super().__init__(kmodel_path, model_input_size, rgb_size, 0)
            self.model_input_size = model_input_size
            self.confidence_threshold = conf_thr
            self.nms_threshold = nms_thr
            self.max_boxes_num = 10
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
        top, bottom, left, right, _ = letterbox_pad_param(self.rgb888p_size, self.model_input_size)
        self.ai2d.pad([0, 0, 0, 0, top, bottom, left, right], 0, [128, 128, 128])
        self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
        self.ai2d.build([1, 3, s[1], s[0]], [1, 3, self.model_input_size[1], self.model_input_size[0]])

    def postprocess(self, results):
        new_result = results[0][0].transpose()
        det_res = aidemo.yolo_license_plate_det_postprocess(
            new_result.copy(), [self.rgb888p_size[1], self.rgb888p_size[0]],
            [self.model_input_size[1], self.model_input_size[0]],
            [self.display_size[1], self.display_size[0]],
            self.confidence_threshold, self.nms_threshold, self.max_boxes_num
        )
        return det_res


class _LicenceRecModel(AIBase):
    DICT_REC = [
        "挂", "使", "领", "澳", "港", "皖", "沪", "津", "渝", "冀",
        "晋", "蒙", "辽", "吉", "黑", "苏", "浙", "京", "闽", "赣",
        "鲁", "豫", "鄂", "湘", "粤", "桂", "琼", "川", "贵", "云",
        "藏", "陕", "甘", "青", "宁", "新", "警", "学",
        "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
        "A", "B", "C", "D", "E", "F", "G", "H", "J", "K",
        "L", "M", "N", "P", "Q", "R", "S", "T", "U", "V",
        "W", "X", "Y", "Z", "_", "-"
    ]

    def __init__(self, kmodel_path, model_input_size, rgb_size, disp_size):
        try:
            super().__init__(kmodel_path, model_input_size, rgb_size, 0)
            self.model_input_size = model_input_size
            self.rgb888p_size = [ALIGN_UP(rgb_size[0], 16), rgb_size[1]]
            self.display_size = [ALIGN_UP(disp_size[0], 16), disp_size[1]]
            self.dict_size = len(self.DICT_REC)
            self.ai2d = Ai2d(0)
            self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT, nn.ai2d_format.NCHW_FMT, np.uint8, np.uint8)
        except BaseException:
            # The caller cannot own this model until construction returns.
            try:
                self.deinit()
            except Exception as error:
                print("model constructor cleanup failed:", error)
            raise

    def config_preprocess(self, input_image_size=None):
        s = input_image_size if input_image_size else self.rgb888p_size
        self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
        self.ai2d.build([1, 3, s[1], s[0]], [1, 3, self.model_input_size[1], self.model_input_size[0]])

    def postprocess(self, results):
        output_data = results[0].reshape((-1, self.dict_size))
        max_indices = np.argmax(output_data, axis=1)
        result_str = ""
        for i in range(max_indices.shape[0]):
            index = max_indices[i]
            if index > 0 and (i == 0 or index != max_indices[i - 1]):
                result_str += self.DICT_REC[index - 1]
        return result_str


class LicenceRecDemo(Application):
    name = "车牌识别"
    rgb_size = [640, 360]
    required_files = [
        config.KMODEL_DIR + "yolo_license_plate_det.kmodel",
        config.KMODEL_DIR + "licence_reco.kmodel",
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
        # Roll back partially-created sub-models on failure: a create() error
        # means runner never calls close(), so any KPU/AI2D already allocated
        # here must be released before re-raising.
        self.licence_det = None
        self.licence_rec = None
        try:
            self.licence_det = _LicenceDetModel(
                config.KMODEL_DIR + "yolo_license_plate_det.kmodel",
                [640, 640], 0.2, 0.2, self.rgb_size, self.display_size
            )
            self.licence_det.config_preprocess()
            self.licence_rec = _LicenceRecModel(
                config.KMODEL_DIR + "licence_reco.kmodel",
                [220, 32], self.rgb_size, self.display_size
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
                print("LicenceRecDemo: video layer disable failed:", e)
            self._video_bound = False
        if sensor is not None:
            try:
                sensor.stop()
            except Exception as e:
                print("LicenceRecDemo: sensor stop failed:", e)

    def _release_owned_resources(self):
        self._osd_img = None

    def run(self, input_np):
        det_res = self.licence_det.run(input_np)
        imgs_array_boxes = aidemo.ocr_rec_preprocess(
            input_np, [self.rgb_size[1], self.rgb_size[0]], det_res[0]
        )
        imgs_array = imgs_array_boxes[0]
        rec_res = []
        for img_array in imgs_array:
            self.licence_rec.config_preprocess(
                input_image_size=[img_array.shape[3], img_array.shape[2]]
            )
            licence_str = self.licence_rec.run(img_array)
            rec_res.append(licence_str)
        # single collect after the loop: a full gc per plate is very slow
        if rec_res:
            gc.collect()
        return det_res, rec_res

    def draw_result(self, img, result):
        det_res, rec_res = result
        det_kps = det_res[0]
        count = 0
        if det_kps is not None and len(det_kps) > 0:
            for det_index in range(len(det_kps)):
                kps = det_kps[det_index].copy()
                for j in range(len(kps)):
                    if j % 2 == 0:
                        kps[j] = kps[j] * self.display_size[0] / self.rgb_size[0]
                    else:
                        kps[j] = kps[j] * self.display_size[1] / self.rgb_size[1]
                points = [(int(kps[i * 2]), int(kps[i * 2 + 1]))
                          for i in range(4)]
                label = rec_res[det_index] \
                    if det_index < len(rec_res) else "PLATE"
                visual.draw_polygon(
                    img, points, label=label, color=visual.ORANGE,
                    font_size=22, font=demo_common.CJK_FONT)
                count += 1
        return count

    def deinit(self):
        for model in (self.licence_det, self.licence_rec):
            if model is None:
                continue
            try:
                deinit_with_retry(model)
            except Exception as e:
                print("LicenceRecDemo: model deinit failed:", e)
        gc.collect()
