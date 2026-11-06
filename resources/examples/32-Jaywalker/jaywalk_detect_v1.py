# jaywalk_detect.py -- CanMV K230
# Detects people standing or walking in the path of traffic (jaywalking),
# counts them once each, outlines them in red, and blurs the face of every
# person on screen. Output goes to the LCD.
#
# Pipeline: sensor chn0 (YUV420) -> video layer, sensor chn2 (RGBP888) -> AI.
# Boxes, mosaics and the HUD are drawn on the ARGB8888 OSD layer above the
# video. Colours are (A, R, G, B) -- alpha first.
#
# NO ROAD MODEL
# Nothing about the scene is learned or configured. The road is wherever
# vehicles are driving right now: every MOVING car, bus, truck or motorbike
# leaves a footprint -- the strip where its wheels meet the ground -- that is
# kept for TRAFFIC_WINDOW_MS ("just drove through") and then forgotten.
#
# A person is a JAYWALKER when, for at least JAY_MIN_MS, their feet are in
# the path of that recent traffic:
#   IN A LANE   -- their feet are inside a recent vehicle footprint, or
#   BETWEEN     -- recent traffic passed on BOTH sides of them, measured
#                  across the direction the vehicles were moving, within
#                  ACROSS_BODY body heights and the same stretch of road.
# Someone on the pavement has traffic on one side only, so is not flagged.
#
# PEOPLE ON VEHICLES are never jaywalkers. A person is "on a vehicle" when
#   - their box sits on a bicycle / motorbike box (or mostly inside a car,
#     bus or truck) for RIDER_MIN_FRAMES frames running -- and stays so for
#     RIDER_HOLD_MS after, because the detector often misses the bike for a
#     frame while still seeing the rider; or
#   - they move faster than a person can run (RIDER_SPEED_BODY body heights
#     per second), which catches riders whose bike is never detected.
# A vehicle's footprint younger than LANE_FRESH_MS is also ignored under a
# person: that is the vehicle they are riding, not a lane they stepped into.
#
# COUNTED ONCE. Duplicate boxes on one person are merged before tracking,
# and a track that is lost (hidden behind a passing car, missed by the
# detector) is remembered for GHOST_MS; a person reappearing near where it
# was lost takes it over, counted state included, instead of starting fresh.
#
# Because only recent, moving traffic counts, nobody is flagged on an empty
# road or while all traffic is stopped. A zebra crossing cannot be told
# apart from the rest of the road this way; if the camera sees one, list it
# in CROSSWALK_ZONES and people inside it are never flagged.
#
# Set DEBUG = True to draw the recent traffic footprints and label every
# person with what the rule measured.

from libs.PipeLine import PipeLine
from libs.AIBase import AIBase
from libs.AI2D import Ai2d
from libs.Utils import *
import os, gc, time, math
from media.media import *
import nncase_runtime as nn
import ulab.numpy as np
import aicube
import aidemo

# ------------------------------- display --------------------------------
DISPLAY_MODE = "lcd"
DISPLAY_SIZE = None             # None = panel default
RGB888P_SIZE = [1280, 720]      # frame handed to the AI (16:9, sensor aspect)

# ------------------------------- traffic --------------------------------
VEH_KMODEL       = "/sdcard/examples/kmodel/yolov8n_320.kmodel"
VEH_INPUT        = [320, 320]
VEH_CONF         = 0.3
VEH_NMS          = 0.45
VEH_CLASSES      = (2, 3, 5, 7)     # COCO: car, motorcycle, bus, truck
RIDE_CLASSES     = (1, 3)           # COCO: bicycle, motorcycle (sat on)
CABIN_CLASSES    = (2, 5, 7)        # COCO: car, bus, truck (sat in)
VEH_EVERY        = 1                # run the vehicle detector every N frames
VEH_SAMPLE_MS    = 200              # sample a vehicle's motion this often
VEH_MIN_MOVE     = 0.05             # min move per sample, x box width
VEH_MAX_MOVE     = 1.5              # max jump between frames, x box size
VEH_SIZE_RATIO   = 1.6              # ... and a match must be a similar size
VEH_FOOT         = 0.25             # bottom fraction of the box = footprint
TRAFFIC_WINDOW_MS = 6000            # footprints older than this are forgotten
TRAFFIC_MAX      = 300              # and never more than this many kept

# ----------------------------- jaywalk rule -----------------------------
JAY_MIN_MS       = 500      # in the traffic path at least this long
LANE_MARGIN      = 0.1      # IN A LANE: footprint grown by this x body height
ACROSS_BODY      = 4.0      # BETWEEN: traffic within this many body heights
ALONG_BODY       = 2.0      # ... across, and this many along the road
SIDE_MIN_BODY    = 0.15     # ... and at least this far to either side
MIN_SIDE_HITS    = 2        # ... with this many footprints on each side
LANE_FRESH_MS    = 800      # footprints this young under a person are their own
PATH_GRACE_MS    = 700      # out-of-path blip shorter than this keeps the timer
JAY_HOLD_MS      = 2000     # keep the red box this long after leaving the path
STAY_BODY        = 0.5      # ... or for as long as they stay within this many
                            # body heights of where they were caught
# Legal crossing zones, normalised (0..1) polygons [(x, y), ...]. Optional.
CROSSWALK_ZONES  = []

# ---------------------------- people on vehicles ------------------------
CABIN_INSIDE     = 0.6        # this much of the person box inside a car/bus
RIDER_MIN_FRAMES = 2          # ... in this many frames
RIDER_WINDOW_MS  = 1000       # ... within this long
RIDER_HOLD_MS    = 3000       # stays "on a vehicle" this long after
RETRACT_MS       = 2000       # a count this recent is undone if they turn
                              # out to be on a vehicle
RIDER_SPEED_BODY = 3.0        # faster than this (body heights / s) = riding
SPEED_WINDOW_MS  = 500        # speed measured over this long
SPEED_GAP_MS     = 400        # a tracking gap longer than this restarts it

# -------------------------------- tracking ------------------------------
TRACK_MIN_HITS   = 3
TRACK_TIMEOUT_MS = 2000
TRACK_MAX_MOVE   = 1.0        # max centre jump between frames, x box size
FOOT_SMOOTH      = 0.5        # EMA weight of the newest foot position
MIN_PERSON_H     = 30         # ignore person boxes shorter than this (AI px)
DUP_CONTAIN      = 0.7        # two person boxes sharing this much of the
                              # smaller one are the same person
GHOST_MS         = 8000       # remember a lost track this long
GHOST_GATE       = 1.0        # revive within this many body heights ...
GHOST_SPEED      = 1.5        # ... plus this many per second lost
GHOST_SIZE_RATIO = 1.8        # ... if the box is a similar height

# -------------------------------- models --------------------------------
PERSON_KMODEL  = "/sdcard/examples/kmodel/person_detect_yolov5n.kmodel"
PERSON_INPUT   = [640, 640]
PERSON_CONF    = 0.3
PERSON_NMS     = 0.5
PERSON_ANCHORS = [10, 13, 16, 30, 33, 23, 30, 61, 62, 45, 59, 119,
                  116, 90, 156, 198, 373, 326]

USE_FACE_DET  = True
FACE_EVERY    = 2         # run the face detector every N frames; between
                          # runs the last faces are reused (heads are blurred
                          # from the person boxes every frame regardless)
FACE_KMODEL   = "/sdcard/examples/kmodel/face_detection_320.kmodel"
FACE_INPUT    = [320, 320]
FACE_ANCHORS  = "/sdcard/examples/utils/prior_data_320.bin"
FACE_CONF     = 0.4
FACE_NMS      = 0.2

# --------------------------------- drawing ------------------------------
BLOCKS        = 5         # mosaic blocks per axis, per face
FACE_PAD      = 0.2
MASK_HOLD_MS  = 500       # keep blurring a head this long after last seen
JAY_RGB       = (255, 0, 0)
JAY_THICK     = 4
SHOW_ALL_PEOPLE = False   # thin grey box around non-jaywalkers
HUD_SIZE      = 32
DEBUG         = False     # draw traffic footprints, label every person with
                          # what the rule measured, print to the console
DEBUG_TIMING  = False
# ------------------------------------------------------------------------


# The CanMV IDE stop button raises Exception("IDE interrupt"), not
# KeyboardInterrupt, so a bare `except Exception` would swallow it.
def _is_interrupt(e):
    return isinstance(e, Exception) and str(e) == "IDE interrupt"


def _require(path, what):
    try:
        os.stat(path)
    except OSError:
        raise OSError("%s not found: %s -- copy the CanMV examples to the SD "
                      "card or fix the path at the top of this file" % (what, path))


# Ray casting point-in-polygon.
def _in_poly(x, y, poly):
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            if x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                inside = not inside
        j = i
    return inside


class TrafficMemory:
    """Footprints of vehicles that moved in the last TRAFFIC_WINDOW_MS."""

    def __init__(self):
        # (t_ms, x0, y0, x1, y1, ux, uy): footprint in AI px and the unit
        # direction the vehicle was moving.
        self.fps = []

    def add(self, box, ux, uy, now):
        x1, y1, x2, y2 = box
        fy = y2 - (y2 - y1) * VEH_FOOT
        self.fps.append((now, x1, fy, x2, y2, ux, uy))
        if len(self.fps) > TRAFFIC_MAX:
            del self.fps[:len(self.fps) - TRAFFIC_MAX]

    def prune(self, now):
        # Oldest first, so only the front ever expires.
        n = 0
        while n < len(self.fps) and \
                time.ticks_diff(now, self.fps[n][0]) > TRAFFIC_WINDOW_MS:
            n += 1
        if n:
            del self.fps[:n]

    def assess(self, fx, fy, box, now):
        """Where the feet (fx, fy) of a person with this box are relative to
        recent traffic.

        Returns "lane" (inside a footprint), "between" (traffic passed on both
        sides), or None.
        """
        bx0, by0, bx1, by1 = box
        body_h = max(1, by1 - by0)
        m = LANE_MARGIN * body_h
        reach_across = ACROSS_BODY * body_h
        reach_along = ALONG_BODY * body_h
        reach2 = (reach_across + reach_along) ** 2
        near = []
        jxx = jyy = jxy = 0.0
        for f in self.fps:
            (t, x0, y0, x1, y1, ux, uy) = f
            # A vehicle under this person right now is the one they ride.
            if (time.ticks_diff(now, t) < LANE_FRESH_MS
                    and x0 < bx1 and x1 > bx0 and y0 < by1 + m and y1 > by0):
                continue
            if x0 - m <= fx <= x1 + m and y0 - m <= fy <= y1 + m:
                return "lane"
            cx = (x0 + x1) * 0.5 - fx
            cy = (y0 + y1) * 0.5 - fy
            if cx * cx + cy * cy > reach2 + ((x1 - x0) * 0.5) ** 2:
                continue
            near.append((cx, cy, (x1 - x0) * 0.5))
            jxx += ux * ux
            jyy += uy * uy
            jxy += ux * uy
        if len(near) < 2 * MIN_SIDE_HITS:
            return None
        # One road direction for the neighbourhood: the dominant axis of the
        # nearby vehicles' motion, averaged sign-free (doubled angle), so a
        # stray footprint from a mismatched track cannot tilt it.
        ang = 0.5 * math.atan2(2 * jxy, jxx - jyy)
        ux, uy = math.cos(ang), math.sin(ang)
        nx, ny = -uy, ux
        floor = SIDE_MIN_BODY * body_h
        pos = neg = 0
        for (cx, cy, half_len) in near:
            if abs(cx * ux + cy * uy) - half_len > reach_along:
                continue
            across = cx * nx + cy * ny
            if across > reach_across or across < -reach_across:
                continue
            if across > floor:
                pos += 1
            elif across < -floor:
                neg += 1
        if pos >= MIN_SIDE_HITS and neg >= MIN_SIDE_HITS:
            return "between"
        return None


def _match(tracks, boxes, now, make, max_move, size_ratio=None):
    """Greedy nearest-centre matching; boxes are (x1, y1, x2, y2).

    size_ratio, if given, refuses matches between boxes whose heights differ
    by more than that factor -- a car in the near lane is not the motorbike
    that was in the far lane a frame ago.
    """
    for t in tracks:
        t.matched = False
    boxes = sorted(boxes, key=lambda b: -(b[3] - b[1]))
    fresh = []
    for b in boxes:
        cx = (b[0] + b[2]) * 0.5
        cy = (b[1] + b[3]) * 0.5
        bh = max(1, b[3] - b[1])
        gate = max(bh, b[2] - b[0]) * max_move
        best = None
        best_d2 = gate * gate
        for t in tracks:
            if t.matched:
                continue
            if size_ratio is not None:
                th = max(1, t.box[3] - t.box[1])
                if th > size_ratio * bh or bh > size_ratio * th:
                    continue
            d2 = ((t.box[0] + t.box[2]) * 0.5 - cx) ** 2 + \
                 ((t.box[1] + t.box[3]) * 0.5 - cy) ** 2
            if d2 <= best_d2:
                best_d2 = d2
                best = t
        if best is None:
            fresh.append(make(b))
            continue
        best.matched = True
        best.hit(b, now)
    tracks.extend(fresh)
    return [t for t in tracks if time.ticks_diff(now, t.last) < TRACK_TIMEOUT_MS]


class _VehTrack:
    def __init__(self, box, now):
        self.box = box
        self.last = now
        self.matched = True
        self.sample_box = box
        self.sample_ms = now

    def hit(self, box, now):
        self.box = box
        self.last = now


class VehicleTracker:
    """Turns vehicle detections into moving-footprint evidence.

    Only vehicles that MOVE count: a car parked on the pavement must not make
    the pavement look like a lane.
    """

    def __init__(self, traffic):
        self.traffic = traffic
        self.tracks = []

    def update(self, dets, now):
        boxes = [(x, y, x + w, y + h) for (x, y, w, h) in dets]
        self.tracks = _match(self.tracks, boxes, now,
                             lambda b: _VehTrack(b, now), VEH_MAX_MOVE,
                             VEH_SIZE_RATIO)
        for t in self.tracks:
            if not t.matched or time.ticks_diff(now, t.sample_ms) < VEH_SAMPLE_MS:
                continue
            dx = (t.box[0] + t.box[2] - t.sample_box[0] - t.sample_box[2]) * 0.5
            dy = t.box[3] - t.sample_box[3]
            d = math.sqrt(dx * dx + dy * dy)
            if d >= VEH_MIN_MOVE * (t.box[2] - t.box[0]) and d > 2:
                # Both ends of the move: a fast vehicle sampled every 200 ms
                # would otherwise leave gaps in its own lane.
                self.traffic.add(t.sample_box, dx / d, dy / d, now)
                self.traffic.add(t.box, dx / d, dy / d, now)
            t.sample_box = t.box
            t.sample_ms = now


class _Track:
    def __init__(self, tid, box, now):
        self.id = tid
        self.box = box                     # (x1, y1, x2, y2) AI-frame px
        self.fx = (box[0] + box[2]) * 0.5  # smoothed foot point
        self.fy = box[3]
        self.hits = 1
        self.last = now
        self.matched = True
        self.path_since = None             # when they entered the traffic path
        self.out_since = None
        self.why = ""                      # what the rule saw (DEBUG)
        self.jay = False
        self.jay_last = 0
        self.jay_x = 0.0                   # where they were last in the path
        self.jay_y = 0.0
        self.counted = False
        self.counted_at = 0
        self.ride_seen = []                # recent times seen on a vehicle
        self.ride_last = None              # last time they were on a vehicle
        self.hist = [(now, self.fx, self.fy)]  # raw feet, for speed

    def hit(self, box, now):
        self.box = box
        self.last = now
        self.hits += 1
        fx, fy = (box[0] + box[2]) * 0.5, box[3]
        self.fx += FOOT_SMOOTH * (fx - self.fx)
        self.fy += FOOT_SMOOTH * (fy - self.fy)
        # Speed only over continuous tracking: across a gap, a box that
        # matched this track again may be a different, faster passer-by, and
        # the long gap would make a motorbike look like walking pace.
        if time.ticks_diff(now, self.hist[-1][0]) > SPEED_GAP_MS:
            self.hist = []
        self.hist.append((now, fx, fy))
        while (len(self.hist) > 2 and
               time.ticks_diff(now, self.hist[1][0]) >= SPEED_WINDOW_MS):
            self.hist.pop(0)

    def revive(self, box, now):
        """A lost track taken over by a reappearing person."""
        self.matched = True
        self.fx, self.fy = (box[0] + box[2]) * 0.5, box[3]
        self.hist = [(now, self.fx, self.fy)]
        self.box = box
        self.last = now
        self.hits += 1
        self.out_since = None

    def speed_known(self):
        return time.ticks_diff(self.hist[-1][0], self.hist[0][0]) >= SPEED_WINDOW_MS

    def speed(self):
        """Feet speed in body heights per second, or 0 if not yet known."""
        t0, x0, y0 = self.hist[0]
        t1, x1, y1 = self.hist[-1]
        dt = time.ticks_diff(t1, t0)
        if dt < SPEED_WINDOW_MS:
            return 0.0
        h = max(1, self.box[3] - self.box[1])
        return math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2) / h * 1000.0 / dt


def _inter(a, b):
    """Intersection area of two (x1, y1, x2, y2) boxes."""
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0


def dedupe_people(boxes):
    """Drop boxes that are mostly inside a bigger one: one person, two boxes
    (full body and upper body, say) would otherwise be two tracks and could
    be counted twice."""
    boxes = sorted(boxes, key=lambda b: -(b[2] - b[0]) * (b[3] - b[1]))
    kept = []
    for b in boxes:
        area = max(1, (b[2] - b[0]) * (b[3] - b[1]))
        if all(_inter(b, k) < DUP_CONTAIN * area for k in kept):
            kept.append(b)
    return kept


class JaywalkTracker:
    """Tracks people and flags those standing in the path of traffic."""

    def __init__(self, traffic, frame_size):
        self.traffic = traffic
        self.tracks = []
        self.ghosts = []                   # recently lost tracks
        self.next_id = 1
        self.total = 0
        w, h = frame_size
        self.zones = [[(x * w, y * h) for (x, y) in z] for z in CROSSWALK_ZONES]

    def _new(self, b, now):
        # Someone reappearing where a track was recently lost is that person:
        # hidden behind a passing car, or missed by the detector for a while.
        # Taking the old track over keeps its counted state, so they are not
        # counted a second time.
        bh = max(1, b[3] - b[1])
        cx, cy = (b[0] + b[2]) * 0.5, (b[1] + b[3]) * 0.5
        best, best_d = None, None
        for g in self.ghosts:
            dt = time.ticks_diff(now, g.last)
            gh = max(1, g.box[3] - g.box[1])
            if dt > GHOST_MS or gh > GHOST_SIZE_RATIO * bh or bh > GHOST_SIZE_RATIO * gh:
                continue
            d = math.sqrt(((g.box[0] + g.box[2]) * 0.5 - cx) ** 2 +
                          ((g.box[1] + g.box[3]) * 0.5 - cy) ** 2)
            if d <= gh * (GHOST_GATE + GHOST_SPEED * dt / 1000.0) and \
                    (best_d is None or d < best_d):
                best, best_d = g, d
        if best is not None:
            self.ghosts.remove(best)
            best.revive(b, now)
            return best
        t = _Track(self.next_id, b, now)
        self.next_id += 1
        return t

    def update(self, boxes, vehicles, now):
        """boxes: person (x1, y1, x2, y2); vehicles: {coco_id: [(x, y, w, h)]}."""
        old = self.tracks
        self.tracks = _match(old, dedupe_people(boxes), now,
                             lambda b: self._new(b, now), TRACK_MAX_MOVE)
        for t in old:
            if t not in self.tracks and t.hits >= TRACK_MIN_HITS:
                self.ghosts.append(t)
        self.ghosts = [g for g in self.ghosts
                       if time.ticks_diff(now, g.last) <= GHOST_MS]
        for t in self.tracks:
            if t.matched:
                self._judge(t, vehicles, now)

    def _seen_on_vehicle(self, t, vehicles):
        """Is this person box on a bike / motorbike, or inside a cabin, now?"""
        p = t.box
        parea = max(1, (p[2] - p[0]) * (p[3] - p[1]))
        cx = (p[0] + p[2]) * 0.5
        for cls in RIDE_CLASSES:
            for (x, y, w, h) in vehicles.get(cls, ()):
                # Sitting on it: centred over the bike, the box reaching down
                # into it, the head above it. Seen side-on a rider is far
                # narrower than the bike, so box overlap alone is no test.
                if (x - 0.1 * w <= cx <= x + 1.1 * w
                        and y <= p[3] <= y + h * 1.25
                        and p[1] < y):
                    return True
        for cls in CABIN_CLASSES:
            for (x, y, w, h) in vehicles.get(cls, ()):
                v = (x, y, x + w, y + h)
                # Seen through a window: inside the vehicle, feet hidden well
                # above its wheels. Someone standing IN FRONT of a bus is
                # inside its box too, but their feet reach the ground.
                if (_inter(p, v) >= CABIN_INSIDE * parea
                        and p[3] < y + h * 0.85):
                    return True
        return False

    def _on_vehicle(self, t, vehicles, now):
        if self._seen_on_vehicle(t, vehicles):
            t.ride_seen.append(now)
        t.ride_seen = [s for s in t.ride_seen
                       if time.ticks_diff(now, s) <= RIDER_WINDOW_MS]
        # Seen on it more than once, so a bike merely passing in front of a
        # pedestrian does not excuse them -- but not necessarily in
        # consecutive frames, because the detector often drops the bike while
        # still seeing the rider. Then held, for the same reason.
        if len(t.ride_seen) >= RIDER_MIN_FRAMES or t.speed() >= RIDER_SPEED_BODY:
            t.ride_last = now
        return (t.ride_last is not None and
                time.ticks_diff(now, t.ride_last) <= RIDER_HOLD_MS)

    def _judge(self, t, vehicles, now):
        where = None
        if self._on_vehicle(t, vehicles, now):
            t.why = "on vehicle"
            # Counted before the vehicle was recognised: take it back.
            if t.counted and time.ticks_diff(now, t.counted_at) <= RETRACT_MS:
                t.counted = False
                self.total -= 1
                print("retracted track %d: on a vehicle" % t.id)
            t.jay = False
            t.path_since = None
            return
        if any(_in_poly(t.fx, t.fy, z) for z in self.zones):
            t.why = "crosswalk"
        else:
            where = self.traffic.assess(t.fx, t.fy, t.box, now)
            t.why = where if where else "clear"
        body_h = max(1, t.box[3] - t.box[1])

        if where is None:
            # Still standing where they were caught: once the traffic around
            # them has aged out of the window, they are no less in the road.
            if (t.jay and abs(t.fx - t.jay_x) + abs(t.fy - t.jay_y)
                    < STAY_BODY * body_h):
                t.jay_last = now
            if t.path_since is not None:
                # Detector jitter can move the feet out of the path for a
                # frame; only reset once they have really left it.
                if t.out_since is None:
                    t.out_since = now
                elif time.ticks_diff(now, t.out_since) > PATH_GRACE_MS:
                    t.path_since = None
                    t.out_since = None
            return

        t.out_since = None
        if t.path_since is None:
            t.path_since = now
        dwell = time.ticks_diff(now, t.path_since)
        if DEBUG:
            t.why = "%s %dms" % (where, dwell)
        # Only once their speed is known: a rider whose bike was never
        # detected is told apart by speed alone, and must not be counted in
        # the first half second before it can be measured.
        if t.hits >= TRACK_MIN_HITS and dwell >= JAY_MIN_MS and t.speed_known():
            t.jay = True
            t.jay_last = now
            t.jay_x, t.jay_y = t.fx, t.fy
            if not t.counted:
                t.counted = True
                t.counted_at = now
                self.total += 1
                print("jaywalker #%d (track %d, %s)" % (self.total, t.id, where))

    def live(self, now):
        return [t for t in self.tracks
                if time.ticks_diff(now, t.last) <= MASK_HOLD_MS]

    def highlighted(self, t, now):
        return t.jay and time.ticks_diff(now, t.jay_last) <= JAY_HOLD_MS


class PersonDetectionApp(AIBase):
    def __init__(self, kmodel_path, model_input_size, anchors,
                 confidence_threshold, nms_threshold, rgb888p_size, debug_mode=0):
        super().__init__(kmodel_path, model_input_size, rgb888p_size, debug_mode)
        self.model_input_size = model_input_size
        self.anchors = anchors
        self.strides = [8, 16, 32]
        self.confidence_threshold = confidence_threshold
        self.nms_threshold = nms_threshold
        self.rgb888p_size = [ALIGN_UP(rgb888p_size[0], 16), rgb888p_size[1]]
        self.debug_mode = debug_mode
        self.ai2d = Ai2d(debug_mode)
        self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT, nn.ai2d_format.NCHW_FMT,
                                 np.uint8, np.uint8)

    def config_preprocess(self, input_image_size=None):
        ai2d_input_size = input_image_size if input_image_size else self.rgb888p_size
        top, bottom, left, right, _ = center_pad_param(self.rgb888p_size,
                                                       self.model_input_size)
        self.ai2d.pad([0, 0, 0, 0, top, bottom, left, right], 0, [0, 0, 0])
        self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
        self.ai2d.build([1, 3, ai2d_input_size[1], ai2d_input_size[0]],
                        [1, 3, self.model_input_size[1], self.model_input_size[0]])

    # Returns [(x1, y1, x2, y2), ...] in AI-frame pixels.
    def postprocess(self, results):
        dets = aicube.anchorbasedet_post_process(
            results[0], results[1], results[2], self.model_input_size,
            self.rgb888p_size, self.strides, 1, self.confidence_threshold,
            self.nms_threshold, self.anchors, False)
        out = []
        if dets:
            w, h = self.rgb888p_size
            for d in dets:
                x1 = max(0, int(d[2]))
                y1 = max(0, int(d[3]))
                x2 = min(w - 1, int(d[4]))
                y2 = min(h - 1, int(d[5]))
                if y2 - y1 >= MIN_PERSON_H and x2 > x1:
                    out.append((x1, y1, x2, y2))
        return out


class VehicleDetectionApp(AIBase):
    """YOLOv8n COCO; returns {class_id: [(x, y, w, h), ...]} for vehicles."""

    def __init__(self, kmodel_path, model_input_size, confidence_threshold,
                 nms_threshold, rgb888p_size, debug_mode=0):
        super().__init__(kmodel_path, model_input_size, rgb888p_size, debug_mode)
        self.model_input_size = model_input_size
        self.confidence_threshold = confidence_threshold
        self.nms_threshold = nms_threshold
        self.rgb888p_size = [ALIGN_UP(rgb888p_size[0], 16), rgb888p_size[1]]
        self.debug_mode = debug_mode
        self.ai2d = Ai2d(debug_mode)
        self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT, nn.ai2d_format.NCHW_FMT,
                                 np.uint8, np.uint8)

    def config_preprocess(self, input_image_size=None):
        ai2d_input_size = input_image_size if input_image_size else self.rgb888p_size
        top, bottom, left, right, _ = letterbox_pad_param(self.rgb888p_size,
                                                          self.model_input_size)
        self.ai2d.pad([0, 0, 0, 0, top, bottom, left, right], 0, [128, 128, 128])
        self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
        self.ai2d.build([1, 3, ai2d_input_size[1], ai2d_input_size[0]],
                        [1, 3, self.model_input_size[1], self.model_input_size[0]])

    def postprocess(self, results):
        new_result = results[0][0].transpose()
        det = aidemo.yolov8_det_postprocess(
            new_result.copy(), [self.rgb888p_size[1], self.rgb888p_size[0]],
            [self.model_input_size[1], self.model_input_size[0]],
            [self.rgb888p_size[1], self.rgb888p_size[0]], 80,
            self.confidence_threshold, self.nms_threshold, 50)
        out = {}
        if det:
            for i in range(len(det[0])):
                cls = int(det[1][i])
                if cls in VEH_CLASSES or cls in RIDE_CLASSES:
                    x, y, w, h = [int(v) for v in det[0][i]]
                    out.setdefault(cls, []).append((x, y, w, h))
        return out


class FaceDetectionApp(AIBase):
    def __init__(self, kmodel_path, model_input_size, anchors,
                 confidence_threshold, nms_threshold, rgb888p_size, debug_mode=0):
        super().__init__(kmodel_path, model_input_size, rgb888p_size, debug_mode)
        self.model_input_size = model_input_size
        self.anchors = anchors
        self.confidence_threshold = confidence_threshold
        self.nms_threshold = nms_threshold
        self.rgb888p_size = [ALIGN_UP(rgb888p_size[0], 16), rgb888p_size[1]]
        self.debug_mode = debug_mode
        self.ai2d = Ai2d(debug_mode)
        self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT, nn.ai2d_format.NCHW_FMT,
                                 np.uint8, np.uint8)

    def config_preprocess(self, input_image_size=None):
        ai2d_input_size = input_image_size if input_image_size else self.rgb888p_size
        top, bottom, left, right, _ = letterbox_pad_param(self.rgb888p_size,
                                                          self.model_input_size)
        self.ai2d.pad([0, 0, 0, 0, top, bottom, left, right], 0, [104, 117, 123])
        self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
        self.ai2d.build([1, 3, ai2d_input_size[1], ai2d_input_size[0]],
                        [1, 3, self.model_input_size[1], self.model_input_size[0]])

    # Returns [(x, y, w, h), ...] in AI-frame pixels.
    def postprocess(self, results):
        post_ret = aidemo.face_det_post_process(
            self.confidence_threshold, self.nms_threshold,
            self.model_input_size[1], self.anchors, self.rgb888p_size, results)
        if len(post_ret) == 0:
            return []
        return [(int(d[0]), int(d[1]), int(d[2]), int(d[3])) for d in post_ret[0]]


class Renderer:
    """Draws mosaics, boxes, traffic footprints and the HUD onto the OSD."""

    def __init__(self, rgb888p_size, display_size):
        self.src_w, self.src_h = rgb888p_size
        self.sx = display_size[0] / self.src_w
        self.sy = display_size[1] / self.src_h

    def _disp(self, x, y, w, h):
        return (int(x * self.sx), int(y * self.sy),
                int(w * self.sx) + 1, int(h * self.sy) + 1)

    # Pixelate (x, y, w, h) using the AI frame's own colours. Each mosaic cell
    # is filled with the colour of the pixel at its centre.
    def mosaic(self, osd, planes, x, y, w, h, pad=0.0):
        px = int(w * pad)
        py = int(h * pad)
        x = max(0, x - px)
        y = max(0, y - py)
        w = min(self.src_w - x, w + 2 * px)
        h = min(self.src_h - y, h + 2 * py)
        if w <= 1 or h <= 1:
            return
        cw = w / BLOCKS
        ch = h / BLOCKS
        for r in range(BLOCKS):
            for c in range(BLOCKS):
                sx = min(int(x + (c + 0.5) * cw), self.src_w - 1)
                sy = min(int(y + (r + 0.5) * ch), self.src_h - 1)
                try:
                    col = (255, int(planes[0][sy][sx]), int(planes[1][sy][sx]),
                           int(planes[2][sy][sx]))
                except Exception:
                    col = (255, 0, 0, 0)
                dx, dy, dw, dh = self._disp(int(x + c * cw), int(y + r * ch),
                                            int(cw) + 1, int(ch) + 1)
                osd.draw_rectangle(dx, dy, dw, dh, fill=True, color=col)

    # Head region of a person box. Head height is ~1/5 of a standing body;
    # when the box is wide relative to its height (upper body only, close to
    # the camera) the width is the better guide.
    def head_of(self, box):
        x1, y1, x2, y2 = box
        bw = x2 - x1
        bh = y2 - y1
        hh = min(bh, max(bh * 0.2, bw * 0.45))
        hw = min(bw, hh * 1.1)
        hx = (x1 + x2) * 0.5 - hw * 0.5
        return int(hx), int(y1), int(hw), int(hh)

    def box(self, osd, box, rgb, thick, label=None):
        x1, y1, x2, y2 = box
        dx, dy, dw, dh = self._disp(x1, y1, x2 - x1, y2 - y1)
        col = (255, rgb[0], rgb[1], rgb[2])
        osd.draw_rectangle(dx, dy, dw, dh, color=col, thickness=thick)
        if label:
            osd.draw_string_advanced(dx, max(0, dy - 30), 26, label, color=col)

    def traffic(self, osd, traffic):
        col = (255, 0, 200, 255)
        for (_, x0, y0, x1, y1, _, _) in traffic.fps:
            dx, dy, dw, dh = self._disp(x0, y0, x1 - x0, y1 - y0)
            osd.draw_rectangle(dx, dy, dw, dh, color=col, thickness=1)

    def hud(self, osd, total, now_count, n_fps):
        osd.draw_rectangle(0, 0, 380, HUD_SIZE * 3 + 20, fill=True,
                           color=(150, 0, 0, 0))
        osd.draw_string_advanced(10, 4, HUD_SIZE, "Jaywalkers: %d" % total,
                                 color=(255, 255, 60, 60))
        osd.draw_string_advanced(10, HUD_SIZE + 8, HUD_SIZE - 6,
                                 "Jaywalking now: %d" % now_count,
                                 color=(255, 255, 255, 255))
        if n_fps:
            status = "Traffic seen (%d)" % n_fps
            col = (255, 120, 255, 120)
        else:
            status = "No moving traffic"
            col = (255, 255, 200, 0)
        osd.draw_string_advanced(10, 2 * HUD_SIZE + 10, HUD_SIZE - 10, status,
                                 color=col)


if __name__ == "__main__":
    pl = PipeLine(rgb888p_size=RGB888P_SIZE, display_mode=DISPLAY_MODE,
                  display_size=DISPLAY_SIZE)
    pl.create()
    display_size = pl.get_display_size()

    person_det = None
    veh_det = None
    face_det = None
    tracker = None
    try:
        _require(PERSON_KMODEL, "person detection kmodel")
        _require(VEH_KMODEL, "vehicle (YOLOv8n COCO) kmodel")
        person_det = PersonDetectionApp(PERSON_KMODEL, PERSON_INPUT, PERSON_ANCHORS,
                                        PERSON_CONF, PERSON_NMS, RGB888P_SIZE)
        person_det.config_preprocess()
        veh_det = VehicleDetectionApp(VEH_KMODEL, VEH_INPUT, VEH_CONF, VEH_NMS,
                                      RGB888P_SIZE)
        veh_det.config_preprocess()

        if USE_FACE_DET:
            _require(FACE_KMODEL, "face detection kmodel")
            _require(FACE_ANCHORS, "face anchor file")
            anchors = np.fromfile(FACE_ANCHORS, dtype=np.float).reshape((4200, 4))
            face_det = FaceDetectionApp(FACE_KMODEL, FACE_INPUT, anchors,
                                        FACE_CONF, FACE_NMS, RGB888P_SIZE)
            face_det.config_preprocess()

        traffic = TrafficMemory()
        tracker = JaywalkTracker(traffic, person_det.rgb888p_size)
        vehicles = VehicleTracker(traffic)
        draw = Renderer(person_det.rgb888p_size, display_size)

        frame_no = 0
        veh = {}
        faces = []
        while True:
            os.exitpoint()
            t0 = time.ticks_ms()
            img = pl.get_frame()                   # RGBP888 ulab array
            planes = img[0] if len(img.shape) == 4 else img

            people = person_det.run(img)
            ran_veh = frame_no % VEH_EVERY == 0
            if ran_veh:
                veh = veh_det.run(img)
            if face_det is not None and frame_no % FACE_EVERY == 0:
                faces = face_det.run(img)
            t1 = time.ticks_ms()

            now = time.ticks_ms()
            traffic.prune(now)
            if ran_veh:
                moving = []
                for cls in VEH_CLASSES:
                    moving.extend(veh.get(cls, []))
                vehicles.update(moving, now)
            tracker.update(people, veh, now)

            osd = pl.osd_img
            osd.clear()
            if DEBUG:
                draw.traffic(osd, traffic)

            live = tracker.live(now)
            # Blur first, boxes on top, so the red outline stays visible.
            for t in live:
                hx, hy, hw, hh = draw.head_of(t.box)
                draw.mosaic(osd, planes, hx, hy, hw, hh, pad=0.1)
            for (fx, fy, fw, fh) in faces:
                draw.mosaic(osd, planes, fx, fy, fw, fh, pad=FACE_PAD)

            jay_now = 0
            for t in live:
                if tracker.highlighted(t, now):
                    jay_now += 1
                    draw.box(osd, t.box, JAY_RGB, JAY_THICK,
                             "JAYWALKING " + t.why if DEBUG else "JAYWALKING")
                elif SHOW_ALL_PEOPLE or DEBUG:
                    draw.box(osd, t.box, (160, 160, 160), 1,
                             t.why if DEBUG else None)

            draw.hud(osd, tracker.total, jay_now, len(traffic.fps))
            pl.show_image()
            gc.collect()
            frame_no += 1

            if DEBUG_TIMING:
                print("ai=%d frame=%d ms people=%d vehicles=%d faces=%d"
                      % (t1 - t0, time.ticks_ms() - t0, len(people),
                         sum(len(v) for v in veh.values()), len(faces)))
    except KeyboardInterrupt:
        pass
    except Exception as e:
        if not _is_interrupt(e):
            raise
    finally:
        if tracker is not None:
            print("jaywalkers counted this run: %d" % tracker.total)
        for app in (person_det, veh_det, face_det):
            if app is not None:
                app.deinit()
        pl.destroy()
