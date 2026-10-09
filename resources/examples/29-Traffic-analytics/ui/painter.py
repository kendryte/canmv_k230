import math

from ui.theme import Colors


class Painter:
    CHAR_WIDTH_RATIO = 0.62      # average glyph width / font size (ASCII)

    def __init__(self, img, theme, origin=(0, 0), scale=1.0, bounds=None, clip=None):
        self.img = img
        self.theme = theme
        self.ox = int(origin[0])
        self.oy = int(origin[1])
        # scale may be a single factor or (sx, sy): the camera window and the
        # full frame have different aspect ratios, so the report needs both.
        if isinstance(scale, (tuple, list)):
            self.sx, self.sy = float(scale[0]), float(scale[1])
        else:
            self.sx = self.sy = float(scale)
        self.savg = (self.sx + self.sy) * 0.5
        self.bounds = bounds or (int(theme.w / self.sx), int(theme.h / self.sy))
        self.clip = clip or (0, 0, self.bounds[0], self.bounds[1])

    # -------------------------------------------------------- transform --
    def _x(self, value):
        return int(self.ox + value * self.sx)

    def _y(self, value):
        return int(self.oy + value * self.sy)

    def _w(self, value):
        scaled = int(value * self.sx)
        return scaled if scaled > 0 else (1 if value > 0 else 0)

    def _h(self, value):
        scaled = int(value * self.sy)
        return scaled if scaled > 0 else (1 if value > 0 else 0)

    def _len(self, value):
        scaled = int(value * self.savg)
        return scaled if scaled > 0 else (1 if value > 0 else 0)

    def _size(self, value):
        return max(10, int(value * self.savg + 0.5))

    def clamp_x(self, value, width=0):
        return max(self.clip[0], min(self.clip[2] - width, value))

    def clamp_y(self, value, height=0):
        return max(self.clip[1], min(self.clip[3] - height, value))

    def text_width(self, size, text):
        return int(len(text) * size * self.CHAR_WIDTH_RATIO)

    def text(self, x, y, size, text, color):
        self.img.draw_string_advanced(self._x(x), self._y(y), self._size(size),
                                      text, color=color)

    def text_centered(self, cx, y, size, text, color):
        self.text(cx - self.text_width(size, text) // 2, y, size, text, color)

    def text_right(self, right_x, y, size, text, color):
        self.text(right_x - self.text_width(size, text), y, size, text, color)

    def tag(self, x, y, text, bg, fg, size):
        """Filled label box. Returns (w, h) in source units."""
        pad = self.theme.px(3)
        w = self.text_width(size, text) + pad * 2
        h = size + pad
        self.rect(x, y, w, h, bg, fill=True)
        self.text(x + pad, y, size, text, fg)
        return w, h

    def rect(self, x, y, w, h, color, thickness=1, fill=False):
        self.img.draw_rectangle(self._x(x), self._y(y), self._w(w), self._h(h),
                                color=color, thickness=max(1, self._len(thickness)),
                                fill=fill)

    def panel(self, x, y, w, h, bg=Colors.PANEL, border=Colors.BORDER):
        self.rect(x, y, w, h, bg, fill=True)
        if border is not None:
            self.rect(x, y, w, h, border, thickness=1)

    def hline(self, x, y, w, color, thickness=1):
        self.rect(x, y, w, thickness, color, fill=True)

    def vline(self, x, y, h, color, thickness=1):
        self.rect(x, y, thickness, h, color, fill=True)

    def line(self, a, b, color, thickness=1):
        self.img.draw_line(self._x(a[0]), self._y(a[1]), self._x(b[0]), self._y(b[1]),
                           color=color, thickness=max(1, self._len(thickness)))

    def polyline(self, points, color, thickness=1, closed=False):
        for i in range(1, len(points)):
            self.line(points[i - 1], points[i], color, thickness)
        if closed and len(points) > 2:
            self.line(points[-1], points[0], color, thickness)

    def circle(self, x, y, radius, color, thickness=1, fill=False):
        self.img.draw_circle(self._x(x), self._y(y), max(1, self._len(radius)),
                             color=color, thickness=max(1, self._len(thickness)), fill=fill)

    def arrow(self, start, end, color, thickness=2):
        self.line(start, end, color, thickness)
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length = math.sqrt(dx * dx + dy * dy)
        if length == 0:
            return
        ux, uy = dx / length, dy / length
        head = self.theme.px(12)
        for sign in (1, -1):
            cos_a, sin_a = 0.866, 0.5 * sign            # +-30 degrees
            hx = ux * cos_a - uy * sin_a
            hy = ux * sin_a + uy * cos_a
            self.line(end, (end[0] - hx * head, end[1] - hy * head), color, thickness)
