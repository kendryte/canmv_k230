# jaywalk_detect_v2.py -- CanMV K230
# Version 2 of jaywalk_detect.py. Every feature of the original is kept as
# it was (detection, jaywalk rule, rider exclusion, ghost re-identification,
# face / head mosaics, HUD, DEBUG drawing, console output), and V2 adds:
#
#   [V2-1] VEHICLE TRACKING -- every car / motorbike / bus / truck gets a
#          unique, persistent ID, a thin 2 px blue box, and a label above
#          the box with its ID and speed in km/h (1 decimal place).
#   [V2-2] JAYWALKER IDs -- every confirmed jaywalker gets a unique,
#          persistent jaywalker ID (J1, J2, ...) drawn next to their red box
#          ("J?" for the first RETRACT_MS, until the count is final).
#   [V2-3] HIT PROBABILITY -- for every (vehicle, jaywalker) pair, a 0-99 %
#          score from their real-world distance and the vehicle's speed.
#   [V2-4] RISK TABLE -- a semi-transparent 4-column table in the bottom
#          right corner (Vehicle ID | Jaywalker ID | Speed km/h | Hit %),
#          rebuilt every frame; rows appear and vanish with the pairs.
#
# All V2 code is marked "[V2]". Tunable values are in the V2 CALIBRATION
# section below; the original settings follow it, unchanged.
#
# COMPATIBILITY ADJUSTMENTS (where the V2 spec met the original platform)
#  * The original runs on CanMV K230 MicroPython (ulab, nncase, aidemo) --
#    OpenCV, full NumPy, SORT/ByteTrack and Ultralytics' tracker are not
#    available there. V2 therefore reuses the original lightweight tracker
#    (_match: greedy nearest-centre association with a motion gate and a
#    size gate, i.e. SORT-style association without the Kalman filter) and
#    adds IDs and speed estimation to it. Its footprint logic, which the
#    jaywalk rule depends on, is not modified.
#  * Vehicle IDs are handed out only once a track is confirmed
#    (VEH_CONFIRM_HITS), so one-frame false detections do not use up IDs.
#    IDs come from a counter that only increases, so an ID is never reused.
#    A vehicle hidden for longer than TRACK_TIMEOUT_MS (original setting)
#    comes back with a new ID.
#  * Jaywalker IDs are kept on the original person track, so a jaywalker
#    re-identified by the original ghost logic keeps their ID. The original
#    logic may retract a count within RETRACT_MS (the person turns out to be
#    a rider), so an ID is only given once the count is older than that:
#    until then the jaywalker shows "J?". This keeps the highest ID equal
#    to the HUD total -- no ID is ever spent on a retracted count. The HUD
#    can briefly be ahead by the number of "J?" labels on screen.
#  * Speed is timed by the real frame timestamps (time.ticks_ms), which
#    stays correct even when processing is slower than the camera frame
#    rate. Set SPEED_FPS to time by frame count at a fixed rate instead.
#  * Drawing order: the risk table is drawn FIRST, then the original
#    mosaics and boxes on top of it. On the OSD a later draw replaces the
#    pixels below it, so this order keeps faces blurred and boxes visible
#    even when people or vehicles pass behind the table.
#
# ---------------------------------------------------------------------------
# Original description (jaywalk_detect.py):
#
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

# ===========================================================================
# [V2] CALIBRATION -- adjust these for your camera and scene
# ===========================================================================
# --- speed: pixels -> metres ---
# "auto":  each vehicle's own box height is its ruler (a car is ~1.5 m
#          tall, see VEH_REF_HEIGHT_M), so near and far vehicles are both
#          measured correctly without any scene setup. Best for most cameras.
# "fixed": one scale for the whole frame, METERS_PER_PIXEL. Use this for a
#          top-down camera, where vehicle heights cannot be seen. To measure
#          it: real length of a known road marking (m) / its length in
#          pixels in the 1280x720 AI frame.
SPEED_MODE          = "auto"
VEH_REF_HEIGHT_M    = {2: 1.5,      # car
                       3: 1.2,      # motorcycle
                       5: 3.2,      # bus
                       7: 3.0}      # truck
METERS_PER_PIXEL    = 0.03          # "fixed" mode only (AI-frame pixels)
PERSON_HEIGHT_M     = 1.7           # "auto" mode: ruler for pedestrians
SPEED_SCALE         = 1.0           # final correction factor: if a car you
                                    # know drives at 40 km/h shows 50, set 0.8
# --- speed: timing ---
SPEED_FPS           = None          # None = real timestamps (recommended);
                                    # a number (e.g. 30) = time by frame count
VEH_SPEED_WINDOW_MS = 600           # speed measured over this long ...
VEH_SPEED_MIN_MS    = 250           # ... and shown once this much is known
VEH_SPEED_GAP_MS    = 500           # a tracking gap longer than this restarts it
SPEED_SMOOTH        = 0.35          # EMA weight of each new speed (0..1)
SCALE_SMOOTH        = 0.2           # EMA weight of each new metres/pixel
SPEED_DEADBAND_KMH  = 2.0           # below this a vehicle shows 0.0 (jitter)
SPEED_MAX_KMH       = 200.0         # upper limit (rejects tracking glitches)

# --- hit probability score ---
# Distance d is in metres, from the vehicle's footprint to the jaywalker's
# feet. For a MOVING vehicle the score is the highest of:
#   proximity  99 * exp(-d / RISK_DIST_SCALE_M)
#                 * ((1 - W_SPEED) + W_SPEED * min(1, kmh / RISK_SPEED_REF_KMH))
#                 * (1 - W_APPROACH * receding)    receding: 0 = heading at
#                                                  them, 1 = driving away
#   time to    99 * exp(-TTC / RISK_TTC_SCALE_S), TTC = d / closing speed
#   contact       (only while the vehicle is closing in on the jaywalker)
#   near floor within RISK_NEAR_M: RISK_NEAR_FLOOR_PCT at RISK_NEAR_M,
#              rising linearly to 99 at contact (d = 0)
# A STOPPED vehicle scores 99 * exp(-d / scale) * RISK_STATIONARY_WEIGHT.
# Rises are smoothed lightly (RISK_RISE_SMOOTH) so danger shows at once,
# falls more (RISK_FALL_SMOOTH) so the score does not flicker down. The
# near floor is applied after smoothing, so it holds from the first frame.
RISK_DIST_SCALE_M      = 5.0    # bigger = risk reaches further out
RISK_SPEED_REF_KMH     = 30.0   # speed at which the speed term is full
RISK_SPEED_WEIGHT      = 0.3    # how much a slow vehicle lowers proximity
RISK_APPROACH_WEIGHT   = 0.5    # how much driving away lowers proximity
RISK_TTC_SCALE_S       = 1.5    # TTC this long -> 37 %; shorter -> higher
RISK_STATIONARY_WEIGHT = 0.4    # stopped vehicle: max 40 % even at contact
RISK_NEAR_M            = 1.0    # moving vehicle this close ...
RISK_NEAR_FLOOR_PCT    = 80     # ... scores at least this (keep > 75)
RISK_RISE_SMOOTH       = 0.8    # EMA weight of a new score above the old
RISK_FALL_SMOOTH       = 0.3    # EMA weight of a new score below the old
RISK_MIN_PCT           = 0      # hard limits of the score -- the spec
RISK_MAX_PCT           = 99     # requires 0..99; do not change

# --- vehicle IDs and display ---
VEH_CONFIRM_HITS = 3                # matched this many times before an ID
VEH_SHOW_MS      = 400              # keep the box this long after last seen
VEH_COLOR        = (255, 0, 0, 255)     # ARGB pure blue box (spec)
VEH_THICK        = 2
VEH_LABEL_SIZE   = 20
VEH_LABEL_FG     = (255, 255, 255, 255)  # white on blue: high contrast
VEH_LABEL_BG     = (255, 0, 0, 255)

# --- jaywalker ID label ---
JAY_ID_SIZE      = 24
JAY_ID_FG        = (255, 0, 0, 0)       # black on yellow: high contrast
JAY_ID_BG        = (255, 255, 230, 0)
JAY_ID_PENDING_BG = (255, 200, 200, 200)  # "J?": count not yet final
                                         # (black on light grey)

# --- risk table (bottom right) ---
TABLE_FONT          = None      # None = sized from the display width
TABLE_MAX_ROWS      = 6         # more pairs than this -> "+N more" line
TABLE_MAX_H_FRAC    = 0.35      # never taller than this part of the screen
TABLE_MAX_W_FRAC    = 0.45      # never wider than this part of the screen
TABLE_MARGIN        = 8         # gap to the screen edges (px)
TABLE_ALPHA         = 150       # background opacity (0..255)
TABLE_ALPHA_OVERLAP = 70        # ... when a tracked box is behind the table
RISK_LOW_PCT        = 30        # score colours: green up to this,
RISK_ORANGE_PCT     = 50        # yellow up to this, orange above it,
RISK_RED_PCT        = 75        # red above this
CHAR_W              = 0.55      # average glyph width / font size (layout)
# ===========================================================================

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
        # [V2] identity and kinematics (unused by the original logic)
        self.id = None          # persistent ID, given once confirmed
        self.hits = 0           # times matched to a detection
        self.cls = None         # latest COCO class
        self.m_px = None        # smoothed metres per AI pixel at the vehicle
        self.hist = []          # (t_ms, frame_no, ground_x, ground_y)
        self.kmh = None         # smoothed speed, None until measurable
        self.vx = 0.0           # image velocity, AI px per second
        self.vy = 0.0

    def hit(self, box, now):
        self.box = box
        self.last = now


# [V2] Speed as shown and used for scoring: None until known, 0.0 below the
# jitter deadband.
def veh_speed(t):
    if t.kmh is None:
        return None
    return 0.0 if t.kmh < SPEED_DEADBAND_KMH else t.kmh


# [V2] Jaywalker ID as shown: "J?" until the count is final.
def jay_text(jay_id):
    return "J?" if jay_id is None else "J%d" % jay_id


class VehicleTracker:
    """Turns vehicle detections into moving-footprint evidence.

    Only vehicles that MOVE count: a car parked on the pavement must not make
    the pavement look like a lane.

    [V2] Also gives each confirmed vehicle a persistent ID and measures its
    speed. classes and frame_no are optional, so the original call
    update(dets, now) still works.
    """

    def __init__(self, traffic):
        self.traffic = traffic
        self.tracks = []
        self.next_id = 1                   # [V2] only ever increases

    def update(self, dets, now, classes=None, frame_no=None):
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

        # [V2] IDs and speed, after (and independent of) the footprint logic.
        cls_of = {}
        if classes:
            for (x, y, w, h), c in zip(dets, classes):
                cls_of[(x, y, x + w, y + h)] = c
        for t in self.tracks:
            if t.matched:
                self._kinematics(t, now, frame_no, cls_of.get(t.box))

    # [V2] ------------------------------------------------------------------
    def _kinematics(self, t, now, frame_no, cls):
        t.hits += 1
        if t.id is None and t.hits >= VEH_CONFIRM_HITS:
            t.id = self.next_id
            self.next_id += 1
        if cls is not None:
            t.cls = cls

        # Metres per pixel at this vehicle. In "auto" mode the vehicle's own
        # height is the ruler, which follows perspective: a far car has a
        # small box, so each of its pixels covers more road.
        bh = max(1, t.box[3] - t.box[1])
        if SPEED_MODE == "fixed":
            mpp = METERS_PER_PIXEL
        else:
            mpp = VEH_REF_HEIGHT_M.get(t.cls, 1.5) / bh
        if t.m_px is None:
            t.m_px = mpp
        else:
            t.m_px += SCALE_SMOOTH * (mpp - t.m_px)

        # Track the ground contact point (bottom centre), which moves with
        # the road surface. The box top bounces with the vehicle body.
        gx = (t.box[0] + t.box[2]) * 0.5
        gy = t.box[3]
        if t.hist and time.ticks_diff(now, t.hist[-1][0]) > VEH_SPEED_GAP_MS:
            t.hist = []
        t.hist.append((now, frame_no, gx, gy))
        while (len(t.hist) > 2 and
               time.ticks_diff(now, t.hist[1][0]) >= VEH_SPEED_WINDOW_MS):
            t.hist.pop(0)

        t0, f0, x0, y0 = t.hist[0]
        t1, f1, x1, y1 = t.hist[-1]
        span_ms = time.ticks_diff(t1, t0)
        if span_ms < VEH_SPEED_MIN_MS:
            return
        if SPEED_FPS and f0 is not None and f1 is not None and f1 > f0:
            dt = (f1 - f0) / float(SPEED_FPS)
        else:
            dt = span_ms / 1000.0
        if dt <= 0:
            return
        t.vx = (x1 - x0) / dt
        t.vy = (y1 - y0) / dt
        kmh = math.sqrt(t.vx * t.vx + t.vy * t.vy) * t.m_px * 3.6 * SPEED_SCALE
        kmh = min(kmh, SPEED_MAX_KMH)
        if t.kmh is None:
            t.kmh = kmh
        else:
            t.kmh += SPEED_SMOOTH * (kmh - t.kmh)

    def shown(self, now):
        """Confirmed vehicles seen recently enough to draw."""
        return [t for t in self.tracks
                if t.id is not None
                and time.ticks_diff(now, t.last) <= VEH_SHOW_MS]

    def total(self):
        return self.next_id - 1


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
        self.jay_id = None                 # [V2] jaywalker ID, once confirmed

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
        self.next_jay_id = 1               # [V2] jaywalker IDs, only increase
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
        for g in self.ghosts:              # [V2] a forgotten count is final
            if time.ticks_diff(now, g.last) > GHOST_MS:
                self._finalize(g, now, force=True)
        self.ghosts = [g for g in self.ghosts
                       if time.ticks_diff(now, g.last) <= GHOST_MS]
        for t in self.tracks:
            if t.matched:
                self._judge(t, vehicles, now)
        # [V2] Jaywalker IDs are handed out only once a count is FINAL, i.e.
        # older than RETRACT_MS, after which the original rule can no longer
        # take it back. So every ID is a count that stands, and the highest
        # ID equals tracker.total once no count is pending (pending ones
        # show as "J?"). Ghosts are checked too: a person hidden during the
        # window keeps their count, so they get their ID as well.
        for t in self.tracks:
            self._finalize(t, now)
        for g in self.ghosts:
            self._finalize(g, now)

    # [V2] ------------------------------------------------------------------
    def _finalize(self, t, now, force=False):
        if (t.jay_id is None and t.counted
                and (force or time.ticks_diff(now, t.counted_at) > RETRACT_MS)):
            t.jay_id = self.next_jay_id
            self.next_jay_id += 1
            print("jaywalker ID J%d confirmed (track %d)" % (t.jay_id, t.id))

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


# [V2] ======================================================================
# Hit probability scoring
# ===========================================================================
class RiskAssessor:
    """Scores every (vehicle, jaywalker) pair from 0 to 99 %.

    Distance is measured in metres between the vehicle's footprint (the
    bottom VEH_FOOT strip of its box, where it meets the road) and the
    jaywalker's feet, i.e. the gap that has to close for a hit. Each pair's
    score is smoothed over frames; pairs that disappear are forgotten, so a
    returning pair starts from its current value.
    """

    def __init__(self):
        self.smooth = {}                   # (veh_id, jay_id) -> score 0..99

    @staticmethod
    def _clamp(score):
        return max(RISK_MIN_PCT, min(RISK_MAX_PCT, score))

    def _raw(self, v, p):
        """Unsmoothed score (0..99) and near floor (0..99, 0 if none) for
        one pair."""
        x1, y1, x2, y2 = v.box
        foot_top = y2 - (y2 - y1) * VEH_FOOT
        fx, fy = p.fx, p.fy
        # Euclidean distance from the feet to the nearest footprint point.
        dx = fx - min(max(fx, x1), x2)
        dy = fy - min(max(fy, foot_top), y2)
        d_px = math.sqrt(dx * dx + dy * dy)
        if SPEED_MODE == "fixed":
            mpp = METERS_PER_PIXEL
        else:
            p_mpp = PERSON_HEIGHT_M / max(1, p.box[3] - p.box[1])
            v_mpp = v.m_px if v.m_px is not None else p_mpp
            mpp = 0.5 * (p_mpp + v_mpp)
        d_m = d_px * mpp

        proximity = math.exp(-d_m / max(0.1, RISK_DIST_SCALE_M))
        kmh = veh_speed(v) or 0.0
        if kmh <= 0:
            # Stopped (or speed not yet known): closeness alone, capped low.
            raw = proximity * RISK_STATIONARY_WEIGHT
            return self._clamp(RISK_MAX_PCT * max(0.0, min(1.0, raw))), 0

        # Direction: +1 heading straight at the jaywalker, -1 straight away.
        cos = 0.0
        vs = math.sqrt(v.vx * v.vx + v.vy * v.vy)
        rx = fx - (x1 + x2) * 0.5
        ry = fy - y2
        rn = math.sqrt(rx * rx + ry * ry)
        if vs > 1e-3 and rn > 1:
            cos = (v.vx * rx + v.vy * ry) / (vs * rn)

        # Proximity, lowered somewhat for slow or departing vehicles.
        spd = min(1.0, kmh / max(0.1, RISK_SPEED_REF_KMH))
        speed_term = (1.0 - RISK_SPEED_WEIGHT) + RISK_SPEED_WEIGHT * spd
        direction_term = 1.0 - RISK_APPROACH_WEIGHT * max(0.0, -cos)
        raw = proximity * speed_term * direction_term

        # Time to contact: how soon the gap closes at the current speed.
        closing_mps = kmh / 3.6 * max(0.0, cos)
        if closing_mps > 0.1:
            ttc = d_m / closing_mps
            raw = max(raw, math.exp(-ttc / max(0.1, RISK_TTC_SCALE_S)))

        # A moving vehicle within RISK_NEAR_M is an imminent hit.
        floor = 0
        if d_m <= RISK_NEAR_M:
            near = 1.0 - d_m / max(0.01, RISK_NEAR_M)  # 0 at edge, 1 at contact
            floor = self._clamp(RISK_NEAR_FLOOR_PCT +
                                (RISK_MAX_PCT - RISK_NEAR_FLOOR_PCT) * near)

        raw = max(0.0, min(1.0, raw))
        return max(self._clamp(RISK_MAX_PCT * raw), floor), floor

    def update(self, vehicles, jaywalkers):
        """vehicles: shown _VehTracks; jaywalkers: highlighted _Tracks.

        Returns table rows (veh_id, jay_id or None while pending, speed_kmh
        or None, score 0..99, person track id), highest risk first.
        """
        rows = []
        seen = {}
        for v in vehicles:
            for p in jaywalkers:
                # Keyed on the person track id, which never changes, so the
                # smoothing carries over when "J?" becomes a real ID.
                key = (v.id, p.id)
                target, floor = self._raw(v, p)
                prev = self.smooth.get(key)
                if prev is None:
                    s = target
                else:
                    k = RISK_RISE_SMOOTH if target > prev else RISK_FALL_SMOOTH
                    s = prev + k * (target - prev)
                # The near floor bypasses smoothing: >75 % from frame one.
                s = self._clamp(max(s, floor))
                seen[key] = s
                pct = int(self._clamp(int(s + 0.5)))
                rows.append((v.id, p.jay_id, veh_speed(v), pct, p.id))
        self.smooth = seen                 # pairs that disappeared are dropped
        rows.sort(key=lambda r: (-r[3], r[0], r[4]))
        return rows


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
        self.disp_w, self.disp_h = display_size[0], display_size[1]  # [V2]

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

    # [V2] ------------------------------------------------------------------
    @staticmethod
    def _text_w(text, size):
        return int(len(text) * size * CHAR_W) + 1

    def disp_box(self, box):
        """AI-frame (x1, y1, x2, y2) -> display (x, y, w, h)."""
        x1, y1, x2, y2 = box
        return self._disp(x1, y1, x2 - x1, y2 - y1)

    def _tag(self, osd, x, y, size, text, fg, bg):
        """Text on a solid background, kept on screen. Solid, not
        transparent, so it reads on any video background."""
        w = self._text_w(text, size) + 8
        h = size + 6
        x = max(0, min(self.disp_w - w, x))
        y = max(0, min(self.disp_h - h, y))
        osd.draw_rectangle(x, y, w, h, fill=True, color=bg)
        osd.draw_string_advanced(x + 4, y + 2, size, text, color=fg)
        return w, h

    def vehicle(self, osd, t):
        """[V2-1] 2 px blue box; ID and speed just above its top edge."""
        dx, dy, dw, dh = self.disp_box(t.box)
        osd.draw_rectangle(dx, dy, dw, dh, color=VEH_COLOR, thickness=VEH_THICK)
        kmh = veh_speed(t)
        spd = "--.-" if kmh is None else "%.1f" % kmh
        text = "ID %d  %s km/h" % (t.id, spd)
        h = VEH_LABEL_SIZE + 6
        y = dy - h
        if y < 0:                          # no room above: just inside the top
            y = dy + VEH_THICK
        self._tag(osd, dx, y, VEH_LABEL_SIZE, text, VEH_LABEL_FG, VEH_LABEL_BG)

    def jay_id(self, osd, t):
        """[V2-2] Jaywalker ID right next to the red box (left if no room).
        "J?" on grey while the count can still be retracted."""
        dx, dy, dw, dh = self.disp_box(t.box)
        text = jay_text(t.jay_id)
        bg = JAY_ID_BG if t.jay_id is not None else JAY_ID_PENDING_BG
        w = self._text_w(text, JAY_ID_SIZE) + 8
        x = dx + dw + JAY_THICK
        if x + w > self.disp_w:
            x = dx - w - JAY_THICK
        self._tag(osd, x, dy, JAY_ID_SIZE, text, JAY_ID_FG, bg)

    def _table_layout(self, font):
        pad = max(4, font // 3)
        heads = ("Veh ID", "Jay ID", "Speed km/h", "Hit %")
        widest = ("V9999", "J9999", "199.9", "99%")
        cols = [max(self._text_w(h, font), self._text_w(v, font)) + 2 * pad
                for h, v in zip(heads, widest)]
        return heads, cols, pad

    def risk_table(self, osd, rows, avoid=()):
        """[V2-4] Semi-transparent risk table in the bottom-right corner.

        rows:  RiskAssessor.update() output, highest risk first.
        avoid: display (x, y, w, h) of tracked objects; if one is behind
               the table, the background is made more transparent.
        """
        font = TABLE_FONT or max(14, min(28, self.disp_w // 40))
        heads, cols, pad = self._table_layout(font)
        # Never wider than TABLE_MAX_W_FRAC of the screen.
        while sum(cols) > self.disp_w * TABLE_MAX_W_FRAC and font > 12:
            font -= 2
            heads, cols, pad = self._table_layout(font)
        row_h = font + pad + 4
        tw = sum(cols)

        # Never taller than TABLE_MAX_H_FRAC of the screen: header + rows +
        # one line for "+N more" or the empty-table message.
        fit = int(self.disp_h * TABLE_MAX_H_FRAC / row_h) - 2
        n = max(1, min(TABLE_MAX_ROWS, fit, len(rows)))
        n = min(n, len(rows))
        extra = 1 if (len(rows) > n or not rows) else 0
        th = row_h * (1 + n + extra)
        x0 = self.disp_w - tw - TABLE_MARGIN
        y0 = self.disp_h - th - TABLE_MARGIN

        alpha = TABLE_ALPHA
        for (bx, by, bw, bh) in avoid:
            if bx < x0 + tw and bx + bw > x0 and by < y0 + th and by + bh > y0:
                alpha = TABLE_ALPHA_OVERLAP
                break

        # Background, header band, and a white rule under the header.
        osd.draw_rectangle(x0, y0, tw, th, fill=True, color=(alpha, 0, 0, 0))
        osd.draw_rectangle(x0, y0, tw, row_h, fill=True,
                           color=(min(255, alpha + 60), 0, 40, 130))
        osd.draw_rectangle(x0, y0 + row_h - 1, tw, 2, fill=True,
                           color=(255, 255, 255, 255))
        x = x0
        for h, cw in zip(heads, cols):
            osd.draw_string_advanced(x + pad, y0 + 2, font, h,
                                     color=(255, 255, 255, 255))
            x += cw

        y = y0 + row_h
        for i in range(n):
            vid, jid, kmh, pct = rows[i][:4]
            if i % 2:                      # zebra stripes for readability
                osd.draw_rectangle(x0, y, tw, row_h, fill=True,
                                   color=(min(255, alpha + 30), 40, 40, 40))
            if pct > RISK_RED_PCT:
                risk_col = (255, 255, 40, 40)      # red
            elif pct > RISK_ORANGE_PCT:
                risk_col = (255, 255, 140, 0)      # orange
            elif pct > RISK_LOW_PCT:
                risk_col = (255, 255, 230, 0)      # yellow
            else:
                risk_col = (255, 0, 255, 120)      # green
            cells = (("V%d" % vid, (255, 120, 190, 255)),
                     (jay_text(jid), (255, 255, 230, 0)),
                     ("--.-" if kmh is None else "%.1f" % kmh,
                      (255, 255, 255, 255)),
                     ("%d%%" % pct, risk_col))
            x = x0
            for (text, col), cw in zip(cells, cols):
                osd.draw_string_advanced(x + pad, y + 2, font, text, color=col)
                x += cw
            y += row_h

        if extra:
            msg = ("+%d more" % (len(rows) - n)) if rows else "No risk pairs"
            osd.draw_string_advanced(x0 + pad, y + 2, font, msg,
                                     color=(255, 210, 210, 210))


if __name__ == "__main__":
    pl = PipeLine(rgb888p_size=RGB888P_SIZE, display_mode=DISPLAY_MODE,
                  display_size=DISPLAY_SIZE)
    pl.create()
    display_size = pl.get_display_size()

    person_det = None
    veh_det = None
    face_det = None
    tracker = None
    vehicles = None
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
        risk = RiskAssessor()                              # [V2-3]

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
                moving_cls = []                    # [V2] class per box
                for cls in VEH_CLASSES:
                    found = veh.get(cls, [])
                    moving.extend(found)
                    moving_cls.extend([cls] * len(found))
                vehicles.update(moving, now, moving_cls, frame_no)
            tracker.update(people, veh, now)

            # [V2] Everything to draw is decided before drawing starts.
            live = tracker.live(now)
            shown_veh = vehicles.shown(now)
            jaywalkers = [t for t in live if tracker.highlighted(t, now)]
            rows = risk.update(shown_veh, jaywalkers)

            osd = pl.osd_img
            osd.clear()
            if DEBUG:
                draw.traffic(osd, traffic)

            # [V2-4] Table first: the mosaics and boxes drawn next replace
            # its pixels, so nothing tracked is ever hidden by the table.
            avoid = [draw.disp_box(v.box) for v in shown_veh] + \
                    [draw.disp_box(t.box) for t in jaywalkers]
            draw.risk_table(osd, rows, avoid)

            # Blur first, boxes on top, so the red outline stays visible.
            for t in live:
                hx, hy, hw, hh = draw.head_of(t.box)
                draw.mosaic(osd, planes, hx, hy, hw, hh, pad=0.1)
            for (fx, fy, fw, fh) in faces:
                draw.mosaic(osd, planes, fx, fy, fw, fh, pad=FACE_PAD)

            # [V2-1] Vehicles under the red jaywalker boxes.
            for v in shown_veh:
                draw.vehicle(osd, v)

            jay_now = 0
            for t in live:
                if tracker.highlighted(t, now):
                    jay_now += 1
                    draw.box(osd, t.box, JAY_RGB, JAY_THICK,
                             "JAYWALKING " + t.why if DEBUG else "JAYWALKING")
                    draw.jay_id(osd, t)            # [V2-2] J<n> or J?
                elif SHOW_ALL_PEOPLE or DEBUG:
                    draw.box(osd, t.box, (160, 160, 160), 1,
                             t.why if DEBUG else None)

            draw.hud(osd, tracker.total, jay_now, len(traffic.fps))
            pl.show_image()
            gc.collect()
            frame_no += 1

            if DEBUG_TIMING:
                print("ai=%d frame=%d ms people=%d vehicles=%d faces=%d "
                      "tracked=%d pairs=%d"
                      % (t1 - t0, time.ticks_ms() - t0, len(people),
                         sum(len(v) for v in veh.values()), len(faces),
                         len(shown_veh), len(rows)))
    except KeyboardInterrupt:
        pass
    except Exception as e:
        if not _is_interrupt(e):
            raise
    finally:
        if tracker is not None:
            print("jaywalkers counted this run: %d" % tracker.total)
        if vehicles is not None:                           # [V2]
            print("vehicles tracked this run: %d" % vehicles.total())
        for app in (person_det, veh_det, face_det):
            if app is not None:
                app.deinit()
        pl.destroy()
