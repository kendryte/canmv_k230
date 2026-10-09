from ui.theme import Colors

# clickable button
class Button:
    def __init__(self, key, label, rect, color=Colors.CYAN, filled=False, font_size=None):
        self.key = key
        self.label = label
        self.rect = rect             # (x, y, w, h)
        self.color = color
        self.filled = filled
        self.font_size = font_size
        self.enabled = True
        self.visible = True

    def is_active(self):
        return self.visible and self.enabled

    # checks whether a touch coordinate is inside the button
    def contains(self, point):
        x, y, w, h = self.rect
        return x <= point[0] < x + w and y <= point[1] < y + h

    # draw button
    def draw(self, painter):
        if not self.visible:
            return
        t = painter.theme

        # Gets button position, color and size
        x, y, w, h = self.rect
        color = self.color if self.enabled else Colors.DISABLED
        size = self.font_size or t.font(15)

        # Draws rectangle
        if self.filled and self.enabled:
            painter.rect(x, y, w, h, color, fill=True)
            text_color = Colors.BLACK
        else:
            painter.rect(x, y, w, h, Colors.BUTTON_BG, fill=True)
            painter.rect(x, y, w, h, color, thickness=t.px(2))
            text_color = color

        # Draws button text
        painter.text_centered(x + w // 2, y + (h - size) // 2, size, self.label, text_color)


# numeric keypad
class Keypad:
    KEYS = ("1", "2", "3", "4", "5", "6", "7", "8", "9", ".", "0", "DEL")

    # only allow 6 character
    MAX_CHARS = 6

    def __init__(self, rect, theme, unit):
        self.rect = rect
        self.theme = theme
        self.unit = unit
        self._text = ""
        x, y, w, h = rect
        pad = theme.px(10)
        gap = theme.px(6)
        self._display_h = theme.px(52)
        key_w = (w - 2 * pad - 2 * gap) // 3
        key_h = (h - 2 * pad - self._display_h - 4 * gap) // 4
        top = y + pad + self._display_h + gap
        self.buttons = []

        # create keypad button
        for i in range(len(self.KEYS)):
            key = self.KEYS[i]
            row, col = divmod(i, 3)
            color = Colors.ORANGE if key == "DEL" else Colors.CYAN
            self.buttons.append(Button(key, key, (x + pad + col * (key_w + gap),
                                                  top + row * (key_h + gap), key_w, key_h),
                                       color, font_size=theme.font(20)))

    def set_value(self, value):
        if value and value > 0:
            text = "%.2f" % value
            self._text = text.rstrip("0").rstrip(".")
        else:
            self._text = ""

    def value(self):
        if not self._text or self._text == ".":
            return None
        try:
            return float(self._text)
        except ValueError:
            return None

    # checks whether a touch coordinate is inside the button
    def handle_tap(self, point):
        for button in self.buttons:
            if button.contains(point):
                self._press(button.key)
                return True
        return False

    # handles the keypad operation
    def _press(self, key):
        if key == "DEL":
            self._text = self._text[:-1]
        elif len(self._text) >= self.MAX_CHARS:
            return
        elif key == ".":
            if "." not in self._text:
                self._text = (self._text or "0") + "."
        elif self._text == "0":
            self._text = key
        else:
            self._text += key

    # draw keypad
    def draw(self, painter, message=None, message_color=Colors.TEXT_DIM):
        t = self.theme
        x, y, w, h = self.rect
        pad = t.px(10)
        painter.panel(x, y, w, h, bg=Colors.CHROME, border=Colors.ACCENT)
        dx, dy, dw = x + pad, y + pad, w - 2 * pad
        painter.rect(dx, dy, dw, self._display_h, Colors.BLACK, fill=True)
        value_text = (self._text or "0") + " " + self.unit
        size = t.font(28)
        painter.text_right(dx + dw - t.px(8), dy + (self._display_h - size) // 2 + t.px(4),
                           size, value_text, Colors.WHITE if self._text else Colors.DISABLED)
        if message:
            painter.text(dx + t.px(6), dy + t.px(3), t.font(11), message, message_color)
        for button in self.buttons:
            button.draw(painter)
