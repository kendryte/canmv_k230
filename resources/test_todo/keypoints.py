# Object tracking with keypoints example.
# Show the camera an object and then run the script. A set of keypoints will be extracted
# once and then tracked in the following frames. If you want a new set of keypoints re-run
# the script. NOTE: see the docs for arguments to tune find_keypoints and match_keypoints.
import time, os, gc, sys

from media.sensor import *
from media.display import *
from media.media import *

DETECT_WIDTH = ALIGN_UP(640, 16)
DETECT_HEIGHT = 480

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
    sensor.set_pixformat(Sensor.YUV420SP)
    # bind sensor chn0 to display layer video 1
    bind_info = sensor.bind_info()
    Display.bind_layer(**bind_info, layer = Display.LAYER_VIDEO1)

    # set chn1 output format
    sensor.set_framesize(width= DETECT_WIDTH, height = DETECT_HEIGHT, chn = CAM_CHN_ID_1)
    sensor.set_pixformat(Sensor.YUV420SP, chn = CAM_CHN_ID_1)

    # use hdmi as display output
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


def camera_drop(frame):
    for i in range(frame):
        os.exitpoint()
        global sensor
        sensor.snapshot()

def capture_picture():
    # create image for drawing
    draw_img = image.Image(DETECT_WIDTH, DETECT_HEIGHT, image.ARGB8888)
    kpts1 = None
    # NOTE: uncomment to load a keypoints descriptor from file
    #kpts1 = image.load_descriptor("/desc.orb")
    camera_drop(60)
    fps = time.clock()
    while True:
        fps.tick()
        try:
            os.exitpoint()
            draw_img.clear()

            global sensor
            yuv420_img = sensor.snapshot(chn = CAM_CHN_ID_1)
            img = image.Image(yuv420_img.width(), yuv420_img.height(), image.GRAYSCALE, alloc=image.ALLOC_HEAP, data=yuv420_img)

            if kpts1 == None:
                # NOTE: By default find_keypoints returns multi-scale keypoints extracted from an image pyramid.
                kpts1 = img.find_keypoints(max_keypoints=150, threshold=10, scale_factor=1.2)
                if kpts1:
                    draw_img.draw_keypoints(kpts1)
                    time.sleep(2)
                    fps.reset()
            else:
                # NOTE: When extracting keypoints to match the first descriptor, we use normalized=True to extract
                # keypoints from the first scale only, which will match one of the scales in the first descriptor.
                kpts2 = img.find_keypoints(max_keypoints=150, threshold=10, normalized=True)
                if kpts2:
                    match = image.match_descriptor(kpts1, kpts2, threshold=85)
                    if (match.count()>10):
                        # If we have at least n "good matches"
                        # Draw bounding rectangle and cross.
                        draw_img.draw_rectangle([v for v in match.rect()])
                        draw_img.draw_cross(match.cx(), match.cy(), size=10)

                    print(kpts2, "matched:%d dt:%d"%(match.count(), match.theta()))
                    # NOTE: uncomment if you want to draw the keypoints
                    #img.draw_keypoints(kpts2, size=KEYPOINTS_SIZE, matched=True)
                pass

            # draw result to screen
            Display.show_image(draw_img)
            del img
            gc.collect()
            print(fps.fps())
        except KeyboardInterrupt as e:
            print("user stop: ", e)
            break
        except BaseException as e:
            print(f"Exception {e}")
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
        sys.print_exception(e)
    finally:
        if camera_is_init:
            print("camera deinit")
            camera_deinit()

if __name__ == "__main__":
    main()
