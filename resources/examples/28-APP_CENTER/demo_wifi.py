# demo_wifi.py - Independent Wi-Fi scan/connect application

import time
import lvgl as lv

import config
import i18n
import lvgl_utils as gui
from app_contract import Application


POLL_MS = 500
CONNECT_TIMEOUT_MS = 15000
DISCONNECT_TIMEOUT_MS = 3000
MAX_NETWORKS = 16

_TEXT = {
    "zh_CN": {
        "status_title": "WI-FI 状态", "networks_title": "可用网络",
        "initializing": "初始化...", "disconnect": "断开连接", "refresh": "刷新",
        "scanning_ui": "正在扫描网络...", "disconnecting_ui": "正在断开连接...",
        "connecting_to": "正在连接 %s", "refresh_tip": "点击刷新搜索 Wi-Fi",
        "connect_title": "连接 %s", "cancel": "取消", "connect": "连接",
        "open": "开放", "locked": "加密",
        "state_unsupported": "当前固件不支持 Wi-Fi", "state_scanning": "正在扫描",
        "state_connecting": "正在连接", "state_disconnecting": "正在断开",
        "state_connected": "已连接", "state_disconnected": "未连接", "state_error": "操作失败",
        "unavailable": "Wi-Fi不可用", "scan_nearby": "正在扫描附近网络...",
        "scan_status": "正在扫描Wi-Fi", "found": "发现 %d 个网络",
        "scan_failed_detail": "扫描失败: %s", "scan_failed": "Wi-Fi扫描失败",
        "connect_status": "正在连接Wi-Fi", "connect_failed_detail": "连接失败: %s",
        "connect_failed": "Wi-Fi连接失败", "disconnecting": "正在断开连接...",
        "disconnect_status": "正在断开Wi-Fi", "disconnect_failed_detail": "断开失败: %s",
        "disconnect_failed": "Wi-Fi断开失败", "connected_detail": "已连接 %s",
        "connected_status": "Wi-Fi已连接", "connect_timeout_detail": "连接超时，请检查密码和信号",
        "connect_timeout": "Wi-Fi连接超时", "disconnected_detail": "已断开连接",
        "disconnected_status": "Wi-Fi已断开", "disconnect_timeout_detail": "断开连接超时",
        "disconnect_timeout": "Wi-Fi断开超时",
    },
    "en_US": {
        "status_title": "WI-FI STATUS", "networks_title": "AVAILABLE NETWORKS",
        "initializing": "Initializing...", "disconnect": "Disconnect", "refresh": "Refresh",
        "scanning_ui": "Scanning networks...", "disconnecting_ui": "Disconnecting...",
        "connecting_to": "Connecting to %s", "refresh_tip": "Tap Refresh to scan for Wi-Fi",
        "connect_title": "Connect to %s", "cancel": "Cancel", "connect": "Connect",
        "open": "OPEN", "locked": "LOCK",
        "state_unsupported": "Wi-Fi is not supported by this firmware", "state_scanning": "Scanning",
        "state_connecting": "Connecting", "state_disconnecting": "Disconnecting",
        "state_connected": "Connected", "state_disconnected": "Disconnected", "state_error": "Operation failed",
        "unavailable": "Wi-Fi unavailable", "scan_nearby": "Scanning nearby networks...",
        "scan_status": "Scanning Wi-Fi", "found": "Found %d networks",
        "scan_failed_detail": "Scan failed: %s", "scan_failed": "Wi-Fi scan failed",
        "connect_status": "Connecting Wi-Fi", "connect_failed_detail": "Connection failed: %s",
        "connect_failed": "Wi-Fi connection failed", "disconnecting": "Disconnecting...",
        "disconnect_status": "Disconnecting Wi-Fi", "disconnect_failed_detail": "Disconnect failed: %s",
        "disconnect_failed": "Wi-Fi disconnect failed", "connected_detail": "Connected to %s",
        "connected_status": "Wi-Fi connected", "connect_timeout_detail": "Connection timed out; check password and signal",
        "connect_timeout": "Wi-Fi connection timed out", "disconnected_detail": "Disconnected",
        "disconnected_status": "Wi-Fi disconnected", "disconnect_timeout_detail": "Disconnect timed out",
        "disconnect_timeout": "Wi-Fi disconnect timed out",
    },
}


def _t(key, *values):
    value = _TEXT[i18n.language()].get(key, key)
    return value % values if values else value


class WiFiUI:
    """LVGL-only Wi-Fi page; network calls stay in WiFiDemo."""

    def __init__(self, screen, layout, content):
        self.screen = screen
        self.layout = layout
        self._values = {}
        self._networks = ()
        self._connected_ssid = ""
        self._modal = None
        cx, cy, cw, ch = content

        self.root = lv.obj(screen)
        self.root.set_size(cw, ch)
        self.root.set_pos(cx, cy)
        self.root.set_style_bg_color(gui.lv_color(0x070A12), lv.PART.MAIN)
        self.root.set_style_bg_opa(255, lv.PART.MAIN)
        self.root.set_style_border_width(0, lv.PART.MAIN)
        self.root.set_style_radius(0, lv.PART.MAIN)
        self.root.set_style_pad_all(0, lv.PART.MAIN)
        try:
            self.root.clear_flag(lv.obj.FLAG.SCROLLABLE)
        except Exception:
            pass

        margin = layout.clamp_px(14, 8, 28)
        gap = layout.clamp_px(12, 7, 24)
        stacked = cw < 600 or ch < 320
        inset = layout.clamp_px(18, 10, 32)
        status_h = max(ch - margin * 2, layout.line_h * 7 + 60 + inset * 2)
        if stacked:
            status_w = list_w = cw - margin * 2
            card_h = max(240, ch - margin * 2)
            list_x, list_y = margin, margin + status_h + gap
            self.root.add_flag(lv.obj.FLAG.SCROLLABLE)
            self.root.set_scroll_dir(lv.DIR.VER)
        else:
            usable_w = cw - margin * 2 - gap
            status_w = usable_w * 40 // 100
            list_w = usable_w - status_w
            card_h = status_h
            list_x, list_y = margin + status_w + gap, margin
            if status_h > ch - margin * 2:
                self.root.add_flag(lv.obj.FLAG.SCROLLABLE)
                self.root.set_scroll_dir(lv.DIR.VER)
        self.status_card = self._make_card(
            margin, margin, status_w, status_h, 0x111827, 0x0A84FF)
        self.list_card = self._make_card(
            list_x, list_y, list_w, card_h, 0x10151F, 0x30D158)

        title_font = (gui.font_cn if i18n.is_chinese() else gui.font_en) or \
            gui.font_cn or gui.font_en
        body_font = gui.font_cn if gui.font_cn else gui.font_en
        inset = layout.clamp_px(18, 10, 32)

        title = self._label(self.status_card, _t("status_title"), 0x5AC8FA,
                            title_font)
        title.set_pos(inset, inset + 0 * (layout.line_h + 4))
        self.state_label = self._label(self.status_card, _t("initializing"),
                                       0xFFFFFF, body_font)
        self.state_label.set_pos(inset, inset + 1 * (layout.line_h + 4))
        self.ssid_label = self._label(self.status_card, "SSID: --",
                                      0xD8E0ED, body_font)
        self.ssid_label.set_pos(inset, inset + 2 * (layout.line_h + 4))
        self.ssid_label.set_width(max(30, status_w - inset * 2))
        try:
            self.ssid_label.set_long_mode(lv.label.LONG.DOT)
        except Exception:
            pass
        self.ip_label = self._label(self.status_card, "IP: --", 0x9DAABD,
                                    gui.font_en)
        self.ip_label.set_pos(inset, inset + 3 * (layout.line_h + 4))
        self.rssi_label = self._label(self.status_card, "RSSI: --",
                                      0x9DAABD, gui.font_en)
        self.rssi_label.set_pos(inset, inset + 4 * (layout.line_h + 4))
        self.message_label = self._label(self.status_card, "",
                                         0xFFB340, body_font)
        self.message_label.set_pos(inset, inset + 5 * (layout.line_h + 4))
        self.message_label.set_width(max(30, status_w - inset * 2))
        for status_label in (title, self.state_label, self.ssid_label,
                             self.ip_label, self.rssi_label, self.message_label):
            status_label.set_size(status_w - inset * 2, layout.line_h)
            status_label.set_long_mode(lv.label.LONG.DOT)

        self.disconnect_btn = self._make_button(
            self.status_card, _t("disconnect"), config.THEME_RED,
            self._request_disconnect)
        self.disconnect_btn.set_size(
            max(80, status_w - inset * 2),
            layout.clamp_px(42, 34, 60))
        self.disconnect_btn.align(lv.ALIGN.BOTTOM_MID, 0,
                                  -layout.clamp_px(16, 8, 28))
        try:
            self.disconnect_btn.add_flag(lv.obj.FLAG.HIDDEN)
        except Exception:
            pass

        list_title = self._label(self.list_card, _t("networks_title"),
                                 0x64D98B, title_font)
        list_title.set_pos(inset, layout.clamp_px(16, 8, 28))
        refresh_w = layout.clamp_px(92, 72, 130)
        refresh_edge = layout.clamp_px(12, 7, 22)
        list_title.set_width(max(24, list_w - inset - refresh_w - refresh_edge - 8))
        list_title.set_long_mode(lv.label.LONG.DOT)
        self.refresh_btn = self._make_button(
            self.list_card, _t("refresh"), config.THEME_ACCENT,
            self._request_scan)
        self.refresh_btn.set_size(refresh_w,
                                  layout.clamp_px(38, 32, 54))
        self.refresh_btn.align(lv.ALIGN.TOP_RIGHT,
                               -layout.clamp_px(12, 7, 22),
                               layout.clamp_px(9, 5, 16))

        list_y = layout.clamp_px(60, 44, 88)
        self._network_list_width = max(10, list_w - inset * 2)
        self.network_list = lv.obj(self.list_card)
        self.network_list.set_size(
            self._network_list_width, max(10, card_h - list_y - inset))
        self.network_list.set_pos(inset, list_y)
        self.network_list.set_style_bg_color(gui.lv_color(0x090D15),
                                              lv.PART.MAIN)
        self.network_list.set_style_bg_opa(255, lv.PART.MAIN)
        self.network_list.set_style_border_width(0, lv.PART.MAIN)
        self.network_list.set_style_radius(layout.overlay_radius,
                                           lv.PART.MAIN)
        self.network_list.set_style_pad_all(layout.clamp_px(5, 3, 9),
                                            lv.PART.MAIN)
        try:
            self.network_list.set_scroll_dir(lv.DIR.VER)
        except Exception:
            pass
        self._render_networks()

    def _make_card(self, x, y, w, h, color, accent):
        card = lv.obj(self.root)
        card.set_size(w, h)
        card.set_pos(x, y)
        card.set_style_bg_color(gui.lv_color(color), lv.PART.MAIN)
        card.set_style_bg_opa(255, lv.PART.MAIN)
        card.set_style_border_color(gui.lv_color(accent), lv.PART.MAIN)
        card.set_style_border_opa(70, lv.PART.MAIN)
        card.set_style_border_width(1, lv.PART.MAIN)
        card.set_style_radius(self.layout.clamp_px(18, 10, 30), lv.PART.MAIN)
        card.set_style_pad_all(0, lv.PART.MAIN)
        try:
            card.clear_flag(lv.obj.FLAG.SCROLLABLE)
        except Exception:
            pass
        return card

    @staticmethod
    def _label(parent, text, color, font=None):
        return gui.make_label(parent, text, color, font)

    def _make_button(self, parent, text, color, callback):
        button = lv.btn(parent)
        button.set_style_bg_color(gui.lv_color(color), lv.PART.MAIN)
        button.set_style_bg_opa(235, lv.PART.MAIN)
        button.set_style_border_width(0, lv.PART.MAIN)
        button.set_style_shadow_width(0, lv.PART.MAIN)
        button.set_style_radius(self.layout.overlay_radius, lv.PART.MAIN)
        label = self._label(button, text, config.THEME_TEXT,
                            gui.font_cn if gui.font_cn else gui.font_en)
        label.align(lv.ALIGN.CENTER, 0, 0)
        button.add_event(lambda e: callback(), lv.EVENT.CLICKED, None)
        return button

    def _app_call(self, name, *args):
        app = config.running_app
        if app is None:
            return False
        callback = getattr(app, name, None)
        return callback(*args) if callback else False

    def _request_scan(self):
        if self._app_call("request_scan"):
            self._set_text("message", self.message_label, _t("scanning_ui"))

    def _request_disconnect(self):
        if self._app_call("request_disconnect"):
            self._set_text("message", self.message_label,
                           _t("disconnecting_ui"))

    def _network_clicked(self, ssid, is_open):
        if ssid == self._connected_ssid:
            return
        if is_open:
            if self._app_call("request_connect", ssid, "", True):
                self._set_text("message", self.message_label,
                               _t("connecting_to", ssid))
            return
        self._show_password_dialog(ssid)

    def _render_networks(self):
        self.network_list.clean()
        if not self._networks:
            empty = self._label(self.network_list, _t("refresh_tip"),
                                config.THEME_SUBTEXT,
                                gui.font_cn if gui.font_cn else gui.font_en)
            empty.set_width(max(24, self._network_list_width - 12))
            empty.set_long_mode(lv.label.LONG.WRAP)
            empty.set_style_text_align(lv.TEXT_ALIGN.CENTER, lv.PART.MAIN)
            empty.align(lv.ALIGN.CENTER, 0, 0)
            return

        list_w = self._network_list_width - \
            self.layout.clamp_px(10, 6, 18)
        stacked = list_w < 320
        row_h = (self.layout.line_h * 2 + 12 if stacked else
                 self.layout.clamp_px(49, 40, 70))
        for index, network in enumerate(self._networks):
            ssid, rssi, is_open = network
            row = lv.obj(self.network_list)
            row.set_size(list_w, row_h - self.layout.clamp_px(4, 2, 7))
            row.set_pos(0, index * row_h)
            selected = ssid == self._connected_ssid
            row.set_style_bg_color(
                gui.lv_color(0x12314A if selected else
                             (0x171D29 if index % 2 == 0 else 0x121823)),
                lv.PART.MAIN)
            row.set_style_bg_opa(255, lv.PART.MAIN)
            row.set_style_border_width(1 if selected else 0, lv.PART.MAIN)
            row.set_style_border_color(gui.lv_color(config.THEME_ACCENT),
                                       lv.PART.MAIN)
            row.set_style_radius(self.layout.clamp_px(9, 6, 15), lv.PART.MAIN)
            row.set_style_pad_all(0, lv.PART.MAIN)
            try:
                row.clear_flag(lv.obj.FLAG.SCROLLABLE)
            except Exception:
                pass
            row.add_event(
                lambda e, s=ssid, o=is_open: self._network_clicked(s, o),
                lv.EVENT.CLICKED, None)

            name = self._label(row, ssid, config.THEME_TEXT,
                               gui.font_cn if gui.font_cn else gui.font_en)
            edge = self.layout.clamp_px(12, 7, 20)
            badge_w = 76
            signal_w = 80
            name.set_width(list_w - edge * 2 if stacked else
                           max(24, list_w - edge * 2 - badge_w - signal_w - 12))
            name.align(lv.ALIGN.TOP_LEFT if stacked else lv.ALIGN.LEFT_MID,
                       edge, 2 if stacked else 0)
            try:
                name.set_long_mode(lv.label.LONG.DOT)
            except Exception:
                pass
            signal = self._label(row, "%d dBm" % int(rssi),
                                 0x8FA1B8, gui.font_en)
            signal.set_width(signal_w)
            signal.set_long_mode(lv.label.LONG.DOT)
            signal.align(lv.ALIGN.BOTTOM_LEFT if stacked else lv.ALIGN.RIGHT_MID,
                         edge if stacked else -(edge + badge_w + 6),
                         -2 if stacked else 0)
            badge = self._label(row, _t("open") if is_open else _t("locked"),
                                config.THEME_GREEN if is_open else
                                config.THEME_ORANGE,
                                gui.font_cn if i18n.is_chinese()
                                else gui.font_en)
            badge.set_width(badge_w)
            badge.set_long_mode(lv.label.LONG.DOT)
            badge.set_style_text_align(lv.TEXT_ALIGN.RIGHT, lv.PART.MAIN)
            badge.align(lv.ALIGN.BOTTOM_RIGHT if stacked else lv.ALIGN.RIGHT_MID,
                        -edge, -2 if stacked else 0)

    def _show_password_dialog(self, ssid):
        if self._modal is not None:
            return
        dw = self.layout.width
        dh = self.layout.height
        backdrop = lv.obj(self.screen)
        backdrop.set_size(dw, dh)
        backdrop.set_pos(0, 0)
        backdrop.set_style_bg_color(gui.lv_color(0x000000), lv.PART.MAIN)
        backdrop.set_style_bg_opa(220, lv.PART.MAIN)
        backdrop.set_style_border_width(0, lv.PART.MAIN)
        backdrop.set_style_radius(0, lv.PART.MAIN)
        backdrop.set_style_pad_all(0, lv.PART.MAIN)
        try:
            backdrop.clear_flag(lv.obj.FLAG.SCROLLABLE)
        except Exception:
            pass
        self._modal = backdrop

        entry = self.layout.text_entry_geometry(560)
        panel_x, panel_y, panel_w, panel_h = entry["panel"]
        keyboard_h = entry["keyboard_h"]
        panel = lv.obj(backdrop)
        panel.set_size(panel_w, panel_h)
        panel.set_pos(panel_x, panel_y)
        panel.set_style_bg_color(gui.lv_color(0x171D29), lv.PART.MAIN)
        panel.set_style_bg_opa(255, lv.PART.MAIN)
        panel.set_style_border_color(gui.lv_color(config.THEME_ACCENT),
                                     lv.PART.MAIN)
        panel.set_style_border_width(1, lv.PART.MAIN)
        panel.set_style_radius(self.layout.overlay_radius, lv.PART.MAIN)
        panel.set_style_pad_all(0, lv.PART.MAIN)
        try:
            panel.clear_flag(lv.obj.FLAG.SCROLLABLE)
        except Exception:
            pass

        title = self._label(panel, _t("connect_title", ssid), config.THEME_TEXT,
                            gui.font_cn if gui.font_cn else gui.font_en)
        title.set_pos(12, 9)
        title.set_width(panel_w - 24)
        try:
            title.set_long_mode(lv.label.LONG.DOT)
        except Exception:
            pass

        field_x, field_y, field_w, field_h = entry["field"]
        cancel_x, button_y, btn_w, button_h = entry["cancel"]
        connect_x = entry["submit"][0]
        textarea = lv.textarea(panel)
        textarea.set_size(field_w, field_h)
        textarea.set_pos(field_x, field_y)
        textarea.set_one_line(True)
        textarea.set_password_mode(True)
        textarea.set_style_bg_color(gui.lv_color(0x090D15), lv.PART.MAIN)
        textarea.set_style_bg_opa(255, lv.PART.MAIN)
        textarea.set_style_border_color(gui.lv_color(config.THEME_BORDER),
                                        lv.PART.MAIN)
        textarea.set_style_border_width(1, lv.PART.MAIN)
        textarea.set_style_text_color(gui.lv_color(config.THEME_TEXT),
                                      lv.PART.MAIN)
        try:
            textarea.set_max_length(63)
        except Exception:
            pass

        keyboard = lv.keyboard(backdrop)
        keyboard.set_size(dw, keyboard_h)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        keyboard.set_textarea(textarea)
        try:
            keyboard.set_style_text_font(lv.font_default, lv.PART.ITEMS)
            textarea.add_state(lv.STATE.FOCUSED)
            keyboard.move_foreground()
        except Exception:
            pass

        closed = [False]

        def finish(connect):
            if closed[0]:
                return
            password = textarea.get_text() if connect else ""
            if connect and not (8 <= len(password) <= 63):
                try:
                    textarea.set_text("")
                    textarea.set_style_border_color(
                        gui.lv_color(config.THEME_RED), lv.PART.MAIN)
                except Exception:
                    pass
                return
            if connect and not self._app_call(
                    "request_connect", ssid, password, False):
                return
            closed[0] = True
            self._modal = None
            backdrop.delete()
            if connect:
                self._set_text("message", self.message_label,
                               _t("connecting_to", ssid))

        cancel = self._make_button(panel, _t("cancel"), config.THEME_SUBTEXT,
                                   lambda: finish(False))
        cancel.set_size(btn_w, field_h)
        cancel.set_pos(cancel_x, button_y)
        connect = self._make_button(panel, _t("connect"), config.THEME_ACCENT,
                                    lambda: finish(True))
        connect.set_size(btn_w, field_h)
        connect.set_pos(connect_x, button_y)
        keyboard.add_event(lambda e: finish(True), lv.EVENT.READY, None)
        keyboard.add_event(lambda e: finish(False), lv.EVENT.CANCEL, None)

    def _set_text(self, key, label, value):
        if self._values.get(key) == value:
            return
        self._values[key] = value
        label.set_text(value)

    def handle_update(self, payload):
        if not isinstance(payload, (tuple, list)) or len(payload) < 10 or \
                payload[0] != "wifi":
            return
        unused_kind, supported, connected, busy, state, ssid, ip, rssi, \
            networks, message = payload
        self._connected_ssid = ssid if connected else ""
        state_text = {
            "unsupported": _t("state_unsupported"),
            "scanning": _t("state_scanning"),
            "connecting": _t("state_connecting"),
            "disconnecting": _t("state_disconnecting"),
            "connected": _t("state_connected"),
            "disconnected": _t("state_disconnected"),
            "error": _t("state_error"),
        }.get(state, state)
        self._set_text("state", self.state_label, state_text)
        self.state_label.set_style_text_color(
            gui.lv_color(config.THEME_GREEN if connected else
                         (config.THEME_ORANGE if busy else
                          (config.THEME_RED if state in ("error", "unsupported")
                           else config.THEME_TEXT))), lv.PART.MAIN)
        self._set_text("ssid", self.ssid_label,
                       "SSID: " + (ssid if ssid else "--"))
        self._set_text("ip", self.ip_label, "IP: " + (ip if ip else "--"))
        self._set_text("rssi", self.rssi_label,
                       "RSSI: %s dBm" % rssi if rssi is not None
                       else "RSSI: --")
        self._set_text("message", self.message_label, message or "")
        try:
            if connected and not busy:
                self.disconnect_btn.clear_flag(lv.obj.FLAG.HIDDEN)
            else:
                self.disconnect_btn.add_flag(lv.obj.FLAG.HIDDEN)
            if busy or not supported:
                self.refresh_btn.add_state(lv.STATE.DISABLED)
            else:
                self.refresh_btn.clear_state(lv.STATE.DISABLED)
        except Exception:
            pass

        new_networks = tuple(networks) if networks else ()
        render_key = (new_networks, self._connected_ssid)
        if self._values.get("networks") != render_key:
            self._values["networks"] = render_key
            self._networks = new_networks
            self._render_networks()

    def clean(self):
        self._modal = None
        self._networks = ()
        self._values = {}


class WiFiDemo(Application):
    name = "Wi-Fi连接"
    ui_show_stats = False

    def __init__(self):
        super().__init__()
        self._wlan = None
        self._supported = True
        self._command = None
        self._phase = None
        self._deadline = None
        self._pending_connect = None
        self._connect_ssid = ""
        self._networks = []
        self._last_poll = None
        self._last_payload = None
        self._last_status = None
        self._message = ""
        self._state = "disconnected"

    @staticmethod
    def create_app_ui(screen, layout, content):
        return WiFiUI(screen, layout, content)

    def start(self):
        super().start()
        try:
            import network
            wlan_type = getattr(network, "WLAN", None)
            if wlan_type is None:
                raise RuntimeError("network.WLAN is unavailable")
            self._wlan = wlan_type(0)
        except Exception as e:
            self._supported = False
            self._state = "unsupported"
            self._message = str(e)
            self._publish()
            self._set_status(_t("unavailable"), config.THEME_RED)
            return
        self._refresh_state()
        self._command = ("scan",)
        self._publish()

    def request_scan(self):
        if self.stop_req or not self._supported or self._command is not None \
                or self._phase is not None:
            return False
        self._command = ("scan",)
        return True

    def request_connect(self, ssid, password, is_open):
        if self.stop_req or not self._supported or self._command is not None \
                or self._phase is not None or not ssid:
            return False
        self._command = ("connect", str(ssid), str(password), bool(is_open))
        return True

    def request_disconnect(self):
        if self.stop_req or not self._supported or self._command is not None \
                or self._phase is not None:
            return False
        self._command = ("disconnect",)
        return True

    @staticmethod
    def _decode_ssid(value):
        if isinstance(value, bytes):
            try:
                return value.decode("utf-8")
            except Exception:
                return "<invalid SSID>"
        return str(value)

    def _connection_info(self):
        if self._wlan is None:
            return False, "", "", None
        try:
            connected = bool(self._wlan.isconnected())
            ip = self._wlan.ifconfig()[0] if connected else ""
            connected = connected and ip != "0.0.0.0"
            if not connected:
                return False, "", "", None
            info = self._wlan.status("ap")
            ssid = self._decode_ssid(info.ssid) if info is not None else \
                self._connect_ssid
            try:
                rssi = int(self._wlan.status("rssi"))
            except Exception:
                rssi = None
            return True, ssid, ip, rssi
        except Exception:
            return False, "", "", None

    def _refresh_state(self):
        connected, unused_ssid, unused_ip, unused_rssi = \
            self._connection_info()
        if self._phase is None:
            self._state = "connected" if connected else "disconnected"

    def _scan(self):
        self._state = "scanning"
        self._message = _t("scan_nearby")
        self._publish()
        self._set_status(_t("scan_status"), config.THEME_ORANGE)
        try:
            raw = self._wlan.scan()
            strongest = {}
            for item in raw:
                ssid = self._decode_ssid(item.ssid)
                if not ssid or ssid == "<invalid SSID>":
                    continue
                rssi = int(getattr(item, "rssi", -99))
                security = int(getattr(item, "security", 1))
                current = strongest.get(ssid)
                if current is None or rssi > current[0]:
                    strongest[ssid] = (rssi, security == 0)
            networks = [(ssid, value[0], value[1])
                        for ssid, value in strongest.items()]
            networks.sort(key=lambda item: item[1], reverse=True)
            self._networks = networks[:MAX_NETWORKS]
            self._message = _t("found", len(self._networks))
            self._refresh_state()
            self._set_status(self._message, config.THEME_GREEN)
        except Exception as e:
            self._state = "error"
            self._message = _t("scan_failed_detail", e)
            self._set_status(_t("scan_failed"), config.THEME_RED)
            print("WiFi: scan failed:", e)
        self._publish()

    def _begin_connect(self, ssid, password, is_open):
        self._connect_ssid = ssid
        self._state = "connecting"
        self._message = _t("connecting_to", ssid)
        self._pending_connect = (ssid, password, is_open)
        self._set_status(_t("connect_status"), config.THEME_ORANGE)
        connected, unused_ssid, unused_ip, unused_rssi = \
            self._connection_info()
        if connected:
            try:
                self._wlan.disconnect()
            except Exception:
                pass
            self._phase = "disconnect_first"
            self._deadline = time.ticks_add(time.ticks_ms(),
                                            DISCONNECT_TIMEOUT_MS)
        else:
            self._start_driver_connect()
        self._publish()

    def _start_driver_connect(self):
        ssid, password, is_open = self._pending_connect
        self._pending_connect = None
        try:
            result = self._wlan.connect(ssid) if is_open else \
                self._wlan.connect(ssid, password)
            password = None
            if result is False:
                raise RuntimeError("driver rejected connection")
            self._phase = "connecting"
            self._deadline = time.ticks_add(time.ticks_ms(),
                                            CONNECT_TIMEOUT_MS)
        except Exception as e:
            password = None
            self._phase = None
            self._state = "error"
            self._message = _t("connect_failed_detail", e)
            self._set_status(_t("connect_failed"), config.THEME_RED)
            print("WiFi: connect failed:", e)

    def _begin_disconnect(self):
        self._state = "disconnecting"
        self._message = _t("disconnecting")
        self._set_status(_t("disconnect_status"), config.THEME_ORANGE)
        try:
            result = self._wlan.disconnect()
            if result is False:
                raise RuntimeError("driver rejected disconnect")
            self._phase = "disconnecting"
            self._deadline = time.ticks_add(time.ticks_ms(),
                                            DISCONNECT_TIMEOUT_MS)
        except Exception as e:
            self._phase = None
            self._state = "error"
            self._message = _t("disconnect_failed_detail", e)
            self._set_status(_t("disconnect_failed"), config.THEME_RED)
            print("WiFi: disconnect failed:", e)
        self._publish()

    def _advance_phase(self, now):
        connected, ssid, ip, unused_rssi = self._connection_info()
        if self._phase == "disconnect_first":
            if not connected or time.ticks_diff(now, self._deadline) >= 0:
                self._start_driver_connect()
                self._publish()
        elif self._phase == "connecting":
            if connected:
                self._phase = None
                self._state = "connected"
                self._message = _t("connected_detail",
                                   ssid or self._connect_ssid)
                self._set_status(_t("connected_status"), config.THEME_GREEN)
                self._publish()
            elif time.ticks_diff(now, self._deadline) >= 0:
                self._phase = None
                self._state = "error"
                self._message = _t("connect_timeout_detail")
                self._set_status(_t("connect_timeout"), config.THEME_RED)
                try:
                    self._wlan.disconnect()
                except Exception:
                    pass
                self._publish()
        elif self._phase == "disconnecting":
            if not connected:
                self._phase = None
                self._state = "disconnected"
                self._message = _t("disconnected_detail")
                self._connect_ssid = ""
                self._set_status(_t("disconnected_status"), config.THEME_GREEN)
                self._publish()
            elif time.ticks_diff(now, self._deadline) >= 0:
                self._phase = None
                self._state = "error"
                self._message = _t("disconnect_timeout_detail")
                self._set_status(_t("disconnect_timeout"), config.THEME_RED)
                self._publish()

    def _set_status(self, text, color):
        value = (text, color)
        if value == self._last_status:
            return
        self._last_status = value
        config.demo_status_text = text
        config.demo_status_color = color

    def _publish(self):
        connected, ssid, ip, rssi = self._connection_info()
        busy = self._phase is not None or self._state == "scanning"
        display_ssid = ssid if connected else \
            (self._connect_ssid if self._state == "connecting" else "")
        payload = ("wifi", self._supported, connected, busy,
                   self._state, display_ssid, ip, rssi,
                   tuple(self._networks), self._message)
        if payload != self._last_payload:
            self._last_payload = payload
            config.demo_ui_request = ("app_ui", payload)

    def run_once(self):
        if not self._supported:
            time.sleep_ms(50)
            return None
        now = time.ticks_ms()
        command = self._command
        if command is not None and self._phase is None:
            self._command = None
            if command[0] == "scan":
                self._scan()
            elif command[0] == "connect":
                self._begin_connect(command[1], command[2], command[3])
            elif command[0] == "disconnect":
                self._begin_disconnect()

        if self._last_poll is None or \
                time.ticks_diff(now, self._last_poll) >= POLL_MS:
            self._last_poll = now
            if self._phase is not None:
                self._advance_phase(now)
            if self._phase is None and self._state not in ("error", "scanning"):
                self._refresh_state()
            self._publish()
        return None

    def _release_owned_resources(self):
        # WLAN is a system singleton. Keep an established connection alive
        # when leaving this page; only the explicit Disconnect action tears it
        # down. Password references are discarded and never written to disk.
        self._pending_connect = None
        self._command = None
        self._wlan = None
        self._networks = []
        self._last_payload = None
