# Local Binary Patterns (LBP) Example
#
# This example shows off how to use the local binary pattern feature descriptor
# on your CanMV Cam. LBP descriptors work like Freak feature descriptors.
#
# WARNING: LBP supports needs to be reworked! As of right now this feature needs
# a lot of work to be made into somethin useful. This script will reamin to show
# that the functionality exists, but, in its current state is inadequate.
import time, os, gc, sys

from media.sensor import *
from media.display import *
from media.media import *

DETECT_WIDTH = ALIGN_UP(320, 16)
DETECT_HEIGHT = 240

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

def camera_drop(frame):
    for i in range(frame):
        os.exitpoint()
        global sensor
        sensor.snapshot()

def capture_picture():
    # create image for drawing
    draw_img = image.Image(DETECT_WIDTH, DETECT_HEIGHT, image.ARGB8888)
    draw_img.draw_string_advanced(0, 0, 32, "Please wait...")
    draw_img.draw_string_advanced(0, 32, 32, "请稍后。。。")
    # draw result to screen
    Display.show_image(draw_img)
    # Load Haar Cascade
    # By default this will use all stages, lower satges is faster but less accurate.
    face_cascade = image.HaarCascade("frontalface", stages=25)
    print(face_cascade)
    d0 = None
    #d0 = image.load_descriptor("/desc.lbp")
    # Skip a few frames to allow the sensor settle down
    # Note: This takes more time when exec from the IDE.
    camera_drop(90)
    fps = time.clock()
    while True:
        fps.tick()
        try:
            os.exitpoint()
            draw_img.clear()

            global sensor
            img = sensor.snapshot()

            objects = img.find_features(face_cascade, threshold=0.5, scale_factor=1.25)
            if objects:
                face = objects[0]
                d1 = img.find_lbp(face)
                if (d0 == None):
                    d0 = d1
                else:
                    dist = image.match_descriptor(d0, d1)
                    draw_img.draw_string_advanced(0, 32, 32, "Match %d%%"%(dist))
                    print("Match %d%%"%(dist))

                draw_img.draw_rectangle([v*SCALE for v in face])
            # Draw FPS
            draw_img.draw_string_advanced(0, 0, 32, "FPS:%.2f"%(fps.fps()))

            # draw result to screen
            Display.show_image(draw_img)

            del img
            gc.collect()
        except KeyboardInterrupt as e:
            print("user stop: ", e)
            break
        except BaseException as e:
            import sys
            sys.print_exception(e)
            break
    del draw_img
    gc.collect()


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
