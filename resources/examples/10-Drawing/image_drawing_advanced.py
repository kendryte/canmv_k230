# Draw Image Testing script with bounce
#
# Exercise draw image with many different values for testing
import time, os, gc, sys

from media.sensor import *
from media.display import *
from media.media import *

DETECT_WIDTH = 640
DETECT_HEIGHT = 480

BOUNCE = True
RESCALE = True

SMALL_IMAGE_SCALE = 3

CYCLE_FORMATS = True
CYCLE_MASK = True

# Used when CYCLE_FORMATS or CYCLE_MASK is true
value_mixer_init = 0

# Location of small image
x_init = 100
y_init = 50

# Bounce direction
xd_init = 1
yd_init = 1

# Small image scaling
rescale_init = 1.0
rd_init = 0.1
max_rescale = 5
min_rescale = 0.2

# Boundary to bounce within
xmin = -DETECT_WIDTH / SMALL_IMAGE_SCALE - 8
ymin = -DETECT_HEIGHT / SMALL_IMAGE_SCALE - 8
xmax = DETECT_WIDTH + 8
ymax = DETECT_HEIGHT + 8

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

    value_mixer = value_mixer_init
    x = x_init
    y = y_init
    xd = xd_init
    yd = yd_init
    rescale = rescale_init
    rd = rd_init

    while True:
        fps.tick()
        # check if should exit.
        os.exitpoint()

        status = ""
        value_mixer = value_mixer + 1

        img = sensor.snapshot()

        small_img = img.mean_pooled(SMALL_IMAGE_SCALE, SMALL_IMAGE_SCALE)
        status = 'rgb565 '
        if CYCLE_FORMATS:
            image_format = (value_mixer >> 8) & 3
            # To test combining different formats
            if (image_format==1): small_img = small_img.to_bitmap(); status = 'bitmap '
            if (image_format==2): small_img = small_img.to_grayscale(); status = 'grayscale '
            if (image_format==3): small_img = small_img.to_rgb565(); status = 'rgb565 '

        # update small image location
        if BOUNCE:
            x = x + xd
            if (x<xmin or x>xmax):
                xd = -xd

            y = y + yd
            if (y<ymin or y>ymax):
                yd = -yd

        # Update small image scale
        if RESCALE:
            rescale = rescale + rd
            if (rescale<min_rescale or rescale>max_rescale):
                rd = -rd

        # Find the center of the image
        scaled_width = int(small_img.width() * abs(rescale))
        scaled_height= int(small_img.height() * abs(rescale))

        apply_mask = CYCLE_MASK and ((value_mixer >> 9) & 1)
        if apply_mask:
            img.draw_image(small_img, int(x), int(y), mask=small_img.to_bitmap(), x_scale=rescale, y_scale=rescale, alpha=240)
            status += 'alpha:240 '
            status += '+mask '
        else:
            img.draw_image(small_img, int(x), int(y), x_scale=rescale, y_scale=rescale, alpha=128)
            status += 'alpha:128 '

        img.draw_string_advanced(8, 0, 32, status)

        # draw result to screen
        Display.show_image(img)

        del small_img
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
