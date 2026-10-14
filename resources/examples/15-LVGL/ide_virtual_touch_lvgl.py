import time, os, sys, gc

import lvgl as lv
import uctypes
from media.display import *
from media.media import *
from machine import TOUCH


DISPLAY_TYPE = Display.VIRT
DISPLAY_WIDTH = ALIGN_UP(800, 16)
DISPLAY_HEIGHT = 480

disp_imgs = None
status_label = None
button_labels = []
button_states = [False, False]
click_count = 0


def print_error(err):
    printer = getattr(sys, "print_exception", None)
    if printer:
        printer(err)
    else:
        print("exception: %s" % err)


class IdeVirtualTouch:
    def __init__(self):
        self.touch = TOUCH(TOUCH.DEV_IDE, range_x=DISPLAY_WIDTH, range_y=DISPLAY_HEIGHT)
        self.indev = lv.indev_create()
        self.indev.set_type(lv.INDEV_TYPE.POINTER)
        self.indev.set_read_cb(self.callback)

    def callback(self, driver, data):
        try:
            points = self.touch.read(1)
            if points and len(points) > 0:
                point = points[0]
                data.point.x = point.x
                data.point.y = point.y
                if point.event in (TOUCH.EVENT_DOWN, TOUCH.EVENT_MOVE):
                    data.state = lv.INDEV_STATE.PRESSED
                else:
                    data.state = lv.INDEV_STATE.RELEASED
            else:
                data.state = lv.INDEV_STATE.RELEASED
        except Exception:
            data.state = lv.INDEV_STATE.RELEASED

    def deinit(self):
        try:
            self.touch.deinit()
        except Exception:
            pass


def lvgl_flush_cb(disp_drv, area, color):
    global disp_imgs
    if disp_drv.flush_is_last():
        ptr = uctypes.addressof(color.__dereference__())
        img_to_show = disp_imgs[0] if disp_imgs[0].virtaddr() == ptr else disp_imgs[1]
        Display.show_image(img_to_show, layer=Display.LAYER_OSD0)
    disp_drv.flush_ready()


def lvgl_setup():
    global disp_imgs

    lv.init()
    disp_imgs = [
        image.Image(DISPLAY_WIDTH, DISPLAY_HEIGHT, image.BGRA8888),
        image.Image(DISPLAY_WIDTH, DISPLAY_HEIGHT, image.BGRA8888),
    ]

    disp_drv = lv.disp_create(DISPLAY_WIDTH, DISPLAY_HEIGHT)
    disp_drv.set_color_format(lv.COLOR_FORMAT.ARGB8888)
    disp_drv.set_draw_buffers(
        disp_imgs[0].bytearray(),
        disp_imgs[1].bytearray(),
        disp_imgs[0].size(),
        lv.DISP_RENDER_MODE.FULL,
    )
    disp_drv.set_flush_cb(lvgl_flush_cb)


def update_status():
    if status_label is None:
        return

    a_state = "ON" if button_states[0] else "OFF"
    b_state = "ON" if button_states[1] else "OFF"
    status_label.set_text(
        "Button A: %s\nButton B: %s\nClicks: %d" % (
            a_state,
            b_state,
            click_count,
        )
    )

    for index, label in enumerate(button_labels):
        label.set_text(
            "Turn %s %s" % (
                "A" if index == 0 else "B",
                "OFF" if button_states[index] else "ON",
            )
        )


def button_clicked(index):
    global click_count
    button_states[index] = not button_states[index]
    click_count += 1
    update_status()
    print(
        "button %s -> %s" % (
            "A" if index == 0 else "B",
            "on" if button_states[index] else "off",
        )
    )


def button_a_event(event):
    button_clicked(0)


def button_b_event(event):
    button_clicked(1)


def create_button(parent, text, align, x, y, callback):
    btn = lv.btn(parent)
    btn.set_size(220, 82)
    btn.align(align, x, y)
    btn.set_style_radius(12, 0)
    btn.set_style_bg_color(lv.palette_main(lv.PALETTE.BLUE), 0)

    label = lv.label(btn)
    label.set_text(text)
    label.center()
    btn.add_event(callback, lv.EVENT.CLICKED, None)
    return label


def user_gui_init():
    global status_label, button_labels

    scr = lv.scr_act()
    scr.set_style_bg_color(lv.color_hex(0x20242A), 0)

    title = lv.label(scr)
    title.set_text("IDE Virtual Touch + LVGL")
    title.set_style_text_color(lv.color_hex(0xFFFFFF), 0)
    title.align(lv.ALIGN.TOP_MID, 0, 28)

    hint = lv.label(scr)
    hint.set_text("Click the buttons from the VS Code Preview image.")
    hint.set_style_text_color(lv.color_hex(0xB8C7D9), 0)
    hint.align(lv.ALIGN.TOP_MID, 0, 62)

    panel = lv.obj(scr)
    panel.set_size(420, 150)
    panel.align(lv.ALIGN.CENTER, 0, -34)
    panel.set_style_bg_color(lv.color_hex(0x101418), 0)
    panel.set_style_border_color(lv.palette_main(lv.PALETTE.CYAN), 0)
    panel.set_style_border_width(2, 0)
    panel.set_style_radius(10, 0)

    status_label = lv.label(panel)
    status_label.set_style_text_color(lv.color_hex(0xD8F6FF), 0)
    status_label.center()

    button_labels = [
        create_button(scr, "Turn A ON", lv.ALIGN.BOTTOM_LEFT, 110, -56, button_a_event),
        create_button(scr, "Turn B ON", lv.ALIGN.BOTTOM_RIGHT, -110, -56, button_b_event),
    ]
    update_status()


def main():
    touch = None
    os.exitpoint(os.EXITPOINT_ENABLE)
    Display.init(DISPLAY_TYPE, width=DISPLAY_WIDTH, height=DISPLAY_HEIGHT, fps=60, to_ide=True)
    try:
        lvgl_setup()
        touch = IdeVirtualTouch()
        user_gui_init()
        print("IDE virtual touch LVGL demo")
        print("Open Preview, then click Button A or Button B.")

        while True:
            os.exitpoint()
            delay = lv.task_handler()
            if delay is None or delay < 5:
                delay = 5
            time.sleep_ms(delay)
    except KeyboardInterrupt as e:
        print("user stop: ", e)
    except BaseException as e:
        print_error(e)
        raise
    finally:
        if touch:
            touch.deinit()
        lv.deinit()
        Display.deinit()
        gc.collect()
        os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
        time.sleep_ms(100)


if __name__ == "__main__":
    main()
