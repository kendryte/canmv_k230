import time, os, urandom, sys

from media.display import *
from media.media import *

from machine import TOUCH

DISPLAY_WIDTH = ALIGN_UP(800, 16)
DISPLAY_HEIGHT = 480

tp = TOUCH(0)

def display_test():
    print("display and touch test")

    # create image for drawing
    img = image.Image(DISPLAY_WIDTH, DISPLAY_HEIGHT, image.ARGB8888)
    img.clear()

    img2 = image.Image(DISPLAY_WIDTH, DISPLAY_HEIGHT, image.ARGB8888)
    img2.clear()

    # use lcd as display output
    Display.init(Display.ST7701, width = DISPLAY_WIDTH, height = DISPLAY_HEIGHT, to_ide = True)

    try:
        while True:
            os.exitpoint()
            point = tp.read(1)
            if len(point):
                print(point)
                pt = point[0]
                if pt.event == 0 or pt.event == TOUCH.EVENT_DOWN or pt.event == TOUCH.EVENT_MOVE:
                    img2.draw_cross(pt.x, pt.y, color=(255,0,0), width = 1, think_ness = 1)
                    Display.show_image(img2, layer = Display.LAYER_OSD2, alpha = 128)

            x = (urandom.getrandbits(11) % img.width())
            y = (urandom.getrandbits(11) % img.height())
            img.draw_string_advanced(x,y,32, "Hello World!，你好世界！！！", color = (0, 0, 255),)
            # draw result to screen
            Display.show_image(img)
            img.clear()
            time.sleep(0.05)
    except KeyboardInterrupt as e:
        print("user stop: ", e)
    except BaseException as e:
        import sys
        sys.print_exception(e)

    # deinit display
    Display.deinit()
    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    time.sleep_ms(100)

if __name__ == "__main__":
    os.exitpoint(os.EXITPOINT_ENABLE)
    display_test()
