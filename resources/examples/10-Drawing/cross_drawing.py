# Cross Drawing
#
# This example shows off drawing crosses on the CanMV Cam.
import time, os, gc, sys, urandom

from media.display import *
from media.media import *


DISPLAY_IS_HDMI = True
DISPLAY_IS_LCD = False
DISPLAY_IS_IDE = False

try:
    # default size
    width = 640
    height = 480
    if DISPLAY_IS_HDMI:
        # use hdmi as display output, set to 1080P
        Display.init(Display.LT9611, width = 1920, height = 1080, to_ide = True)
        width = 1920
        height = 1080
    elif DISPLAY_IS_LCD:
        # use lcd as display output
        Display.init(Display.ST7701, width = 800, height = 480, to_ide = True)
        width = 800
        height = 480
    elif DISPLAY_IS_IDE:
        # use IDE as output
        Display.init(Display.VIRT, width = 800, height = 480, fps = 100, to_ide = True)
        width = 800
        height = 480
    else:
        raise ValueError("Shoule select a display.")
    # init media manager
    MediaManager.init()

    fps = time.clock()
    # create image for drawing
    img = image.Image(width, height, image.ARGB8888)

    while True:
        fps.tick()

        # check if should exit.
        os.exitpoint()

        img.clear()
        for i in range(10):
            x = (urandom.getrandbits(30) % (2*img.width())) - (img.width()//2)
            y = (urandom.getrandbits(30) % (2*img.height())) - (img.height()//2)
            r = (urandom.getrandbits(30) % 127) + 128
            g = (urandom.getrandbits(30) % 127) + 128
            b = (urandom.getrandbits(30) % 127) + 128
            # If the first argument is a scaler then this method expects
            # to see x and y. Otherwise, it expects a (x,y) tuple.
            img.draw_cross(x, y, color = (r, g, b), size = 10, thickness = 2)

        # draw result to screen
        Display.show_image(img)

        print(fps.fps())

        # max 100 fps
        time.sleep_ms(10)

except KeyboardInterrupt as e:
    print(f"user stop")
except BaseException as e:
    print(f"Exception '{e}'")
finally:
    # deinit display
    Display.deinit()

    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    time.sleep_ms(100)

    # release media buffer
    MediaManager.deinit()
