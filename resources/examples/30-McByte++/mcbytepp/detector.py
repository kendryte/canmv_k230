# mcbytepp/detector.py - the detection half of tracking-by-detection.
#
# McByte++ uses YOLOX-X on an H100.  The stand-in here is the YOLOv5n person
# detector shipped with CanMV, which is what a K230 can actually run in real
# time.  The tracker does not care which produced the boxes.
#
# This talks to nncase_runtime directly rather than importing /sdcard/libs, so
# the only file it needs off the card is the kmodel itself.

import aicube
import nncase_runtime as nn
import ulab.numpy as np


def align_up(x, n):
    return (x + n - 1) & ~(n - 1)


def center_pad_param(input_size, output_size):
    """Letterbox the AI frame into the square model input, centred."""
    ratio = min(output_size[0] / input_size[0], output_size[1] / input_size[1])
    new_w = int(ratio * input_size[0])
    new_h = int(ratio * input_size[1])
    dw = (output_size[0] - new_w) / 2
    dh = (output_size[1] - new_h) / 2
    return (int(round(dh - 0.1)), int(round(dh + 0.1)),
            int(round(dw - 0.1)), int(round(dw - 0.1)), ratio)


class PersonDetector:
    def __init__(self, cfg):
        self.cfg = cfg
        self.frame_size = [align_up(cfg.det_frame_size[0], 16),
                           cfg.det_frame_size[1]]
        self.model_size = cfg.det_input_size

        self.kpu = nn.kpu()
        self.kpu.load_kmodel(cfg.kmodel_path)

        self.ai2d = nn.ai2d()
        self.ai2d.set_dtype(nn.ai2d_format.NCHW_FMT, nn.ai2d_format.NCHW_FMT,
                            np.uint8, np.uint8)
        top, bottom, left, right, _ = center_pad_param(self.frame_size,
                                                       self.model_size)
        self.ai2d.set_pad_param(True, [0, 0, 0, 0, top, bottom, left, right],
                                0, [0, 0, 0])
        self.ai2d.set_resize_param(True, nn.interp_method.tf_bilinear,
                                   nn.interp_mode.half_pixel)
        self.builder = self.ai2d.build(
            [1, 3, self.frame_size[1], self.frame_size[0]],
            [1, 3, self.model_size[1], self.model_size[0]])
        self.out_tensor = nn.from_numpy(
            np.ones((1, 3, self.model_size[1], self.model_size[0]),
                    dtype=np.uint8))
        self.in_tensor = None
        # Last frame's raw detection stats, before any tracker threshold -- the
        # only way to tell "the detector saw nothing" from "the tracker threw
        # everything away".
        self.last_count = 0
        self.last_max_score = 0.0

    def run(self, input_np):
        """input_np: CHW uint8 RGB from the AI channel. -> [[x1,y1,x2,y2,score]]"""
        new_in = nn.from_numpy(input_np)
        self.builder.run(new_in, self.out_tensor)
        old_in = self.in_tensor
        self.in_tensor = new_in
        _release(old_in)

        self.kpu.set_input_tensor(0, self.out_tensor)
        self.kpu.run()
        outputs = []
        for i in range(self.kpu.outputs_size()):
            t = self.kpu.get_output_tensor(i)
            try:
                outputs.append(t.to_numpy())
            finally:
                _release(t)

        cfg = self.cfg
        dets = aicube.anchorbasedet_post_process(
            outputs[0], outputs[1], outputs[2], self.model_size,
            self.frame_size, cfg.strides, len(cfg.labels),
            cfg.conf_low, cfg.nms_threshold, cfg.anchors, False)
        if not dets:
            self.last_count = 0
            self.last_max_score = 0.0
            return []
        # aicube hands back [label, score, x1, y1, x2, y2]
        out = [[d[2], d[3], d[4], d[5], d[1]] for d in dets]
        self.last_count = len(out)
        best = 0.0
        for d in out:
            if d[4] > best:
                best = d[4]
        self.last_max_score = best
        return out

    def deinit(self):
        for name in ("in_tensor", "out_tensor", "builder", "kpu", "ai2d"):
            obj = getattr(self, name, None)
            setattr(self, name, None)
            _release(obj)
        try:
            nn.shrink_memory_pool()
        except Exception:
            pass


def _release(obj):
    if obj is None:
        return
    fn = getattr(obj, "release", None)
    if callable(fn):
        try:
            fn()
        except Exception:
            pass
