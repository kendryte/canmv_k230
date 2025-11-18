# Erode and Dilate Example
#
# This example shows off the erode and dilate functions which you can run on
# a binary image to remove noise. This example was originally a test but its
# useful for showing off how these functions work.
import time, os, gc, sys

from media.sensor import *
from media.display import *
from media.media import *

DETECT_WIDTH = ALIGN_UP(640, 16)
DETECT_HEIGHT = 480

grayscale_thres = (170, 255)
rgb565_thres = (70, 100, -128, 127, -128, 127)

sensor = None

def camera_init():
    global sensor
    # construct a Sensor object with default configure
    sensor = Sensor(width=DETECT_WIDTH,height=DETECT_HEIGHT)
    # sensor reset
    sensor.reset()
    # set hmirror
    # sensor.set_hmirror(False)
    # sensor vflip
    # sensor.set_vflip(False)

    # set chn0 output size
    sensor.set_framesize(width=DETECT_WIDTH,height=DETECT_HEIGHT)
    # set chn0 output format
    sensor.set_pixformat(Sensor.RGB565)

    # use IDE as display output
    Display.init(Display.VIRT, width= DETECT_WIDTH, height = DETECT_HEIGHT,fps=100,to_ide = True)


    # sensor start run
    sensor.run()

def camera_deinit():
    global sensor

    # sensor stop run
    sensor.stop()
    # deinit display
    Display.deinit()
    # sleep
    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    time.sleep_ms(100)
    # release media buffer


def capture_picture():

    frame_count = 0
    fps = time.clock()
    while True:
        fps.tick()
        try:
            os.exitpoint()
            global sensor
            img = sensor.snapshot()
            # Test red threshold
            if frame_count < 100:
                img.binary([rgb565_thres])
                img.erode(2)
            # Test green threshold
            elif frame_count < 200:
                img.binary([rgb565_thres])
                img.dilate(2)
            # Test blue threshold
            elif frame_count < 300:
                img = img.to_grayscale()
                img.binary([grayscale_thres])
                img.erode(2)
                img = img.to_rgb565()
            # Test not red threshold
            elif frame_count < 400:
                img = img.to_grayscale()
                img.binary([grayscale_thres])
                img.dilate(2)
                img = img.to_rgb565()
            else:
                frame_count = 0
            frame_count = frame_count + 1
            # draw result to screen
            Display.show_image(img)
            img = None
            gc.collect()
            print(fps.fps())
        except KeyboardInterrupt as e:
            print("user stop: ", e)
            break
        except BaseException as e:
            import sys
            sys.print_exception(e)
            break

def main():
    os.exitpoint(os.EXITPOINT_ENABLE)
    camera_is_init = False
    try:
        print("camera init")
        camera_init()
        camera_is_init = True
        print("camera capture")
        capture_picture()
    except Exception as e:
        import sys
        sys.print_exception(e)
    finally:
        if camera_is_init:
            print("camera deinit")
            camera_deinit()

if __name__ == "__main__":
    main()
