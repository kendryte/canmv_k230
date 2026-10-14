import time, os, sys, gc

from media.display import *
from media.media import *
from machine import TOUCH


DISPLAY_WIDTH = ALIGN_UP(640, 16)
DISPLAY_HEIGHT = 480

EVENT_NAME = {
    TOUCH.EVENT_NONE: "none",
    TOUCH.EVENT_DOWN: "down",
    TOUCH.EVENT_UP: "up",
    TOUCH.EVENT_MOVE: "move",
}

EVENT_COLOR = {
    TOUCH.EVENT_DOWN: (0, 255, 0),
    TOUCH.EVENT_UP: (255, 80, 80),
    TOUCH.EVENT_MOVE: (255, 220, 0),
}


def event_name(event):
    return EVENT_NAME.get(event, "event-%d" % event)


def print_error(err):
    printer = getattr(sys, "print_exception", None)
    if printer:
        printer(err)
    else:
        print("exception: %s" % err)


def draw_screen(img, last_point, event_count, fps):
    img.clear()
    img.draw_rectangle(0, 0, img.width() - 1, img.height() - 1,
                       color=(80, 80, 80), thickness=2, fill=False)
    img.draw_cross(img.width() // 2, img.height() // 2,
                   color=(80, 80, 80), size=16, thickness=1)
    img.draw_string_advanced(12, 8, 22, "IDE virtual touch test",
                             color=(255, 255, 255))
    img.draw_string_advanced(12, 36, 18,
                             "Click the VS Code preview webview.",
                             color=(180, 220, 255))
    img.draw_string_advanced(12, 62, 18,
                             "events=%d  fps=%.1f" % (event_count, fps),
                             color=(180, 180, 180))

    if last_point is None:
        img.draw_string_advanced(12, 96, 20, "waiting for touch...",
                                 color=(255, 220, 0))
        return

    x = max(0, min(img.width() - 1, last_point.x))
    y = max(0, min(img.height() - 1, last_point.y))
    color = EVENT_COLOR.get(last_point.event, (255, 255, 255))

    img.draw_cross(x, y, color=color, size=28, thickness=3)
    img.draw_circle(x, y, 18, color=color, thickness=2, fill=False)
    img.draw_string_advanced(12, 96, 20,
                             "%s id=%d x=%d y=%d w=%d t=%d" % (
                                 event_name(last_point.event),
                                 last_point.track_id,
                                 last_point.x,
                                 last_point.y,
                                 last_point.width,
                                 last_point.timestamp,
                             ),
                             color=color)


def virtual_touch_test():
    print("IDE virtual touch test")
    print("Open Preview, then click inside the image.")

    touch = TOUCH(TOUCH.DEV_IDE, range_x=DISPLAY_WIDTH, range_y=DISPLAY_HEIGHT)
    img = image.Image(DISPLAY_WIDTH, DISPLAY_HEIGHT, image.ARGB8888)
    clock = time.clock()
    last_point = None
    event_count = 0
    last_redraw = time.ticks_ms()
    redraw_count = 0

    Display.init(Display.VIRT, width=DISPLAY_WIDTH, height=DISPLAY_HEIGHT,
                 fps=60, to_ide=True)

    try:
        while True:
            os.exitpoint()
            clock.tick()

            points = touch.read(5)
            if len(points):
                for point in points:
                    event_count += 1
                    last_point = point
                    print("%s id=%d x=%d y=%d w=%d t=%d" % (
                        event_name(point.event),
                        point.track_id,
                        point.x,
                        point.y,
                        point.width,
                        point.timestamp,
                    ))

            now = time.ticks_ms()
            if time.ticks_diff(now, last_redraw) >= 100:
                draw_screen(img, last_point, event_count, clock.fps())
                Display.show_image(img)
                last_redraw = now
                redraw_count += 1
                if redraw_count >= 50:
                    gc.collect()
                    redraw_count = 0
            time.sleep_ms(5)
    except KeyboardInterrupt as e:
        print("user stop: ", e)
    except BaseException as e:
        print_error(e)
        raise
    finally:
        touch.deinit()
        Display.deinit()
        os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
        time.sleep_ms(100)


if __name__ == "__main__":
    os.exitpoint(os.EXITPOINT_ENABLE)
    virtual_touch_test()
