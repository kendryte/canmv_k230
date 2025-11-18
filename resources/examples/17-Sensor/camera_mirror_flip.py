# Camera Example
import time, os, sys

from media.sensor import *
from media.display import *
from media.media import *

sensor = None
try:
    print("camera_test")

    # construct a Sensor object with default configure
    sensor = Sensor()
    # sensor reset
    sensor.reset()
    # set hmirror
    sensor.set_hmirror(True)
    # sensor vflip
    sensor.set_vflip(True)

    # set chn0 output size, 1920x1080
    sensor.set_framesize(Sensor.FHD)
    # set chn0 output format
    sensor.set_pixformat(Sensor.YUV420SP)
    # bind sensor chn0 to display layer video 1
    bind_info = sensor.bind_info()
    Display.bind_layer(**bind_info, layer = Display.LAYER_VIDEO1)

    # use hdmi as display output
    Display.init(Display.LT9611, to_ide = True)


    # sensor start run
    sensor.run()

    while True:
        os.exitpoint()
        time.sleep(1)
except KeyboardInterrupt as e:
    print("user stop")
except BaseException as e:
    print(f"Exception '{e}'")
finally:
    # sensor stop run
    if isinstance(sensor, Sensor):
        sensor.stop()
    # deinit display
    Display.deinit()
    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    time.sleep_ms(100)
    # release media buffer

