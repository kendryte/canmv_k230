# Fast Linear Regression Example
#
# This example shows off how to use the get_regression() method on your CanMV Cam
# to get the linear regression of a ROI. Using this method you can easily build
# a robot which can track lines which all point in the same general direction
# but are not actually connected. Use find_blobs() on lines that are nicely
# connected for better filtering options and control.
#
# This is called the fast linear regression because we use the least-squares
# method to fit the line. However, this method is NOT GOOD FOR ANY images that
# have a lot (or really any) outlier points which corrupt the line fit...
import time, os, gc, sys

from media.sensor import *
from media.display import *
from media.media import *


DETECT_WIDTH = ALIGN_UP(640, 16)
DETECT_HEIGHT = 480

THRESHOLD = (0, 100) # Grayscale threshold for dark things...
BINARY_VISIBLE = True # Does binary first so you can see what the linear regression
                      # is being run on... might lower FPS though.

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
    sensor.set_pixformat(Sensor.GRAYSCALE)

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

def capture_picture():
    fps = time.clock()
    while True:
        fps.tick()
        try:
            os.exitpoint()

            global sensor
            img = sensor.snapshot()
            img = img.binary([THRESHOLD]) if BINARY_VISIBLE else img
            # Returns a line object similar to line objects returned by find_lines() and
            # find_line_segments(). You have x1(), y1(), x2(), y2(), length(),
            # theta() (rotation in degrees), rho(), and magnitude().
            #
            # magnitude() represents how well the linear regression worked. It goes from
            # (0, INF] where 0 is returned for a circle. The more linear the
            # scene is the higher the magnitude.
            line = img.get_regression([(255,255) if BINARY_VISIBLE else THRESHOLD])
            if (line): img.draw_line(line.line(), color = 127)
            print("FPS %f, mag = %s" % (fps.fps(), str(line.magnitude()) if (line) else "N/A"))

            # draw result to screen
            Display.show_image(img)

            del img
            gc.collect()
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
