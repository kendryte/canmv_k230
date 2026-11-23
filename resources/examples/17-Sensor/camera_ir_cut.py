import time
import os
import sys

from media.sensor import *
from media.display import *
from media.media import *

# 当前板级配置里，IR-Cut 接在 CSI0（电平保持，GPIO10）。摄像头在别的 CSI 上时改这里。
sensor_id = 0
sensor = None

# 显示模式选择：可以是 "VIRT"、"LCD" 或 "HDMI"
DISPLAY_MODE = "LCD"

# 曝光比例初值，只在本示例里使用，驱动不保存。
DAY2NIGHT = 0.75
NIGHT2DAY = 0.20
# IMX415 的红外 ISP 把 R/G、B/G 固定在约 0.63、0.48。窗口避开这个点，
# 亮光时比值落在窗外，回切才只看曝光比例是否低于 NIGHT2DAY。
RG_MIN = 1.20
RG_MAX = 2.50
BG_MIN = 1.20
BG_MAX = 2.50
CHECK_INTERVAL_MS = 500
SWITCH_COUNT = 3
# 切换后先让自动曝光稳定，再开始计数。
SETTLE_MS = 2000

MODE_NAME = {
    Sensor.IRCUT_COLOR: "COLOR",
    Sensor.IRCUT_IR: "IR",
}
SUGGEST_NAME = {
    Sensor.IR_SWITCH_NONE: "NONE",
    Sensor.IR_SWITCH_TO_IR: "TO_IR",
    Sensor.IR_SWITCH_TO_COLOR: "TO_COLOR",
}

# 根据模式设置显示宽高
if DISPLAY_MODE == "VIRT":
    DISPLAY_WIDTH = ALIGN_UP(1920, 16)
    DISPLAY_HEIGHT = 1080
elif DISPLAY_MODE == "LCD":
    DISPLAY_WIDTH = 800
    DISPLAY_HEIGHT = 480
elif DISPLAY_MODE == "HDMI":
    DISPLAY_WIDTH = 1920
    DISPLAY_HEIGHT = 1080
else:
    raise ValueError("未知的 DISPLAY_MODE, 请选择 'VIRT', 'LCD' 或 'HDMI'")

# 根据模式初始化显示器
if DISPLAY_MODE == "VIRT":
    Display.init(Display.VIRT, width=DISPLAY_WIDTH, height=DISPLAY_HEIGHT, fps=60)
elif DISPLAY_MODE == "LCD":
    Display.init(Display.ST7701, width=DISPLAY_WIDTH, height=DISPLAY_HEIGHT, to_ide=True)
elif DISPLAY_MODE == "HDMI":
    Display.init(Display.LT9611, width=DISPLAY_WIDTH, height=DISPLAY_HEIGHT, to_ide=True)


def start_sensor(mode):
    sensor.reset()
    sensor.set_framesize(width=DISPLAY_WIDTH, height=DISPLAY_HEIGHT, chn=CAM_CHN_ID_0)
    sensor.set_pixformat(Sensor.RGB888, chn=CAM_CHN_ID_0)
    sensor.ircut_apply(mode)
    sensor.run()
    applied = sensor.ircut_apply()
    print("ircut mode:", MODE_NAME.get(applied, applied))


def mode_for_suggest(suggest):
    if suggest == Sensor.IR_SWITCH_TO_IR:
        return Sensor.IRCUT_IR
    if suggest == Sensor.IR_SWITCH_TO_COLOR:
        return Sensor.IRCUT_COLOR
    return None


try:
    sensor = Sensor(id=sensor_id)
    MediaManager.init()
    start_sensor(Sensor.IRCUT_COLOR)

    caps = sensor.ircut_caps()
    print("ircut caps:", caps)
    ircut_supported = bool(caps.get("is_support"))
    if not ircut_supported:
        print("this sensor has no IR-cut, preview only")

    same_suggest = Sensor.IR_SWITCH_NONE
    same_count = 0
    next_check_ms = time.ticks_add(time.ticks_ms(), SETTLE_MS)

    while True:
        os.exitpoint()

        img = sensor.snapshot(chn=CAM_CHN_ID_0)
        mode = sensor.ircut_apply()
        img.draw_string(8, 8, "IR-Cut " + MODE_NAME.get(mode, str(mode)), color=(255, 255, 0))
        Display.show_image(img)

        if not ircut_supported:
            continue
        now = time.ticks_ms()
        if time.ticks_diff(next_check_ms, now) > 0:
            continue
        next_check_ms = time.ticks_add(now, CHECK_INTERVAL_MS)

        suggest = sensor.ircut_check(
            DAY2NIGHT, NIGHT2DAY, RG_MIN, RG_MAX, BG_MIN, BG_MAX)
        if suggest == Sensor.IR_SWITCH_NONE:
            same_suggest = Sensor.IR_SWITCH_NONE
            same_count = 0
        elif suggest != same_suggest:
            same_suggest = suggest
            same_count = 1
        else:
            same_count += 1
        print("ircut suggest:", SUGGEST_NAME.get(suggest, suggest), "count:", same_count)
        if same_count < SWITCH_COUNT:
            continue

        new_mode = mode_for_suggest(suggest)
        print("switch ircut to", MODE_NAME[new_mode])
        sensor.stop()
        start_sensor(new_mode)
        same_suggest = Sensor.IR_SWITCH_NONE
        same_count = 0
        next_check_ms = time.ticks_add(time.ticks_ms(), SETTLE_MS)

except KeyboardInterrupt as e:
    print("user stop: ", e)
except BaseException as e:
    sys.print_exception(e)
    raise

finally:
    if isinstance(sensor, Sensor):
        try:
            sensor.stop()
        except Exception as e:
            print("sensor stop:", e)
    Display.deinit()
    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    time.sleep_ms(100)
    MediaManager.deinit()
