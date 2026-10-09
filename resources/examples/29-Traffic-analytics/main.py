# K230 Traffic Analytics System - entry point + configuration.
# This is the ONLY file you need to edit.
import sys

APP_DIR = "/sdcard/examples/29-Traffic-analytics"
sys.path.insert(0, APP_DIR)

# =====================================================================
# CONFIGURATION
# =====================================================================
APP_NAME = "TRAFFIC ANALYTICS"

# touch
TOUCH_INDEX = 0
TOUCH_DEBOUNCE_MS = 260

# Also accept clicks from the CanMV IDE preview window
TOUCH_ALLOW_IDE = True
TOUCH_SWAP_XY = False
TOUCH_FLIP_X = False
TOUCH_FLIP_Y = False

# display
DISPLAY_MODE = "lcd"
DISPLAY_SIZE = None
SENSOR_ID = None
SENSOR_FPS = 30
RGB888P_SIZE = [1280, 720]

# model
MODEL_NAME = "YOLOv8n"
KMODEL_PATH = "/sdcard/examples/kmodel/yolov8n_224.kmodel"
MODEL_INPUT_SIZE = [224, 224]
CONFIDENCE_THRESHOLD = 0.35
NMS_THRESHOLD = 0.45
MAX_BOXES = 40
MIN_BOX_SIZE = 6               # px, smaller detections are ignored

CLASS_NAMES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
    "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat",
    "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack",
    "umbrella", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball",
    "kite", "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket",
    "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
    "couch", "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
    "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear", "hair drier",
    "toothbrush",
]

# Model label -> internal vehicle type. Labels not listed here are ignored.
VEHICLE_LABEL_MAP = {
    "car": "car",
    "motorcycle": "motorcycle",
    "bicycle": "bicycle",
    "bus": "bus",
    "truck": "truck",
}
VEHICLE_TYPES = ("car", "motorcycle", "bicycle", "bus", "truck")
VEHICLE_DISPLAY_NAMES = {
    "car": "Car",
    "motorcycle": "Motor",
    "bicycle": "Bicycle",
    "bus": "Bus",
    "truck": "Truck",
}

# tracker
TRACK_IOU_MATCH = 0.20         # IoU needed for a confident match
TRACK_DISTANCE_GATE = 0.8      # fallback: centre distance < gate * box size
TRACK_MIN_HITS = 3             # detections before a track is trusted
TRACK_TIMEOUT_MS = 1200        # confirmed track dropped after this long unseen
STILL_TRACK_TIMEOUT_MS = 4000  # a stationary vehicle keeps its id through
                               # occlusion, so its stop timer is not restarted
TENTATIVE_TIMEOUT_MS = 400     # unconfirmed track dropped sooner
TRACK_VISIBLE_MS = 500         # track still drawn/counted if seen this recently
TRACK_HISTORY_LEN = 40         # ~3 s of anchors at 13 fps (stillness window)
TRAIL_POINTS = 10
SHOW_TRAILS = True

# speed
SPEED_WINDOW_MS = 1000         # displacement measured over this window
SPEED_MIN_SPAN_MS = 300
SPEED_DEADBAND_PX = 4          # box jitter below this is treated as 0 motion
SPEED_SMOOTHING = 0.35         # EMA weight of the newest measurement
SPEEDING_CONFIRM_FRAMES = 3    # consecutive over-limit frames before red box

# stops / incidents
STILL_WINDOW_MS = 1500         # displacement window used for the stop test
STILL_MOVE_RATIO = 0.18        # moved < 18 % of its own size = still
STILL_DECAY = 2.0              # how fast the stop timer unwinds once moving
                               # (1 frame of motion cancels 2 frames of stop)
STOP_ALERT_SEC = 8             # stationary this long (not in a queue) = alert
ALERT_HOLD_FRAMES = 8          # frames an alert survives a dropped detection
MIN_ALERT_BOX_PX = 26          # ignore boxes smaller than this: too jittery
MIN_ALERT_TRACK_MS = 2000      # a track must be this old before it can alert

INCIDENT_MIN_STOP_SEC = 5      # both vehicles stopped at least this long
INCIDENT_IOU = 0.25            # overlapping this much counts as "collided"
INCIDENT_GAP_RATIO = 0.55      # or anchors closer than 55 % of the box width
INCIDENT_CONFIRM_FRAMES = 10   # the pair must hold together this many frames
QUEUE_MIN_VEHICLES = 3         # this many slow/stopped neighbours = queueing
QUEUE_RADIUS_RATIO = 3.0       # "neighbour" = within 3 box widths

# density / congestion
DENSITY_MEDIUM = 0.12          # vehicle-box area / lane area
DENSITY_HIGH = 0.30
DENSITY_SMOOTHING = 0.2
CONGESTION_SLOW_RATIO = 0.50   # avg speed / speed limit
CONGESTION_JAM_RATIO = 0.25
FLOW_WINDOW_SEC = 60

# heatmap
HEATMAP_CELL_PX = 20           # accumulator cell size, in stage pixels
HEATMAP_BLUR = 31              # cv_lite gaussian kernel used in the report
HEATMAP_GAIN = 1.15            # >1 makes light traffic easier to see
HEATMAP_ALPHA_MAX = 185        # heatmap transparency
HEATMAP_LANES_ONLY = True      # heat is only painted inside the lane polygons

# setup
LANE_MAX = 6
LANE_MAX_POINTS = 16
MIN_LINE_PX = 20
EDGE_SNAP_PX = 16              # taps this close to the edges snap to the edge
CLOSE_SNAP_PX = 22             # tap near first vertex closes the lane
CALIB_MIN_M, CALIB_MAX_M = 0.5, 500.0
SPEED_LIMIT_MIN, SPEED_LIMIT_MAX = 5.0, 300.0

# UI
TOAST_MS = 3500
ALERT_TICKER_MS = 2500         # how long each footer alert stays up

# Reports saved path
DATA_DIR = "/data/traffic_analysis"
FALLBACK_DATA_DIR = "/sdcard/traffic_analysis"
SCENE_SAVE_FILE = "scene_setup.json"

# =====================================================================
# END OF CONFIGURATION - nothing below needs to be edited
# =====================================================================


# ---------------------------------------------------------------------
# Compatibility shim: expose the settings above as a module named
# "config", so the other files keep working unchanged with
# `import config` / `from config import X`.
# (Importing "main" from them would re-run this script, so we register
# a lightweight module object instead.)
# ---------------------------------------------------------------------
class _ConfigNamespace:
    """Plain attribute holder (MicroPython cannot instantiate `module`)."""


def _publish_config():
    # Must run before any app submodule imports: they import config at module scope.
    cfg = _ConfigNamespace()
    for key, value in list(globals().items()):
        if key.isupper():
            setattr(cfg, key, value)
    sys.modules["config"] = cfg


_publish_config()


import gc
import time

from analytics.heatmap import HeatmapAccumulator
from analytics.traffic_analyzer import TrafficAnalyzer
from helper import FpsCounter, enable_exitpoint, exitpoint
from reporting.report_generator import ReportGenerator
from ui.analytics_view import ACTION_REPORT, ACTION_RESET, ACTION_SETUP, AnalyticsView
from ui.layout import Layout
from ui.scene_painter import ScenePainter
from ui.setup_wizard import SetupWizard
from ui.theme import Theme
from ui.touch_controller import TouchController
from vision.camera import CameraPipeline
from vision.detector import VehicleDetector
from vision.tracker import VehicleTracker


class TrafficApp:
    def __init__(self):
        self.camera = None
        self.detector = None

    def start(self):
        enable_exitpoint()
        try:
            self._init_hardware()
            self._init_components()
            while True:
                scene = SetupWizard(self.camera, self.touch, self.theme,
                                    self.layout, self.scene_painter).run()
                self._run_analytics(scene)
        except KeyboardInterrupt:
            print("[app] stopped by user")
        except BaseException as err:
            sys.print_exception(err)
        finally:
            self._shutdown()

    def _init_hardware(self):
        self.camera = CameraPipeline()
        display_size = self.camera.open_display()
        self.theme = Theme(display_size)
        self.layout = Layout(self.theme)
        self.camera.start(self.layout.stage)

    def _init_components(self):
        self.touch = TouchController(self.theme.size())
        self.scene_painter = ScenePainter(self.theme)
        self.heatmap = HeatmapAccumulator(self.layout.stage_size)
        self.reporter = ReportGenerator(self.camera, self.theme,
                                        self.layout, self.scene_painter)
        self.detector = VehicleDetector(self.layout.stage_size)
        self.detector.config_preprocess()

    def _run_analytics(self, scene):
        tracker = VehicleTracker()
        self.heatmap.reset()
        analyzer = TrafficAnalyzer(scene, self.heatmap)
        view = AnalyticsView(self.theme, self.layout, self.scene_painter, scene)
        fps = FpsCounter()
        view.toast("Analytics running - tap SAVE REPORT anytime")

        while True:
            exitpoint()
            self.touch.poll()
            frame = self.camera.get_ai_frame()
            self.touch.poll()
            detections = self.detector.detect(frame)
            now_ms = time.ticks_ms()
            tracks = tracker.update(detections, now_ms)
            stats = analyzer.update(tracks, now_ms)
            stats.fps = fps.tick(now_ms)

            self.touch.poll()
            action = view.hit_test(self.touch.take_tap())
            if action == ACTION_SETUP:
                return
            if action == ACTION_RESET:
                analyzer.reset()
                self.heatmap.reset()
                view.toast("Counters and heatmap reset")
            elif action == ACTION_REPORT:
                self._save_report(view, scene, analyzer.stats, tracks, now_ms)

            view.render(self.camera.osd_img, tracks, stats, now_ms)
            self.camera.show()
            gc.collect()

    def _save_report(self, view, scene, stats, tracks, now_ms):
        view.render_busy(self.camera.osd_img, "SAVING REPORT")
        self.camera.show()
        try:
            paths = self.reporter.generate(scene, stats, tracks, self.heatmap, now_ms)
            print("[app] report saved:", paths)
            folder = paths[0].rsplit("/", 1)[0]
            view.toast("Saved 2 reports to " + folder)
        except Exception as err:
            sys.print_exception(err)
            view.toast("Report failed: {}".format(err))
        gc.collect()

    def _shutdown(self):
        if self.detector is not None:
            try:
                self.detector.deinit()
            except Exception as err:
                print("[app] detector deinit:", err)
        if self.camera is not None:
            try:
                self.camera.destroy()
            except Exception as err:
                print("[app] camera destroy:", err)
        gc.collect()


if __name__ == "__main__":
    TrafficApp().start()
