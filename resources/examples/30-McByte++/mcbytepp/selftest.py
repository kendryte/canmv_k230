# mcbytepp/selftest.py - run the whole tracker without a camera or a kmodel.
#
# A synthetic scene is rendered into a real image.Image at the aux resolution,
# so the CMC, mask-cue and re-ID paths execute against genuine firmware image
# operations -- phase correlation, mean pooling, crops -- rather than stubs.
# Detections are generated from the scene's ground truth.  Only the kmodel is
# absent, which makes this runnable on a board whose SD card is unreadable:
#
#     import sys; sys.path.insert(0, "/tmp")
#     from mcbytepp.selftest import run; run()
#
# Pass show=True to also render the run to the LCD -- the scene is painted into
# the OSD layer with the real tracking overlay on top, so you can watch boxes,
# trails and re-ID happen on the panel without a camera or a model:
#
#     run(show=True)
#
# What it checks:
#   1. linear assignment and the Kalman filter, standalone
#   2. no identity switches while two subjects cross
#   3. the pan is absorbed by conditional CMC
#   4. a subject who leaves for 40 frames gets the same ID back (long-term re-ID)

import gc
import time

import image

from .config import Config
from .kalman import KalmanFilterXYAH
from .lap import iou, linear_assignment
from .tracker import McBytePlusPlus

DET_W = 1280
DET_H = 720
N_FRAMES = 120
PAN_START = 50
PAN_END = 70
PAN_PX = 20.0          # detector-frame pixels per frame (2 px at CMC scale)


class Actor:
    def __init__(self, name, body, head, x0, vx, y, w, h, spans):
        self.name = name
        self.body = body
        self.head = head
        self.x0 = x0
        self.vx = vx
        self.y = y
        self.w = w
        self.h = h
        self.spans = spans

    def present(self, f):
        for a, b in self.spans:
            if a <= f <= b:
                return True
        return False

    def box(self, f):
        if not self.present(f):
            return None
        # Re-entering actors resume from their span's own start.
        start = 1
        for a, b in self.spans:
            if a <= f <= b:
                start = a
                break
        x = self.x0 + self.vx * (f - start) + cam_offset(f)
        return [x, self.y, x + self.w, self.y + self.h]


def cam_offset(f):
    if f <= PAN_START:
        return 0.0
    if f >= PAN_END:
        return PAN_PX * (PAN_END - PAN_START)
    return PAN_PX * (f - PAN_START)


def make_actors():
    return [
        # red shirt, walks right, leaves at 40, comes back at 80.  The 40-frame
        # absence is longer than track_buffer, so the tracklet really does die
        # and the ID can only come back through the long-term memory.
        Actor("A", (250, 60, 60), (240, 200, 160), 120.0, 18.0, 250, 110, 330,
              [(1, 40), (80, N_FRAMES)]),
        # blue shirt, walks left, on screen throughout; crosses A around f=31
        Actor("B", (60, 140, 255), (120, 90, 60), 900.0, -8.0, 260, 105, 320,
              [(1, N_FRAMES)]),
    ]


def render(cfg, f, actors):
    """Draw the scene at aux resolution, as the sensor would deliver it."""
    aw, ah = cfg.aux_size
    img = image.Image(aw, ah, image.RGB888)
    img.clear()
    sx = aw / float(DET_W)
    sy = ah / float(DET_H)

    # Background texture, panning with the camera: phase correlation needs
    # structure to lock onto, and a flat field would leave CMC blind.
    ox = int(cam_offset(f) * sx)
    step = 24
    for gy in range(0, ah, step):
        for gx in range(0, aw, step):
            shade = 40 + ((gx // step + gy // step) % 3) * 28
            px = (gx + ox) % aw
            img.draw_rectangle(px, gy, 13, 13,
                               color=(shade, shade, shade + 12), fill=True)

    for a in actors:
        b = a.box(f)
        if b is None:
            continue
        x = int(b[0] * sx)
        y = int(b[1] * sy)
        w = int((b[2] - b[0]) * sx)
        h = int((b[3] - b[1]) * sy)
        if w <= 0 or h <= 0:
            continue
        img.draw_rectangle(x, y, w, h, color=a.body, fill=True)
        img.draw_rectangle(x, y, w, max(1, h // 4), color=a.head, fill=True)
    return img


class Rng:
    """Deterministic LCG - the firmware's random module is not guaranteed."""

    def __init__(self, seed=12345):
        self.s = seed

    def next(self):
        self.s = (1103515245 * self.s + 12345) & 0x7FFFFFFF
        return self.s

    def uniform(self, lo, hi):
        return lo + (hi - lo) * (self.next() / 2147483647.0)


def detections(f, actors, rng, drop_rate=0.10):
    dets = []
    for a in actors:
        b = a.box(f)
        if b is None:
            continue
        if rng.uniform(0, 1) < drop_rate:
            continue                      # a missed detection
        n = lambda: rng.uniform(-4, 4)
        score = rng.uniform(0.72, 0.95)
        dets.append([b[0] + n(), b[1] + n(), b[2] + n(), b[3] + n(), score])
    # An occasional low-confidence ghost, to exercise BYTE's second stage.
    if rng.uniform(0, 1) < 0.15:
        x = rng.uniform(0, DET_W - 80)
        y = rng.uniform(100, DET_H - 200)
        dets.append([x, y, x + 70, y + 180, rng.uniform(0.15, 0.34)])
    return dets


# --------------------------------------------------------------- unit checks
def check_assignment():
    cost = [[0.1, 0.8, 0.9],
            [0.7, 0.2, 0.9],
            [0.9, 0.9, 0.3]]
    matches, ur, uc = linear_assignment(cost, 0.8, 3, 3)
    ok = sorted(matches) == [(0, 0), (1, 1), (2, 2)] and not ur and not uc

    # One row whose only cheap option is above the threshold must go unmatched.
    cost2 = [[0.95, 0.99], [0.1, 0.9]]
    m2, ur2, uc2 = linear_assignment(cost2, 0.8, 2, 2)
    ok = ok and m2 == [(1, 0)] and ur2 == [0] and uc2 == [1]

    # With no tracks yet, every detection must come back unmatched, or nothing
    # would ever be born.
    m3, ur3, uc3 = linear_assignment([], 0.8, 0, 4)
    ok = ok and m3 == [] and ur3 == [] and uc3 == [0, 1, 2, 3]

    # More rows than columns exercises the transpose path.
    cost4 = [[0.9, 0.1], [0.2, 0.9], [0.7, 0.7]]
    m4, ur4, uc4 = linear_assignment(cost4, 0.5, 3, 2)
    ok = ok and sorted(m4) == [(0, 1), (1, 0)] and ur4 == [2]
    return ok


def check_kalman():
    kf = KalmanFilterXYAH()
    mean, cov = kf.initiate([100.0, 200.0, 0.5, 300.0])
    for i in range(12):
        mean, cov = kf.predict(mean, cov)
        mean, cov = kf.update(mean, cov,
                              [100.0 + 10 * (i + 1), 200.0, 0.5, 300.0])
    # After a dozen constant-velocity steps it should have learned vx ~ 10.
    vx = mean[0, 4]
    return 8.0 < vx < 12.0


def _best_actor(box, actors, f):
    best = None
    best_iou = 0.3
    for a in actors:
        b = a.box(f)
        if b is None:
            continue
        v = iou(box, b)
        if v > best_iou:
            best_iou = v
            best = a.name
    return best


def _mode(values):
    counts = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    best = None
    best_n = 0
    for k, n in counts.items():
        if n > best_n:
            best_n = n
            best = k
    return best


class _Preview:
    """Optional LCD output for the synthetic run.

    There is no camera here, so the scene is painted into the OSD layer and
    the tracking overlay is composited on top of it -- which exercises the
    real Renderer, on the real panel, with no kmodel in sight.
    """

    def __init__(self, cfg, det_size):
        from media.display import Display
        from .app import DISPLAY_MAP, Renderer
        from .config import display_candidates

        self.Display = Display
        self.osd = None
        self.size = None
        for name in display_candidates(cfg.display_mode):
            attr = DISPLAY_MAP.get(name)
            if attr is None or not hasattr(Display, attr):
                continue
            size = cfg.display_size or ([800, 480] if name == "virt" else None)
            try:
                if size:
                    Display.init(getattr(Display, attr), width=size[0],
                                 height=size[1], osd_num=1,
                                 to_ide=cfg.display_to_ide)
                    self.size = list(size)
                else:
                    Display.init(getattr(Display, attr), osd_num=1,
                                 to_ide=cfg.display_to_ide)
                    self.size = [Display.width(), Display.height()]
                print("[selftest] preview on %s %dx%d"
                      % (name, self.size[0], self.size[1]))
                break
            except Exception as e:
                print("[selftest] display %s failed (%r)" % (name, e))
        if self.size is None:
            raise RuntimeError("no usable display driver")

        self.osd = image.Image(self.size[0], self.size[1], image.ARGB8888)
        self.renderer = Renderer(cfg, det_size, self.size)

    def show(self, scene, tracks, tracker, fps):
        self.osd.clear()
        try:
            self.osd.draw_image(scene, 0, 0,
                                x_size=self.size[0], y_size=self.size[1])
        except Exception:
            pass          # background is a nicety; the overlay is the point
        self.renderer.draw(self.osd, tracks, tracker, fps, clear=False)
        self.Display.show_image(self.osd, 0, 0, self.Display.LAYER_OSD3)

    def close(self):
        try:
            self.Display.deinit()
        except Exception:
            pass


def run(verbose=True, show=False):
    """show=True also renders the synthetic run to the LCD."""
    cfg = Config()
    cfg.mot_output = None
    cfg.reid_extract_stride = 2
    cfg.print_stats_every = 0

    results = []
    results.append(("linear assignment", check_assignment()))
    results.append(("kalman filter", check_kalman()))

    actors = make_actors()
    rng = Rng()
    tracker = McBytePlusPlus(cfg, [DET_W, DET_H], cfg.aux_size, frame_rate=30)

    history = {"A": [], "B": []}
    total_ms = 0
    cmc_before_pan = 0

    preview = _Preview(cfg, [DET_W, DET_H]) if show else None
    try:
        for f in range(1, N_FRAMES + 1):
            aux = render(cfg, f, actors)
            gray = aux.to_grayscale()
            grid = gray.mean_pooled(cfg.mask_grid_div, cfg.mask_grid_div)
            buf = grid.bytearray()
            dets = detections(f, actors, rng)

            t0 = time.ticks_ms()
            tracks = tracker.update(dets, aux, buf)
            total_ms += time.ticks_diff(time.ticks_ms(), t0)

            if f == PAN_START:
                cmc_before_pan = tracker.cmc.applied
            for t in tracks:
                name = _best_actor(t.tlbr, actors, f)
                if name:
                    history[name].append((f, t.track_id))

            if preview:
                preview.show(aux, tracks, tracker, 30.0)
                time.sleep_ms(33)      # watchable, rather than as fast as it runs
            del aux, gray, grid, buf
            gc.collect()
    finally:
        if preview:
            preview.close()

    # B is on screen the whole time and must keep one ID throughout.
    b_ids = [tid for f, tid in history["B"] if f > 5]
    b_switches = 0
    for i in range(1, len(b_ids)):
        if b_ids[i] != b_ids[i - 1]:
            b_switches += 1
    results.append(("no ID switch while crossing", b_switches == 0))

    # The pan must have produced usable CMC estimates.
    cmc_during_pan = tracker.cmc.applied - cmc_before_pan
    results.append(("cmc engaged during pan", cmc_during_pan > 0))

    # A left at frame 40 and returned at 80: it should come back as itself.
    a_before = _mode([tid for f, tid in history["A"] if 10 <= f <= 40])
    a_after = _mode([tid for f, tid in history["A"] if f >= 90])
    reid_ok = a_before is not None and a_before == a_after
    results.append(("long-term re-ID recovers the ID", reid_ok))

    if verbose:
        print("")
        print("=== McByte++ K230 self-test ===")
        for name, ok in results:
            print("  [%s] %s" % ("PASS" if ok else "FAIL", name))
        print("")
        print("  actor A: id %s before the gap, id %s after" % (a_before, a_after))
        print("  actor B: %d id switches over %d observations"
              % (b_switches, len(b_ids)))
        print("  tracker: %.2f ms/frame over %d frames"
              % (total_ms / float(N_FRAMES), N_FRAMES))
        print("  cmc: %d applied, %d skipped (%d during the pan)"
              % (tracker.cmc.applied, tracker.cmc.skipped, cmc_during_pan))
        print("  mask cue: %d cost entries adjusted" % tracker.masks.hits)
        print("  re-ID: %d identities recovered, %d in memory"
              % (tracker.stats["reid_hits"], len(tracker.memory.entries)))
        print("  ids issued: %d" % tracker._next_id)
        print("")

    return all(ok for _, ok in results), results
