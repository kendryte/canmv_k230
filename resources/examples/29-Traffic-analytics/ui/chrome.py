import config
from helper import format_duration
from ui.theme import Colors


class Header:
    def __init__(self, theme, rect):
        self.theme = theme
        self.rect = rect

    def render(self, p, stats, lane_count, right_top, right_bottom=None,
               accent=Colors.ACCENT):
        t = self.theme
        x, y, w, h = self.rect
        pad = t.px(10)
        p.rect(x, y, w, h, Colors.CHROME, fill=True)
        p.hline(x, y + h - t.px(2), w, accent, t.px(2))
        p.vline(x + pad - t.px(4), y + t.px(7), h - t.px(16), accent, t.px(3))

        title_size = t.font(20)
        p.text(x + pad + t.px(4), y + t.px(4), title_size, config.APP_NAME, Colors.WHITE)
        p.text(x + pad + t.px(4), y + t.px(26), t.font(11),
               "{} | {} lane(s) | K230".format(config.MODEL_NAME, lane_count),
               Colors.TEXT_FAINT)

        right = x + w - pad
        p.text_right(right, y + t.px(4), t.font(16), right_top, Colors.WHITE)
        if right_bottom:
            p.text_right(right, y + t.px(26), t.font(11), right_bottom, Colors.TEXT_DIM)

        # Chips fill whatever room is left between the title and the clock.
        limit = right - max(p.text_width(t.font(16), right_top),
                            p.text_width(t.font(11), right_bottom or "")) - t.px(16)
        chip_x = x + pad + t.px(4) + p.text_width(title_size, config.APP_NAME) + t.px(24)
        chip_y = y + (h - t.px(26)) // 2
        chips = [("DENSITY", stats.density, Colors.DENSITY.get(stats.density, Colors.WHITE)),
                 ("TRAFFIC", stats.congestion,
                  Colors.CONGESTION.get(stats.congestion, Colors.WHITE))]
        if stats.incidents_now:
            chips.append(("INCIDENT", str(stats.incidents_now), Colors.RED))
        elif stats.stopped_now:
            chips.append(("STOPPED", str(stats.stopped_now), Colors.ORANGE))
        for label, value, color in chips:
            width = self._chip_width(p, label, value)
            if chip_x + width > limit:
                break
            self._chip(p, chip_x, chip_y, label, value, color)
            chip_x += width + t.px(8)

    def _chip_width(self, p, label, value):
        t = self.theme
        return (t.px(10) + p.text_width(t.font(10), label) + t.px(6)
                + p.text_width(t.font(13), value) + t.px(10))

    def _chip(self, p, x, y, label, value, color):
        t = self.theme
        label_size = t.font(10)
        value_size = t.font(13)
        w = self._chip_width(p, label, value)
        height = t.px(26)
        p.rect(x, y, w, height, Colors.TILE_BG, fill=True)
        p.vline(x, y, height, color, t.px(3))
        p.text(x + t.px(10), y + t.px(8), label_size, label, Colors.TEXT_FAINT)
        p.text(x + t.px(10) + p.text_width(label_size, label) + t.px(6), y + t.px(5),
               value_size, value, color)
        return w


class Footer:
    def __init__(self, theme, rect):
        self.theme = theme
        self.rect = rect

    def render(self, p, buttons, stats, now_ms, message=None, accent=Colors.ACCENT):
        t = self.theme
        x, y, w, h = self.rect
        p.rect(x, y, w, h, Colors.CHROME, fill=True)
        p.hline(x, y, w, accent, t.px(2))
        self._status(p, stats, now_ms, message)
        for button in buttons:
            button.draw(p)

    def _status(self, p, stats, now_ms, message):
        t = self.theme
        x, y, _, h = self.rect
        pad = t.px(10)
        size = t.font(14)
        text_y = y + (h - size) // 2

        if stats.alerts:
            # Rotate through the alerts so three at once still get seen.
            index = (now_ms // config.ALERT_TICKER_MS) % len(stats.alerts)
            blink = (now_ms // 400) % 2 == 0
            text = "! " + stats.alerts[index]
            width = p.text_width(size, text) + t.px(20)
            p.rect(pad, y + t.px(8), width, h - t.px(16),
                   Colors.RED if blink else (150, 26, 26), fill=True)
            p.text(pad + t.px(10), text_y, size, text, Colors.WHITE)
            return

        if message:
            p.text(pad, text_y, size, message, Colors.GREEN)
            return

        p.text(pad, text_y, size, "Uptime {}  |  {} passed  |  {} in / {} out".format(
            format_duration(stats.elapsed_ms), stats.passed_total,
            stats.count_in, stats.count_out), Colors.TEXT_DIM)
