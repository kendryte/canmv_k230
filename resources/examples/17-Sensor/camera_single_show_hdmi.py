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
    # sensor.set_hmirror(False)
    # sensor vflip
    # sensor.set_vflip(False)

    # set chn0 output size, 1920x1080
    sensor.set_framesize(Sensor.FHD)
    # set chn0 output format
    sensor.set_pixformat(Sensor.YUV420SP)
    # bind sensor chn0 to display layer video 1
    bind_info = sensor.bind_info()
    Display.bind_layer(**bind_info, layer = Display.LAYER_VIDEO1)

    # set chn1 output format
    sensor.set_framesize(width = 640, height = 480, chn = CAM_CHN_ID_1)
    sensor.set_pixformat(Sensor.RGB888, chn = CAM_CHN_ID_1)

    # set chn2 output format
    sensor.set_framesize(width = 640, height = 480, chn = CAM_CHN_ID_2)
    sensor.set_pixformat(Sensor.RGB565, chn = CAM_CHN_ID_2)

    # use hdmi as display output
    Display.init(Display.LT9611, to_ide = True, osd_num = 2)


    # sensor start run
    sensor.run()

    while True:
        os.exitpoint()

        img = sensor.snapshot(chn = CAM_CHN_ID_1)
        Display.show_image(img, alpha = 128)

        img = sensor.snapshot(chn = CAM_CHN_ID_2)
        Display.show_image(img, x = 1920 - 640, layer = Display.LAYER_OSD1)

except KeyboardInterrupt as e:
    print("user stop: ", e)
except BaseException as e:
    import sys
    sys.print_exception(e)
finally:
    # sensor stop run
    if isinstance(sensor, Sensor):
        sensor.stop()
    # deinit display
    Display.deinit()
    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    time.sleep_ms(100)
    # release media buffer

