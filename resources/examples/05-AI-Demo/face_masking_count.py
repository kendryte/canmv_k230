# face_masking_count.py -- CanMV K230
# Pixelate people's faces on the live camera view, count them, and show a
# running total on screen. 
#
# This demo provides face-masking feature for privacy protection purposes.
#
# Pipeline: sensor chn0 (YUV420) -> video layer, sensor chn2 (RGBP888) -> AI.
# The mask is painted on the ARGB8888 OSD layer above the video.
#
# Colours here are (A, R, G, B) -- alpha first; see color_four in libs/Utils.py.
#
# WHY FACE DETECTION AND NOT BODY SEGMENTATION. This file used to carry a
# second mode built on body_seg.kmodel, which masks far more of a person. It
# was removed as dead code (it was never selected), but the reasoning is worth
# keeping because it is why the file is shaped the way it is:
#
#   - Counting. body_seg is *semantic* segmentation -- it labels a pixel "arm"
#     and says nothing about whose arm -- so a count has to be guessed from
#     connected blobs, and it miscounts every time people overlap or an
#     occlusion splits someone in two. Face detection returns one box per face,
#     which is an actual instance, so the count is a real count.
#   - Speed. body_seg ran at ~600 ms/frame (~1.6 fps) against ~39 ms here.
#   - Memory. body_seg needs ~25 MB of weights plus a 512*512*15*4 B = 15.7 MB
#     output tensor. Loading a second kmodel alongside it exhausts the nncase
#     pool and the board hard-aborts, so the two could never run together.
#
# The trade is real and worth stating: face detection only finds reasonably
# frontal faces. Turn away from the camera and you are neither masked nor
# counted, where body_seg would still have covered the back of your head.
# MASK_HOLD_MS softens the flicker but cannot fix a sustained profile view.
#
# PERFORMANCE, measured on this board (01Studio K230 2G, fw v1.8-0), at
# 1280x720 with the default three detection passes -- ~37-38 ms/frame (~27 fps):
#
#   kpu.run x3                 13.1 ms   NPU, irreducible
#   face_det_post_process x3    8.3 ms   C, 4200 anchors per pass
#   ai2d preprocess x3          5.3 ms   (6.2 ms before the tensor hoist in run())
#   gc.collect                  3.4 ms   see the note in the main loop
#   show_image                  2.7 ms
#   get_frame                   2.7 ms   blocks on the sensor
#   mosaic + boxes              ~1.2 ms per face
#   get_output_tensor x3        0.9 ms
#   osd.clear                   0.2 ms
#
# Detection is ~76% of the frame and all of it is either NPU time or C. The
# drawing code, which is what looks expensive, is under 2% -- so the levers
# that matter are the number of passes (FACE_TILES) and the AI frame size, not
# the mosaic loop. For reference: one pass instead of three is ~24.5 ms/frame
# (~41 fps), and 512x512 single-pass is ~15 ms (~65 fps). Both cost small faces.

from libs.PipeLine import PipeLine
from libs.AIBase import AIBase
from libs.AI2D import Ai2d
from libs.Utils import *
import os, gc, time
from media.media import *
import nncase_runtime as nn
import ulab.numpy as np
import aidemo

# ----------------------------- settings --------------------------------
# Faces are covered with a mosaic of their own pixels -- recognisable as a
# person, not as a face. MASK_RGB is only the fallback: if reading pixels out
# of the AI frame ever fails, the mask degrades to a solid block of it rather
# than to nothing.
MASK_RGB    = (0, 0, 0)
PAD_RATIO   = 0.18          # grow each face box by this fraction (hair / chin)
BLOCKS      = 6             # mosaic blocks per axis, per face

# --------------------------- people counting ---------------------------
COUNT_PEOPLE = True

# Counting is by TRACKING, not by counting detections per frame. Counting per
# frame is what produced the nonsense totals: the detector drops a face for a
# frame or two all the time, so "0 faces, then 1 face" repeats over and over
# and every redetection of the SAME person adds one. At these frame rates that
# is not a small error -- it is tens of phantom people a minute.
#
# So each detection is matched to a track by nearest centre, and a person is
# added to the total once, when their track is first confirmed. A face that
# vanishes for a few frames keeps its track and does not get recounted.
#
# All the thresholds below are in milliseconds rather than frames on purpose,
# so that changing the pass count does not silently retune the tracker.
TRACK_MIN_HITS   = 3        # detections before a track counts as a person
TRACK_TIMEOUT_MS = 1200     # retire a track unseen this long; recount after
TRACK_HOLD_MS    = 400      # keep showing a track as "in frame" this long
TRACK_MAX_MOVE   = 1.2      # max centre travel between frames, x face width
MIN_FACE_PX      = 14       # drop detections smaller than this (AI-frame px)

# The last two are the false-positive defence, and they are why CONF_TH and
# MIN_FACE_PX can be set as low as they are. A spurious detection has to land
# in the same place on TRACK_MIN_HITS frames running before it is counted, and
# noise does not do that. MIN_FACE_PX is 14 because tiled inference reaches
# 18 px faces (see FACE_TILES); leaving it at 20 would have thrown them away.
# TRACK_MIN_HITS is 3, not 4, because tiling costs frame rate and this keeps a
# face confirmed in about the same wall-clock time as before (~130 ms).

# Keep masking a face for this long after the detector last saw it. Dropouts
# of a frame or two are constant, and an unmasked face for even 30 ms defeats
# the point. Costs nothing: it just reuses the track's last known box.
MASK_HOLD_MS = 500

DRAW_BOXES = True           # green box around each counted person
BOX_RGB    = (0, 255, 0)
BOX_THICK  = 3              # outline width; ignored when BOX_FILL is True
BOX_FILL   = False          # True paints the box solid, hiding the mosaic

SHOW_COUNT = True           # the "Total / In frame" readout, top-left
HUD_XY     = (12, 8)
HUD_SIZE   = 28
HUD_RGB    = (0, 255, 0)

# Nothing here is ever written to disk. The whole point of this script is that
# no image of anybody's face leaves the device: frames are masked on the OSD
# and discarded, and only the counts are ever printed.

SHOW_STATUS  = False        # overlay a status line
DEBUG_TIMING = False        # print per-stage milliseconds

DISPLAY_MODE = "lcd"        # hdmi/lcd/lt9611/st7701/.../virt
DISPLAY_SIZE = None         # None = panel default; e.g. [800, 480] for virt

# Size of the frame handed to the AI: 16:9, the sensor's own aspect ratio.
# Squeezing 1920x1080 into a square would make every face 44% narrower than the
# detector was trained on, costing detections at exactly the angles that are
# already marginal. The letterbox pad in config_preprocess turns the 16:9 frame
# back into the model's 320x320 square without distortion.
FACE_FRAME_SIZE = [1280, 720]

FACE_KMODEL  = "/sdcard/examples/kmodel/face_detection_320.kmodel"
FACE_INPUT   = [320, 320]
FACE_ANCHORS = "/sdcard/examples/utils/prior_data_320.bin"
CONF_TH      = 0.25
NMS_TH       = 0.2

# --- sensitivity: finding SMALL faces ----------------------------------
# The detector is 320x320. A 1280x720 frame letterboxes into it at scale 0.25
# with 140 blank rows at the bottom, so a face 40 px wide in the frame is only
# 10 px wide by the time the model sees it, and 44% of the model's input is
# wasted on padding. That -- not the confidence threshold -- is what sets the
# smallest detectable face. Measured over 250 identical frames on this board,
# sweeping the threshold on one shared inference:
#
#   conf   frames w/ a face   detections   smallest face
#   0.50        94 (38%)          149         28 px
#   0.30       133 (53%)          251         28 px
#   0.25       146 (58%)          297         27 px
#   0.15       161 (64%)          442         26 px
#   0.05       182 (73%)         1084         26 px
#
# Lowering the threshold finds the same faces more OFTEN (38% -> 58% of frames)
# but barely any smaller (28 -> 26 px), and below ~0.20 the detection count runs
# away into false positives for little recall. Hence CONF_TH = 0.25: the knee.
#
# To actually reach smaller faces the frame is also run again as overlapping
# square TILES. A 720x720 tile letterboxes at scale 0.444 with zero padding --
# 1.78x bigger at the model input, and no wasted area. Same 250 frames:
#
#   full frame alone:   50/250 frames,  68 faces, smallest 31 px, 10.2 ms
#   full + two tiles:  113/250 frames, 200 faces, smallest 18 px, 29.7 ms
#
# and of those, 63 frames were found by the tiles ONLY while zero were found by
# the full frame only -- tiling is a strict superset, it never loses a face.
#
# Cost is one inference per entry (~10 ms each): ~41 fps traded for ~27 fps to
# roughly double the number of frames a face is found in and nearly halve the
# smallest face that can be found at all. Worth it for a privacy mask: a face
# the detector never sees is a face that never gets covered.
#
# Each entry is (x, y, w, h) in AI-frame pixels, or None for the whole frame.
# Keep None in the list: the tiles are 720 wide and overlap by only 160 px, so a
# face wider than that (someone close to the camera) could be clipped in both,
# and an unmasked face is the one failure this script must not have. Set
# FACE_TILES = [None] for the old single-pass behaviour at ~41 fps.
FACE_TILES = [
    None,               # whole frame  -- large faces, and spans the tile seam
    (0,   0, 720, 720),  # left  square -- overlaps the right one by 160 px
    (560, 0, 720, 720),  # right square
]
# Two boxes from different passes overlapping by more than this are the same
# face, and the larger-area one wins. Deliberately loose: the same face seen at
# two scales lands in slightly different places.
TILE_MERGE_IOU = 0.35
# -----------------------------------------------------------------------

# The CanMV IDE's stop button does NOT raise KeyboardInterrupt. Verified on this
# firmware: KeyboardInterrupt is not even a subclass of Exception here, while
# os.exitpoint() raises a bare Exception("IDE interrupt"). So a plain
# `except Exception` swallows the stop request. Check for it first and re-raise.
def _is_interrupt(e):
    return isinstance(e, Exception) and str(e) == "IDE interrupt"

# The SD card is a kernel (RT-Smart) mount surfaced through MicroPython's
# VfsPosix: os.statvfs('/') returns all zeros, so nothing under / is a
# MicroPython VFS mount and os.mount/os.umount cannot repair it. After a hard
# abort the kernel mmc driver can be left wedged -- /sdcard survives as an empty
# directory and every path under it raises OSError EIO -- because "MPY: soft
# reboot" restarts only the MicroPython VM, not kernel init. Fail here with a
# clear message instead of deep inside a 25 MB kmodel load.
def _check_sdcard():
    try:
        entries = os.listdir("/sdcard")
    except OSError as e:
        raise OSError("/sdcard is unreadable (%s). The SD mount is wedged: the "
                    "MicroPython VM restarted but the kernel mmc driver did "
                    "not. Recover with machine.reset(), or power-cycle." % e)
    if not entries:
        raise OSError("/sdcard is mounted but lists empty -- the SD mount is "
                    "wedged after a hard abort. Recover with machine.reset(), "
                    "or power-cycle.")

# Top-left readout. Drawn last, so it stays legible over the mosaic.
def _draw_hud(osd, total, in_frame):
    if not SHOW_COUNT:
        return
    col = (255, HUD_RGB[0], HUD_RGB[1], HUD_RGB[2])
    x, y = HUD_XY
    osd.draw_string_advanced(x, y, HUD_SIZE, "Total: %d" % total, color=col)
    osd.draw_string_advanced(x, y + HUD_SIZE + 4, HUD_SIZE,
                            "In frame: %d" % in_frame, color=col)

class _FaceTracker:
    """Matches face detections to persistent tracks, and counts the tracks.

    This is what makes the running total mean something. Counting detections
    per frame counts the same person again every time the detector blinks;
    counting *tracks* counts each person once, because a track survives the
    blink and the next detection lands back on it.

    Greedy nearest-centre matching, which is enough here for two reasons: the
    gate is proportional to face width, so a small distant face cannot be
    stolen by a large near one, and at these frame rates a face moves a pixel
    or two per frame, so the nearest track is essentially always the right one.
    Proper Hungarian assignment would buy nothing.

    A track is only added to the total after TRACK_MIN_HITS detections, so a
    one-frame false positive never becomes a person.
    """

    # Tracks are plain lists, not objects -- they are rewritten every frame.
    # Layout, referred to by index throughout:
    #   0 id   1 cx   2 cy   3 w   4 h
    #   5 hits   6 last_seen_ms   7 counted   8 matched_this_frame
    def __init__(self):
        self.tracks = []
        self.next_id = 1
        self.total = 0

    # boxes are (x, y, w, h) in AI-frame pixels. Returns nothing; read the
    # results off live_boxes() and the counters.
    def update(self, boxes, now):
        for t in self.tracks:
            t[8] = False            # matched-this-frame flag

        for (bx, by, bw, bh) in boxes:
            cx = bx + bw * 0.5
            cy = by + bh * 0.5
            gate = bw * TRACK_MAX_MOVE
            best = None
            best_d2 = gate * gate
            for t in self.tracks:
                if t[8]:
                    continue        # already claimed this frame
                dx = t[1] - cx
                dy = t[2] - cy
                d2 = dx * dx + dy * dy
                if d2 <= best_d2:
                    best_d2 = d2
                    best = t
            if best is None:
                self.tracks.append([self.next_id, cx, cy, bw, bh, 1, now,
                                    False, True])
                self.next_id += 1
                continue
            best[1] = cx
            best[2] = cy
            best[3] = bw
            best[4] = bh
            best[5] += 1
            best[6] = now
            best[8] = True
            if not best[7] and best[5] >= TRACK_MIN_HITS:
                best[7] = True      # confirmed: this is a person, count once
                self.total += 1

        self.tracks = [t for t in self.tracks
                    if time.ticks_diff(now, t[6]) < TRACK_TIMEOUT_MS]

    # Boxes to mask: every track seen within MASK_HOLD_MS, confirmed or not.
    # Unconfirmed ones are included deliberately -- a face that has only been
    # seen twice is still a face, and waiting for TRACK_MIN_HITS before
    # covering it would leave it bare for the first few frames.
    def live_boxes(self, now):
        out = []
        for t in self.tracks:
            if time.ticks_diff(now, t[6]) <= MASK_HOLD_MS:
                out.append((int(t[1] - t[3] * 0.5), int(t[2] - t[4] * 0.5),
                            int(t[3]), int(t[4]), t[7]))
        return out

    # How many confirmed people are on screen right now.
    def in_frame(self, now):
        n = 0
        for t in self.tracks:
            if t[7] and time.ticks_diff(now, t[6]) <= TRACK_HOLD_MS:
                n += 1
        return n

class FaceMaskApp(AIBase):
    """Detects faces and pixelates them. Faces only -- no limbs."""

    def __init__(self, kmodel_path, model_input_size, anchors,
                confidence_threshold=0.5, nms_threshold=0.2,
                rgb888p_size=[512, 512], display_size=[1920, 1080], debug_mode=0):
        super().__init__(kmodel_path, model_input_size, rgb888p_size, debug_mode)
        self.kmodel_path = kmodel_path
        self.model_input_size = model_input_size
        self.confidence_threshold = confidence_threshold
        self.nms_threshold = nms_threshold
        self.anchors = anchors
        self.rgb888p_size = [ALIGN_UP(rgb888p_size[0], 16), rgb888p_size[1]]
        self.display_size = [ALIGN_UP(display_size[0], 16), display_size[1]]
        self.debug_mode = debug_mode
        self.mask_argb = None          # set by the caller
        self.sample_ok = True          # cleared if pixel sampling is unavailable
        self.tracker = _FaceTracker()
        self.people = 0                # confirmed faces on screen now
        self.total_seen = 0            # confirmed faces ever, only ever rises
        # AI-frame -> display scale. Both sizes are fixed from here on, so these
        # are computed once rather than per drawn cell (_pixelate draws
        # BLOCKS*BLOCKS of them per face).
        self._sx = self.display_size[0] / self.rgb888p_size[0]
        self._sy = self.display_size[1] / self.rgb888p_size[1]
        # One (ai2d, src_size, origin_x, origin_y) per detection pass. Each Ai2d
        # owns its own 320*320*3 output tensor (~307 KB), which is the whole
        # memory cost of tiling.
        self.passes = []
        self.ai2d = None               # AIBase.preprocess() is not used; see run()

    # Build one crop+letterbox+resize chain per entry in FACE_TILES.
    #
    # crop() selects the tile out of the full AI frame; the pad then letterboxes
    # whatever that tile's aspect ratio is into the model's 320x320 square
    # without distortion. For the whole 16:9 frame that pad is 140 rows at the
    # bottom (44% of the input wasted); for a 720x720 tile it is zero, which is
    # exactly why the tiles see faces 1.78x larger.
    def config_preprocess(self, input_image_size=None):
        with ScopedTiming("set preprocess config", self.debug_mode > 0):
            ai2d_input_size = input_image_size if input_image_size else self.rgb888p_size
            self.passes = []
            for tile in FACE_TILES:
                a = Ai2d(self.debug_mode)
                a.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT, nn.ai2d_format.NCHW_FMT,
                                np.uint8, np.uint8)
                if tile is None:
                    src, ox, oy = list(self.rgb888p_size), 0, 0
                else:
                    ox, oy, tw, th = tile
                    # Clamp, so an over-large tile in the settings degrades to a
                    # smaller one instead of reading off the end of the frame.
                    tw = min(tw, self.rgb888p_size[0] - ox)
                    th = min(th, self.rgb888p_size[1] - oy)
                    a.crop(ox, oy, tw, th)
                    src = [tw, th]
                top, bottom, left, right, _ = letterbox_pad_param(src,
                                                                self.model_input_size)
                a.pad([0, 0, 0, 0, top, bottom, left, right], 0, [104, 117, 123])
                a.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
                a.build([1, 3, ai2d_input_size[1], ai2d_input_size[0]],
                        [1, 3, self.model_input_size[1], self.model_input_size[0]])
                self.passes.append((a, src, ox, oy))

    # Run every pass over the one frame and merge the results.
    #
    # This replaces AIBase.run() rather than extending it: AIBase.run does a
    # single preprocess->inference->postprocess through self.ai2d, and the whole
    # point here is N of them. inference() and the tracker are unchanged.
    def run(self, input_np):
        self.cur_img = input_np
        # One tensor wrap for the whole frame. Ai2d.run() calls nn.from_numpy()
        # internally, so going through it wraps the same 1280x720x3 array once
        # per pass. Driving the builders directly avoids that without touching
        # libs/AI2D.py, which the stock examples share. Same builders, same
        # params, same source array, so the ai2d output -- and therefore the
        # detections -- are identical.
        #
        # Paired A/B, 150 frames, alternating which version ran first:
        # 6.203 -> 5.345 ms for the three passes, faster in 148/150 frames.
        in_t = nn.from_numpy(input_np)
        merged = []
        for (a, src, ox, oy) in self.passes:
            a.ai2d_builder.run(in_t, a.ai2d_output_tensor)
            results = self.inference([a.ai2d_output_tensor])
            for det in self._decode(results, src, ox, oy):
                merged.append(det)
        return self._merge(merged)

    # AIBase.deinit only knows about self.ai2d, which here is None. Drop the
    # per-pass Ai2d objects first or their output tensors survive
    # shrink_memory_pool() and the next run starts short of nncase memory.
    def deinit(self):
        self.passes = []
        gc.collect()
        super().deinit()

    def _decode(self, results, src, ox, oy):
        # src, not self.rgb888p_size: the postprocess scales boxes back up to
        # whatever frame produced them, which for a tile is the tile. Adding the
        # tile's origin then puts them back into full-frame coordinates.
        with ScopedTiming("face postprocess", self.debug_mode > 0):
            post_ret = aidemo.face_det_post_process(self.confidence_threshold,
                                                    self.nms_threshold,
                                                    self.model_input_size[1],
                                                    self.anchors,
                                                    src,
                                                    results)
        if len(post_ret) == 0:
            return []
        return [(int(d[0]) + ox, int(d[1]) + oy, int(d[2]), int(d[3]))
                for d in post_ret[0]]

    # Greedy NMS across passes. The per-pass NMS inside face_det_post_process
    # cannot see the other passes, so the same face comes back once per pass
    # that covers it -- up to three times in the tile overlap.
    def _merge(self, dets):
        if len(dets) < 2:
            return dets
        # Biggest first: a face found on the full frame and on a tile is the
        # same face, and the bigger box is the better-resolved one.
        dets = sorted(dets, key=lambda d: -(d[2] * d[3]))
        kept = []
        for (x, y, w, h) in dets:
            dup = False
            for (kx, ky, kw, kh) in kept:
                ix = min(x + w, kx + kw) - max(x, kx)
                iy = min(y + h, ky + kh) - max(y, ky)
                if ix <= 0 or iy <= 0:
                    continue
                inter = ix * iy
                if inter > TILE_MERGE_IOU * (w * h + kw * kh - inter):
                    dup = True
                    break
            if not dup:
                kept.append((x, y, w, h))
        return kept

    # ---------------------------- masking ------------------------------

    # The three colour planes of the AI frame, or None if they cannot be read.
    # Sampling is probed here, once per frame, instead of inside a try/except
    # around every mosaic cell: an element read either works for this frame or
    # it does not, and the old form wrapped BLOCKS*BLOCKS cells per face.
    def _planes(self, frame):
        try:
            return frame[0] if len(frame.shape) == 4 else frame
        except Exception:
            return None

    # AI-frame coordinates -> display coordinates. The two scale factors are
    # fixed once both sizes are known, so __init__ precomputes them rather than
    # dividing on every call.
    def _to_display(self, x, y, w, h):
        return (int(x * self._sx), int(y * self._sy),
                int(w * self._sx) + 1, int(h * self._sy) + 1)

    def _sample(self, planes, x, y):
        try:
            return (255, int(planes[0][y][x]), int(planes[1][y][x]),
                    int(planes[2][y][x]))
        except Exception:
            return None

    # mosaic: one filled block per cell, coloured from the cell's centre pixel
    #
    # This loop was rewritten once to hoist per-row channel slices out of the
    # inner loop and step the display grid directly, on the theory that
    # planes[c][y][x] was re-slicing three times per cell. Measured on the
    # board, that version was consistently SLOWER -- paired A/B over 150 frames
    # per case, alternating which version ran first:
    #
    #     1 face   1.327 -> 1.515 ms   (-14%)   faster in   1/150 frames
    #     3 faces  3.691 -> 4.729 ms   (-25%)   faster in  57/150
    #     5 faces  5.589 -> 7.535 ms   (-33%)   faster in  23/150
    #
    # ulab returns views, so the "throwaway slices" it was avoiding cost 0.008
    # ms/frame in total. It has been reverted. Do not re-apply it without a
    # paired measurement -- an unpaired one on this board has roughly +-30%
    # frame-to-frame noise and will happily show whatever you expect.
    def _pixelate(self, osd, planes, bx, by, bw, bh):
        src_w, src_h = self.rgb888p_size
        cw = bw / BLOCKS
        ch = bh / BLOCKS
        for r in range(BLOCKS):
            for c in range(BLOCKS):
                col = self.mask_argb
                sx = min(int(bx + (c + 0.5) * cw), src_w - 1)
                sy = min(int(by + (r + 0.5) * ch), src_h - 1)
                got = self._sample(planes, sx, sy)
                if got is not None:
                    col = got
                x, y, w, h = self._to_display(int(bx + c * cw), int(by + r * ch),
                                            int(cw) + 1, int(ch) + 1)
                osd.draw_rectangle(x, y, w, h, fill=True, color=col)

    # Feed this frame's detections to the tracker and refresh the counters.
    # Detections smaller than MIN_FACE_PX are dropped first: at 1280x720 the
    # detector will occasionally fire on a 10 px patch of background texture,
    # and one of those confirming into a track is a phantom person on the total.
    def track(self, dets):
        now = time.ticks_ms()
        boxes = []
        if dets:
            for det in dets:
                bx, by, bw, bh = [int(round(v)) for v in det[:4]]
                if bw >= MIN_FACE_PX and bh >= MIN_FACE_PX:
                    boxes.append((bx, by, bw, bh))
        if COUNT_PEOPLE:
            self.tracker.update(boxes, now)
            self.people = self.tracker.in_frame(now)
            self.total_seen = self.tracker.total
            return self.tracker.live_boxes(now)
        # Counting off: mask exactly what was detected, nothing held over.
        return [(b[0], b[1], b[2], b[3], True) for b in boxes]

    def draw_hud(self, osd):
        _draw_hud(osd, self.total_seen, self.people)

    # Masks from TRACKS, not raw detections, so a face the detector drops for
    # a frame or two stays covered -- see MASK_HOLD_MS.
    def mask_faces(self, osd, boxes, frame):
        with ScopedTiming("face draw", self.debug_mode > 0):
            if not boxes:
                return 0
            src_w, src_h = self.rgb888p_size
            planes = None
            if self.sample_ok:
                planes = self._planes(frame)
                if planes is None:
                    self.sample_ok = False
                    print("pixel sampling unavailable -> falling back to solid mask")
            count = 0
            for (bx, by, bw, bh, confirmed) in boxes:
                px = int(bw * PAD_RATIO)
                py = int(bh * PAD_RATIO)
                bx = max(0, bx - px)
                by = max(0, by - py)
                bw = min(src_w - bx, bw + 2 * px)
                bh = min(src_h - by, bh + 2 * py)
                if bw <= 0 or bh <= 0:
                    continue
                if planes is not None:
                    self._pixelate(osd, planes, bx, by, bw, bh)
                else:
                    x, y, w, h = self._to_display(bx, by, bw, bh)
                    osd.draw_rectangle(x, y, w, h, fill=True, color=self.mask_argb)
                # Box only the confirmed ones, so the green outline agrees with
                # the number in the HUD.
                if DRAW_BOXES and confirmed:
                    x, y, w, h = self._to_display(bx, by, bw, bh)
                    osd.draw_rectangle(x, y, w, h,
                                    color=(255, BOX_RGB[0], BOX_RGB[1],
                                            BOX_RGB[2]),
                                    thickness=BOX_THICK, fill=BOX_FILL)
                count += 1
            return count

def _require(path, what):
    try:
        os.stat(path)
    except OSError:
        raise OSError("%s not found: %s -- copy the CanMV examples to the SD card "
                    "or fix the path at the top of this file" % (what, path))

if __name__ == "__main__":
    _check_sdcard()

    mask_argb = (255, MASK_RGB[0], MASK_RGB[1], MASK_RGB[2])
    face_det = None
    pl = PipeLine(rgb888p_size=FACE_FRAME_SIZE, display_mode=DISPLAY_MODE,
                display_size=DISPLAY_SIZE)
    pl.create()                       # pl.create(sensor_id=2) to pick another camera
    display_size = pl.get_display_size()

    try:
        _require(FACE_KMODEL, "face detection kmodel")
        _require(FACE_ANCHORS, "face anchor file")
        anchors = np.fromfile(FACE_ANCHORS, dtype=np.float).reshape((4200, 4))
        face_det = FaceMaskApp(FACE_KMODEL, model_input_size=FACE_INPUT,
                            anchors=anchors,
                            confidence_threshold=CONF_TH,
                            nms_threshold=NMS_TH,
                            rgb888p_size=FACE_FRAME_SIZE,
                            display_size=display_size, debug_mode=0)
        face_det.config_preprocess()
        face_det.mask_argb = mask_argb

        last_total = 0
        while True:
            os.exitpoint()            # lets the IDE / Ctrl-C stop the loop
            if DEBUG_TIMING:
                t0 = time.ticks_ms()
            img = pl.get_frame()                  # AI frame, RGBP888
            osd = pl.osd_img
            if DEBUG_TIMING:
                t1 = time.ticks_ms()

            dets = face_det.run(img)
            if DEBUG_TIMING:
                t2 = time.ticks_ms()
            osd.clear()
            covered = face_det.mask_faces(osd, face_det.track(dets), img)
            face_det.draw_hud(osd)
            if face_det.total_seen != last_total:
                last_total = face_det.total_seen
                print("person %d (in frame %d)"
                    % (last_total, face_det.people))
            if DEBUG_TIMING:
                t3 = time.ticks_ms()

            if SHOW_STATUS:
                osd.draw_string_advanced(10, 10, 32, "faces %d" % covered,
                                        color=(255, 0, 255, 0))
            pl.show_image()
            # Every frame, deliberately -- batching this is a trap. Measured on
            # this board over 120-frame runs: collecting every 10th frame saves
            # only 0.09 ms/frame amortised but more than doubles p95 frame time
            # (18.5 -> 43.9 ms), because the cost is proportional to accumulated
            # garbage, not a fixed heap scan (3.4 ms per collect at every-frame,
            # 24.2 ms at every-10). At every-30 or never an automatic collect
            # fires instead and the AVERAGE gets worse (17.5 -> 19.0/19.2 ms)
            # with 94-100 ms stalls. A stall that long leaves a face unmasked
            # for several frames, which is the one failure this must not have.
            gc.collect()
            if DEBUG_TIMING:
                t4 = time.ticks_ms()
                print("get=%d infer=%d mask=%d show=%d total=%d ms"
                    % (t1 - t0, t2 - t1, t3 - t2, t4 - t3, t4 - t0))
    except KeyboardInterrupt:
        pass
    except Exception as e:
        # the IDE stop button lands here, not in the branch above; a real error
        # propagates. This firmware has no sys.print_exception, and a handler
        # that raises AttributeError just hides the real traceback.
        if not _is_interrupt(e):
            raise
    finally:
        if face_det is not None:
            print("people counted this run: %d" % face_det.total_seen)
            face_det.deinit()
        pl.destroy()


