"""Capture JPEG images by clicking Capture in the IDE preview window.

The virtual display receives IDE mouse events through TOUCH.DEV_IDE.
No physical display, touchscreen or GPIO button is required.
"""

import gc
import os
import sys
import time
import uctypes

import cv_lite
import image
import lvgl as lv
from machine import TOUCH
from media.display import Display
from media.sensor import Sensor, CAM_CHN_ID_0, CAM_CHN_ID_2
from libs.DisplayConfig import init_display


display_mode = "virt"
display_size = [1280, 720]  # Set the virtual display width and height.
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
IMG_SAVE_PATH = "/data/collect_data/"
IMG_SAVE_NAME_BEGIN = "1_"

# Independent hardware layers, ordered from the preview to the controls.
PREVIEW_LAYER = Display.LAYER_VIDEO1
GUIDE_LAYER = Display.LAYER_OSD1
UI_LAYER = Display.LAYER_OSD2


def prepare_directory():
    """Create the output directory and return the next unused image index."""
    current = ""
    for part in IMG_SAVE_PATH.strip("/").split("/"):
        current += "/" + part
        try:
            os.mkdir(current)
        except OSError as exc:
            if exc.args[0] != 17:
                raise
            if not os.stat(current)[0] & 0x4000:
                raise
    next_index = 0
    for name in os.listdir(IMG_SAVE_PATH):
        if name.startswith(IMG_SAVE_NAME_BEGIN) and name.endswith(".jpg"):
            number = name[len(IMG_SAVE_NAME_BEGIN):-4]
            if number.isdigit():
                next_index = max(next_index, int(number) + 1)
    return next_index


class CaptureApp:
    """Own the camera, display, LVGL buffers and touch devices."""

    def __init__(self):
        self.sensor = None
        self.video_bound = False
        self.display_ready = False
        self.lv_ready = False
        self.buffers = []
        self.guide_image = None
        self.touches = []
        self.inputs = []
        self.pending = False
        self.save_num = 0

    def flush(self, driver, area, color):
        """Present the completed transparent UI buffer above the preview."""
        try:
            if driver.flush_is_last():
                address = uctypes.addressof(color.__dereference__())
                frame = self.buffers[0]
                if address != frame.virtaddr():
                    frame = self.buffers[1]
                Display.show_image(frame, layer=UI_LAYER)
        finally:
            driver.flush_ready()

    def add_touch(self, device):
        """Attach one physical or IDE touch source to LVGL."""
        try:
            touch = TOUCH(device, range_x=self.width, range_y=self.height)
        except Exception as exc:
            print("Touch unavailable:", device, exc)
            return
        self.touches.append(touch)
        point = lv.point_t({"x": 0, "y": 0})

        def read_touch(driver, data):
            points = touch.read(1)
            data.state = lv.INDEV_STATE.RELEASED
            if points:
                point.x = points[0].x
                point.y = points[0].y
                if points[0].event in (TOUCH.EVENT_DOWN, TOUCH.EVENT_MOVE):
                    data.state = lv.INDEV_STATE.PRESSED
            data.point = point

        indev = lv.indev_create()
        self.inputs.append(indev)
        indev.set_type(lv.INDEV_TYPE.POINTER)
        indev.set_read_cb(read_touch)

    def request_capture(self, event):
        """Queue one capture; file I/O runs outside the LVGL callback."""
        if not self.pending:
            self.pending = True
            self.button.add_state(lv.STATE.DISABLED)
            self.status.set_text("Saving...")

    def setup(self):
        """Initialize display, camera and a transparent capture interface."""
        self.save_num = prepare_directory()
        self.width, self.height = init_display(
            display_mode, display_size, to_ide=True, osd_num=2)
        self.display_ready = True
        self.sensor = Sensor(fps=30)
        self.sensor.reset()
        self.sensor.set_framesize(w=self.width, h=self.height,
                                  chn=CAM_CHN_ID_0)
        self.sensor.set_pixformat(Sensor.YUV420SP, chn=CAM_CHN_ID_0)
        self.sensor.set_framesize(w=VIDEO_WIDTH, h=VIDEO_HEIGHT,
                                  chn=CAM_CHN_ID_2)
        self.sensor.set_pixformat(Sensor.RGB888, chn=CAM_CHN_ID_2)
        # VICAP scales the live preview without allocating Python frame copies.
        Display.bind_layer(**self.sensor.bind_info(x=0, y=0, chn=CAM_CHN_ID_0),
                           layer=PREVIEW_LAYER)
        self.video_bound = True

        lv.init()
        self.lv_ready = True
        self.driver = lv.disp_create(self.width, self.height)
        for _ in range(2):
            buffer = image.Image(self.width, self.height, image.BGRA8888)
            buffer.clear()
            self.buffers.append(buffer)
        self.driver.set_color_format(lv.COLOR_FORMAT.ARGB8888)
        self.driver.set_draw_buffers(
            self.buffers[0].bytearray(), self.buffers[1].bytearray(),
            self.buffers[0].size(), lv.DISP_RENDER_MODE.FULL)
        self.driver.set_flush_cb(self.flush)
        self.add_touch(TOUCH.DEV_IDE)
        if not self.touches:
            raise RuntimeError("IDE virtual touch is required for mouse capture")

        screen = lv.scr_act()
        screen.set_style_bg_opa(lv.OPA.TRANSP, 0)
        screen.clear_flag(lv.obj.FLAG.SCROLLABLE)
        size = min(VIDEO_WIDTH, VIDEO_HEIGHT) * 6 // 7
        # The guide is static: allocate and submit it once, outside LVGL.
        self.guide_image = image.Image(self.width, self.height, image.ARGB8888)
        self.guide_image.clear()
        self.guide_image.draw_rectangle(
            (VIDEO_WIDTH - size) * self.width // (2 * VIDEO_WIDTH),
            (VIDEO_HEIGHT - size) * self.height // (2 * VIDEO_HEIGHT),
            size * self.width // VIDEO_WIDTH, size * self.height // VIDEO_HEIGHT,
            color=(255, 255, 0, 0), thickness=2)
        Display.show_image(self.guide_image, layer=GUIDE_LAYER)
        footer = lv.obj(screen)
        footer.set_size(self.width, 76)
        footer.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        footer.set_style_pad_all(0, 0)
        footer.set_style_radius(0, 0)
        footer.set_style_border_width(0, 0)
        footer.set_style_bg_color(lv.color_hex(0x202020), 0)
        footer.set_style_bg_opa(220, 0)
        footer.clear_flag(lv.obj.FLAG.SCROLLABLE)

        self.button = lv.btn(footer)
        self.button.set_size(116, 48)
        self.button.align(lv.ALIGN.RIGHT_MID, -12, 0)
        self.button.set_style_radius(8, 0)
        self.button.add_event(self.request_capture, lv.EVENT.CLICKED, None)
        label = lv.label(self.button)
        label.set_text(lv.SYMBOL.SAVE + " Capture")
        label.center()
        self.status = lv.label(footer)
        self.status.set_width(self.width - 152)
        self.status.set_long_mode(lv.label.LONG.DOT)
        self.status.set_style_text_color(lv.color_hex(0xFFFFFF), 0)
        self.status.align(lv.ALIGN.LEFT_MID, 12, 0)
        self.status.set_text("Ready | 640x480")
        self.sensor.run()

    def capture(self, frame):
        """Save the unannotated RGB frame using the original JPEG interface."""
        name = IMG_SAVE_NAME_BEGIN + str(self.save_num) + ".jpg"
        try:
            cv_lite.save_image(
                IMG_SAVE_PATH + name, [VIDEO_HEIGHT, VIDEO_WIDTH],
                frame.to_numpy_ref().copy())
            self.save_num += 1
            self.status.set_text("Saved: " + name)
            print("Saved:", IMG_SAVE_PATH + name)
        except Exception as exc:
            self.status.set_text("Save failed")
            sys.print_exception(exc)
        finally:
            self.pending = False
            self.button.clear_state(lv.STATE.DISABLED)
            gc.collect()

    def run(self):
        """Poll mouse input while hardware streams the independent preview."""
        while True:
            os.exitpoint()
            lv.task_handler()
            if self.pending:
                frame = self.sensor.snapshot(chn=CAM_CHN_ID_2)
                try:
                    self.capture(frame)
                finally:
                    frame = None
                    gc.collect()
            time.sleep_ms(5)

    def close(self):
        """Attempt every cleanup step even if an individual release fails."""
        actions = [indev.delete for indev in self.inputs]
        actions.extend(touch.deinit for touch in self.touches)
        if self.lv_ready:
            actions.append(lv.deinit)
        if self.video_bound:
            actions.append(lambda: Display.unbind_layer(PREVIEW_LAYER))
        if self.sensor is not None:
            actions.append(self.sensor.stop)
        if self.display_ready:
            actions.append(Display.deinit)
        for release in actions:
            try:
                release()
            except Exception as exc:
                sys.print_exception(exc)


def main():
    """Run until IDE stop or an unrecoverable camera/display error."""
    app = CaptureApp()
    os.exitpoint(os.EXITPOINT_ENABLE)
    try:
        app.setup()
        app.run()
    except KeyboardInterrupt:
        print("Capture stopped")
    except BaseException as exc:
        sys.print_exception(exc)
    finally:
        app.close()
        app = None
        gc.collect()
        os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
        time.sleep_ms(50)


if __name__ == "__main__":
    main()
