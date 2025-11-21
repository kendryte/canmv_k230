import time, os, sys

from media.sensor import *
from media.display import *
from media.media import *

sensor_id = 2
sensor = None

# 显示模式选择：可以是 "VIRT"、"LCD" 或 "HDMI"
DISPLAY_MODE = "LCD"

# 根据模式设置显示宽高
if DISPLAY_MODE == "VIRT":
    # 虚拟显示器模式
    DISPLAY_WIDTH = ALIGN_UP(1920, 16)
    DISPLAY_HEIGHT = 1080
elif DISPLAY_MODE == "LCD":
    # 3.1寸屏幕模式
    DISPLAY_WIDTH = 800
    DISPLAY_HEIGHT = 480
elif DISPLAY_MODE == "HDMI":
    # HDMI扩展板模式
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

# 构造一个具有默认配置的摄像头对象
sensor = Sensor(id=sensor_id)
# 重置摄像头sensor
sensor.reset()

# 设置水平镜像
# sensor.set_hmirror(False)
# 设置垂直翻转
# sensor.set_vflip(False)

sensor.set_framesize(width=DISPLAY_WIDTH, height=DISPLAY_HEIGHT, chn=CAM_CHN_ID_0)
sensor.set_pixformat(Sensor.RGB888, chn=CAM_CHN_ID_0)
sensor.auto_focus(True)

# 初始化媒体管理器
MediaManager.init()
# 启动传感器
sensor.run()

while True:
    os.exitpoint()

    # 捕获通道0的图像
    img = sensor.snapshot(chn=CAM_CHN_ID_0)
    # 显示捕获的图像
    Display.show_image(img)

    current_focus_pos = sensor.focus_pos()
    print("当前对焦位置:", current_focus_pos)

# sensor stop run
if isinstance(sensor, Sensor):
    sensor.stop()
# deinit display
Display.deinit()
os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
time.sleep_ms(100)
# release media buffer
MediaManager.deinit()
