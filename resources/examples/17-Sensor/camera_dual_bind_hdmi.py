# Camera Example
#
# Note: You will need an SD card to run this example.
#
# You can start 2 camera preview.
import time, os, sys

from media.sensor import *
from media.display import *
from media.media import *

sensor0 = None
sensor1 = None

# 注意：当使用多个 Sensor 时，分辨率建议均设置为 1920 × 1080,且 fps 设置为 30
# 使用其他分辨率或帧率时有可能导致输出的图像显示错误

try:
    print("camera_test")

    sensor0 = Sensor(id = 0, width = 1920, height = 1080, fps = 30)
    sensor0.reset()
    # set chn0 output size, 960x540
    sensor0.set_framesize(width = 960, height = 540)
    # set chn0 out format
    sensor0.set_pixformat(Sensor.YUV420SP)
    # bind sensor chn0 to display layer video 1
    bind_info = sensor0.bind_info(x = 0, y = 0)
    Display.bind_layer(**bind_info, layer = Display.LAYER_VIDEO1)

    sensor1 = Sensor(id = 1, width = 1920, height = 1080, fps = 30)
    sensor1.reset()
    # set chn0 output size, 960x540
    sensor1.set_framesize(width = 960, height = 540)
    # set chn0 out format
    sensor1.set_pixformat(Sensor.YUV420SP)

    bind_info = sensor1.bind_info(x = 960, y = 540)
    Display.bind_layer(**bind_info, layer = Display.LAYER_VIDEO2)

    # use hdmi as display output
    Display.init(Display.LT9611, to_ide = True)
    # init media manager
    MediaManager.init()

    # multiple sensor only need one excute run()
    sensor0.run()

    while True:
        os.exitpoint()
        time.sleep(1)
except KeyboardInterrupt as e:
    print("user stop")
except BaseException as e:
    print(f"Exception '{e}'")
finally:
    # multiple sensor all need excute stop()
    if isinstance(sensor0, Sensor):
        sensor0.stop()
    if isinstance(sensor1, Sensor):
        sensor1.stop()
    # or call Sensor.deinit()
    # Sensor.deinit()

    # deinit display
    Display.deinit()

    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    time.sleep_ms(100)
    # deinit media buffer
    MediaManager.deinit()
