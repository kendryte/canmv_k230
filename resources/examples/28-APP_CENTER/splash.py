# splash.py - One-shot, lightweight K230 brand splash animation

import time
import lvgl as lv
import config
import lvgl_utils as gui


SPLASH_MS = 2200
FRAME_MS = 40
IMAGE_WIDTH = 800
IMAGE_HEIGHT = 480


class SplashScreen:
    """Animate LVGL objects over one static PNG, then release everything.

    This deliberately avoids GIF/video decoding.  The only recurring work is
    moving two labels and resizing a small progress bar for about two seconds.
    """

    def __init__(self):
        self.layout = config.ui_layout
        self.done = False
        self._start = time.ticks_ms()
        self._last_frame = time.ticks_add(self._start, -FRAME_MS)
        self._large_font = None
        self._brand_font = None
        self.screen = lv.obj()
        self.screen.set_size(self.layout.width, self.layout.height)
        self.screen.set_style_bg_color(gui.lv_color(0x020711), lv.PART.MAIN)
        self.screen.set_style_bg_opa(255, lv.PART.MAIN)
        self.screen.set_style_border_width(0, lv.PART.MAIN)
        self.screen.set_style_radius(0, lv.PART.MAIN)
        self.screen.set_style_pad_all(0, lv.PART.MAIN)
        try:
            self.screen.clear_flag(lv.obj.FLAG.SCROLLABLE)
            self.screen.add_flag(lv.obj.FLAG.CLICKABLE)
            self.screen.add_event(self._skip, lv.EVENT.CLICKED, None)
        except Exception:
            pass

        self._build_background()
        self._build_brand()
        lv.scr_load(self.screen)

    def _create_font(self, size):
        for path in gui.CN_FONT_CANDIDATES:
            if config.file_exists(path):
                try:
                    font = lv.freetype_font_create(path, size, 0)
                    if font is not None:
                        return font
                except Exception:
                    pass
        return gui.font_cn if gui.font_cn else gui.font_en

    def _build_background(self):
        path = config.ICON_PATH + "app_center_splash.png"
        if not config.file_exists(path):
            return
        try:
            image = lv.img(self.screen)
            image.set_src(config.ICON_LV_PATH + "app_center_splash.png")
            zoom = max(self.layout.width * 256 // IMAGE_WIDTH,
                       self.layout.height * 256 // IMAGE_HEIGHT)
            image.set_zoom(max(64, min(768, zoom)))
            try:
                image.set_pivot(IMAGE_WIDTH // 2, IMAGE_HEIGHT // 2)
            except Exception:
                pass
            image.align(lv.ALIGN.CENTER, 0, 0)
            try:
                image.clear_flag(lv.obj.FLAG.CLICKABLE)
                image.clear_flag(lv.obj.FLAG.SCROLLABLE)
            except Exception:
                pass
            self._image = image
        except Exception as e:
            self._image = None
            print("APP Center splash image unavailable:", e)

    def _build_brand(self):
        DW = self.layout.width
        DH = self.layout.height
        left = max(12, DW * 7 // 100)
        base_y = max(12, (DH - 210) // 2)
        self._brand_base_y = base_y
        self._large_font = self._create_font(
            self.layout.clamp_px(58, 38, 76))
        self._brand_font = self._create_font(
            self.layout.clamp_px(22, 16, 30))

        self.k230 = gui.make_label(self.screen, "K230", 0xFFFFFF,
                                   self._large_font)
        self.k230.set_pos(left, base_y + 16)
        try:
            self.k230.set_style_text_letter_space(
                0, lv.PART.MAIN)
        except Exception:
            pass

        self.brand = gui.make_label(self.screen, "CANAAN  |  勘智Kendryte",
                                    0x76C7FF, self._brand_font)
        self.brand.set_pos(left + 2,
                           base_y + self.layout.clamp_px(72, 52, 92) + 16)

        self.tagline = gui.make_label(
            self.screen, "EDGE AI APPLICATION PLATFORM",
            config.THEME_SUBTEXT, gui.font_en if gui.font_en else gui.font_cn)
        self.tagline.set_pos(left + 3,
                             base_y + self.layout.clamp_px(108, 84, 132) + 16)

        track_w = min(self.layout.clamp_px(250, 180, 360), DW - left * 2)
        track_h = self.layout.clamp_px(3, 2, 5)
        track_y = min(DH - self.layout.clamp_px(54, 34, 72),
                      base_y + self.layout.clamp_px(154, 124, 188))
        for label in (self.brand, self.tagline):
            label.set_width(DW - left * 2 - 6)
            label.set_long_mode(lv.label.LONG.DOT)
        self._track_w = track_w
        track = lv.obj(self.screen)
        track.set_size(track_w, track_h)
        track.set_pos(left + 3, track_y)
        track.set_style_bg_color(gui.lv_color(0x244563), lv.PART.MAIN)
        track.set_style_bg_opa(180, lv.PART.MAIN)
        track.set_style_border_width(0, lv.PART.MAIN)
        track.set_style_radius(track_h, lv.PART.MAIN)
        track.set_style_pad_all(0, lv.PART.MAIN)

        progress = lv.obj(self.screen)
        progress.set_size(1, track_h)
        progress.set_pos(left + 3, track_y)
        progress.set_style_bg_color(gui.lv_color(config.THEME_ACCENT),
                                    lv.PART.MAIN)
        progress.set_style_bg_opa(255, lv.PART.MAIN)
        progress.set_style_border_width(0, lv.PART.MAIN)
        progress.set_style_radius(track_h, lv.PART.MAIN)
        progress.set_style_pad_all(0, lv.PART.MAIN)
        self.progress = progress

    def _skip(self, event):
        # Ignore accidental power-on touches during the first half second.
        if time.ticks_diff(time.ticks_ms(), self._start) > 500:
            self.done = True

    def update(self, now=None):
        if self.done or self.screen is None:
            return
        if now is None:
            now = time.ticks_ms()
        if time.ticks_diff(now, self._last_frame) < FRAME_MS:
            return
        self._last_frame = now
        elapsed = max(0, time.ticks_diff(now, self._start))
        if elapsed >= SPLASH_MS:
            self.progress.set_width(self._track_w)
            self.done = True
            return

        # Ease out from a short 16 px slide.  Integer arithmetic keeps the
        # animation deterministic and inexpensive on MicroPython.
        intro = min(600, elapsed)
        offset = 16 * (600 - intro) * (600 - intro) // (600 * 600)
        self.k230.set_y(self._brand_base_y + offset)
        brand_y = self._brand_base_y + \
            self.layout.clamp_px(72, 52, 92) + offset
        self.brand.set_y(brand_y)
        self.tagline.set_y(self._brand_base_y +
                           self.layout.clamp_px(108, 84, 132) + offset)
        self.progress.set_width(max(1, self._track_w * elapsed // SPLASH_MS))

    def clean(self):
        if self.screen is not None:
            self.screen.clean()
            self.screen.delete()
            self.screen = None
        try:
            # Release the decoded 800x480 splash before any model is loaded.
            lv.img.cache_invalidate_src(
                config.ICON_LV_PATH + "app_center_splash.png")
        except Exception:
            pass
        for font in (self._large_font, self._brand_font):
            if font is None or font is gui.font_cn or font is gui.font_en:
                continue
            try:
                font.freetype_font_del()
            except Exception:
                pass
        self._image = None
        self.k230 = None
        self.brand = None
        self.tagline = None
        self.progress = None
        self._large_font = None
        self._brand_font = None
