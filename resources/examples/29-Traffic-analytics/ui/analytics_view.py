import time

import config
from helper import display_timestamp
from ui.chrome import Footer, Header
from ui.dashboard import DashboardPanel
from ui.painter import Painter
from ui.theme import Colors
from ui.widgets import Button

ACTION_SETUP = "setup"
ACTION_RESET = "reset"
ACTION_REPORT = "report"


class AnalyticsView:
    def __init__(self, theme, layout, scene_painter, scene):
        self.theme = theme
        self.layout = layout
        self.scene = scene
        self.scene_painter = scene_painter
        self.header = Header(theme, layout.header)
        self.footer = Footer(theme, layout.footer)
        self.panel = DashboardPanel(theme, layout.panel)
        self.buttons = self._build_buttons()
        self._toast_text = None
        self._toast_until = 0

    def _build_buttons(self):
        t = self.theme
        fx, fy, fw, fh = self.layout.footer
        height = fh - t.px(14)
        y = fy + t.px(7)
        gap = t.px(8)
        specs = ((ACTION_REPORT, "SAVE REPORT", t.px(140), Colors.GREEN, True),
                 (ACTION_RESET, "RESET", t.px(80), Colors.ORANGE, False),
                 (ACTION_SETUP, "SETUP", t.px(80), Colors.CYAN, False))
        buttons = []
        right = fx + fw - t.px(10)
        for key, label, width, color, filled in specs:
            right -= width
            buttons.append(Button(key, label, (right, y, width, height), color, filled))
            right -= gap
        return buttons

    def hit_test(self, point):
        if point is None:
            return None
        for button in self.buttons:
            if button.is_active() and button.contains(point):
                return button.key
        return None

    def toast(self, text):
        self._toast_text = text
        self._toast_until = time.ticks_add(time.ticks_ms(), config.TOAST_MS)

    def render(self, osd, tracks, stats, now_ms):
        t = self.theme
        osd.clear()
        stage = Painter(osd, t, origin=self.layout.stage_origin,
                        bounds=self.layout.stage_size)
        self.scene_painter.draw_lanes(stage, self.scene.lanes, thickness=t.px(2))
        self.scene_painter.draw_count_line(stage, self.scene.count_line,
                                           self.scene.in_side, show_direction=False)
        self.scene_painter.draw_tracks(stage, tracks, now_ms)
        self._draw_speed_sign(stage)

        chrome = Painter(osd, t)
        self.panel.render(chrome, stats, self.scene)
        self.header.render(chrome, stats, len(self.scene.lanes),
                           display_timestamp(), "FPS {:.1f}".format(stats.fps))
        self.footer.render(chrome, self.buttons, stats, now_ms, self._message(now_ms))
        self._frame_stage(chrome)

    def render_busy(self, osd, message):
        t = self.theme
        p = Painter(osd, t)
        w, h = t.px(340), t.px(86)
        sx, sy, sw, sh = self.layout.stage
        x, y = sx + (sw - w) // 2, sy + (sh - h) // 2
        p.panel(x, y, w, h, bg=Colors.CHROME, border=Colors.YELLOW)
        p.text_centered(x + w // 2, y + t.px(16), t.font(22), message, Colors.YELLOW)
        p.text_centered(x + w // 2, y + t.px(52), t.font(13),
                        "Capturing scene and building the heatmap...", Colors.TEXT_DIM)

    def _frame_stage(self, p):
        t = self.theme
        x, y, w, h = self.layout.stage
        p.rect(x - t.px(1), y - t.px(1), w + t.px(2), h + t.px(2), Colors.BORDER, thickness=1)

    def _draw_speed_sign(self, p):
        t = self.theme
        radius = t.px(22)
        cx = self.layout.stage[2] - radius - t.px(10)
        cy = radius + t.px(10)
        p.circle(cx, cy, radius, Colors.WHITE, fill=True)
        p.circle(cx, cy, radius, Colors.RED, thickness=t.px(4))
        size = t.font(17)
        p.text_centered(cx, cy - size // 2 - t.px(1), size,
                        "{:.0f}".format(self.scene.speed_limit_kmh), Colors.BLACK)

    def _message(self, now_ms):
        if self._toast_text is None:
            return None
        if time.ticks_diff(self._toast_until, now_ms) <= 0:
            self._toast_text = None
            return None
        return self._toast_text
