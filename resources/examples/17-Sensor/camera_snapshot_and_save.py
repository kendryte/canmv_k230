# Camera Example
#
# Note: You will need an SD card to run this example.
#
# You can start camera preview and capture yuv image.
import time, os, sys

from media.sensor import *
from media.display import *
from media.media import *

# save image raw data, use 7yuv to preview

def save_img(img, chn):
    if img.format() == image.YUV420:
        suffix = "yuv420sp"
    elif img.format() == image.RGB888:
        suffix = "rgb888"
    elif img.format() == image.RGBP888:
        suffix = "rgb888p"
    else:
        suffix = "unkown"

    filename = f"/sdcard/camera_chn_{chn:02d}_{img.width()}x{img.height()}.{suffix}"
    print("save capture image to file:", filename)
    img.save(filename)

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
    sensor.set_pixformat(Sensor.RGBP888, chn = CAM_CHN_ID_2)

    # use hdmi as display output
    Display.init(Display.LT9611, to_ide = True)


    # sensor start run
    sensor.run()

    # drop 100 frames
    for i in range(100):
        sensor.snapshot()

    # snapshot and save
    img = sensor.snapshot(chn = CAM_CHN_ID_0)
    save_img(img, 0)

    img = sensor.snapshot(chn = CAM_CHN_ID_1)
    save_img(img, 1)

    img = sensor.snapshot(chn = CAM_CHN_ID_2)
    save_img(img, 2)

except KeyboardInterrupt as e:
    print(f"user stop")
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

