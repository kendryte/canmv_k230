# Camera Example
import time, os, sys

from media.sensor import *
from media.display import *
from media.media import *

sensor = None

DISPLAY_WIDTH = 960
DISPLAY_HEIGHT = 540

def align_to_8(x):
    """将尺寸对齐到8的倍数"""
    return (x // 8) * 8  # 向下取整对齐


try:
    print("camera_test")

    # construct a Sensor object with default configure
    sensor = Sensor()
    # sensor reset
    sensor.reset()
    # set hmirror
    # sensor.set_hmirror(False)
    # sensor vflip
    # sensor.set_vflip(False)

    # set chn0 output size, 540x960
    sensor.set_framesize(width = DISPLAY_WIDTH, height = align_to_8(DISPLAY_HEIGHT))
    # set chn0 output format
    sensor.set_pixformat(Sensor.YUV420SP)
    # bind sensor chn0 to display layer video 1
    bind_info = sensor.bind_info()
    Display.bind_layer(**bind_info, layer = Display.LAYER_VIDEO1)

    # use lcd as display output
    Display.init(Display.NT35516,width=DISPLAY_WIDTH,height=DISPLAY_HEIGHT,to_ide=True)
    # init media manager
    MediaManager.init()
    # sensor start run
    sensor.run()

    while True:
        os.exitpoint()
except KeyboardInterrupt as e:
    print("user stop: ", e)
except BaseException as e:
    print(f"Exception {e}")
finally:
    # sensor stop run
    if isinstance(sensor, Sensor):
        sensor.stop()
    # deinit display
    Display.deinit()
    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    time.sleep_ms(100)
    # release media buffer
    MediaManager.deinit()
