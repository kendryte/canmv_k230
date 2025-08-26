# Image Drawing Alpha Blending Test
#
# This script tests the performance and quality of the draw_image()
# method which can perform nearest neighbor, bilinear, bicubic, and
# area scaling along with color channel extraction, alpha blending,
# color palette application, and alpha palette application.
import time, os, gc, sys

from media.sensor import *
from media.display import *
from media.media import *

DETECT_WIDTH = 640
DETECT_HEIGHT = 480

small_img = image.Image(4,4,image.RGB565)
small_img.set_pixel(0, 0, (0,   0,   127))
small_img.set_pixel(1, 0, (47,  255, 199))
small_img.set_pixel(2, 0, (0,   188, 255))
small_img.set_pixel(3, 0, (0,   0,   127))
small_img.set_pixel(0, 1, (0,   176, 255))
small_img.set_pixel(1, 1, (222, 0,   0  ))
small_img.set_pixel(2, 1, (50,  255, 195))
small_img.set_pixel(3, 1, (86,  255, 160))
small_img.set_pixel(0, 2, (255, 211, 0  ))
small_img.set_pixel(1, 2, (83,  255, 163))
small_img.set_pixel(2, 2, (255, 211, 0))
small_img.set_pixel(3, 2, (0,   80,  255))
small_img.set_pixel(0, 3, (255, 118, 0  ))
small_img.set_pixel(1, 3, (127, 0,   0  ))
small_img.set_pixel(2, 3, (0,   144, 255))
small_img.set_pixel(3, 3, (50,  255, 195))

big_img = image.Image(128,128,image.RGB565)
big_img.draw_image(small_img, 0, 0, x_scale=32, y_scale=32)

alpha_div = 1
alpha_value_init = 0
alpha_step_init = 2

x_bounce_init = DETECT_WIDTH//2
x_bounce_toggle_init = 1

y_bounce_init = DETECT_HEIGHT//2
y_bounce_toggle_init = 1

sensor = None

try:
    # construct a Sensor object with default configure
    sensor = Sensor(width = DETECT_WIDTH, height = DETECT_HEIGHT)
    # sensor reset
    sensor.reset()
    # set hmirror
    # sensor.set_hmirror(False)
    # sensor vflip
    # sensor.set_vflip(False)
    # set chn0 output size
    sensor.set_framesize(width = DETECT_WIDTH, height = DETECT_HEIGHT)
    # set chn0 output format
    sensor.set_pixformat(Sensor.RGB565)

    # use hdmi as display output, set to VGA
    # Display.init(Display.LT9611, width = 640, height = 480, to_ide = True)

    # use hdmi as display output, set to 1080P
    # Display.init(Display.LT9611, width = 1920, height = 1080, to_ide = True)

    # use lcd as display output
    # Display.init(Display.ST7701, to_ide = True)

    # use IDE as output
    Display.init(Display.VIRT, width = DETECT_WIDTH, height = DETECT_HEIGHT, fps = 100, to_ide = True)

    # init media manager
    MediaManager.init()
    # sensor start run
    sensor.run()

    fps = time.clock()

    alpha_value = alpha_value_init
    alpha_step = alpha_step_init
    x_bounce = x_bounce_init
    x_bounce_toggle = x_bounce_toggle_init
    y_bounce = y_bounce_init
    y_bounce_toggle = y_bounce_toggle_init

    while True:
        fps.tick()
        # check if should exit.
        os.exitpoint()

        img = sensor.snapshot()

        img.draw_image(big_img, x_bounce, y_bounce, rgb_channel=-1, alpha=alpha_value//alpha_div)

        x_bounce += x_bounce_toggle
        if abs(x_bounce-(img.width()//2)) >= (img.width()//2): x_bounce_toggle = -x_bounce_toggle

        y_bounce += y_bounce_toggle
        if abs(y_bounce-(img.height()//2)) >= (img.height()//2): y_bounce_toggle = -y_bounce_toggle

        alpha_value += alpha_step
        if not alpha_value or alpha_value//alpha_div == 256: alpha_step = -alpha_step

        # draw result to screen
        Display.show_image(img)

        gc.collect()
        print(fps.fps())
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
    MediaManager.deinit()
