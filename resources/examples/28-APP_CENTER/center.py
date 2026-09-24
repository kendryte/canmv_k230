# center.py - Home screen with icon grid, button-based page switching

import lvgl as lv
import config
import lvgl_utils as gui
import i18n

SHORT_MAP = {
    "face": "FD",  "yolo": "YO",  "hand_det": "HD",
    "face_reg": "FR", "face_rec": "FI", "person": "PD",
    "tracker": "NT", "self_learn": "SL",
    "sys_info": "SI",
    "wifi": "WF",
    "pose": "PE",  "body_seg": "BS", "face_mesh": "FM",
    "landmark":"FL","seg": "YS",  "obb": "OB",
    "face_pose":"FP",
    "face_parse":"FC",
    "falldown":  "FT",
    "hand_kp":   "HK",
    "licence":   "LP",
    "licence_pose": "YP",
    "ocr":       "OC",
    "liveness":  "LV",
    "kws":       "KW",
    "eye_gaze":  "EG",
    "tts":       "TS",
    "dyn_gest":  "DG",
    "cv_edge":   "CE",
    "cv_lines":  "CL",
    "cv_circles":"CC",
    "cv_rects":  "CR",
    "omv_edge":  "OE",
    "omv_lines": "OL",
    "omv_circles":"MC",
    "omv_rects": "MR",
}

# Dedicated face registration/recognition artwork.  The home screen still
# falls back to SHORT_MAP if an image is unavailable.
ICON_FILE_MAP = {
    "face_reg": "face_reg.png",
    "face_rec": "face_rec.png",
    "person": "person.png",
}

class HomeScreen:
    def __init__(self):
        self.layout = config.ui_layout
        if self.layout is None:
            raise RuntimeError("UI layout is not initialized")
        self._page = 0
        self.wifi_label = None
        self._title_label = None
        self._language_label = None
        self._description_dialog = None
        self._touch_point = lv.point_t()
        self._touch_origin = None
        self._touch_moved = False
        self._touch_consumed = False
        self._items = []
        for _, items in config.HOME_SECTIONS:
            self._items.extend(items)
        self._per_page = self.layout.rows * self.layout.cols
        self._pages = max(1, (len(self._items) + self._per_page - 1) //
                          self._per_page)

        self.screen = lv.obj()
        self.screen.set_size(self.layout.width, self.layout.height)
        self.screen.set_style_bg_color(gui.lv_color(config.THEME_BG), lv.PART.MAIN)
        self.screen.set_style_bg_opa(255, lv.PART.MAIN)
        self.screen.set_style_border_width(0, lv.PART.MAIN)
        self.screen.set_style_radius(0, lv.PART.MAIN)
        self.screen.set_style_pad_all(0, lv.PART.MAIN)
        self.screen.clear_flag(lv.obj.FLAG.SCROLLABLE)

        self._build_status_bar()
        self._card_area = lv.obj(self.screen)
        self._card_area.set_size(self.layout.width, self.layout.card_area_h)
        self._card_area.set_pos(0, self.layout.card_area_y)
        self._card_area.set_style_bg_opa(0, lv.PART.MAIN)
        self._card_area.set_style_border_width(0, lv.PART.MAIN)
        self._card_area.set_style_radius(0, lv.PART.MAIN)
        self._card_area.set_style_pad_all(0, lv.PART.MAIN)
        self._card_area.clear_flag(lv.obj.FLAG.SCROLLABLE)
        self._card_area.add_flag(lv.obj.FLAG.PRESS_LOCK)

        self._prev_btn = None
        self._next_btn = None
        self._dots = []
        self._page_label = None
        if self._pages > 1:
            self._build_nav()
        self._enable_swipe()
        self._show_page(0)
        lv.scr_load(self.screen)

    def _enable_swipe(self):
        # Track the whole contact, including pauses and movement back to origin.
        self._card_area.add_event(self._touch_pressed, lv.EVENT.PRESSED, None)
        self._card_area.add_event(self._touch_update, lv.EVENT.PRESSING, None)
        self._card_area.add_event(self._touch_released, lv.EVENT.RELEASED, None)
        self._card_area.add_event(self._touch_lost, lv.EVENT.PRESS_LOST, None)

    def _touch_pressed(self, event):
        indev = lv.indev_get_act()
        self._touch_origin = None
        self._touch_moved = False
        self._touch_consumed = False
        if indev is not None:
            indev.get_point(self._touch_point)
            self._touch_origin = (self._touch_point.x, self._touch_point.y)

    def _touch_update(self, event=None):
        indev = lv.indev_get_act()
        if self._touch_origin is None or indev is None:
            return 0, 0
        indev.get_point(self._touch_point)
        dx = self._touch_point.x - self._touch_origin[0]
        dy = self._touch_point.y - self._touch_origin[1]
        if max(abs(dx), abs(dy)) > self.layout.tap_max_move:
            self._touch_moved = True
        return dx, dy

    def _touch_lost(self, event):
        self._touch_consumed = True
        self._touch_origin = None

    def _touch_released(self, event):
        dx, dy = self._touch_update()
        if self._touch_consumed or self._description_dialog is not None:
            return
        if (self._touch_moved and abs(dx) >= self.layout.swipe_min_dx and
                abs(dx) > abs(dy) * 2):
            # Consume before replacing cards; release may be followed by CLICKED.
            self._touch_consumed = True
            if dx < 0:
                self._page_next()
            else:
                self._page_prev()

    def reload(self):
        lv.scr_load(self.screen)

    def _build_status_bar(self):
        bar = lv.obj(self.screen)
        bar.set_size(self.layout.status_w, self.layout.status_h)
        bar.set_pos(self.layout.status_x, self.layout.status_y)
        bar.set_style_bg_color(gui.lv_color(config.THEME_BG), lv.PART.MAIN)
        bar.set_style_bg_opa(255, lv.PART.MAIN)
        bar.set_style_border_width(0, lv.PART.MAIN)
        bar.set_style_radius(0, lv.PART.MAIN)
        bar.set_style_pad_all(0, lv.PART.MAIN)
        bar.clear_flag(lv.obj.FLAG.SCROLLABLE)

        f = gui.font_cn if gui.font_cn else gui.font_en
        self._title_label = gui.make_label(
            bar, i18n.text("app_center"), config.THEME_TEXT, f)
        title_w = max(40, self.layout.status_w -
                      self.layout.clamp_px(230, 150, 340))
        self._title_label.set_width(title_w)
        try:
            self._title_label.set_long_mode(lv.label.LONG.DOT)
            self._title_label.set_style_text_align(lv.TEXT_ALIGN.CENTER,
                                                   lv.PART.MAIN)
        except Exception:
            pass
        self._title_label.align(lv.ALIGN.CENTER, 0, 0)

        lang_w = self.layout.clamp_px(70, 54, 108)
        lang_h = self.layout.clamp_px(30, 24, 44)
        lang_btn = lv.btn(bar)
        lang_btn.set_size(lang_w, lang_h)
        lang_btn.align(lv.ALIGN.LEFT_MID,
                       self.layout.clamp_px(12, 6, 22), 0)
        lang_btn.set_style_bg_color(gui.lv_color(config.THEME_ACCENT),
                                    lv.PART.MAIN)
        lang_btn.set_style_bg_opa(42, lv.PART.MAIN)
        lang_btn.set_style_border_color(gui.lv_color(config.THEME_ACCENT),
                                        lv.PART.MAIN)
        lang_btn.set_style_border_width(1, lv.PART.MAIN)
        lang_btn.set_style_radius(lang_h // 2, lv.PART.MAIN)
        lang_btn.set_style_shadow_width(0, lv.PART.MAIN)
        self._language_label = gui.make_label(
            lang_btn, i18n.text("switch_language"),
            config.THEME_ACCENT, f)
        self._language_label.align(lv.ALIGN.CENTER, 0, 0)
        lang_btn.add_event(self._toggle_language, lv.EVENT.CLICKED, None)

        self.wifi_label = lv.label(bar)
        self.wifi_label.set_text(lv.SYMBOL.WIFI)
        self.wifi_label.set_style_text_color(
            gui.lv_color(config.THEME_GREEN), lv.PART.MAIN)
        self.wifi_label.align(
            lv.ALIGN.RIGHT_MID, -self.layout.clamp_px(18, 10, 34), 0)
        self.set_wifi_connected(config.wifi_connected)

    def _toggle_language(self, event):
        i18n.toggle()
        self._title_label.set_text(i18n.text("app_center"))
        self._language_label.set_text(i18n.text("switch_language"))
        # Rebuild only the visible page. No application is running here, and
        # language lookup never enters an application's frame loop.
        self._show_page(self._page)

    def set_wifi_connected(self, connected):
        if self.wifi_label is None:
            return
        try:
            if connected:
                self.wifi_label.clear_flag(lv.obj.FLAG.HIDDEN)
            else:
                self.wifi_label.add_flag(lv.obj.FLAG.HIDDEN)
        except Exception:
            self.wifi_label.set_text(lv.SYMBOL.WIFI if connected else "")

    def _make_nav_btn(self, x, y, symbol, cb):
        btn = lv.btn(self.screen)
        btn.set_size(self.layout.nav_btn_w, self.layout.nav_btn_h)
        btn.set_pos(x, y)
        btn.set_style_bg_color(gui.lv_color(0xFFFFFF), lv.PART.MAIN)
        btn.set_style_bg_opa(25, lv.PART.MAIN)
        btn.set_style_border_width(0, lv.PART.MAIN)
        btn.set_style_radius(self.layout.nav_radius, lv.PART.MAIN)
        btn.set_style_shadow_width(0, lv.PART.MAIN)
        lbl = lv.label(btn)
        lbl.set_text(symbol)
        lbl.set_style_text_color(gui.lv_color(config.THEME_TEXT), lv.PART.MAIN)
        lbl.align(lv.ALIGN.CENTER, 0, 0)
        btn.add_event(lambda e: cb(), lv.EVENT.CLICKED, None)
        return btn

    def _build_nav(self):
        self._prev_btn = self._make_nav_btn(self.layout.prev_btn_x,
                                            self.layout.nav_btn_y,
                                            lv.SYMBOL.LEFT, self._page_prev)
        self._next_btn = self._make_nav_btn(self.layout.next_btn_x,
                                            self.layout.nav_btn_y,
                                            lv.SYMBOL.RIGHT, self._page_next)

        if self._pages > 9:
            self._page_label = gui.make_label(
                self.screen, "", config.THEME_SUBTEXT, gui.font_cn or gui.font_en)
            self._page_label.set_size(100, self.layout.line_h)
            self._page_label.set_style_text_align(lv.TEXT_ALIGN.CENTER, lv.PART.MAIN)
            self._page_label.align(lv.ALIGN.BOTTOM_MID, 0, -4)
            self._update_dots()
            return
        dot_s = self.layout.dot_size
        gap = self.layout.dot_gap
        area_w = self._pages * dot_s + (self._pages - 1) * gap
        start_x = (self.layout.width - area_w) // 2
        for i in range(self._pages):
            dot = lv.obj(self.screen)
            dot.set_size(dot_s, dot_s)
            dot.set_pos(start_x + i * (dot_s + gap), self.layout.dot_y)
            dot.set_style_radius(dot_s // 2, lv.PART.MAIN)
            dot.set_style_border_width(0, lv.PART.MAIN)
            dot.set_style_bg_opa(255, lv.PART.MAIN)
            self._dots.append(dot)
        self._update_dots()

    def _update_dots(self):
        if self._page_label is not None:
            self._page_label.set_text('%d / %d' % (self._page + 1, self._pages))
        if not self._dots:
            return
        for i, dot in enumerate(self._dots):
            if i == self._page:
                dot.set_style_bg_color(gui.lv_color(config.THEME_ACCENT), lv.PART.MAIN)
                dot.set_style_bg_opa(255, lv.PART.MAIN)
            else:
                dot.set_style_bg_color(gui.lv_color(config.THEME_SUBTEXT), lv.PART.MAIN)
                dot.set_style_bg_opa(80, lv.PART.MAIN)

    def _page_prev(self):
        if self._page > 0:
            self._show_page(self._page - 1)

    def _page_next(self):
        if self._page < self._pages - 1:
            self._show_page(self._page + 1)

    def _show_page(self, p):
        self._page = p
        self._card_area.clean()
        self._card_area.invalidate()
        start = p * self._per_page
        end = min(start + self._per_page, len(self._items))
        page_items = self._items[start:end]

        for idx, (code, unused_title, color_idx) in enumerate(page_items):
            col = idx % self.layout.cols
            row = idx // self.layout.cols
            x = self.layout.grid_x + \
                col * (self.layout.card_w + self.layout.gap_x)
            y = self.layout.grid_y + \
                row * (self.layout.card_h + self.layout.gap_y)
            color = config.ICON_COLORS[color_idx % len(config.ICON_COLORS)]
            self._make_card(x, y, code, i18n.app_title(code), color)
        self._update_dots()

    def _make_app_icon(self, card, code, color):
        """Create an app image, falling back to the old abbreviation icon.

        LVGL's stdio file-system driver uses the ``A:`` prefix.  Check the
        normal MicroPython path first so a missing optional asset cannot leave
        an empty card or prevent the home screen from loading.
        """
        filename = ICON_FILE_MAP.get(code, code + ".png")
        file_path = config.ICON_PATH + filename
        icon_img = None
        if config.file_exists(file_path):
            try:
                icon_img = lv.img(card)
                icon_img.set_src(config.ICON_LV_PATH + filename)
                try:
                    icon_img.set_zoom(self.layout.icon_zoom())
                except Exception:
                    pass
                # Image transforms use the original 48x48 object box and a
                # center pivot.  Offset that box so the visible scaled image
                # keeps the same top edge as the fallback vector icon.
                icon_box_y = self.layout.icon_y + \
                             (self.layout.icon_size - 48) // 2
                icon_img.align(lv.ALIGN.TOP_MID, 0, icon_box_y)
                # The image is decorative; the card owns all click/swipe input.
                try:
                    icon_img.clear_flag(lv.obj.FLAG.CLICKABLE)
                    icon_img.clear_flag(lv.obj.FLAG.SCROLLABLE)
                except Exception:
                    pass
                return
            except Exception as e:
                print("HomeScreen: icon load failed (%s): %s" % (code, e))
                if icon_img is not None:
                    try:
                        icon_img.delete()
                    except Exception:
                        pass

        icon_ct = gui.make_icon(card, self.layout.icon_size, color)
        icon_ct.align(lv.ALIGN.TOP_MID, 0, self.layout.icon_y)

        short = SHORT_MAP.get(code, code[:2].upper())
        ef = gui.font_cn if gui.font_cn else gui.font_en
        icon_lbl = lv.label(card)
        if ef:
            icon_lbl.set_style_text_font(ef, 0)
        icon_lbl.set_style_text_color(gui.lv_color(0xFFFFFF), lv.PART.MAIN)
        icon_lbl.set_text(short)
        try:
            icon_lbl.align_to(icon_ct, lv.ALIGN.CENTER, 0, 0)
        except Exception:
            icon_lbl.align(lv.ALIGN.TOP_MID, 0,
                           self.layout.icon_y +
                           (self.layout.icon_size - self.layout.font_size) // 2)

    def _make_card(self, x, y, code, title, color):
        card = lv.obj(self._card_area)
        card.set_size(self.layout.card_w, self.layout.card_h)
        card.set_pos(x, y)
        card.set_style_bg_color(gui.lv_color(config.THEME_CARD), lv.PART.MAIN)
        card.set_style_bg_opa(255, lv.PART.MAIN)
        card.set_style_radius(self.layout.card_radius, lv.PART.MAIN)
        card.set_style_border_width(0, lv.PART.MAIN)
        card.set_style_shadow_width(0, lv.PART.MAIN)
        card.set_style_pad_all(0, lv.PART.MAIN)
        try:
            card.set_scroll_dir(lv.DIR.NONE)
        except Exception:
            pass

        card.add_event(lambda e, c=code: self._card_clicked(c),
                       lv.EVENT.CLICKED, None)
        card.add_event(lambda e, c=code: self._card_long_pressed(c),
                       lv.EVENT.LONG_PRESSED, None)
        card.add_flag(lv.obj.FLAG.CLICKABLE)
        try:
            card.add_flag(lv.obj.FLAG.PRESS_LOCK)
            card.clear_flag(lv.obj.FLAG.SCROLLABLE)
        except Exception:
            pass
        try:
            # let presses bubble to the screen so swipe works over cards
            card.add_flag(lv.obj.FLAG.EVENT_BUBBLE)
        except Exception:
            pass

        self._make_app_icon(card, code, color)

        cf = gui.font_cn if gui.font_cn else gui.font_en
        name = gui.make_label(card, title, config.THEME_TEXT, cf)
        name.set_width(max(24, self.layout.card_w -
                           self.layout.clamp_px(12, 8, 20)))
        try:
            name.set_long_mode(lv.label.LONG.WRAP)
            name.set_style_text_align(lv.TEXT_ALIGN.CENTER, lv.PART.MAIN)
        except Exception:
            pass
        # Content height avoids an empty second line below short titles.
        name.set_style_text_line_space(0, lv.PART.MAIN)
        name.set_height(lv.SIZE_CONTENT)
        name.set_style_max_height(self.layout.text_h, lv.PART.MAIN)
        name.align(lv.ALIGN.BOTTOM_MID, 0, self.layout.text_y)

    def _card_clicked(self, code):
        self._touch_update()
        if (self._description_dialog is not None or self._touch_origin is None or
                self._touch_moved or self._touch_consumed):
            return
        self._touch_consumed = True
        _launch(code)

    def _card_long_pressed(self, code):
        self._touch_update()
        if (self._description_dialog is not None or self._touch_origin is None or
                self._touch_moved or self._touch_consumed):
            return
        self._touch_consumed = True
        self._show_app_description(code)

    def _show_app_description(self, code):
        backdrop = lv.obj(self.screen)
        backdrop.set_size(self.layout.width, self.layout.height)
        backdrop.set_pos(0, 0)
        backdrop.set_style_bg_color(gui.lv_color(0x000000), lv.PART.MAIN)
        backdrop.set_style_bg_opa(210, lv.PART.MAIN)
        backdrop.set_style_border_width(0, lv.PART.MAIN)
        backdrop.set_style_radius(0, lv.PART.MAIN)
        backdrop.set_style_pad_all(0, lv.PART.MAIN)
        try:
            backdrop.clear_flag(lv.obj.FLAG.SCROLLABLE)
        except Exception:
            pass
        self._description_dialog = backdrop

        panel_w = min(max(280, self.layout.width - 32),
                      max(1, self.layout.width - 12), 620)
        panel_h = min(max(190, self.layout.height - 80),
                      max(1, self.layout.height - 12), 330)
        panel = lv.obj(backdrop)
        panel.set_size(panel_w, panel_h)
        panel.set_pos((self.layout.width - panel_w) // 2,
                      (self.layout.height - panel_h) // 2)
        panel.set_style_bg_color(gui.lv_color(config.THEME_CARD),
                                 lv.PART.MAIN)
        panel.set_style_bg_opa(255, lv.PART.MAIN)
        panel.set_style_border_color(gui.lv_color(config.THEME_BORDER),
                                     lv.PART.MAIN)
        panel.set_style_border_width(1, lv.PART.MAIN)
        panel.set_style_radius(self.layout.overlay_radius, lv.PART.MAIN)
        panel.set_style_pad_all(0, lv.PART.MAIN)
        try:
            panel.clear_flag(lv.obj.FLAG.SCROLLABLE)
        except Exception:
            pass

        accent_h = self.layout.clamp_px(4, 3, 8)
        accent = lv.obj(panel)
        accent.set_size(panel_w, accent_h)
        accent.set_pos(0, 0)
        accent.set_style_bg_color(gui.lv_color(config.THEME_ACCENT),
                                  lv.PART.MAIN)
        accent.set_style_bg_opa(255, lv.PART.MAIN)
        accent.set_style_border_width(0, lv.PART.MAIN)
        accent.set_style_radius(0, lv.PART.MAIN)
        try:
            accent.clear_flag(lv.obj.FLAG.CLICKABLE)
            accent.clear_flag(lv.obj.FLAG.SCROLLABLE)
        except Exception:
            pass

        font = gui.font_cn if gui.font_cn else gui.font_en
        edge = self.layout.clamp_px(22, 14, 34)
        close_size = self.layout.clamp_px(38, 30, 54)
        heading = gui.make_label(panel, i18n.text("app_description"),
                                 config.THEME_ACCENT, font)
        heading.set_pos(edge, self.layout.clamp_px(18, 12, 28))

        close_button = lv.btn(panel)
        close_button.set_size(close_size, close_size)
        close_button.set_pos(panel_w - close_size - edge // 2,
                             self.layout.clamp_px(10, 7, 16))
        close_button.set_style_bg_color(gui.lv_color(config.THEME_SUBTEXT),
                                        lv.PART.MAIN)
        close_button.set_style_bg_opa(150, lv.PART.MAIN)
        close_button.set_style_border_width(0, lv.PART.MAIN)
        close_button.set_style_shadow_width(0, lv.PART.MAIN)
        close_button.set_style_radius(close_size // 2, lv.PART.MAIN)
        close_label = lv.label(close_button)
        try:
            close_label.set_text(lv.SYMBOL.CLOSE)
        except Exception:
            close_label.set_text("X")
        close_label.set_style_text_color(gui.lv_color(config.THEME_TEXT),
                                         lv.PART.MAIN)
        close_label.align(lv.ALIGN.CENTER, 0, 0)

        title_y = self.layout.clamp_px(58, 44, 78)
        title = gui.make_label(panel, i18n.app_title(code),
                               config.THEME_TEXT, font)
        title.set_width(panel_w - edge * 2)
        title.set_pos(edge, title_y)
        try:
            title.set_long_mode(lv.label.LONG.DOT)
        except Exception:
            pass

        body_y = title_y + self.layout.clamp_px(38, 30, 52)
        body = gui.make_label(panel, i18n.app_description(code),
                              config.THEME_SUBTEXT, font)
        body.set_width(panel_w - edge * 2)
        body.set_pos(edge, body_y)
        try:
            body.set_long_mode(lv.label.LONG.WRAP)
        except Exception:
            pass

        def close_dialog():
            if self._description_dialog is None:
                return
            dialog = self._description_dialog
            self._description_dialog = None
            dialog.delete()

        close_button.add_event(lambda e: close_dialog(),
                               lv.EVENT.CLICKED, None)

    def clean(self):
        if self.screen:
            self.screen.clean()
            self.screen.delete()
            self.screen = None
        self.wifi_label = None
        self._title_label = None
        self._language_label = None
        self._description_dialog = None


def _launch(code):
    import runner
    runner.start_demo(code)
