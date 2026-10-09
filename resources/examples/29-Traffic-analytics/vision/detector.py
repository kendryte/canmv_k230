from libs.AIBase import AIBase
from libs.AI2D import Ai2d
from libs.Utils import *
from media.media import *
import nncase_runtime as nn
import ulab.numpy as np
import aidemo

import config


class Detection:
    def __init__(self, box, vtype, score):
        self.box = box          # (x, y, w, h)
        self.vtype = vtype      # internal vehicle type, e.g. "car"
        self.score = score


class VehicleDetector(AIBase):
    # Run YOLO and return vehicle-only detections
    def __init__(self, output_size, debug_mode=0):
        # Load YOLO KModel and configure input/output sizes.
        rgb888p_size = config.RGB888P_SIZE
        model_input_size = config.MODEL_INPUT_SIZE
        super().__init__(config.KMODEL_PATH, model_input_size, rgb888p_size, debug_mode)
        self.labels = config.CLASS_NAMES
        self.model_input_size = model_input_size
        self.rgb888p_size = [ALIGN_UP(rgb888p_size[0], 16), rgb888p_size[1]]
        self.display_size = [ALIGN_UP(output_size[0], 16), output_size[1]]
        self.debug_mode = debug_mode
        self._frame_w = output_size[0]
        self._frame_h = output_size[1]
        self.ai2d = Ai2d(debug_mode)

        # Configure image format conversion for the model.
        self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT, nn.ai2d_format.NCHW_FMT,
                                 np.uint8, np.uint8)

    def config_preprocess(self, input_image_size=None):
        # Resize camera image to YOLO input size using letterbox.
        with ScopedTiming("set preprocess config", self.debug_mode > 0):
            ai2d_input_size = input_image_size if input_image_size else self.rgb888p_size
            top, bottom, left, right, self.scale = letterbox_pad_param(
                self.rgb888p_size, self.model_input_size)
            self.ai2d.pad([0, 0, 0, 0, top, bottom, left, right], 0, [128, 128, 128])
            self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
            self.ai2d.build([1, 3, ai2d_input_size[1], ai2d_input_size[0]],
                            [1, 3, self.model_input_size[1], self.model_input_size[0]])

    def postprocess(self, results):
        # Convert raw YOLO output into boxes/classes/scores.
        with ScopedTiming("postprocess", self.debug_mode > 0):
            output = results[0][0].transpose()
            return aidemo.yolov8_det_postprocess(
                output.copy(),
                [self.rgb888p_size[1], self.rgb888p_size[0]],
                [self.model_input_size[1], self.model_input_size[0]],
                [self.display_size[1], self.display_size[0]],
                len(self.labels),
                config.CONFIDENCE_THRESHOLD,
                config.NMS_THRESHOLD,
                config.MAX_BOXES)

    def detect(self, input_np):
        # Run YOLO and return only valid vehicle detections
        raw = self.run(input_np)
        detections = []
        if not raw or len(raw) < 3:
            return detections
        boxes, class_ids, scores = raw[0], raw[1], raw[2]
        for i in range(len(boxes)):
            detection = self._to_detection(boxes[i], int(class_ids[i]), scores[i])
            if detection is not None:
                detections.append(detection)

        return detections

    def _to_detection(self, box, class_id, score):
        # Ignore invalid YOLO class IDs.
        if class_id < 0 or class_id >= len(self.labels):
            return None

        # Convert YOLO class into our vehicle type.
        vtype = config.VEHICLE_LABEL_MAP.get(self.labels[class_id])

        # Ignore non-vehicle classes.
        if vtype is None:
            return None

        # Convert box to integer display coordinates.
        x0 = max(0, int(box[0] + 0.5))
        y0 = max(0, int(box[1] + 0.5))
        x1 = min(self._frame_w - 1, int(box[0] + box[2] + 0.5))
        y1 = min(self._frame_h - 1, int(box[1] + box[3] + 0.5))

        # Ignore very small detections.
        if x1 - x0 < config.MIN_BOX_SIZE or y1 - y0 < config.MIN_BOX_SIZE:
            return None
        return Detection((x0, y0, x1 - x0, y1 - y0), vtype, float(score))
