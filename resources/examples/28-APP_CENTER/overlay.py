# overlay.py - Full-screen application overlay with fixed LVGL bars and controls

import lvgl as lv
import config
import lvgl_utils as gui
import i18n


class DemoOverlay:
    def __init__(self, demo_name, on_stop, on_back, is_audio_only=False,
                 phrases=None, on_phrase=None, action_label=None,
                 on_action=None, on_name_submit=None,
                 name_title=None, name_placeholder=None,
                 roi_select=False, on_roi=None,
                 database=False, database_title=None,
                 on_database_query=None, on_database_clear=None,
                 app_ui_factory=None, show_stats=True):
        self.layout = config.ui_layout
        if self.layout is None:
            raise RuntimeError("UI layout is not initialized")
        self._on_name_submit = on_name_submit
        self._name_title = name_title or i18n.text("name_title")
        self._name_placeholder = name_placeholder or \
            i18n.text("name_placeholder")
        self._name_dialog = None
        self._database_title = database_title or i18n.text("database")
        self._on_database_query = on_database_query
        self._on_database_clear = on_database_clear
        self._app_ui = None
        # freetype font created for the phrase menu when the shared CJK font is
        # unavailable; owned here so clean() can release it (font_cn is not).
        self._phrase_font = None
        self._database_dialog = None
        self._database_rows = []
        self._database_widgets = None
        self._confirm_dialog = None
        self.action_button = None
        self._action_label = None
        self._roi_area = None
        self._roi_box = None
        self._roi_enabled = False
        self._roi_start = None
        self._on_roi = on_roi
        self.wifi_label = None
        DW = self.layout.width
        DH = self.layout.height

        # Application VIDEO/OSD planes cover the physical display below OSD3.
        # Only reserve safe geometry for interactive LVGL controls; do not mask
        # or crop the application image to a UI-owned camera viewport.
        cx = 0
        cy = self.layout.header_h
        cw = DW
        ch = max(1, DH - self.layout.header_h - self.layout.footer_h)

        # cached label values: set_text() always invalidates (full-frame
        # redraw in FULL render mode), so only update on actual change
        self._last_fps_text = None
        self._last_det = None
        self._last_status = None
        self._last_wifi = None
        self._show_stats = show_stats

        self.screen = lv.obj()
        self.screen.set_size(DW, DH)
        self.screen.set_style_bg_opa(0, lv.PART.MAIN)
        self.screen.set_style_border_width(0, lv.PART.MAIN)
        self.screen.set_style_radius(0, lv.PART.MAIN)
        self.screen.set_style_pad_all(0, lv.PART.MAIN)
        try:
            self.screen.clear_flag(lv.obj.FLAG.SCROLLABLE)
        except Exception:
            pass

        hdr = lv.obj(self.screen)
        hdr.set_size(DW, self.layout.header_h)
        hdr.set_pos(0, 0)
        hdr.set_style_bg_color(gui.lv_color(0x000000), lv.PART.MAIN)
        hdr.set_style_bg_opa(220, lv.PART.MAIN)
        hdr.set_style_radius(0, lv.PART.MAIN)
        hdr.set_style_border_width(0, lv.PART.MAIN)
        hdr.set_style_pad_all(0, lv.PART.MAIN)
        hdr.clear_flag(lv.obj.FLAG.SCROLLABLE)

        btn_y = (self.layout.header_h - self.layout.overlay_btn_size) // 2
        self._make_round_btn(hdr, self.layout.overlay_edge, btn_y,
                             lv.SYMBOL.LEFT,
                             config.THEME_ACCENT, on_back)
        self._make_round_btn(hdr,
                             DW - self.layout.overlay_btn_size -
                             self.layout.overlay_edge,
                             btn_y, lv.SYMBOL.STOP,
                             config.THEME_RED, on_stop)

        f = gui.font_cn if gui.font_cn else gui.font_en
        title = gui.make_label(hdr, demo_name, config.THEME_TEXT, f)
        title.set_width(max(24, DW - 2 * (
            self.layout.overlay_edge + self.layout.overlay_btn_size + 8)))
        try:
            title.set_long_mode(lv.label.LONG.DOT)
            title.set_style_text_align(lv.TEXT_ALIGN.CENTER, lv.PART.MAIN)
        except Exception:
            pass
        title.align(lv.ALIGN.CENTER, 0, 0)

        ft = lv.obj(self.screen)
        ft.set_size(DW, self.layout.footer_h)
        ft.set_pos(0, DH - self.layout.footer_h)
        ft.set_style_bg_color(gui.lv_color(0x000000), lv.PART.MAIN)
        ft.set_style_bg_opa(220, lv.PART.MAIN)
        ft.set_style_radius(0, lv.PART.MAIN)
        ft.set_style_border_width(0, lv.PART.MAIN)
        ft.set_style_pad_all(0, lv.PART.MAIN)
        ft.clear_flag(lv.obj.FLAG.SCROLLABLE)

        self.status_dot = lv.obj(ft)
        dot_size = self.layout.status_dot_size
        self.status_dot.set_size(dot_size, dot_size)
        self.status_dot.set_style_bg_color(gui.lv_color(config.THEME_GREEN),
                                           lv.PART.MAIN)
        self.status_dot.set_style_bg_opa(255, lv.PART.MAIN)
        self.status_dot.set_style_radius(dot_size // 2, lv.PART.MAIN)
        self.status_dot.set_style_border_width(0, lv.PART.MAIN)

        fe = gui.font_cn if gui.font_cn else gui.font_en
        self._font_cn = gui.font_cn if gui.font_cn else None
        self.status_label = gui.make_label(ft, i18n.text("running"),
                                           config.THEME_GREEN, self._font_cn)
        try:
            self.status_label.set_long_mode(lv.label.LONG.DOT)
        except Exception:
            pass

        self.fps_label = lv.label(ft)
        if fe:
            self.fps_label.set_style_text_font(fe, 0)
        self.fps_label.set_text("-- fps")
        self.fps_label.set_style_text_color(gui.lv_color(config.THEME_GREEN),
                                            lv.PART.MAIN)

        self.wifi_label = lv.label(ft)
        self.wifi_label.set_text(lv.SYMBOL.WIFI)
        self.wifi_label.set_style_text_color(
            gui.lv_color(config.THEME_GREEN), lv.PART.MAIN)

        self.det_label = gui.make_label(ft, "", config.THEME_SUBTEXT, fe)
        self.status_label.set_style_text_align(lv.TEXT_ALIGN.LEFT, lv.PART.MAIN)
        self.fps_label.set_style_text_align(
            lv.TEXT_ALIGN.LEFT if self.layout.narrow else lv.TEXT_ALIGN.CENTER,
            lv.PART.MAIN)
        self.det_label.set_style_text_align(lv.TEXT_ALIGN.RIGHT, lv.PART.MAIN)
        self.wifi_label.set_style_text_align(lv.TEXT_ALIGN.RIGHT, lv.PART.MAIN)
        self.set_wifi_connected(config.wifi_connected)
        for label in (self.fps_label, self.det_label):
            label.set_long_mode(lv.label.LONG.DOT)

        if not show_stats:
            try:
                self.fps_label.add_flag(lv.obj.FLAG.HIDDEN)
                self.det_label.add_flag(lv.obj.FLAG.HIDDEN)
            except Exception:
                pass

        if app_ui_factory:
            try:
                # The application module creates only its LVGL content here.
                # Hardware access remains in the worker-owned Application.
                self._app_ui = app_ui_factory(
                    self.screen, self.layout, (cx, cy, cw, ch))
            except Exception as e:
                print("application UI creation failed:", e)
        if phrases and on_phrase:
            self._build_phrase_menu(cx, cy, cw, ch, phrases, on_phrase)
        if roi_select and on_roi:
            self._build_roi_selector(cx, cy, cw, ch)
        if action_label and on_action:
            self._build_action_button(cx, cy, cw, ch,
                                      action_label, on_action)
        if database and on_database_query and on_database_clear:
            self._build_database_buttons(cx, cy, cw, ch,
                                         on_database_query,
                                         on_database_clear)
        lv.scr_load(self.screen)

    def _action_button_width(self, content_width):
        if i18n.is_chinese():
            width = self.layout.clamp_px(132, 92, 220)
        else:
            width = self.layout.clamp_px(180, 116, 240)
        return min(width, max(80, content_width - 16))

    def _build_action_button(self, cx, cy, cw, ch, text, callback):
        x, y, btn_w, btn_h = self.layout.action_rects()[0]
        button = lv.btn(self.screen)
        button.set_size(btn_w, btn_h)
        button.set_pos(x, y)
        button.set_style_pad_all(0, lv.PART.MAIN)
        button.set_style_bg_color(gui.lv_color(config.THEME_ACCENT),
                                  lv.PART.MAIN)
        button.set_style_bg_opa(235, lv.PART.MAIN)
        button.set_style_border_width(0, lv.PART.MAIN)
        button.set_style_radius(self.layout.overlay_radius, lv.PART.MAIN)
        button.set_style_shadow_width(0, lv.PART.MAIN)
        label = gui.make_label(button, text, config.THEME_TEXT,
                               self._font_cn)
        label.set_width(max(20, btn_w - 10))
        try:
            label.set_long_mode(lv.label.LONG.WRAP)
            label.set_style_text_align(lv.TEXT_ALIGN.CENTER, lv.PART.MAIN)
        except Exception:
            pass
        label.align(lv.ALIGN.CENTER, 0, 0)
        button.add_event(lambda e: callback(), lv.EVENT.CLICKED, None)
        self.action_button = button
        self._action_label = label

    def _build_database_buttons(self, cx, cy, cw, ch,
                                query_callback, clear_callback):
        positions = self.layout.action_rects(database=True)
        if self.action_button is not None:
            ax, ay, aw, ah = positions[2]
            self.action_button.set_pos(ax, ay)
            self.action_button.set_size(aw, ah)
            self._action_label.set_width(aw - 10)

        def make_button(position, text, color, callback):
            x, y, btn_w, btn_h = position
            button = lv.btn(self.screen)
            button.set_size(btn_w, btn_h)
            button.set_pos(x, y)
            button.set_style_bg_color(gui.lv_color(color), lv.PART.MAIN)
            button.set_style_bg_opa(235, lv.PART.MAIN)
            button.set_style_border_width(0, lv.PART.MAIN)
            button.set_style_radius(self.layout.overlay_radius,
                                    lv.PART.MAIN)
            button.set_style_shadow_width(0, lv.PART.MAIN)
            label = gui.make_label(button, text, config.THEME_TEXT,
                                   self._font_cn)
            button.set_style_pad_all(0, lv.PART.MAIN)
            label.set_width(btn_w - 8)
            label.set_long_mode(lv.label.LONG.WRAP)
            label.set_style_text_align(lv.TEXT_ALIGN.CENTER, lv.PART.MAIN)
            label.align(lv.ALIGN.CENTER, 0, 0)
            button.add_event(lambda e: callback(), lv.EVENT.CLICKED, None)

        make_button(positions[0], i18n.text("query_data"), config.THEME_ACCENT,
                    lambda: self.show_database_dialog(query_callback))
        make_button(positions[1], i18n.text("clear_data"),
                    config.THEME_RED,
                    lambda: self.show_clear_confirmation(clear_callback))

    def _build_roi_selector(self, cx, cy, cw, ch):
        """Create a UI-only drag surface; applications receive final coords."""
        area = lv.obj(self.screen)
        area.set_size(cw, ch)
        area.set_pos(cx, cy)
        area.set_style_bg_opa(0, lv.PART.MAIN)
        area.set_style_border_width(0, lv.PART.MAIN)
        area.set_style_radius(0, lv.PART.MAIN)
        area.set_style_pad_all(0, lv.PART.MAIN)
        try:
            area.clear_flag(lv.obj.FLAG.SCROLLABLE)
            area.add_flag(lv.obj.FLAG.HIDDEN)
        except Exception:
            pass

        box = lv.obj(area)
        box.set_size(1, 1)
        box.set_pos(0, 0)
        box.set_style_bg_color(gui.lv_color(config.THEME_ACCENT),
                               lv.PART.MAIN)
        box.set_style_bg_opa(28, lv.PART.MAIN)
        box.set_style_border_color(gui.lv_color(config.THEME_ACCENT),
                                   lv.PART.MAIN)
        box.set_style_border_width(self.layout.clamp_px(3, 2, 5),
                                   lv.PART.MAIN)
        box.set_style_radius(self.layout.clamp_px(4, 2, 8), lv.PART.MAIN)
        box.set_style_pad_all(0, lv.PART.MAIN)
        try:
            box.clear_flag(lv.obj.FLAG.CLICKABLE)
            box.clear_flag(lv.obj.FLAG.SCROLLABLE)
            box.add_flag(lv.obj.FLAG.HIDDEN)
        except Exception:
            pass

        area.add_event(self._roi_pressed, lv.EVENT.PRESSED, None)
        area.add_event(self._roi_pressing, lv.EVENT.PRESSING, None)
        area.add_event(self._roi_released, lv.EVENT.RELEASED, None)
        self._roi_area = area
        self._roi_box = box
        self._roi_geometry = (cx, cy, cw, ch)

    @staticmethod
    def _pointer_position():
        try:
            indev = lv.indev_get_act()
            if indev is not None:
                point = lv.point_t()
                indev.get_point(point)
                return point.x, point.y
        except Exception:
            pass
        return None

    def _clip_roi_point(self, point):
        if point is None:
            return None
        cx, cy, cw, ch = self._roi_geometry
        x = max(cx, min(cx + cw - 1, int(point[0])))
        y = max(cy, min(cy + ch - 1, int(point[1])))
        return x, y

    def _update_roi_box(self, end_point):
        if self._roi_start is None or end_point is None:
            return None
        cx, cy, unused_w, unused_h = self._roi_geometry
        x1 = min(self._roi_start[0], end_point[0])
        y1 = min(self._roi_start[1], end_point[1])
        x2 = max(self._roi_start[0], end_point[0])
        y2 = max(self._roi_start[1], end_point[1])
        width = max(1, x2 - x1)
        height = max(1, y2 - y1)
        self._roi_box.set_pos(x1 - cx, y1 - cy)
        self._roi_box.set_size(width, height)
        try:
            self._roi_box.clear_flag(lv.obj.FLAG.HIDDEN)
        except Exception:
            pass
        return x1, y1, width, height

    def _roi_pressed(self, event):
        if not self._roi_enabled:
            return
        self._roi_start = self._clip_roi_point(self._pointer_position())
        self._update_roi_box(self._roi_start)

    def _roi_pressing(self, event):
        if not self._roi_enabled or self._roi_start is None:
            return
        point = self._clip_roi_point(self._pointer_position())
        self._update_roi_box(point)

    def _roi_released(self, event):
        if not self._roi_enabled or self._roi_start is None:
            return
        point = self._clip_roi_point(self._pointer_position())
        roi = self._update_roi_box(point)
        self._roi_start = None
        if roi is not None and self._on_roi:
            self._on_roi(*roi)

    def set_action_label(self, text):
        if self._action_label is not None:
            self._action_label.set_text(text)

    def set_roi_mode(self, mode):
        if self._roi_area is None:
            return
        selecting = mode == "select"
        self._roi_enabled = selecting
        self._roi_start = None
        try:
            if selecting:
                self._roi_area.clear_flag(lv.obj.FLAG.HIDDEN)
            else:
                self._roi_area.add_flag(lv.obj.FLAG.HIDDEN)
            self._roi_box.add_flag(lv.obj.FLAG.HIDDEN)
        except Exception:
            pass
        if mode == "select":
            self.set_action_label(i18n.text("track_start"))
            self.set_fps(None)
        elif mode in ("tracking", "lost"):
            self.set_action_label(i18n.text("track_reselect"))
        else:
            self.set_action_label(i18n.text("track_pause"))

    def _build_phrase_menu(self, cx, cy, cw, ch, phrases, on_phrase):
        N = len(phrases)
        if not N:
            return
        gap = self.layout.overlay_gap
        btn_h = max(self.layout.line_h + 8, self.layout.clamp_px(52, 32, 104))
        total_h = N * btn_h + (N - 1) * gap
        menu = lv.obj(self.screen)
        menu.set_size(cw, ch)
        menu.align(lv.ALIGN.TOP_LEFT, cx, cy)
        menu.set_style_bg_opa(0, lv.PART.MAIN)
        menu.set_style_border_width(0, lv.PART.MAIN)
        menu.set_style_pad_all(0, lv.PART.MAIN)
        if total_h > ch:
            menu.add_flag(lv.obj.FLAG.SCROLLABLE)
            menu.set_scroll_dir(lv.DIR.VER)
        else:
            menu.clear_flag(lv.obj.FLAG.SCROLLABLE)
        y0 = max(0, (ch - total_h) // 2)
        horizontal_pad = self.layout.clamp_px(40, 20, 80)
        btn_w = min(580, cw - horizontal_pad)
        x0 = (cw - btn_w) // 2
        f = gui.font_cn
        if not f:
            try:
                f = lv.freetype_font_create(
                    "/sdcard/res/font/AlibabaPuHuiTi-3-45-Light.ttf",
                    self.layout.font_size, 0)
                # Own this handle so clean() releases it; the previous code
                # dropped it as a local and leaked one font per overlay.
                self._phrase_font = f
            except Exception:
                f = None

        for i, phrase in enumerate(phrases):
            btn = lv.btn(menu)
            btn.set_size(btn_w, btn_h)
            btn.set_pos(x0, y0 + i * (btn_h + gap))
            btn.set_style_bg_color(gui.lv_color(config.THEME_CARD),
                                   lv.PART.MAIN)
            btn.set_style_bg_opa(255, lv.PART.MAIN)
            btn.set_style_border_width(0, lv.PART.MAIN)
            btn.set_style_radius(self.layout.overlay_radius, lv.PART.MAIN)
            btn.set_style_shadow_width(0, lv.PART.MAIN)
            btn.set_style_pad_all(0, lv.PART.MAIN)
            lbl = lv.label(btn)
            if f:
                lbl.set_style_text_font(f, 0)
            lbl.set_style_text_color(gui.lv_color(config.THEME_TEXT),
                                     lv.PART.MAIN)
            lbl.set_text(phrase)
            lbl.set_width(btn_w - 12)
            lbl.set_long_mode(lv.label.LONG.DOT)
            lbl.set_style_text_align(lv.TEXT_ALIGN.CENTER, lv.PART.MAIN)
            lbl.align(lv.ALIGN.CENTER, 0, 0)
            btn.add_event(lambda e, t=phrase: on_phrase(t),
                          lv.EVENT.CLICKED, None)

    def _make_round_btn(self, parent, x, y, symbol, sym_color, cb):
        btn = lv.btn(parent)
        size = self.layout.overlay_btn_size
        btn.set_size(size, size)
        btn.set_pos(x, y)
        btn.clear_flag(lv.obj.FLAG.SCROLLABLE)
        btn.set_ext_click_area(self.layout.clamp_px(8, 6, 12))
        btn.set_style_bg_color(gui.lv_color(0xFFFFFF), lv.PART.MAIN)
        btn.set_style_bg_opa(20, lv.PART.MAIN)
        btn.set_style_border_width(0, lv.PART.MAIN)
        btn.set_style_radius(size // 2, lv.PART.MAIN)
        btn.set_style_shadow_width(0, lv.PART.MAIN)
        lbl = lv.label(btn)
        lbl.set_text(symbol)
        lbl.set_style_text_color(gui.lv_color(sym_color), lv.PART.MAIN)
        lbl.align(lv.ALIGN.CENTER, 0, 0)
        # Stop is idempotent and only requests worker-owned cleanup.
        btn.add_event(lambda e: cb(), lv.EVENT.PRESSED, None)
        return btn

    def set_fps(self, fps):
        text = "-- fps" if fps is None or fps <= 0 else "%.0f fps" % fps
        if text != self._last_fps_text:
            self._last_fps_text = text
            self.fps_label.set_text(text)

    def set_status(self, text, color=config.THEME_GREEN):
        state = (text, color)
        if state == self._last_status:
            return
        self._last_status = state
        self.status_label.set_text(text)
        self.status_label.set_style_text_color(gui.lv_color(color), lv.PART.MAIN)
        self.status_dot.set_style_bg_color(gui.lv_color(color), lv.PART.MAIN)

    def set_wifi_connected(self, connected):
        connected = bool(connected)
        if self.wifi_label is None or connected == self._last_wifi:
            return
        self._last_wifi = connected
        rects = self.layout.footer_rects(self._show_stats, connected)
        for key, label in (("dot", self.status_dot), ("status", self.status_label),
                           ("fps", self.fps_label), ("result", self.det_label),
                           ("wifi", self.wifi_label)):
            x, y, width, height = rects[key]
            label.set_size(width, height)
            if key != "dot":
                # Symbol and text fonts have different line heights.
                font = label.get_style_text_font(lv.PART.MAIN)
                label.set_style_pad_top(
                    max(0, (height - font.get_line_height()) // 2), lv.PART.MAIN)
            # set_pos alone keeps any earlier CENTER/RIGHT alignment.
            label.align(lv.ALIGN.TOP_LEFT, x, y)
        try:
            if connected:
                self.wifi_label.clear_flag(lv.obj.FLAG.HIDDEN)
            else:
                self.wifi_label.add_flag(lv.obj.FLAG.HIDDEN)
        except Exception:
            self.wifi_label.set_text(lv.SYMBOL.WIFI if connected else "")

    def set_det_count(self, count):
        count = count if (count is not None and count > 0) else 0
        if count == self._last_det:
            return
        self._last_det = count
        self.det_label.set_text(i18n.text("det_count", count)
                                if count else "")

    def handle_ui_request(self, request):
        if request == "face_name" or request == "name_input":
            self.show_name_keyboard()
        elif isinstance(request, (tuple, list)) and len(request) >= 2:
            if request[0] == "app_ui" and self._app_ui is not None:
                callback = getattr(self._app_ui, "handle_update", None)
                if callback:
                    try:
                        callback(request[1])
                    except Exception as e:
                        print("application UI update failed:", e)
                        self.set_status(i18n.text("ui_error"),
                                        config.THEME_RED)
            elif request[0] == "roi_mode":
                self.set_roi_mode(request[1])
            elif request[0] == "database_rows":
                self.update_database_rows(request[1])
            elif request[0] == "database_error":
                self.update_database_error(request[1])

    def _make_modal_backdrop(self):
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
        return backdrop

    def show_database_dialog(self, query_callback):
        if self.screen is None or self._database_dialog is not None or \
                self._name_dialog is not None or \
                self._confirm_dialog is not None:
            return
        DW = self.layout.width
        DH = self.layout.height
        backdrop = self._make_modal_backdrop()
        self._database_dialog = backdrop
        self._database_rows = []

        panel_w, panel_h = self.layout.dialog_size(620, 460)
        panel = lv.obj(backdrop)
        panel.set_size(panel_w, panel_h)
        panel.set_pos((DW - panel_w) // 2, (DH - panel_h) // 2)
        panel.set_style_bg_color(gui.lv_color(config.THEME_CARD),
                                 lv.PART.MAIN)
        panel.set_style_bg_opa(255, lv.PART.MAIN)
        panel.set_style_border_width(1, lv.PART.MAIN)
        panel.set_style_border_color(gui.lv_color(config.THEME_BORDER),
                                     lv.PART.MAIN)
        panel.set_style_radius(self.layout.overlay_radius, lv.PART.MAIN)
        panel.set_style_pad_all(0, lv.PART.MAIN)
        try:
            panel.clear_flag(lv.obj.FLAG.SCROLLABLE)
        except Exception:
            pass

        title = gui.make_label(panel, self._database_title,
                               config.THEME_TEXT, self._font_cn)
        title.set_pos(12, 10)
        title.set_width(panel_w - 72)
        title.set_long_mode(lv.label.LONG.DOT)

        close_size = self.layout.clamp_px(36, 30, 52)
        close_button = lv.btn(panel)
        close_button.set_size(close_size, close_size)
        close_button.set_pos(panel_w - close_size - 8, 6)
        close_button.set_style_bg_color(gui.lv_color(config.THEME_SUBTEXT),
                                        lv.PART.MAIN)
        close_button.set_style_bg_opa(160, lv.PART.MAIN)
        close_button.set_style_border_width(0, lv.PART.MAIN)
        close_button.set_style_radius(close_size // 2, lv.PART.MAIN)
        close_label = lv.label(close_button)
        close_label.set_text("X")
        close_label.set_style_text_color(gui.lv_color(config.THEME_TEXT),
                                         lv.PART.MAIN)
        close_label.align(lv.ALIGN.CENTER, 0, 0)

        field_h = self.layout.clamp_px(40, 34, 56)
        field_y = close_size + 12
        textarea = lv.textarea(panel)
        textarea.set_size(panel_w - 24, field_h)
        textarea.set_pos(12, field_y)
        textarea.set_one_line(True)
        textarea.set_style_bg_color(gui.lv_color(0x2C2C2E), lv.PART.MAIN)
        textarea.set_style_bg_opa(255, lv.PART.MAIN)
        textarea.set_style_border_width(1, lv.PART.MAIN)
        textarea.set_style_border_color(gui.lv_color(config.THEME_BORDER),
                                        lv.PART.MAIN)
        textarea.set_style_text_color(gui.lv_color(config.THEME_TEXT),
                                      lv.PART.MAIN)
        search_font = self._font_cn if self._font_cn else gui.font_en
        if search_font:
            textarea.set_style_text_font(search_font, lv.PART.MAIN)
        try:
            textarea.set_max_length(24)
            textarea.set_placeholder_text(i18n.text("search"))
        except Exception:
            pass

        summary_y = field_y + field_h + 5
        summary = gui.make_label(panel, i18n.text("loading"),
                                 config.THEME_SUBTEXT, self._font_cn)
        summary.set_pos(14, summary_y)
        list_y = summary_y + self.layout.clamp_px(27, 22, 40)
        result_h = max(1, panel_h - list_y - 10)
        results = lv.obj(panel)
        results.set_size(panel_w - 24, result_h)
        results.set_pos(12, list_y)
        results.set_style_bg_color(gui.lv_color(0x111113), lv.PART.MAIN)
        results.set_style_bg_opa(245, lv.PART.MAIN)
        results.set_style_border_width(0, lv.PART.MAIN)
        results.set_style_radius(self.layout.overlay_radius, lv.PART.MAIN)
        results.set_style_pad_all(4, lv.PART.MAIN)
        try:
            results.set_scroll_dir(lv.DIR.VER)
        except Exception:
            pass

        keyboard_h = self.layout.keyboard_height()
        keyboard = lv.keyboard(backdrop)
        keyboard.set_size(DW, keyboard_h)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        keyboard.set_textarea(textarea)
        try:
            keyboard.add_flag(lv.obj.FLAG.HIDDEN)
            keyboard.set_style_text_font(lv.font_default, lv.PART.ITEMS)
        except Exception:
            pass

        def render_rows():
            query = textarea.get_text().strip().lower()
            results.clean()
            visible = 0
            row_h = self.layout.clamp_px(38, 30, 54)
            list_w = panel_w - 32
            for row in self._database_rows:
                if isinstance(row, (tuple, list)):
                    name = str(row[0]) if len(row) else ""
                    count = row[1] if len(row) > 1 else None
                else:
                    name = str(row)
                    count = None
                if query and query not in name.lower():
                    continue
                display_text = name if count is None else \
                    "%s    x%d" % (name, int(count))
                item = lv.obj(results)
                item.set_size(list_w, row_h - 4)
                item.set_pos(0, visible * row_h)
                item.set_style_bg_color(
                    gui.lv_color(0x252529 if visible % 2 == 0 else 0x1C1C1E),
                    lv.PART.MAIN)
                item.set_style_bg_opa(255, lv.PART.MAIN)
                item.set_style_border_width(0, lv.PART.MAIN)
                item.set_style_radius(self.layout.clamp_px(7, 4, 12),
                                      lv.PART.MAIN)
                item.set_style_pad_all(0, lv.PART.MAIN)
                try:
                    item.clear_flag(lv.obj.FLAG.SCROLLABLE)
                except Exception:
                    pass
                label = gui.make_label(item, display_text,
                                       config.THEME_TEXT, self._font_cn)
                label.align(lv.ALIGN.LEFT_MID, 10, 0)
                visible += 1
            summary.set_text(i18n.text(
                "results", visible, len(self._database_rows)))
            if visible == 0:
                empty = gui.make_label(results, i18n.text("no_data"),
                                       config.THEME_SUBTEXT, self._font_cn)
                empty.align(lv.ALIGN.CENTER, 0, 0)

        def show_keyboard():
            try:
                keyboard.clear_flag(lv.obj.FLAG.HIDDEN)
                keyboard.move_foreground()
                panel.set_pos((DW - panel_w) // 2, 4)
                panel.set_height(DH - keyboard_h - 8)
                summary.add_flag(lv.obj.FLAG.HIDDEN)
                results.add_flag(lv.obj.FLAG.HIDDEN)
                textarea.add_state(lv.STATE.FOCUSED)
            except Exception:
                pass

        def hide_keyboard():
            try:
                keyboard.add_flag(lv.obj.FLAG.HIDDEN)
                panel.set_height(panel_h)
                panel.set_pos((DW - panel_w) // 2, (DH - panel_h) // 2)
                summary.clear_flag(lv.obj.FLAG.HIDDEN)
                results.clear_flag(lv.obj.FLAG.HIDDEN)
                textarea.clear_state(lv.STATE.FOCUSED)
            except Exception:
                pass

        def close_dialog():
            if self._database_dialog is None:
                return
            self._database_dialog = None
            self._database_widgets = None
            backdrop.delete()

        textarea.add_event(lambda e: render_rows(),
                           lv.EVENT.VALUE_CHANGED, None)
        textarea.add_event(lambda e: show_keyboard(),
                           lv.EVENT.CLICKED, None)
        keyboard.add_event(lambda e: hide_keyboard(), lv.EVENT.READY, None)
        keyboard.add_event(lambda e: hide_keyboard(), lv.EVENT.CANCEL, None)
        close_button.add_event(lambda e: close_dialog(),
                               lv.EVENT.CLICKED, None)
        self._database_widgets = (textarea, summary, results, render_rows)
        query_result = query_callback()
        if query_result is not True:
            error = query_result if isinstance(query_result, str) else \
                i18n.text("database_busy")
            self.update_database_error(error)

    def update_database_rows(self, rows):
        self._database_rows = list(rows) if rows else []
        if self._database_widgets is not None:
            self._database_widgets[3]()

    def update_database_error(self, error):
        if self._database_widgets is None:
            return
        unused_textarea, summary, results, unused_render = \
            self._database_widgets
        results.clean()
        summary.set_text(i18n.text("query_failed"))
        label = gui.make_label(results, str(error),
                               config.THEME_RED, self._font_cn)
        label.align(lv.ALIGN.CENTER, 0, 0)

    def show_clear_confirmation(self, clear_callback):
        if self.screen is None or self._confirm_dialog is not None or \
                self._name_dialog is not None or \
                self._database_dialog is not None:
            return
        DW = self.layout.width
        DH = self.layout.height
        backdrop = self._make_modal_backdrop()
        self._confirm_dialog = backdrop
        panel_w, panel_h = self.layout.dialog_size(440, 160)
        panel = lv.obj(backdrop)
        panel.set_size(panel_w, panel_h)
        panel.set_pos((DW - panel_w) // 2, (DH - panel_h) // 2)
        panel.set_style_bg_color(gui.lv_color(config.THEME_CARD),
                                 lv.PART.MAIN)
        panel.set_style_bg_opa(255, lv.PART.MAIN)
        panel.set_style_border_width(1, lv.PART.MAIN)
        panel.set_style_border_color(gui.lv_color(config.THEME_RED),
                                     lv.PART.MAIN)
        panel.set_style_radius(self.layout.overlay_radius, lv.PART.MAIN)
        panel.set_style_pad_all(0, lv.PART.MAIN)
        try:
            panel.clear_flag(lv.obj.FLAG.SCROLLABLE)
        except Exception:
            pass

        message = gui.make_label(panel, i18n.text("clear_confirm"),
                                 config.THEME_TEXT, self._font_cn)
        message.set_width(panel_w - 20)
        try:
            message.set_style_text_align(lv.TEXT_ALIGN.CENTER, lv.PART.MAIN)
        except Exception:
            pass
        message.align(lv.ALIGN.TOP_MID, 0,
                      self.layout.clamp_px(24, 16, 36))
        btn_w = self.layout.clamp_px(100, 82, 140)
        btn_h = self.layout.clamp_px(42, 34, 58)
        gap = self.layout.clamp_px(14, 8, 24)
        button_y = panel_h - btn_h - self.layout.clamp_px(16, 10, 24)
        x0 = (panel_w - btn_w * 2 - gap) // 2

        def make_button(x, text, color, confirm):
            button = lv.btn(panel)
            button.set_size(btn_w, btn_h)
            button.set_pos(x, button_y)
            button.set_style_bg_color(gui.lv_color(color), lv.PART.MAIN)
            button.set_style_bg_opa(245, lv.PART.MAIN)
            button.set_style_border_width(0, lv.PART.MAIN)
            button.set_style_radius(self.layout.overlay_radius,
                                    lv.PART.MAIN)
            label = gui.make_label(button, text, config.THEME_TEXT,
                                   self._font_cn)
            label.align(lv.ALIGN.CENTER, 0, 0)
            button.add_event(lambda e: finish(confirm),
                             lv.EVENT.CLICKED, None)

        def finish(confirm):
            if self._confirm_dialog is None:
                return
            self._confirm_dialog = None
            backdrop.delete()
            if confirm:
                result = clear_callback()
                if result is not True:
                    self.set_status(i18n.text("database_busy"),
                                    config.THEME_RED)

        make_button(x0, i18n.text("cancel"), config.THEME_SUBTEXT, False)
        make_button(x0 + btn_w + gap, i18n.text("confirm_clear"),
                    config.THEME_RED, True)

    def show_name_keyboard(self):
        if self._name_dialog is not None or self.screen is None:
            return
        DW = self.layout.width
        DH = self.layout.height
        backdrop = lv.obj(self.screen)
        backdrop.set_size(DW, DH)
        backdrop.set_pos(0, 0)
        backdrop.set_style_bg_color(gui.lv_color(0x000000), lv.PART.MAIN)
        backdrop.set_style_bg_opa(190, lv.PART.MAIN)
        backdrop.set_style_border_width(0, lv.PART.MAIN)
        backdrop.set_style_radius(0, lv.PART.MAIN)
        backdrop.set_style_pad_all(0, lv.PART.MAIN)
        try:
            backdrop.clear_flag(lv.obj.FLAG.SCROLLABLE)
        except Exception:
            pass
        self._name_dialog = backdrop

        entry = self.layout.text_entry_geometry(520)
        dialog_x, dialog_y, dialog_w, dialog_h = entry["panel"]
        keyboard_h = entry["keyboard_h"]
        dialog = lv.obj(backdrop)
        dialog.set_size(dialog_w, dialog_h)
        dialog.set_pos(dialog_x, dialog_y)
        dialog.set_style_bg_color(gui.lv_color(config.THEME_CARD),
                                  lv.PART.MAIN)
        dialog.set_style_bg_opa(255, lv.PART.MAIN)
        dialog.set_style_border_width(0, lv.PART.MAIN)
        dialog.set_style_radius(self.layout.overlay_radius, lv.PART.MAIN)
        dialog.set_style_pad_all(0, lv.PART.MAIN)
        try:
            dialog.clear_flag(lv.obj.FLAG.SCROLLABLE)
        except Exception:
            pass

        title = gui.make_label(dialog, self._name_title,
                               config.THEME_TEXT, self._font_cn)
        title.set_pos(10, 8)
        title.set_width(dialog_w - 20)
        title.set_long_mode(lv.label.LONG.DOT)
        field_x, field_y, field_w, field_h = entry["field"]
        cancel_x, button_y, dialog_btn_w, button_h = entry["cancel"]
        save_x = entry["submit"][0]
        textarea = lv.textarea(dialog)
        textarea.set_size(field_w, field_h)
        textarea.set_pos(field_x, field_y)
        textarea.set_one_line(True)
        textarea.set_style_bg_color(gui.lv_color(0x2C2C2E), lv.PART.MAIN)
        textarea.set_style_bg_opa(255, lv.PART.MAIN)
        textarea.set_style_border_width(1, lv.PART.MAIN)
        textarea.set_style_border_color(gui.lv_color(config.THEME_BORDER),
                                        lv.PART.MAIN)
        textarea.set_style_text_color(gui.lv_color(config.THEME_TEXT),
                                      lv.PART.MAIN)
        try:
            textarea.set_max_length(24)
            textarea.set_placeholder_text(self._name_placeholder)
        except Exception:
            pass

        keyboard = lv.keyboard(backdrop)
        keyboard.set_size(DW, keyboard_h)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        keyboard.set_textarea(textarea)
        try:
            keyboard.clear_flag(lv.obj.FLAG.HIDDEN)
            keyboard.move_foreground()
            textarea.add_state(lv.STATE.FOCUSED)
        except Exception:
            pass
        try:
            keyboard.set_style_text_font(lv.font_default, lv.PART.ITEMS)
        except Exception:
            pass

        closed = [False]

        def finish(submit):
            if closed[0]:
                return
            name = textarea.get_text().strip() if submit else ""
            if submit and not name:
                try:
                    textarea.set_placeholder_text(self._name_placeholder)
                except Exception:
                    pass
                return
            closed[0] = True
            callback = self._on_name_submit
            self._name_dialog = None
            backdrop.delete()
            if callback:
                callback(name)

        cancel_button = lv.btn(dialog)
        cancel_button.set_size(dialog_btn_w, field_h)
        cancel_button.set_pos(cancel_x, button_y)
        cancel_button.set_style_bg_color(gui.lv_color(config.THEME_SUBTEXT),
                                         lv.PART.MAIN)
        cancel_button.set_style_bg_opa(230, lv.PART.MAIN)
        cancel_button.set_style_border_width(0, lv.PART.MAIN)
        cancel_label = gui.make_label(cancel_button, i18n.text("cancel"),
                                      config.THEME_TEXT, self._font_cn)
        cancel_label.align(lv.ALIGN.CENTER, 0, 0)
        cancel_button.add_event(lambda e: finish(False),
                                lv.EVENT.CLICKED, None)

        save_button = lv.btn(dialog)
        save_button.set_size(dialog_btn_w, field_h)
        save_button.set_pos(save_x, button_y)
        save_button.set_style_bg_color(gui.lv_color(config.THEME_ACCENT),
                                       lv.PART.MAIN)
        save_button.set_style_bg_opa(255, lv.PART.MAIN)
        save_button.set_style_border_width(0, lv.PART.MAIN)
        save_label = gui.make_label(save_button, i18n.text("save"),
                                    config.THEME_TEXT, self._font_cn)
        save_label.align(lv.ALIGN.CENTER, 0, 0)
        save_button.add_event(lambda e: finish(True),
                              lv.EVENT.CLICKED, None)

        keyboard.add_event(lambda e: finish(True), lv.EVENT.READY, None)
        keyboard.add_event(lambda e: finish(False), lv.EVENT.CANCEL, None)

    def clean(self):
        # Release the app-UI's own resources (e.g. its freetype fonts) BEFORE
        # deleting the screen, so its clean() never touches already-freed LVGL
        # child widgets.
        if self._app_ui is not None:
            callback = getattr(self._app_ui, "clean", None)
            if callback:
                try:
                    callback()
                except Exception as e:
                    print("application UI cleanup failed:", e)
            self._app_ui = None
        if self.screen:
            self.screen.clean()
            self.screen.delete()
            self.screen = None
        if self._phrase_font is not None:
            try:
                self._phrase_font.freetype_font_del()
            except Exception as e:
                print("overlay phrase font cleanup failed:", e)
            self._phrase_font = None
        self._name_dialog = None
        self._database_dialog = None
        self._database_rows = []
        self._database_widgets = None
        self._confirm_dialog = None
        self.action_button = None
        self._action_label = None
        self._roi_area = None
        self._roi_box = None
        self._roi_start = None
        self._on_roi = None
        self._on_database_query = None
        self._on_database_clear = None
        self.wifi_label = None
