# Geometry is computed once from the initialized display, never per frame.
DESIGN_WIDTH = 800
DESIGN_HEIGHT = 480
SCALE_ONE = 1024


class UILayout:
    def __init__(self, width, height):
        if width < 240 or height < 240:
            raise ValueError("APP Center requires at least 240x240 pixels")
        self.width = int(width)
        self.height = int(height)
        self.scale = max(1, min(width * SCALE_ONE // DESIGN_WIDTH,
                                height * SCALE_ONE // DESIGN_HEIGHT))
        self.viewport_w = self.width
        self.viewport_h = self.height
        self.offset_x = self.offset_y = 0
        self.compact = height < 360
        self.narrow = width < 480
        self.font_size = 16 if self.compact else 20
        self.line_h = self.font_size * 3 // 2

        self.header_h = self.clamp_px(60, 44, 80)
        self.footer_h = (self.line_h * 2 + 12 if self.narrow else
                         self.clamp_px(52, 40, 72))
        self.overlay_btn_size = min(self.header_h - 8,
                                    self.clamp_px(48, 32, 64))
        self.overlay_edge = self.clamp_px(22, 8, 32)
        self.status_dot_size = self.clamp_px(8, 6, 12)
        self.overlay_gap = self.clamp_px(8, 4, 12)
        self.overlay_radius = 8

        self.status_x = self.status_y = 0
        self.status_w = width
        self.status_h = max(40, self.line_h + 12)
        self.nav_btn_w = self.clamp_px(36, 28, 48)
        self.nav_btn_h = self.clamp_px(80, 48, 96)
        self.prev_btn_x = 2
        self.next_btn_x = width - self.nav_btn_w - 2
        self.nav_radius = 8
        self.gap_x = self.clamp_px(20, 8, 24)
        self.gap_y = self.clamp_px(10, 6, 16)
        side = self.nav_btn_w + self.gap_x
        available_w = width - 2 * side
        bottom_h = self.line_h + 8
        self.card_area_y = self.status_h
        self.card_area_h = height - self.status_h - bottom_h
        available_h = self.card_area_h - 2 * self.gap_y

        target_w = 120 if self.compact else 188
        self.text_h = (self.font_size + 4) * 2
        self.text_y = -6
        self.icon_size = 48
        icon_top = self.clamp_px(12, 12, 24)
        self.icon_text_gap = 4
        icon_gap = self.icon_text_gap
        target_h = self.icon_size + icon_top + icon_gap + self.text_h - self.text_y
        self.cols = max(1, min(5, (available_w + self.gap_x) //
                              (target_w + self.gap_x)))
        self.rows = max(1, min(4, (available_h + self.gap_y) //
                              (target_h + self.gap_y)))
        self.card_w = (available_w - (self.cols - 1) * self.gap_x) // self.cols
        self.card_h = (available_h - (self.rows - 1) * self.gap_y) // self.rows
        self.grid_x = side
        self.grid_y = self.gap_y
        self.card_radius = 8
        icon_area_h = self.card_h - self.text_h + self.text_y
        self.icon_y = min(
            icon_area_h - self.icon_size - icon_gap,
            max(icon_top, (icon_area_h - self.icon_size - icon_gap) // 2) + 4)
        self.nav_btn_y = self.card_area_y + (self.card_area_h - self.nav_btn_h) // 2
        self.dot_size = 6
        self.dot_gap = 8
        self.dot_y = height - bottom_h // 2 - self.dot_size // 2
        self.swipe_min_dx = self.clamp_px(15, 10, 32)
        self.tap_max_move = self.clamp_px(10, 8, 24)

    def px(self, value):
        sign = -1 if value < 0 else 1
        return sign * ((abs(value) * self.scale + SCALE_ONE // 2) // SCALE_ONE)

    def clamp_px(self, value, minimum, maximum):
        return max(minimum, min(maximum, self.px(value)))

    def x(self, design_x):
        return self.px(design_x)

    def y(self, design_y):
        return self.px(design_y)

    def icon_zoom(self):
        return max(1, self.icon_size * 256 // 48)

    def footer_rects(self, show_stats=True, wifi_connected=False):
        edge = self.clamp_px(16, 8, 32)
        dot = self.status_dot_size
        wifi_w = self.clamp_px(32, 24, 52)
        reserved = wifi_w if wifi_connected else 0
        left = edge + dot * 2
        y = (self.footer_h - self.line_h) // 2
        if self.narrow and show_stats:
            y = 4
            second_y = self.line_h + 6
            status = (left, y, self.width - left - edge - reserved, self.line_h)
            fps = (edge, second_y, self.width // 2 - edge, self.line_h)
            result = (self.width // 2, second_y,
                      self.width - self.width // 2 - edge, self.line_h)
        else:
            fps_w = min(120, max(72, self.width // 5))
            fps_x = (self.width - fps_w) // 2
            status_w = (fps_x - left if show_stats else
                        self.width - left - edge - reserved)
            status = (left, y, status_w, self.line_h)
            fps = (fps_x, y, fps_w, self.line_h)
            result = (fps_x + fps_w, y,
                      self.width - edge - reserved - fps_x - fps_w, self.line_h)
        return {
            "dot": (edge, y + (self.line_h - dot) // 2, dot, dot),
            "status": status, "fps": fps, "result": result,
            "wifi": (self.width - edge - wifi_w, y, wifi_w, self.line_h),
        }

    def dialog_size(self, preferred_w, preferred_h, margin=12):
        return (min(preferred_w, self.width - margin * 2),
                min(preferred_h, self.height - margin * 2))

    def keyboard_height(self):
        return min(230, self.height * 40 // 100)

    def action_rects(self, database=False):
        edge, gap = 8, 6
        button_h = max(40, self.line_h * 2 + 4)
        bottom = self.height - self.footer_h - edge
        if not database:
            width = min(220, self.width - edge * 2)
            return [(self.width - edge - width, bottom - button_h, width, button_h)]
        if self.width < 480:
            width = (self.width - edge * 2 - gap) // 2
            top = bottom - button_h * 2 - gap
            return [(edge, top, width, button_h),
                    (edge + width + gap, top, width, button_h),
                    (edge, bottom - button_h, self.width - edge * 2, button_h)]
        width = (self.width - edge * 2 - gap * 2) // 3
        return [(edge + i * (width + gap), bottom - button_h, width, button_h)
                for i in range(3)]

    def text_entry_geometry(self, preferred_width):
        width = min(preferred_width, self.width - 16)
        field_h = 32 if self.compact else 40
        field_y = self.line_h + 8
        if width < 420:
            height = field_y + field_h * 2 + 20
            button_w = (width - 26) // 2
            field = (10, field_y, width - 20, field_h)
            cancel = (10, field_y + field_h + 6, button_w, field_h)
            submit = (16 + button_w, cancel[1], button_w, field_h)
        else:
            height = field_y + field_h + 12
            button_w = 80
            field = (10, field_y, width - button_w * 2 - 32, field_h)
            cancel = (width - button_w * 2 - 16, field_y, button_w, field_h)
            submit = (width - button_w - 10, field_y, button_w, field_h)
        keyboard_h = min(self.keyboard_height(), self.height - height - 12)
        x = (self.width - width) // 2
        y = max(4, (self.height - keyboard_h - height) // 2)
        return {"panel": (x, y, width, height), "field": field,
                "cancel": cancel, "submit": submit, "keyboard_h": keyboard_h}
