import time
import math
import os
import config

# Timestamp formatting helpers.
def display_timestamp():
    t = time.localtime()
    return "{:02d}-{:02d}-{:04d} {:02d}:{:02d}:{:02d}".format(
        t[2], t[1], t[0], t[3], t[4], t[5])


def file_timestamp():
    t = time.localtime()
    stamp = "{:04d}{:02d}{:02d}_{:02d}{:02d}{:02d}".format(
        t[0], t[1], t[2], t[3], t[4], t[5])
    if t[0] < 2024:
        # RTC not set: add uptime so file names stay unique across reboots
        stamp += "_{}".format(time.ticks_ms())
    return stamp


def format_duration(ms):
    seconds = int(ms // 1000)
    return "{:02d}:{:02d}:{:02d}".format(
        seconds // 3600, (seconds // 60) % 60, seconds % 60)


# Pure geometry helpers. Points are (x, y); boxes are (x, y, w, h)
def distance(a, b):
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    return math.sqrt(dx * dx + dy * dy)


def side_of_line(a, b, p):
    """+1 / -1 depending on which side of line a->b point p lies, 0 if on it."""
    cross = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
    if cross > 0:
        return 1
    if cross < 0:
        return -1
    return 0


def line_normal(a, b):
    """Unit normal pointing to the +1 side of line a->b."""
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    length = math.sqrt(dx * dx + dy * dy)
    if length == 0:
        return (0.0, 0.0)
    return (-dy / length, dx / length)


def projection_t(a, b, p):
    """Position of p projected on segment a->b (0 = a, 1 = b)."""
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    den = dx * dx + dy * dy
    if den == 0:
        return 0.0
    return ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / den


def midpoint(a, b):
    return ((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5)


def point_in_polygon(p, poly):
    """Ray casting test, works for any simple (also concave) polygon."""
    x, y = p
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            x_cross = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < x_cross:
                inside = not inside
        j = i
    return inside


def polygon_area(poly):
    area = 0.0
    j = len(poly) - 1
    for i in range(len(poly)):
        area += (poly[j][0] + poly[i][0]) * (poly[j][1] - poly[i][1])
        j = i
    return abs(area) * 0.5


def polygon_centroid(poly):
    """Vertex average - good enough for placing a label."""
    if not poly:
        return (0, 0)
    sx = 0.0
    sy = 0.0
    for x, y in poly:
        sx += x
        sy += y
    return (sx / len(poly), sy / len(poly))


def bounding_box(poly):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return (min(xs), min(ys), max(xs), max(ys))


def box_center(box):
    return (box[0] + box[2] * 0.5, box[1] + box[3] * 0.5)


def box_anchor(box):
    """Bottom-centre: the point where the vehicle touches the road."""
    return (box[0] + box[2] * 0.5, box[1] + box[3])


def box_iou(a, b):
    ax1 = a[0] + a[2]
    ay1 = a[1] + a[3]
    bx1 = b[0] + b[2]
    by1 = b[1] + b[3]
    iw = min(ax1, bx1) - max(a[0], b[0])
    ih = min(ay1, by1) - max(a[1], b[1])
    if iw <= 0 or ih <= 0:
        return 0.0
    inter = iw * ih
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


def clamp(value, low, high):
    return low if value < low else (high if value > high else value)


# Small runtime utilities shared by every loop

def enable_exitpoint():
    try:
        os.exitpoint(os.EXITPOINT_ENABLE)
    except Exception:
        pass


def exitpoint():
    fn = getattr(os, "exitpoint", None)
    if fn is not None:
        fn()


class FpsCounter:
    def __init__(self, smoothing=0.9):
        self._last_ms = None
        self._fps = 0.0
        self._smoothing = smoothing

    def tick(self, now_ms):
        if self._last_ms is not None:
            dt = time.ticks_diff(now_ms, self._last_ms)
            if dt > 0:
                instant = 1000.0 / dt
                if self._fps == 0:
                    self._fps = instant
                else:
                    k = self._smoothing
                    self._fps = k * self._fps + (1 - k) * instant
        self._last_ms = now_ms
        return self._fps


# File-system helpers: finds a writable folder for the report images.
class Storage:
    _base_dir = None

    @staticmethod
    def exists(path):
        try:
            os.stat(path)
            return True
        except Exception:
            return False

    @classmethod
    def makedirs(cls, path):
        current = ""
        for part in path.strip("/").split("/"):
            current += "/" + part
            if not cls.exists(current):
                try:
                    os.mkdir(current)
                except Exception:
                    return False
        return True

    @staticmethod
    def is_writable(folder):
        probe = folder + "/.probe"
        try:
            with open(probe, "w") as f:
                f.write("ok")
            os.remove(probe)
            return True
        except Exception:
            return False

    @classmethod
    def base_dir(cls):
        """config.DATA_DIR if writable, otherwise the SD-card fallback."""
        if cls._base_dir is None:
            for folder in (config.DATA_DIR, config.FALLBACK_DATA_DIR):
                if cls.makedirs(folder) and cls.is_writable(folder):
                    cls._base_dir = folder
                    break
            if cls._base_dir is None:
                raise OSError("No writable folder for traffic reports")
            print("[storage] using", cls._base_dir)
        return cls._base_dir
