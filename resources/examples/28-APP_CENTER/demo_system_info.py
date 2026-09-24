# demo_system_info.py - Independent chip/RTC/temperature/resource dashboard

import time
import binascii
import gc
import os
import machine
import lvgl as lv

import config
import i18n
import lvgl_utils as gui
from app_contract import Application


POLL_MS = 200
TEMP_POLL_MS = 1000
RESOURCE_POLL_MS = 1000
NETWORK_CHECK_MS = 2000
WEEKDAYS_ZH = ("星期日", "星期一", "星期二", "星期三",
               "星期四", "星期五", "星期六")
WEEKDAYS_EN = ("Sunday", "Monday", "Tuesday", "Wednesday",
               "Thursday", "Friday", "Saturday")

_TEXT = {
    "zh_CN": {
        "rtc_title": "RTC 时钟", "chip_title": "芯片 ID", "temp_title": "芯片温度",
        "load_title": "内存与 CPU", "heap_title": "系统堆", "page_title": "页内存",
        "mmz_title": "媒体内存", "cpu_title": "CPU 占用",
        "sensor_tag": "片上温度传感器", "reading": "读取中...", "partial": "部分信息不可用",
        "monitoring": "实时监测", "rtc_unavailable": "RTC不可用", "syncing": "正在同步 RTC",
        "sensor_unavailable": "传感器不可用", "live_temp": "实时温度",
        "sync_failed": "RTC 校时失败", "unavailable": "不可用",
    },
    "en_US": {
        "rtc_title": "RTC CLOCK", "chip_title": "CHIP ID", "temp_title": "CHIP TEMP",
        "load_title": "MEMORY & CPU", "heap_title": "HEAP", "page_title": "PAGE",
        "mmz_title": "MMZ", "cpu_title": "CPU USAGE",
        "sensor_tag": "ON-CHIP SENSOR", "reading": "Reading...", "partial": "Some information is unavailable",
        "monitoring": "Live monitoring", "rtc_unavailable": "RTC unavailable", "syncing": "Synchronizing RTC",
        "sensor_unavailable": "Sensor unavailable", "live_temp": "Live temperature",
        "sync_failed": "RTC synchronization failed", "unavailable": "Unavailable",
    },
}


def _t(key):
    return _TEXT[i18n.language()].get(key, key)


class SystemInfoUI:
    """LVGL-only dashboard; hardware access stays in SystemInfoDemo."""

    def __init__(self, screen, layout, content):
        self.layout = layout
        self._large_fonts = []
        self._values = {}
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
        inner_w = max(2, cw - margin * 2)
        inner_h = max(2, ch - margin * 2)
        stacked = cw < 640 or ch < 320
        if stacked:
            left_w = right_w = inner_w
            clock_h, chip_h, temp_h, load_h = 180, 120, 170, 220
            clock_y = margin
            chip_y = clock_y + clock_h + gap
            temp_y = chip_y + chip_h + gap
            load_y = temp_y + temp_h + gap
            right_x = margin
            self.root.add_flag(lv.obj.FLAG.SCROLLABLE)
            self.root.set_scroll_dir(lv.DIR.VER)
        else:
            usable_w = inner_w - gap
            usable_h = inner_h - gap
            left_w = usable_w * 58 // 100
            right_w = usable_w - left_w
            clock_h = usable_h * 64 // 100
            chip_h = usable_h - clock_h
            temp_h = usable_h * 42 // 100
            load_h = usable_h - temp_h
            clock_y = temp_y = margin
            chip_y = margin + clock_h + gap
            load_y = margin + temp_h + gap
            right_x = margin + left_w + gap
        self.clock_card = self._make_card(
            margin, clock_y, left_w, clock_h, 0x121827, 0x0A84FF)
        self.chip_card = self._make_card(
            margin, chip_y, left_w, chip_h, 0x101722, 0x30D158)
        self.temp_card = self._make_card(
            right_x, temp_y, right_w, temp_h, 0x171622, 0xFF9F0A)
        self.load_card = self._make_card(
            right_x, load_y, right_w, load_h, 0x101923, 0x5AC8FA)

        title_font = (gui.font_cn if i18n.is_chinese() else gui.font_en) or \
            gui.font_cn or gui.font_en
        body_font = gui.font_cn if gui.font_cn else gui.font_en
        time_font = self._create_font(max(22, min(
            layout.clamp_px(52, 24, 86), clock_h * 29 // 100)))
        temp_font = self._create_font(max(24, min(
            layout.clamp_px(58, 28, 92), right_w * 22 // 100,
            temp_h * 30 // 100)))
        inset = layout.clamp_px(18, 10, 32)

        clock_title = self._label(self.clock_card, _t("rtc_title"), 0x5AC8FA,
                                  title_font)
        clock_title.set_pos(inset, layout.clamp_px(16, 8, 28))
        self.time_label = self._label(self.clock_card, "--:--:--",
                                      0xFFFFFF, time_font)
        self.time_label.align(lv.ALIGN.CENTER, 0,
                              -layout.clamp_px(8, 2, 16))
        self.date_label = self._label(self.clock_card, "---- -- --",
                                      0xB8C1D1, body_font)
        self.date_label.align(lv.ALIGN.BOTTOM_LEFT, inset,
                              -layout.clamp_px(16, 8, 28))
        self.weekday_label = self._label(self.clock_card, "--", 0x5AC8FA,
                                         body_font)
        self.weekday_label.align(lv.ALIGN.BOTTOM_RIGHT, -inset,
                                 -layout.clamp_px(16, 8, 28))

        if left_w < 360:
            self.date_label.align(lv.ALIGN.BOTTOM_LEFT, inset, -layout.line_h - 8)
            self.weekday_label.align(lv.ALIGN.BOTTOM_LEFT, inset, -8)

        chip_title = self._label(self.chip_card, _t("chip_title"), 0x64D98B,
                                 title_font)
        chip_title.set_pos(inset, layout.clamp_px(10, 5, 18))
        self.chip_line1 = self._label(self.chip_card, _t("reading"),
                                      0xFFFFFF, body_font)
        self.chip_line1.align(lv.ALIGN.CENTER, 0,
                              -layout.clamp_px(7, 3, 12))
        self.chip_line2 = self._label(self.chip_card, "", 0xAEB8C8,
                                      gui.font_en)
        self.chip_line2.align(lv.ALIGN.CENTER, 0,
                              layout.clamp_px(15, 9, 24))
        for label in (self.chip_line1, self.chip_line2):
            label.set_width(left_w - inset * 2)
            label.set_long_mode(lv.label.LONG.DOT)
            label.set_style_text_align(lv.TEXT_ALIGN.CENTER, lv.PART.MAIN)

        temp_title = self._label(self.temp_card, _t("temp_title"), 0xFFB340,
                                 title_font)
        temp_title.set_pos(inset, layout.clamp_px(16, 8, 28))
        sensor_tag = self._label(self.temp_card, _t("sensor_tag"), 0x756A80,
                                 title_font)
        sensor_tag.align(lv.ALIGN.TOP_RIGHT, -inset,
                         layout.clamp_px(16, 8, 28))
        if right_w < 280:
            sensor_tag.add_flag(lv.obj.FLAG.HIDDEN)
        self.temp_label = self._label(self.temp_card, "--.- C", 0xFFFFFF,
                                      temp_font)
        self.temp_label.align(lv.ALIGN.CENTER, 0,
                              -layout.clamp_px(8, 4, 16))
        self.temp_state = self._label(self.temp_card, _t("reading"), 0x8E8E93,
                                      body_font)
        self.temp_state.align(lv.ALIGN.CENTER, 0,
                              layout.clamp_px(28, 16, 44))
        self.temp_bar = lv.bar(self.temp_card)
        self.temp_bar.set_size(
            max(30, right_w - inset * 2), layout.clamp_px(7, 4, 11))
        self.temp_bar.align(lv.ALIGN.BOTTOM_MID, 0,
                            -layout.clamp_px(14, 8, 24))
        self.temp_bar.set_range(0, 100)
        self.temp_bar.set_value(0, lv.ANIM.OFF)
        self.temp_bar.set_style_bg_color(gui.lv_color(0x30313A),
                                         lv.PART.MAIN)
        self.temp_bar.set_style_bg_opa(255, lv.PART.MAIN)
        self.temp_bar.set_style_radius(999, lv.PART.MAIN)
        self.temp_bar.set_style_bg_color(gui.lv_color(0xFF9F0A),
                                         lv.PART.INDICATOR)
        self.temp_bar.set_style_bg_opa(255, lv.PART.INDICATOR)
        self.temp_bar.set_style_radius(999, lv.PART.INDICATOR)

        load_title = self._label(self.load_card, _t("load_title"), 0x5AC8FA,
                                 title_font)
        load_title.set_pos(inset, layout.clamp_px(10, 6, 18))
        metric_top = min(layout.clamp_px(38, 30, 54),
                         max(20, load_h // 5))
        metric_h = max(14, (load_h - metric_top) // 4)
        bar_h = 2 if load_h < 90 else layout.clamp_px(6, 4, 10)
        bar_w = max(30, right_w - inset * 2)
        # Keep every metric text line strictly above its bar.  The row height
        # bounds the text height (1.3x font size covers the FreeType line
        # height), so shrink the metric font instead of letting labels and
        # bars overlap on tight layouts.
        text_gap = 2
        row_gap = layout.clamp_px(4, 2, 8)
        max_text_h = max(10, metric_h - bar_h - text_gap - row_gap)
        metric_font_size = max(10, min(layout.font_size,
                                       max_text_h * 10 // 13))
        if metric_font_size < layout.font_size:
            metric_font = self._create_font(metric_font_size)
        else:
            metric_font = body_font
        text_h = metric_font_size * 13 // 10
        bar_offset = max(10, min(text_h + text_gap,
                                 metric_h - bar_h - row_gap))

        self.heap_label, self.heap_bar = self._make_metric_row(
            metric_top, _t("heap_title"), inset, bar_w, bar_h, bar_offset,
            metric_font, text_h, 0x0A84FF)
        self.page_label, self.page_bar = self._make_metric_row(
            metric_top + metric_h, _t("page_title"), inset, bar_w, bar_h,
            bar_offset, metric_font, text_h, 0xBF5AF2)
        self.mmz_label, self.mmz_bar = self._make_metric_row(
            metric_top + metric_h * 2, _t("mmz_title"), inset, bar_w, bar_h,
            bar_offset, metric_font, text_h, 0xFF9F0A)
        self.cpu_label, self.cpu_bar = self._make_metric_row(
            metric_top + metric_h * 3, _t("cpu_title"), inset, bar_w, bar_h,
            bar_offset, metric_font, text_h, 0x30D158)

    def _make_card(self, x, y, w, h, color, accent):
        card = lv.obj(self.root)
        card.set_size(w, h)
        card.set_pos(x, y)
        card.set_style_bg_color(gui.lv_color(color), lv.PART.MAIN)
        card.set_style_bg_opa(255, lv.PART.MAIN)
        card.set_style_border_color(gui.lv_color(accent), lv.PART.MAIN)
        card.set_style_border_opa(75, lv.PART.MAIN)
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

    def _metric_value_label(self, parent, x, y, width, height, text, font):
        label = self._label(parent, text, 0xFFFFFF, font)
        label.set_size(width, height)
        label.set_pos(x, y)
        try:
            label.set_long_mode(lv.label.LONG.DOT)
            label.set_style_text_align(lv.TEXT_ALIGN.RIGHT, lv.PART.MAIN)
        except Exception:
            pass
        return label

    def _make_metric_row(self, y, title, inset, width, bar_h, bar_offset,
                         font, text_h, color):
        title_label = self._label(self.load_card, title, 0x9BA9BC, font)
        title_width = max(28, width * 35 // 100)
        title_label.set_size(title_width, text_h)
        try:
            title_label.set_long_mode(lv.label.LONG.DOT)
        except Exception:
            pass
        title_label.set_pos(inset, y)
        value_label = self._metric_value_label(
            self.load_card, inset + title_width, y,
            max(1, width - title_width), text_h, _t("reading"), font)
        bar = self._make_metric_bar(
            self.load_card, inset, y + bar_offset, width, bar_h, color)
        return value_label, bar

    @staticmethod
    def _make_metric_bar(parent, x, y, width, height, color):
        bar = lv.bar(parent)
        bar.set_size(width, height)
        bar.set_pos(x, y)
        bar.set_range(0, 100)
        bar.set_value(0, lv.ANIM.OFF)
        bar.set_style_bg_color(gui.lv_color(0x283240), lv.PART.MAIN)
        bar.set_style_bg_opa(255, lv.PART.MAIN)
        bar.set_style_radius(999, lv.PART.MAIN)
        bar.set_style_bg_color(gui.lv_color(color), lv.PART.INDICATOR)
        bar.set_style_bg_opa(255, lv.PART.INDICATOR)
        bar.set_style_radius(999, lv.PART.INDICATOR)
        return bar

    def _create_font(self, size):
        for path in gui.CN_FONT_CANDIDATES:
            if not config.file_exists(path):
                continue
            try:
                font = lv.freetype_font_create(path, size, 0)
                if font is not None:
                    self._large_fonts.append(font)
                    return font
            except Exception:
                pass
        return gui.font_cn if gui.font_cn else gui.font_en

    def _set_text(self, key, label, value):
        if self._values.get(key) == value:
            return
        self._values[key] = value
        label.set_text(value)

    def handle_update(self, payload):
        if not isinstance(payload, (tuple, list)) or len(payload) < 17 or \
                payload[0] != "system_info":
            return
        unused_kind, time_text, date_text, weekday, temp_value, temp_text, \
            temp_state, chip_line1, chip_line2, heap_value, heap_text, \
            page_value, page_text, mmz_value, mmz_text, cpu_value, \
            cpu_text = payload
        self._set_text("time", self.time_label, time_text)
        self._set_text("date", self.date_label, date_text)
        self._set_text("weekday", self.weekday_label, weekday)
        self._set_text("temp", self.temp_label, temp_text)
        self._set_text("temp_state", self.temp_state, temp_state)
        self._set_text("chip1", self.chip_line1, chip_line1)
        self._set_text("chip2", self.chip_line2, chip_line2)
        self._set_text("heap", self.heap_label, heap_text)
        self._set_text("page", self.page_label, page_text)
        self._set_text("mmz", self.mmz_label, mmz_text)
        self._set_text("cpu", self.cpu_label, cpu_text)

        if temp_value is None:
            value = 0
            color = config.THEME_SUBTEXT
        else:
            value = max(0, min(100, int(temp_value)))
            color = config.THEME_ORANGE
        bar_state = (value, color)
        if self._values.get("temp_bar") != bar_state:
            self._values["temp_bar"] = bar_state
            self.temp_bar.set_value(value, lv.ANIM.OFF)
            self.temp_bar.set_style_bg_color(gui.lv_color(color),
                                             lv.PART.INDICATOR)
            self.temp_state.set_style_text_color(gui.lv_color(color),
                                                 lv.PART.MAIN)

        self._set_metric("heap_bar", self.heap_bar, self.heap_label,
                         heap_value, 0x0A84FF)
        self._set_metric("page_bar", self.page_bar, self.page_label,
                         page_value, 0xBF5AF2)
        self._set_metric("mmz_bar", self.mmz_bar, self.mmz_label,
                         mmz_value, 0xFF9F0A)
        self._set_metric("cpu_bar", self.cpu_bar, self.cpu_label,
                         cpu_value, 0x30D158)

    def _set_metric(self, key, bar, label, value, normal_color):
        if value is None:
            meter_value = 0
            color = config.THEME_SUBTEXT
        else:
            meter_value = max(0, min(100, int(value)))
            if meter_value >= 90:
                color = config.THEME_RED
            elif meter_value >= 75:
                color = config.THEME_ORANGE
            else:
                color = normal_color
        state = (meter_value, color)
        if self._values.get(key) == state:
            return
        self._values[key] = state
        bar.set_value(meter_value, lv.ANIM.OFF)
        bar.set_style_bg_color(gui.lv_color(color), lv.PART.INDICATOR)
        label.set_style_text_color(gui.lv_color(color), lv.PART.MAIN)

    def clean(self):
        if self.root is not None:
            self.root.delete()
            self.root = None
        for font in self._large_fonts:
            try:
                font.freetype_font_del()
            except Exception:
                pass
        self._large_fonts = []
        self._values = {}


class SystemInfoDemo(Application):
    name = "系统信息"
    ui_show_stats = False

    def __init__(self):
        super().__init__()
        self._rtc = None
        self._wlan = None
        self._chip_lines = (_t("unavailable"), "")
        self._temperature = None
        self._heap_percent = None
        self._heap_text = _t("reading")
        self._page_percent = None
        self._page_text = _t("reading")
        self._mmz_percent = None
        self._mmz_text = _t("reading")
        self._cpu_percent = None
        self._cpu_text = _t("reading")
        self._last_poll = None
        self._last_temp_poll = None
        self._last_resource_poll = None
        self._last_network_check = None
        self._last_payload = None
        self._last_status = None
        self._chip_ok = False
        self._temp_error_reported = False
        self._heap_error_reported = False
        self._page_error_reported = False
        self._mmz_error_reported = False
        self._cpu_error_reported = False
        self._rtc_error_reported = False
        self._network_connected = False
        # NTP runs once per connection. "pending" leaves one UI cycle for the
        # existing RTC value before the worker performs the blocking sync.
        self._ntp_state = "idle"

    @staticmethod
    def create_app_ui(screen, layout, content):
        return SystemInfoUI(screen, layout, content)

    @staticmethod
    def _format_chip_id(raw):
        encoded = binascii.hexlify(raw).decode().upper()
        groups = [encoded[i:i + 8] for i in range(0, len(encoded), 8)]
        split = max(1, (len(groups) + 1) // 2)
        return " ".join(groups[:split]), " ".join(groups[split:])

    def start(self):
        super().start()
        errors = 0
        try:
            self._chip_lines = self._format_chip_id(machine.chipid())
            self._chip_ok = True
        except Exception as e:
            errors += 1
            print("SystemInfo: chip ID read failed:", e)
        try:
            self._rtc = machine.RTC()
        except Exception as e:
            errors += 1
            print("SystemInfo: RTC open failed:", e)
        try:
            import network
            wlan_type = getattr(network, "WLAN", None)
            self._wlan = wlan_type(0) if wlan_type else None
        except Exception:
            self._wlan = None
        self._publish_status(_t("partial") if errors else _t("monitoring"),
                             config.THEME_ORANGE if errors
                             else config.THEME_GREEN)

    def _publish_status(self, text, color):
        value = (text, color)
        if value == self._last_status:
            return
        self._last_status = value
        config.demo_status_text = text
        config.demo_status_color = color

    def _read_temperature(self, now):
        if self._last_temp_poll is not None and time.ticks_diff(
                now, self._last_temp_poll) < TEMP_POLL_MS:
            return self._temperature is not None
        self._last_temp_poll = now
        try:
            self._temperature = machine.temperature()
            self._temp_error_reported = False
            return True
        except Exception as e:
            self._temperature = None
            if not self._temp_error_reported:
                print("SystemInfo: temperature read failed:", e)
                self._temp_error_reported = True
            return False

    @staticmethod
    def _format_memory(percent, used, total):
        if total >= 1024 * 1024:
            divisor = 1024 * 1024
            unit = "MB"
        elif total >= 1024:
            divisor = 1024
            unit = "KB"
        else:
            divisor = 1
            unit = "B"
        used_value = (used + divisor // 2) // divisor
        total_value = (total + divisor // 2) // divisor
        return "%d%%  %d/%d %s" % (
            percent, used_value, total_value, unit)

    def _read_memory_metric(self, reader, gc_fallback=False):
        try:
            total, used, _unused_free = reader()
        except Exception:
            if not gc_fallback:
                raise
            used = int(gc.mem_alloc())
            total = used + int(gc.mem_free())
        total = int(total)
        used = int(used)
        if (total <= 0 or used < 0) and gc_fallback:
            used = int(gc.mem_alloc())
            total = used + int(gc.mem_free())
        if total <= 0 or used < 0:
            raise ValueError("invalid memory statistics")
        used = max(0, min(total, used))
        percent = max(0, min(100, int(used * 100 // total)))
        return percent, self._format_memory(percent, used, total)

    def _read_resources(self, now):
        if self._last_resource_poll is not None and time.ticks_diff(
                now, self._last_resource_poll) < RESOURCE_POLL_MS:
            return self._heap_percent is not None, \
                self._page_percent is not None, \
                self._mmz_percent is not None, \
                self._cpu_percent is not None
        self._last_resource_poll = now

        try:
            self._heap_percent, self._heap_text = \
                self._read_memory_metric(gc.sys_heap, True)
            self._heap_error_reported = False
        except Exception as e:
            self._heap_percent = None
            self._heap_text = _t("unavailable")
            if not self._heap_error_reported:
                print("SystemInfo: heap usage read failed:", e)
                self._heap_error_reported = True

        try:
            self._page_percent, self._page_text = \
                self._read_memory_metric(gc.sys_page)
            self._page_error_reported = False
        except Exception as e:
            self._page_percent = None
            self._page_text = _t("unavailable")
            if not self._page_error_reported:
                print("SystemInfo: page usage read failed:", e)
                self._page_error_reported = True

        try:
            self._mmz_percent, self._mmz_text = \
                self._read_memory_metric(gc.sys_mmz)
            self._mmz_error_reported = False
        except Exception as e:
            self._mmz_percent = None
            self._mmz_text = _t("unavailable")
            if not self._mmz_error_reported:
                print("SystemInfo: MMZ usage read failed:", e)
                self._mmz_error_reported = True

        try:
            usage = int(os.cpu_usage())
            if usage < 0:
                raise ValueError("invalid CPU usage")
            self._cpu_percent = max(0, min(100, usage))
            self._cpu_text = "%d%%" % self._cpu_percent
            self._cpu_error_reported = False
        except Exception as e:
            self._cpu_percent = None
            self._cpu_text = _t("unavailable")
            if not self._cpu_error_reported:
                print("SystemInfo: CPU usage read failed:", e)
                self._cpu_error_reported = True

        return self._heap_percent is not None, \
            self._page_percent is not None, \
            self._mmz_percent is not None, \
            self._cpu_percent is not None

    def _read_clock(self):
        if self._rtc is None:
            return "--:--:--", "---- -- --", _t("rtc_unavailable"), False
        try:
            dt = self._rtc.datetime()
            self._rtc_error_reported = False
            weekday = int(dt[3])
            weekdays = WEEKDAYS_ZH if i18n.is_chinese() else WEEKDAYS_EN
            weekday_text = weekdays[weekday] if 0 <= weekday < 7 else "--"
            return ("%02d:%02d:%02d" % (dt[4], dt[5], dt[6]),
                    "%04d-%02d-%02d" % (dt[0], dt[1], dt[2]),
                    weekday_text, True)
        except Exception as e:
            if not self._rtc_error_reported:
                print("SystemInfo: RTC read failed:", e)
                self._rtc_error_reported = True
            return "--:--:--", "---- -- --", _t("rtc_unavailable"), False

    def _has_network(self):
        if self._wlan is None:
            return False
        try:
            return self._wlan.isconnected() and \
                self._wlan.ifconfig()[0] != "0.0.0.0"
        except Exception:
            return False

    def _sync_rtc(self):
        if self._rtc is None:
            self._ntp_state = "failed"
            return False
        try:
            if self._rtc.ntp_sync():
                self._ntp_state = "done"
                print("SystemInfo: RTC synchronized by NTP")
                return True
            self._ntp_state = "failed"
            print("SystemInfo: RTC NTP synchronization failed")
        except Exception as e:
            self._ntp_state = "failed"
            print("SystemInfo: RTC NTP synchronization failed:", e)
        return False

    def _rtc_sync_step(self, now):
        if self._last_network_check is None or time.ticks_diff(
                now, self._last_network_check) >= NETWORK_CHECK_MS:
            self._last_network_check = now
            self._network_connected = self._has_network()

        if not self._network_connected:
            self._ntp_state = "idle"
            return False
        if self._ntp_state == "idle":
            self._ntp_state = "pending"
            self._publish_status(_t("syncing"), config.THEME_ORANGE)
            return False
        if self._ntp_state == "pending":
            return self._sync_rtc()
        return False

    def run_once(self):
        now = time.ticks_ms()
        if self._last_poll is not None and time.ticks_diff(
                now, self._last_poll) < POLL_MS:
            return None
        self._last_poll = now

        temp_ok = self._read_temperature(now)
        heap_ok, page_ok, mmz_ok, cpu_ok = self._read_resources(now)
        time_text, date_text, weekday, rtc_ok = self._read_clock()
        if self._rtc_sync_step(now):
            # Publish the new RTC value in the same worker iteration in which
            # NTP completes, without waiting for the next 200 ms poll.
            time_text, date_text, weekday, rtc_ok = self._read_clock()

        if self._temperature is None:
            temp_text = "--.- C"
            temp_state = _t("sensor_unavailable")
        else:
            temp_text = "%.1f C" % self._temperature
            temp_state = _t("live_temp")

        payload = ("system_info", time_text, date_text, weekday,
                   self._temperature, temp_text, temp_state,
                   self._chip_lines[0], self._chip_lines[1],
                   self._heap_percent, self._heap_text,
                   self._page_percent, self._page_text,
                   self._mmz_percent, self._mmz_text,
                   self._cpu_percent, self._cpu_text)
        if payload != self._last_payload:
            self._last_payload = payload
            config.demo_ui_request = ("app_ui", payload)

        if not (self._chip_ok and temp_ok and rtc_ok and
                heap_ok and page_ok and mmz_ok and cpu_ok):
            self._publish_status(_t("partial"), config.THEME_ORANGE)
        elif self._ntp_state == "pending":
            self._publish_status(_t("syncing"), config.THEME_ORANGE)
        elif self._ntp_state == "failed":
            self._publish_status(_t("sync_failed"), config.THEME_ORANGE)
        else:
            self._publish_status(_t("monitoring"), config.THEME_GREEN)
        return None

    def _release_owned_resources(self):
        self._rtc = None
        self._wlan = None
        self._ntp_state = "idle"
        self._heap_percent = None
        self._page_percent = None
        self._mmz_percent = None
        self._cpu_percent = None
        self._last_payload = None
