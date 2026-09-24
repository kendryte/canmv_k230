# config.py - Application constants, theme, and global state

import os
from media.display import *
from media.media import *

# ---- Display request ----
# Set both dimensions to 0 to use the selected panel's board default.  main.py
# replaces them with Display.width()/height() immediately after initialization,
# so every UI consumer sees the real physical resolution.
DISPLAY_WIDTH  = 0
DISPLAY_HEIGHT = 0
# None follows the board policy; a Display constant explicitly overrides it.
DISPLAY_TYPE   = None

# ---- Runtime Application Surface ----
# main.py replaces these compatibility names with the physical display
# geometry after Display.init(). Applications draw below LVGL on the full
# screen; the OSD3 top/bottom UI bars may cover the corresponding edges.
CAM_WIN_X   = 0
CAM_WIN_Y   = 0
CAM_WIN_W   = DISPLAY_WIDTH
CAM_WIN_H   = DISPLAY_HEIGHT

# ---- Paths ----
FONT_PATH     = "/sdcard/examples/15-LVGL/data/font/"
FONT_EN       = "A:" + FONT_PATH + "montserrat-16.fnt"
FONT_CN       = "A:" + FONT_PATH + "lv_font_simsun_16_cjk.fnt"
KMODEL_DIR    = "/sdcard/examples/kmodel/"
UTILS_DIR     = "/sdcard/examples/utils/"
ICON_PATH     = "/sdcard/examples/utils/icons/"
ICON_LV_PATH  = "A:" + ICON_PATH

# ---- App Info ----
# Legacy/default metadata. HomeScreen uses i18n.text("app_center") so the
# visible title can switch without changing application configuration.
APP_NAME      = "应用中心"

# ---- Theme Colors ----
THEME_BG         = 0x000000
THEME_CARD       = 0x1C1C1E
THEME_BORDER     = 0x38383A

THEME_ACCENT     = 0x0A84FF
THEME_GREEN      = 0x30D158
THEME_RED        = 0xFF453A
THEME_ORANGE     = 0xFF9F0A

THEME_TEXT       = 0xFFFFFF
THEME_SUBTEXT    = 0x8E8E93

# ---- Icon Colors ----
ICON_COLORS = [
    0x0A84FF, 0x30D158, 0xFF9F0A, 0xBF5AF2,
    0x5AC8FA, 0xFF375F, 0xFFD60A, 0xFF453A, 0x66D4CF,
]

# ---- Global State ----
# demo_thread: None = no demo thread; any other value = thread alive.
#   Set to a sentinel BEFORE the thread starts, cleared (None) by the
#   thread itself in its finally block.
# demo_error:  set by the demo thread when it dies from an exception,
#   consumed by the main loop for user feedback.
app_state     = "home"
active_demo   = None
# running_app is the application instance owned by the worker thread.  UI code
# may only call its non-blocking request_stop(); it must never free resources.
running_app   = None
demo_thread   = None
demo_abort    = False
demo_session  = 0
demo_fps_val  = 0.0
demo_det_cnt  = 0
demo_error    = None
# Worker-to-LVGL messages. Applications only write lightweight immutable
# values/tuples; main.py consumes them and performs all LVGL object operations.
demo_ui_request   = None
demo_status_text  = ""
demo_status_color = THEME_GREEN
# Read-only shell status. main.py polls the shared network interface; Wi-Fi
# applications own connect/disconnect operations and never expose credentials.
wifi_connected = False
exit_flag     = False

# AppDisplay is initialized by main after the shared Display.  It is the only
# display service supplied by the center to applications; Sensor/Media/KPU
# resources remain application-owned.
app_display   = None
ui_layout     = None

tts_text      = ""
# Stable TTS state code (generating/playing/ready/done/error). main.py applies
# the current language at the UI boundary; worker logic never compares text.
tts_status    = ""

# ---- Home Screen Sections ----
HOME_SECTIONS = [
    ("系统工具", [
        ("wifi", "Wi-Fi连接", 1),
        ("sys_info", "系统信息", 0),
    ]),
    ("AI 视觉", [
        ("face",      "人脸检测",   0),
        ("face_reg",  "人脸注册",   1),
        ("face_rec",  "人脸识别",   2),
        ("person",    "行人检测",   3),
        ("tracker",   "单目标跟踪", 6),
        ("self_learn","自学习分类", 4),
        ("yolo",      "物体检测",   1),
        ("hand_det",  "手掌检测",   2),
        ("pose",      "姿态估计",   3),
        ("body_seg",  "人体分割",   4),
        ("face_mesh", "人脸网格",   5),
        ("landmark",  "人脸关键点", 6),
        ("seg",       "YOLO 分割",  7),
        ("obb",       "YOLO OBB",   8),
        ("face_pose", "人脸姿态",   0),
        ("face_parse","人脸解析",   3),
        ("falldown",  "跌倒检测",   8),
        ("hand_kp",   "手势识别",   5),
        ("licence",   "车牌识别",   2),
        ("licence_pose", "YOLO车牌检测", 6),
        ("ocr",       "OCR 识别",   7),
        ("liveness",  "活体检测",   1),
        ("kws",       "关键词唤醒", 4),
        ("eye_gaze",  "视线估计",   6),
        ("tts",       "语音合成",   5),
        ("dyn_gest",  "动态手势",   3),
    ]),
    ("图像处理", [
        ("cv_edge",    "OpenCV 边缘", 1),
        ("cv_lines",   "OpenCV 直线", 2),
        ("cv_circles", "OpenCV 圆形", 3),
        ("cv_rects",   "OpenCV 矩形", 4),
        ("omv_edge",   "OpenMV 边缘", 5),
        ("omv_lines",  "OpenMV 直线", 6),
        ("omv_circles","OpenMV 圆形", 7),
        ("omv_rects",  "OpenMV 矩形", 8),
    ]),
]


def file_exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False
