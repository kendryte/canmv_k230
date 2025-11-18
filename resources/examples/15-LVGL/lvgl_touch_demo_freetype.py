from media.display import *
from media.media import *
import time, os, sys, gc
import lvgl as lv
from machine import TOUCH

DISPLAY_WIDTH = ALIGN_UP(800, 16)
DISPLAY_HEIGHT = 480

def display_init():
    # use hdmi for display
    Display.init(Display.ST7701, width = 800, height = 480, to_ide = True)



def display_deinit():
    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    time.sleep_ms(50)
    # deinit display
    Display.deinit()
    # release media buffer


def disp_drv_flush_cb(disp_drv, area, color):
    global disp_img1, disp_img2

    if disp_drv.flush_is_last() == True:
        if disp_img1.virtaddr() == uctypes.addressof(color.__dereference__()):
            Display.show_image(disp_img1)
            print(f"disp disp_img1 {disp_img1}")
        else:
            Display.show_image(disp_img2)
            print(f"disp disp_img2 {disp_img2}")
        time.sleep(0.01)

    disp_drv.flush_ready()

class touch_screen():
    def __init__(self):
        self.state = lv.INDEV_STATE.RELEASED

        self.indev_drv = lv.indev_create()
        self.indev_drv.set_type(lv.INDEV_TYPE.POINTER)
        self.indev_drv.set_read_cb(self.callback)
        self.touch = TOUCH(0)

    def callback(self, driver, data):
        x, y, state = 0, 0, lv.INDEV_STATE.RELEASED
        tp = self.touch.read(1)
        if len(tp):
            x, y, event = tp[0].x, tp[0].y, tp[0].event
            if event == 2 or event == 3:
                state = lv.INDEV_STATE.PRESSED
        data.point = lv.point_t({'x': x, 'y': y})
        data.state = state

def lvgl_init():
    global disp_img1, disp_img2

    lv.init()
    lv.freetype_init(1, 0, 65535)
    disp_drv = lv.disp_create(DISPLAY_WIDTH, DISPLAY_HEIGHT)
    disp_drv.set_flush_cb(disp_drv_flush_cb)
    disp_img1 = image.Image(DISPLAY_WIDTH, DISPLAY_HEIGHT, image.BGRA8888)
    disp_img2 = image.Image(DISPLAY_WIDTH, DISPLAY_HEIGHT, image.BGRA8888)
    disp_drv.set_draw_buffers(disp_img1.bytearray(), disp_img2.bytearray(), disp_img1.size(), lv.DISP_RENDER_MODE.DIRECT)
    tp = touch_screen()

def lvgl_deinit():
    global disp_img1, disp_img2

    lv.freetype_uninit()
    lv.deinit()
    del disp_img1
    del disp_img2

def btn_clicked_event(event):
    btn = lv.btn.__cast__(event.get_target())
    label = lv.label.__cast__(btn.get_user_data())
    if "on" == label.get_text():
        label.set_text("off")
    else:
        label.set_text("on")

def user_gui_init():
    res_path = "/sdcard/examples/15-LVGL/data/"

    chinese_font = lv.freetype_font_create("/sdcard/res/font/SourceHanSansSC-Normal-Min.ttf", 20, 0)
    if not chinese_font:
        raise Exception("Failed to load fonts")

    ltr_label = lv.label(lv.scr_act())
    ltr_label.set_text("In modern terminology, a microcontroller is similar to a system on a chip (SoC).")
    ltr_label.set_style_text_font(chinese_font,0)
    ltr_label.set_width(400)
    ltr_label.align(lv.ALIGN.TOP_MID, 0, 0)

    cz_label = lv.label(lv.scr_act())
    cz_label.set_style_text_font(chinese_font, 0)
    cz_label.set_text("嵌入式系统（Embedded System），\n是一种嵌入机械或电气系统内部、具有专一功能和实时计算性能的计算机系统。")
    cz_label.set_width(400)
    cz_label.align(lv.ALIGN.BOTTOM_MID, 0, 0)

    anim_imgs = [None]*4
    with open(res_path + 'img/animimg001.png','rb') as f:
        anim001_data = f.read()

    anim_imgs[0] = lv.img_dsc_t({
    'data_size': len(anim001_data),
    'data': anim001_data
    })
    anim_imgs[-1] = anim_imgs[0]

    with open(res_path + 'img/animimg002.png','rb') as f:
        anim002_data = f.read()

    anim_imgs[1] = lv.img_dsc_t({
    'data_size': len(anim002_data),
    'data': anim002_data
    })

    with open(res_path + 'img/animimg003.png','rb') as f:
        anim003_data = f.read()

    anim_imgs[2] = lv.img_dsc_t({
    'data_size': len(anim003_data),
    'data': anim003_data
    })

    animimg0 = lv.animimg(lv.scr_act())
    animimg0.center()
    animimg0.set_src(anim_imgs, 4)
    animimg0.set_duration(2000)
    animimg0.set_repeat_count(lv.ANIM_REPEAT_INFINITE)
    animimg0.start()

    btn = lv.btn(lv.scr_act())
    btn.align(lv.ALIGN.CENTER, 0, lv.pct(25))
    label = lv.label(btn)
    label.set_text('on')
    btn.set_user_data(label)
    btn.add_event(btn_clicked_event, lv.EVENT.CLICKED, None)

def main():
    os.exitpoint(os.EXITPOINT_ENABLE)
    try:
        display_init()
        lvgl_init()
        user_gui_init()
        while True:
            time.sleep_ms(lv.task_handler())
    except BaseException as e:
        import sys
        sys.print_exception(e)
    lvgl_deinit()
    display_deinit()
    gc.collect()

if __name__ == "__main__":
    main()
