# demo_common.py - Shared resources for demos: labels, face detector sub-model

import ulab.numpy as np
import nncase_runtime as nn
import aidemo
import config
from libs.AIBase import AIBase
from libs.AI2D import Ai2d
from media.media import ALIGN_UP
from libs.Utils import *

# CJK-capable TTF used by demos that draw Chinese strings on the OSD
CJK_FONT = "/sdcard/res/font/AlibabaPuHuiTi-3-45-Light.ttf"

FACE_DET_KMODEL  = config.KMODEL_DIR + "face_detection_320.kmodel"
FACE_ANCHOR_FILE = config.UTILS_DIR + "prior_data_320.bin"

COCO_LABELS = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
    "truck", "boat", "traffic light", "fire hydrant", "stop sign",
    "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep",
    "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
    "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard",
    "sports ball", "kite", "baseball bat", "baseball glove", "skateboard",
    "surfboard", "tennis racket", "bottle", "wine glass", "cup", "fork",
    "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
    "couch", "potted plant", "bed", "dining table", "toilet", "tv",
    "laptop", "mouse", "remote", "keyboard", "cell phone", "microwave",
    "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase",
    "scissors", "teddy bear", "hair drier", "toothbrush"
]


def load_face_anchors():
    """Load retinaface prior anchors. Returns (4200, 4) float array.

    Falls back to zeros (detection disabled) with a loud warning instead
    of failing silently.
    """
    try:
        return np.fromfile(FACE_ANCHOR_FILE,
                           dtype=np.float).reshape((4200, 4))
    except Exception as e:
        print("WARNING: failed to load face anchors '%s' (%s); "
              "face detection will not work" % (FACE_ANCHOR_FILE, e))
        return np.zeros((4200, 4), dtype=np.float)


class FaceDetSubModel(AIBase):
    """Shared retinaface detector used as the first stage of the
    face landmark / mesh / pose / parse demos."""

    def __init__(self, rgb_size, disp_size, conf_thr=0.5, nms_thr=0.2,
                 anchors=None, model_input_size=None):
        try:
            self.model_input_size = model_input_size if model_input_size else [320, 320]
            super().__init__(FACE_DET_KMODEL, self.model_input_size, rgb_size, 0)
            self.confidence_threshold = conf_thr
            self.nms_threshold = nms_thr
            self.anchors = anchors if anchors is not None else load_face_anchors()
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
        top, bottom, left, right, _ = letterbox_pad_param(
            self.rgb888p_size, self.model_input_size)
        self.ai2d.pad([0, 0, 0, 0, top, bottom, left, right], 0,
                      [104, 117, 123])
        self.ai2d.resize(nn.interp_method.tf_bilinear,
                         nn.interp_mode.half_pixel)
        self.ai2d.build([1, 3, s[1], s[0]],
                        [1, 3, self.model_input_size[1], self.model_input_size[0]])

    def postprocess(self, results):
        res = aidemo.face_det_post_process(
            self.confidence_threshold, self.nms_threshold,
            self.model_input_size[0], self.anchors,
            self.rgb888p_size, results)
        return res[0] if len(res) else []
