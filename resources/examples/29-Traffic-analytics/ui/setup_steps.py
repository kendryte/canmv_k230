import config
from helper import distance
from ui.theme import Colors
from ui.widgets import Button, Keypad

ACTION_NEXT = "next"
ACTION_BACK = "back"
ACTION_LOAD = "load"
ACTION_FINISH = "finish"


def format_number(value):
    return ("%.2f" % value).rstrip("0").rstrip(".")


class SetupStep:
    title = ""
    numbered = True           # shows "STEP n/N" in the banner
    snap_to_edges = False     # taps near the picture border snap onto it

    def __init__(self, wizard):
        self.wizard = wizard
        self.buttons = []

    @property
    def scene(self):
        return self.wizard.scene

    @property
    def theme(self):
        return self.wizard.theme

    @property
    def layout(self):
        return self.wizard.layout

    def enter(self):
        self.buttons = self.build_buttons()
        self.refresh()

    def build_buttons(self):
        return []

    def refresh(self):
        """Update button enabled states after any change."""

    def hint(self):
        return ""

    def handle_tap(self, point):
        for button in self.buttons:
            if button.is_active() and button.contains(point):
                return self.on_button(button.key)
        if self.layout.in_stage(point):
            local = self.layout.to_stage(point)
            if self.snap_to_edges:
                local = self.layout.snap_to_stage_edge(
                    local, self.theme.px(config.EDGE_SNAP_PX))
            return self.on_canvas_tap(local)
        return None

    def on_button(self, key):
        if key == "back":
            return ACTION_BACK
        if key == "next":
            return ACTION_NEXT
        return None

    def on_canvas_tap(self, point):
        return None

    def draw(self):
        pass

    def button(self, key):
        for b in self.buttons:
            if b.key == key:
                return b
        return None


class WelcomeStep(SetupStep):
    title = "WELCOME"
    numbered = False

    def build_buttons(self):
        t = self.theme
        sx, sy, sw, sh = self.layout.stage
        bw, bh, gap = t.px(180), t.px(52), t.px(20)
        y = sy + sh // 2 + t.px(46)
        cx = sx + sw // 2
        return [
            Button("new", "NEW SETUP", (cx - bw - gap // 2, y, bw, bh), Colors.CYAN, True,
                   t.font(18)),
            Button("load", "LOAD LAST", (cx + gap // 2, y, bw, bh), Colors.GREEN, False,
                   t.font(18)),
        ]

    def refresh(self):
        self.button("load").enabled = self.wizard.saved_scene is not None

    def on_button(self, key):
        if key == "new":
            self.wizard.start_new_scene()
            return ACTION_NEXT
        if key == "load":
            return ACTION_LOAD
        return None

    def hint(self):
        return "Configure the camera scene once, then start live analytics."

    def draw(self):
        t = self.theme
        p = self.wizard.chrome
        sx, sy, sw, sh = self.layout.stage
        w, h = min(sw - t.px(20), t.px(480)), t.px(200)
        x, y = sx + (sw - w) // 2, sy + (sh - h) // 2 - t.px(30)
        p.panel(x, y, w, h, bg=Colors.CHROME, border=Colors.ACCENT)
        cx = x + w // 2
        p.text_centered(cx, y + t.px(16), t.font(28), config.APP_NAME, Colors.YELLOW)
        p.text_centered(cx, y + t.px(56), t.font(14),
                        "Counting | Speed | Lanes | Congestion | Incidents", Colors.CYAN)
        p.text_centered(cx, y + t.px(84), t.font(13),
                        "1 Calibrate  2 Distance  3 Limit  4 Count line  5 Lanes",
                        Colors.TEXT_DIM)
        saved = self.wizard.saved_scene
        if saved is not None:
            info = "Last setup: {} lane(s), limit {:.0f} km/h".format(
                len(saved.lanes), saved.speed_limit_kmh)
            color = Colors.GREEN
        else:
            info = "No setup in memory - tap NEW SETUP"
            color = Colors.ORANGE
        p.text_centered(cx, y + t.px(120), t.font(13), info, color)
        p.text_centered(cx, y + t.px(150), t.font(11),
                        "Last setup is saved to storage and reloaded automatically.",
                        Colors.TEXT_FAINT)

class LineStep(SetupStep):
    def __init__(self, wizard, attr, title, first_hint, directional=False, context=()):
        super().__init__(wizard)
        self.context = context
        self.attr = attr
        self.title = title
        self.first_hint = first_hint
        self.directional = directional

    def _points(self):
        return getattr(self.scene, self.attr)

    def build_buttons(self):
        specs = [("back", "BACK", None), ("undo", "UNDO", None)]
        if self.directional:
            specs.append(("flip", "FLIP IN/OUT", None))
        specs.append(("next", "NEXT", "primary"))
        return self.wizard.toolbar(specs)

    def refresh(self):
        points = self._points()
        valid = len(points) == 2 and distance(points[0], points[1]) >= config.MIN_LINE_PX
        self.button("next").enabled = valid
        self.button("undo").enabled = len(points) > 0
        if self.directional:
            self.button("flip").enabled = valid

    def on_canvas_tap(self, point):
        points = list(self._points())
        if len(points) >= 2:
            points = []                   # third tap starts a new line
        points.append(point)
        setattr(self.scene, self.attr, points)
        return None

    def on_button(self, key):
        if key == "undo":
            setattr(self.scene, self.attr, list(self._points())[:-1])
            return None
        if key == "flip":
            self.scene.in_side = -self.scene.in_side
            return None
        return super().on_button(key)

    def hint(self):
        count = len(self._points())
        if count == 0:
            return self.first_hint
        if count == 1:
            return "Now tap the END point of the line."
        if self.directional:
            return "Green arrow = IN direction. FLIP if needed, then NEXT."
        return "Tap again to redraw, or press NEXT."

    def draw(self):
        self.wizard.draw_context(self.context)
        painter = self.wizard.scene_painter
        if self.directional:
            painter.draw_count_line(self.wizard.stage, self._points(), self.scene.in_side,
                                    show_direction=True)
        else:
            painter.draw_calibration_line(self.wizard.stage, self._points(),
                                          self.scene.calib_meters)


class NumberStep(SetupStep):
    def __init__(self, wizard, attr, title, prompt, unit, min_value, max_value, context=()):
        super().__init__(wizard)
        self.context = context
        self.attr = attr
        self.title = title
        self.prompt = prompt
        self.unit = unit
        self.min_value = min_value
        self.max_value = max_value
        self.keypad = None

    def enter(self):
        t = self.theme
        sx, sy, sw, sh = self.layout.stage
        width = min(sw - t.px(20), t.px(280))
        height = min(sh - t.px(12), t.px(330))
        rect = (sx + (sw - width) // 2, sy + (sh - height) // 2, width, height)
        self.keypad = Keypad(rect, t, self.unit)
        self.keypad.set_value(getattr(self.scene, self.attr))
        super().enter()

    def build_buttons(self):
        return self.wizard.toolbar([("back", "BACK", None), ("next", "NEXT", "primary")])

    def _is_valid(self):
        value = self.keypad.value()
        return value is not None and self.min_value <= value <= self.max_value

    def refresh(self):
        self.button("next").enabled = self._is_valid()

    def handle_tap(self, point):
        for button in self.buttons:
            if button.is_active() and button.contains(point):
                return self.on_button(button.key)
        if self.keypad.handle_tap(point):
            return None
        return None

    def on_button(self, key):
        if key == "next" and self._is_valid():
            setattr(self.scene, self.attr, self.keypad.value())
        return super().on_button(key)

    def hint(self):
        return "{}  (range {} - {} {})".format(self.prompt, format_number(self.min_value),
                                               format_number(self.max_value), self.unit)

    def draw(self):
        self.wizard.draw_context(self.context)
        value = self.keypad.value()
        if value is not None and not self._is_valid():
            self.keypad.draw(self.wizard.chrome, "Out of range", Colors.RED)
        else:
            self.keypad.draw(self.wizard.chrome, self.title, Colors.TEXT_DIM)


class LaneStep(SetupStep):
    title = "LANES"
    snap_to_edges = True

    def __init__(self, wizard):
        super().__init__(wizard)
        self.current = []

    def enter(self):
        self.current = []
        super().enter()
        self.wizard.toast("Tip: tap near the picture border to snap to the edge",
                          Colors.CYAN)

    def build_buttons(self):
        return self.wizard.toolbar([
            ("back", "BACK", None),
            ("undo", "UNDO", None),
            ("close", "CLOSE LANE", None),
            ("clear", "CLEAR ALL", "danger"),
            ("next", "NEXT", "primary"),
        ])

    def refresh(self):
        lanes = self.scene.lanes
        has_any = bool(self.current) or bool(lanes)
        current_ok = len(self.current) == 0 or len(self.current) >= 3
        self.button("undo").enabled = has_any
        self.button("clear").enabled = has_any
        self.button("close").enabled = len(self.current) >= 3
        self.button("next").enabled = current_ok and (bool(lanes) or len(self.current) >= 3)

    def on_canvas_tap(self, point):
        close_px = self.theme.px(config.CLOSE_SNAP_PX)
        if len(self.current) >= 3 and distance(point, self.current[0]) <= close_px:
            self._close_lane()
        elif not self.current and len(self.scene.lanes) >= config.LANE_MAX:
            self.wizard.toast("Maximum {} lanes reached".format(config.LANE_MAX), Colors.RED)
        elif len(self.current) >= config.LANE_MAX_POINTS:
            self.wizard.toast("Point limit reached - press CLOSE LANE", Colors.ORANGE)
        else:
            self.current.append(point)
        return None

    def on_button(self, key):
        if key == "undo":
            if self.current:
                self.current.pop()
            elif self.scene.lanes:                 # reopen the last lane
                self.current = list(self.scene.lanes[-1])
                self.scene.lanes = self.scene.lanes[:-1]
            return None
        if key == "close":
            self._close_lane()
            return None
        if key == "clear":
            self.current = []
            self.scene.lanes = []
            return None
        if key == "next" and len(self.current) >= 3:
            self._close_lane()
        return super().on_button(key)

    def _close_lane(self):
        self.scene.lanes = self.scene.lanes + [list(self.current)]
        self.current = []
        self.wizard.toast("Lane {} saved".format(len(self.scene.lanes)), Colors.GREEN)

    def hint(self):
        number = len(self.scene.lanes) + 1
        count = len(self.current)
        if count == 0:
            extra = " Or press NEXT." if self.scene.lanes else ""
            return "Lane {}: tap points around its outline, follow curves.{}".format(number, extra)
        if count < 3:
            return "Lane {}: {} point(s). Keep tapping around the lane.".format(number, count)
        return "Tap the first point (big ring) or CLOSE LANE to finish lane {}.".format(number)

    def draw(self):
        t = self.theme
        p = self.wizard.stage
        self.wizard.draw_context(("count_line",))
        self.wizard.scene_painter.draw_lanes(p, self.scene.lanes, thickness=t.px(3))
        if not self.current:
            return
        color = Colors.lane(len(self.scene.lanes))
        p.polyline(self.current, color, t.px(3))
        if len(self.current) >= 3:
            p.line(self.current[-1], self.current[0], Colors.TEXT_DIM, 1)
        for i in range(len(self.current)):
            point = self.current[i]
            if i == 0:
                p.circle(point[0], point[1], t.px(config.CLOSE_SNAP_PX // 2), color,
                         thickness=t.px(3))
            p.circle(point[0], point[1], t.px(5), color, fill=True)


class ReviewStep(SetupStep):
    title = "REVIEW & START"

    def build_buttons(self):
        return self.wizard.toolbar([("back", "BACK", None),
                                    ("start", "START ANALYTICS", "primary")])

    def refresh(self):
        self.button("start").enabled = self.scene.is_complete()

    def on_button(self, key):
        if key == "start" and self.scene.is_complete():
            return ACTION_FINISH
        return super().on_button(key)

    def hint(self):
        return "Check the overlay. BACK to edit any step, START to go live."

    def draw(self):
        t = self.theme
        scene = self.scene
        self.wizard.draw_context(("lanes", "calib_line", "count_line"))
        lines = (
            ("Scale", "1 px = {:.3f} m".format(scene.meters_per_pixel)),
            ("Calibration", "{:.1f} m over {:.0f} px".format(scene.calib_meters,
                                                             scene.calib_pixels)),
            ("Speed limit", "{:.0f} km/h".format(scene.speed_limit_kmh)),
            ("Counting line", "set (arrow = IN)" if len(scene.count_line) == 2 else "missing"),
            ("Lanes", str(len(scene.lanes))),
        )
        p = self.wizard.chrome
        sx, sy, _, _ = self.layout.stage
        x, y = sx + t.px(10), sy + t.px(10)
        w, h = t.px(250), t.px(36) + len(lines) * t.px(20)
        p.panel(x, y, w, h, bg=Colors.CHROME, border=Colors.ACCENT)
        p.text(x + t.px(10), y + t.px(7), t.font(15), "SETUP SUMMARY", Colors.YELLOW)
        row_y = y + t.px(30)
        for label, value in lines:
            p.text(x + t.px(10), row_y, t.font(13), label, Colors.TEXT_DIM)
            p.text(x + t.px(108), row_y, t.font(13), value, Colors.WHITE)
            row_y += t.px(20)
