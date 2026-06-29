from media.display import *
from media.media import *
import time, os, sys, gc
import lvgl as lv
from machine import TOUCH
import uctypes

# Configuration
DISPLAY_TYPE = Display.ST7701 
DISPLAY_WIDTH = ALIGN_UP(800, 16)
DISPLAY_HEIGHT = 480
RES_PATH = "/sdcard/examples/15-LVGL/data/"

class TouchScreen():
    def __init__(self):
        try:
            # 1. Keep a reference to the touch hardware
            self.touch = TOUCH(0)
            print("Touch hardware initialized.")
        except Exception as e:
            print(f"Touch init failed: {e}")
            self.touch = None
            return

        # 2. Create the input device
        self.indev = lv.indev_create()
        self.indev.set_type(lv.INDEV_TYPE.POINTER)

        # 3. Set the callback (matching the demo style)
        self.indev.set_read_cb(self.callback)

    def callback(self, driver, data):
        if self.touch is None:
            data.state = lv.INDEV_STATE.RELEASED
            return

        try:
            # Read 1 point from hardware
            tp = self.touch.read(1)

            if tp and len(tp) > 0:
                # 4. Update existing members directly
                data.point.x = tp[0].x
                data.point.y = tp[0].y

                # Event 2 = Down, 3 = Move
                if tp[0].event in [2, 3]:
                    data.state = lv.INDEV_STATE.PRESSED
                else:
                    data.state = lv.INDEV_STATE.RELEASED
            else:
                data.state = lv.INDEV_STATE.RELEASED
        except Exception as e:
            # Prevent callback crashes from killing the thread
            data.state = lv.INDEV_STATE.RELEASED

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

    # image size should match DISPLAY_WIDTH * DISPLAY_HEIGHT * LV_COLOR_DEPTH / 8
    # current LV_COLOR_DEPTH is 32.
    disp_imgs = [image.Image(DISPLAY_WIDTH, DISPLAY_HEIGHT, image.BGRA8888) for _ in range(2)]

    disp_drv = lv.disp_create(DISPLAY_WIDTH, DISPLAY_HEIGHT)

    # when differ with LV_COLOR_DEPTH, the Display.show_image should set the argument
    # Display.show_image(....., pixel_format = image.xxxx)
    # lv.COLOR_FORMAT.RGB565 -> image.RGB565
    # lv.COLOR_FORMAT.RGB888 -> image.BGR888
    # lv.COLOR_FORMAT.ARGB8888 -> image.BGRA8888
    disp_drv.set_color_format(lv.COLOR_FORMAT.ARGB8888)
    disp_drv.set_draw_buffers(disp_imgs[0].bytearray(), disp_imgs[1].bytearray(), 
                              disp_imgs[0].size(), lv.DISP_RENDER_MODE.FULL)
    disp_drv.set_flush_cb(lvgl_flush_cb)

def btn_clicked_event(event):
    btn = lv.btn.__cast__(event.get_target())
    label = lv.label.__cast__(btn.get_user_data())
    label.set_text("off" if label.get_text() == "on" else "on")

def user_gui_init():
    scr = lv.scr_act()

    # 1. Standard Fonts & Labels
    font_montserrat_16 = lv.font_load("A:" + RES_PATH + "font/montserrat-16.fnt")
    if not font_montserrat_16:
        raise RuntimeError("Font load failed")
    ltr_label = lv.label(scr)
    ltr_label.set_text("In modern terminology, a microcontroller is similar to a system on a chip (SoC).")
    ltr_label.set_style_text_font(font_montserrat_16, 0)
    ltr_label.set_width(DISPLAY_WIDTH//2 - 10)
    ltr_label.align(lv.ALIGN.TOP_MID, 0, 10)

    font_simsun_16_cjk = lv.font_load("A:" + RES_PATH + "font/lv_font_simsun_16_cjk.fnt")
    if not font_simsun_16_cjk:
        raise RuntimeError("Font load failed")
    cz_label = lv.label(scr)
    cz_label.set_style_text_font(font_simsun_16_cjk, 0)
    cz_label.set_text("嵌入式系统（Embedded System），\n是一种嵌入机械或电气系统内部、具有专一功能和实时计算性能的计算机系统。")
    cz_label.set_width(DISPLAY_WIDTH//2 - 10)
    cz_label.align(lv.ALIGN.BOTTOM_LEFT, 0, -10)

    # 2. FreeType Font Test
    try:
        ft_font = lv.freetype_font_create("/sdcard/res/font/SourceHanSansSC-Normal-Min.ttf", 18, 0)
        if ft_font:
            ft_label = lv.label(scr)
            ft_label.set_style_text_font(ft_font, 0)
            ft_label.set_text("FreeType Test: \n嵌入式系统（Embedded System），\n是一种嵌入机械或电气系统内部、具有专一功能和实时计算性能的计算机系统。")
            ft_label.align(lv.ALIGN.BOTTOM_RIGHT, 0, -10)
            ft_label.set_width(DISPLAY_WIDTH//2 - 10)
    except:
        print("FreeType font skip/fail")

    # 3. Animation
    anim_imgs = [None]*4
    for i in range(3):
        with open(f'{RES_PATH}img/animimg00{i+1}.png', 'rb') as f:
            data = f.read()
            anim_imgs[i] = lv.img_dsc_t({'data_size': len(data), 'data': data})
    anim_imgs[3] = anim_imgs[0]

    animimg0 = lv.animimg(scr)
    animimg0.center()
    animimg0.set_src(anim_imgs, 4)
    animimg0.set_duration(2000)
    animimg0.set_repeat_count(lv.ANIM_REPEAT_INFINITE)
    animimg0.start()

    # 4. Interactive Button
    btn = lv.btn(scr)
    btn.align(lv.ALIGN.CENTER, 0, lv.pct(25))
    label = lv.label(btn)
    label.set_text('on')
    btn.set_user_data(label)
    btn.add_event(btn_clicked_event, lv.EVENT.CLICKED, None)

def main():
    Display.init(DISPLAY_TYPE, width=DISPLAY_WIDTH, height=DISPLAY_HEIGHT, to_ide=True)
    try:
        lvgl_setup()
        tp = TouchScreen()
        user_gui_init()
        while True:
            time.sleep_ms(max(lv.task_handler(), 10))
    except BaseException as e:
        import sys
        sys.print_exception(e)
    finally:
        lv.freetype_uninit()
        lv.deinit()
        Display.deinit()
        gc.collect()

if __name__ == "__main__":
    main()
