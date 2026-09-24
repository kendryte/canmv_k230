# demos_body_seg.py - Body segmentation demo

import nncase_runtime as nn
import ulab.numpy as np
import image
import aidemo
import config
import app_visual as visual
from media.sensor import *
from media.display import Display
from media.media import ALIGN_UP
from app_contract import Application
from libs.AIBase import AIBase
from libs.AI2D import Ai2d
from libs.Utils import *


class BodySegDemo(Application, AIBase):
    name = "人体分割"
    model_path = config.KMODEL_DIR + "body_seg.kmodel"
    model_size = [512, 512]
    rgb_size   = [512, 512]
    NUM_CLASSES = 15

    SENSOR_ID = 2
    SENSOR_FPS = 60
    DISPLAY_CHANNEL = CAM_CHN_ID_0
    AI_CHANNEL = CAM_CHN_ID_2
    DISPLAY_FORMAT = Sensor.YUV420SP
    AI_FORMAT = Sensor.RGBP888
    VIDEO_LAYER = Display.LAYER_VIDEO1

    COLORS = [
        (127, 0, 0, 0), (127, 185, 218, 255), (127, 240, 255, 240),
        (127, 180, 180, 238), (127, 190, 190, 190), (127, 237, 149, 100),
        (127, 0, 165, 255), (127, 238, 238, 175), (127, 115, 198, 205),
        (127, 106, 106, 255), (127, 107, 183, 189), (127, 0, 255, 255),
        (127, 153, 136, 119), (127, 159, 255, 84), (127, 137, 137, 139)
    ]

    def __init__(self):
        try:
            self.rgb_size = [ALIGN_UP(self.rgb_size[0], 16), self.rgb_size[1]]
            self.display_size = [ALIGN_UP(config.CAM_WIN_W, 16), config.CAM_WIN_H]
            Application.__init__(self)
            AIBase.__init__(self, self.model_path, self.model_size,
                            self.rgb_size, 0)
            self.ai2d = Ai2d(0)
            self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT,
                                     nn.ai2d_format.NCHW_FMT,
                                     np.uint8, np.uint8)
            self._colors = np.array(self.COLORS, dtype=np.uint8).reshape(-1)
            self.sensor = None
            self._ai_img = None
            self._osd_img = None
            self._video_bound = False
        except BaseException:
            # The caller cannot own this model until construction returns.
            try:
                self.deinit()
            except Exception as error:
                print("model constructor cleanup failed:", error)
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
        self.config_preprocess()
        if self.stop_req:
            return
        self.start()
        self._opened = True

    def run_once(self):
        self._ai_img = self.sensor.snapshot(chn=self.AI_CHANNEL)
        result = AIBase.run(self, self._ai_img.to_numpy_ref())
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
                print("BodySegDemo: video layer disable failed:", e)
            self._video_bound = False
        if sensor is not None:
            try:
                sensor.stop()
            except Exception as e:
                print("BodySegDemo: sensor stop failed:", e)

    def _release_owned_resources(self):
        self._osd_img = None

    def config_preprocess(self, input_size=None):
        ai_input = input_size if input_size else self.rgb_size
        self.ai2d.resize(nn.interp_method.tf_bilinear,
                         nn.interp_mode.half_pixel)
        self.ai2d.build([1, 3, ai_input[1], ai_input[0]],
                        [1, 3, self.model_size[1], self.model_size[0]])

    def postprocess(self, results):
        mask = aidemo.body_seg_postprocess(
            self.results[0], self.NUM_CLASSES,
            [self.rgb_size[1], self.rgb_size[0]],
            [self.display_size[1], self.display_size[0]],
            self._colors
        )
        return image.Image(self.display_size[0], self.display_size[1],
                           image.ARGB8888, alloc=image.ALLOC_REF, data=mask)

    def draw_result(self, img, mask):
        if mask:
            mask.copy_to(img)
            visual.draw_mode_badge(img, "PERSON SEGMENTATION",
                                   visual.VIOLET)
        return 0
