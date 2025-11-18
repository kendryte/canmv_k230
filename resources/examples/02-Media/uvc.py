import time, os, urandom, sys, gc

from media.display import *
from media.media import *
from media.uvc import *

DISPLAY_WIDTH = ALIGN_UP(800, 16)
DISPLAY_HEIGHT = 480

# use lcd as display output
Display.init(Display.ST7701, width = DISPLAY_WIDTH, height = DISPLAY_HEIGHT, to_ide = True)

while True:
    plugin, dev = UVC.probe()
    if plugin:
        print(f"detect USB Camera {dev}")
        break

mode = UVC.video_mode(640, 480, UVC.FORMAT_MJPEG, 30)

succ, mode = UVC.select_video_mode(mode)
print(f"select mode success: {succ}, mode: {mode}")

UVC.start(cvt = False)

fps = time.clock()

while True:
    fps.tick()
    img = UVC.snapshot()
    if img is not None:
        try:
            img = img.to_rgb565()
            Display.show_image(img)
            img.__del__()
            gc.collect()
        except OSError as e:
            pass

    print(f"fps: {fps.fps()}")

# deinit display
Display.deinit()
UVC.stop()
time.sleep_ms(100)
