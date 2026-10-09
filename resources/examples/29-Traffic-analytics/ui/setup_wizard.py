import time

import config
from analytics import scene_config
from analytics.scene_config import SceneConfig
from helper import exitpoint
from ui.painter import Painter
from ui.setup_steps import (ACTION_BACK, ACTION_FINISH, ACTION_LOAD, ACTION_NEXT,
                            LaneStep, LineStep, NumberStep, ReviewStep, WelcomeStep)
from ui.theme import Colors
from ui.widgets import Button

STEP_NAMES = ("Calibration line", "Real distance", "Speed limit",
              "Counting line", "Lanes", "Review")


class SetupWizard:
    POLL_SLEEP_MS = 10

    def __init__(self, camera, touch, theme, layout, scene_painter):
        self.camera = camera
        self.touch = touch
        self.theme = theme
        self.layout = layout
        self.scene_painter = scene_painter
        self.scene = SceneConfig(layout.stage_size)
        self.saved_scene = None
        self.stage = None            # Painter for scene geometry
        self.chrome = None           # Painter for widgets and bars
        self._toast_text = None
        self._toast_color = Colors.GREEN
        self._toast_until = 0

    # ------------------------------------------------------------ public --
    def run(self):
        self.saved_scene = scene_config.recall(self.layout.stage_size)
        steps = self._build_steps()
        index = 0
        step = steps[index]
        step.enter()
        dirty = True
        while True:
            exitpoint()
            self.touch.poll()
            tap = self.touch.take_tap()
            if tap is not None:
                action = step.handle_tap(tap)
                if action == ACTION_FINISH:
                    scene_config.remember(self.scene)
                    return self.scene
                if action == ACTION_LOAD and self.saved_scene is not None:
                    self.scene = self.saved_scene
                    index = len(steps) - 1
                elif action == ACTION_NEXT:
                    index = min(index + 1, len(steps) - 1)
                elif action == ACTION_BACK:
                    index = max(0, index - 1)
                if action in (ACTION_NEXT, ACTION_BACK, ACTION_LOAD):
                    step = steps[index]
                    step.enter()
                step.refresh()
                dirty = True

            if self._toast_text is not None and time.ticks_diff(self._toast_until, time.ticks_ms()) <= 0:
                self._toast_text = None
                dirty = True
            if dirty:
                self._render(step, index, len(steps) - 1)
                dirty = False
            time.sleep_ms(self.POLL_SLEEP_MS)

    def start_new_scene(self):
        self.scene = SceneConfig(self.layout.stage_size)

    def toast(self, text, color=Colors.GREEN):
        self._toast_text = text
        self._toast_color = color
        self._toast_until = time.ticks_add(time.ticks_ms(), config.TOAST_MS)

    def toolbar(self, specs):
        """specs: [(key, label, style)] with style None / 'primary' / 'danger'."""
        t = self.theme
        fx, fy, fw, fh = self.layout.footer
        count = len(specs)
        pad, gap = t.px(10), t.px(8)
        height = fh - t.px(14)
        y = fy + t.px(7)
        width = min(t.px(170), (fw - 2 * pad - (count - 1) * gap) // count)
        x = fx + fw - pad - (count * width + (count - 1) * gap)
        styles = {"primary": Colors.GREEN, "danger": Colors.RED}
        buttons = []
        for key, label, style in specs:
            buttons.append(Button(key, label, (x, y, width, height),
                                  styles.get(style, Colors.CYAN), filled=(style == "primary")))
            x += width + gap
        return buttons

    def draw_context(self, layers):
        t = self.theme
        scene = self.scene
        if "lanes" in layers:
            self.scene_painter.draw_lanes(self.stage, scene.lanes, thickness=t.px(2))
        if "calib_line" in layers and len(scene.calib_line) == 2:
            self.scene_painter.draw_calibration_line(self.stage, scene.calib_line,
                                                     scene.calib_meters)
        if "count_line" in layers and len(scene.count_line) == 2:
            self.scene_painter.draw_count_line(self.stage, scene.count_line, scene.in_side)

    def _build_steps(self):
        return [
            WelcomeStep(self),
            LineStep(self, "calib_line", "CALIBRATION LINE",
                     "Tap 2 points on the road whose real distance you know."),
            NumberStep(self, "calib_meters", "REAL DISTANCE", "Enter the real length of that line",
                       "m", config.CALIB_MIN_M, config.CALIB_MAX_M, context=("calib_line",)),
            NumberStep(self, "speed_limit_kmh", "SPEED LIMIT", "Enter the road speed limit",
                       "km/h", config.SPEED_LIMIT_MIN, config.SPEED_LIMIT_MAX),
            LineStep(self, "count_line", "COUNTING LINE",
                     "Tap 2 points to draw the counting line across the road.", directional=True,
                     context=("lanes",)),
            LaneStep(self),
            ReviewStep(self),
        ]

    def _render(self, step, index, total):
        osd = self.camera.osd_img
        osd.clear()
        self.stage = Painter(osd, self.theme, origin=self.layout.stage_origin,
                             bounds=self.layout.stage_size)
        self.chrome = Painter(osd, self.theme)
        step.draw()
        self._draw_banner(step, index, total)
        self._draw_panel(step, index)
        self._draw_footer(step)
        self._frame_stage()
        self.camera.show()

    def _frame_stage(self):
        t = self.theme
        x, y, w, h = self.layout.stage
        self.chrome.rect(x - t.px(1), y - t.px(1), w + t.px(2), h + t.px(2),
                         Colors.ACCENT, thickness=1)

    def _draw_banner(self, step, index, total):
        t = self.theme
        p = self.chrome
        x, y, w, h = self.layout.header
        p.rect(x, y, w, h, Colors.CHROME, fill=True)
        p.hline(x, y + h - t.px(2), w, Colors.ACCENT, t.px(2))
        cursor = t.px(10)
        if step.numbered:
            pill_w, _ = p.tag(cursor, y + t.px(5), "STEP {}/{}".format(index, total),
                              Colors.CYAN, Colors.BLACK, t.font(15))
            cursor += pill_w + t.px(10)
        p.text(cursor, y + t.px(4), t.font(18), step.title, Colors.YELLOW)
        p.text(t.px(10), y + t.px(26), t.font(12), step.hint(), Colors.WHITE)

    def _draw_panel(self, step, index):
        t = self.theme
        p = self.chrome
        x0, y0, w, h = self.layout.panel
        pad = t.px(8)
        p.rect(x0, y0, w, h, Colors.PANEL, fill=True)
        p.vline(x0 + w - t.px(2), y0, h, Colors.BORDER, t.px(2))

        x = x0 + pad
        y = y0 + pad
        inner_w = w - 2 * pad - t.px(2)
        size = t.font(13)
        p.text(x, y, size, "SETUP STEPS", Colors.YELLOW)
        p.hline(x, y + size + t.px(3), inner_w, Colors.BORDER, 1)
        y += size + t.px(10)

        row = t.font(13)
        for i in range(len(STEP_NAMES)):
            number = i + 1
            if number < index:
                mark, color = "OK", Colors.GREEN
            elif number == index:
                mark, color = ">", Colors.CYAN
            else:
                mark, color = "-", Colors.TEXT_FAINT
            p.text(x, y, row, mark, color)
            p.text(x + t.px(26), y, row, STEP_NAMES[i], color)
            y += t.px(19)

        y += t.px(10)
        p.hline(x, y, inner_w, Colors.BORDER, 1)
        y += t.px(10)
        # Notices live here rather than in the footer, where the toolbar
        # buttons leave no room for a full sentence.
        if self._toast_text is not None:
            self._wrapped(p, x, y, inner_w, self._toast_text, self._toast_color)
        else:
            p.text(x, y, t.font(12), "Tap inside the picture", Colors.TEXT_DIM)
            p.text(x, y + t.px(16), t.font(12), "to place points.", Colors.TEXT_DIM)

    def _wrapped(self, p, x, y, width, text, color):
        t = self.theme
        size = t.font(12)
        line = ""
        for word in text.split(" "):
            candidate = word if not line else line + " " + word
            if p.text_width(size, candidate) > width and line:
                p.text(x, y, size, line, color)
                y += t.px(15)
                line = word
            else:
                line = candidate
        if line:
            p.text(x, y, size, line, color)

    def _draw_footer(self, step):
        t = self.theme
        p = self.chrome
        x, y, w, h = self.layout.footer
        p.rect(x, y, w, h, Colors.CHROME, fill=True)
        p.hline(x, y, w, Colors.ACCENT, t.px(2))
        for button in step.buttons:
            button.draw(p)
