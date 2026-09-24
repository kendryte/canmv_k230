# lvgl_utils.py - LVGL initialization, flush callback, UI helpers

import lvgl as lv
import uctypes
import image
import config
from media.display import Display

disp_img1  = None
disp_img2  = None
_img1_addr = 0
font_en    = None
font_cn    = None
# Track fonts created via lv.font_load (bitmap .fnt): these need font.free(),
# unlike freetype fonts which are released by lv.freetype_uninit().
_font_en_via_load = False
_font_cn_via_load = False
_lvgl_ready = False

CN_FONT_CANDIDATES = [
    "/sdcard/res/font/SourceHanSansSC-Normal-Min.ttf",
    "/sdcard/res/font/AlibabaPuHuiTi-3-45-Light.ttf",
]


def _disp_flush_cb(disp_drv, area, color):
    buf = color.__dereference__()
    if uctypes.addressof(buf) == _img1_addr:
        Display.show_image(disp_img1, layer=Display.LAYER_OSD3)
    else:
        Display.show_image(disp_img2, layer=Display.LAYER_OSD3)
    disp_drv.flush_ready()


def lvgl_init():
    global disp_img1, disp_img2, _img1_addr, font_en, font_cn, _lvgl_ready
    global _font_en_via_load, _font_cn_via_load
    if _lvgl_ready:
        return
    lv.init()
    try:
        disp_drv = lv.disp_create(config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT)
        disp_drv.set_color_format(lv.COLOR_FORMAT.ARGB8888)
        disp_drv.set_flush_cb(_disp_flush_cb)
        disp_img1 = image.Image(config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT,
                                image.BGRA8888)
        disp_img2 = image.Image(config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT,
                                image.BGRA8888)
        disp_img1.clear()
        disp_img2.clear()
        _img1_addr = disp_img1.virtaddr()
        disp_drv.set_draw_buffers(
            disp_img1.bytearray(), disp_img2.bytearray(),
            disp_img1.size(), lv.DISP_RENDER_MODE.FULL
        )

        font_size = config.ui_layout.font_size if config.ui_layout else 20
        for path in CN_FONT_CANDIDATES:
            if config.file_exists(path):
                try:
                    font_cn = lv.freetype_font_create(path, font_size, 0)
                    if font_cn is not None:
                        break
                except Exception:
                    continue

        if font_cn is None and config.file_exists(config.FONT_PATH + "lv_font_simsun_16_cjk.fnt"):
            font_cn = lv.font_load(config.FONT_CN)
            _font_cn_via_load = font_cn is not None

        if config.file_exists(config.FONT_PATH + "montserrat-16.fnt"):
            font_en = lv.font_load(config.FONT_EN)
            _font_en_via_load = font_en is not None
        _lvgl_ready = True
    except Exception:
        # Make a partial initialization safe to retry or tear down.
        try:
            lv.deinit()
        except Exception:
            pass
        disp_img1 = None
        disp_img2 = None
        font_en = None
        font_cn = None
        _img1_addr = 0
        raise


def lvgl_deinit():
    global disp_img1, disp_img2, _img1_addr, font_en, font_cn, _lvgl_ready
    global _font_en_via_load, _font_cn_via_load
    if not _lvgl_ready:
        return
    # Bitmap fonts loaded with lv.font_load must be freed with font.free()
    # before lv.deinit(); freetype fonts are handled by freetype_uninit().
    if font_en is not None and _font_en_via_load:
        try:
            font_en.free()
        except Exception as e:
            print("font_en free failed:", e)
    if font_cn is not None and _font_cn_via_load:
        try:
            font_cn.free()
        except Exception as e:
            print("font_cn free failed:", e)
    _font_en_via_load = False
    _font_cn_via_load = False
    font_en = None
    font_cn = None
    try:
        lv.freetype_uninit()
    except Exception:
        pass
    try:
        lv.deinit()
    finally:
        # Release draw buffers only after LVGL has stopped referencing them.
        disp_img1 = None
        disp_img2 = None
        _img1_addr = 0
        _lvgl_ready = False
def clear_buffers():
    if disp_img1:
        disp_img1.clear()
    if disp_img2:
        disp_img2.clear()


def lv_color(hex_val):
    return lv.color_hex(hex_val)


def make_icon(parent, size, color):
    circle = lv.obj(parent)
    circle.set_size(size, size)
    circle.set_style_bg_color(lv_color(color), lv.PART.MAIN)
    circle.set_style_bg_opa(255, lv.PART.MAIN)
    circle.set_style_radius(999, lv.PART.MAIN)
    circle.set_style_border_width(0, lv.PART.MAIN)
    # purely decorative: lv.obj is CLICKABLE by default and would swallow
    # presses, making the center of the parent card impossible to click
    try:
        circle.clear_flag(lv.obj.FLAG.CLICKABLE)
        circle.clear_flag(lv.obj.FLAG.SCROLLABLE)
    except Exception:
        pass
    return circle


def make_label(parent, text, color=config.THEME_TEXT, font=None):
    label = lv.label(parent)
    if font:
        label.set_style_text_font(font, 0)
    label.set_style_text_color(lv_color(color), lv.PART.MAIN)
    label.set_text(text)
    return label
