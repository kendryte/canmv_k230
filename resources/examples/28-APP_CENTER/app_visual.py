# app_visual.py - Stateless commercial-style drawing primitives for app OSDs

import config


# ARGB8888 colors.  The palette is shared only for visual consistency; this
# module owns no Image, Display, Sensor, model, or application lifecycle state.
CYAN = (255, 0, 214, 255)
BLUE = (255, 10, 132, 255)
GREEN = (255, 48, 209, 88)
ORANGE = (255, 255, 159, 10)
RED = (255, 255, 69, 58)
VIOLET = (255, 191, 90, 242)
WHITE = (255, 245, 249, 255)
PANEL = (220, 7, 16, 30)
SHADOW = (170, 0, 0, 0)


def _limits(img):
    width = img.width()
    height = img.height()
    layout = config.ui_layout
    if layout is None:
        return width, height, 6, height - 6
    return width, height, layout.header_h + 6, \
        height - layout.footer_h - 6


def _clip(value, low, high):
    if value < low:
        return low
    if value > high:
        return high
    return value


def _text_units(text):
    units = 0
    for char in str(text):
        units += 2 if ord(char) > 127 else 1
    return units


def draw_badge(img, text, x, y, color=CYAN, font_size=20, font=None):
    """Draw a compact dark information badge with an accent rail."""
    if text is None or text == "":
        return
    width, height, safe_top, safe_bottom = _limits(img)
    badge_h = max(24, font_size + 8)
    badge_w = _text_units(text) * font_size // 2 + 20
    badge_w = _clip(badge_w, 52, max(52, width - 12))
    x = _clip(int(x), 6, max(6, width - badge_w - 6))
    y = _clip(int(y), safe_top, max(safe_top, safe_bottom - badge_h))
    img.draw_rectangle(x, y, badge_w, badge_h, color=PANEL, fill=True)
    img.draw_rectangle(x, y, 4, badge_h, color=color, fill=True)
    if font is None:
        img.draw_string_advanced(x + 10, y + 4, font_size, str(text),
                                 color=WHITE)
    else:
        img.draw_string_advanced(x + 10, y + 4, font_size, str(text),
                                 color=WHITE, font=font)


def _label_text(label, score):
    if score is None:
        return str(label) if label else ""
    try:
        return "%s  %d%%" % (label, int(float(score) * 100 + 0.5))
    except Exception:
        return str(label) if label else ""


def draw_detection(img, x, y, w, h, label="", score=None,
                   color=CYAN, font_size=20, font=None):
    """Draw a high-contrast target frame, label badge and score rail."""
    width, height, safe_top, unused = _limits(img)
    x = _clip(int(x), 0, max(0, width - 2))
    y = _clip(int(y), 0, max(0, height - 2))
    w = _clip(int(w), 2, max(2, width - x - 1))
    h = _clip(int(h), 2, max(2, height - y - 1))

    # One dark under-stroke keeps the frame readable on bright camera scenes.
    img.draw_rectangle(x, y, w, h, color=SHADOW, thickness=6)
    img.draw_rectangle(x, y, w, h, color=color, thickness=2)

    if score is not None:
        try:
            ratio = _clip(float(score), 0.0, 1.0)
            rail_w = max(1, int(max(1, w - 4) * ratio))
            rail_w = min(rail_w, max(1, w - 4))
            img.draw_rectangle(x + 2, y + h - 6, rail_w, 4,
                               color=color, fill=True)
        except Exception:
            pass

    text = _label_text(label, score)
    if text:
        badge_h = max(24, font_size + 8)
        badge_y = y - badge_h - 3
        if badge_y < safe_top:
            badge_y = y + 5
        draw_badge(img, text, x, badge_y, color, font_size, font)


def draw_polygon(img, points, label="", score=None, color=CYAN,
                 font_size=20, font=None):
    """Draw a shadowed closed polygon with illuminated vertices."""
    if points is None or len(points) < 2:
        return
    width, height, unused_top, unused_bottom = _limits(img)
    normalized = [(_clip(int(point[0]), 0, width - 1),
                   _clip(int(point[1]), 0, height - 1))
                  for point in points]
    for index in range(len(normalized)):
        x1, y1 = normalized[index]
        x2, y2 = normalized[(index + 1) % len(normalized)]
        img.draw_line(x1, y1, x2, y2, color=SHADOW, thickness=7)
        img.draw_line(x1, y1, x2, y2, color=color, thickness=3)
    for x, y in normalized:
        img.draw_circle(x, y, 3, color=color, fill=True)
    text = _label_text(label, score)
    if text:
        anchor_x = min(point[0] for point in normalized)
        anchor_y = min(point[1] for point in normalized)
        draw_badge(img, text, anchor_x, anchor_y - font_size - 12,
                   color, font_size, font)


def draw_keypoint(img, x, y, color=CYAN, radius=4):
    """Draw a keypoint with a dark halo for camera-scene contrast."""
    width, height, unused_top, unused_bottom = _limits(img)
    x = _clip(int(x), 0, width - 1)
    y = _clip(int(y), 0, height - 1)
    img.draw_circle(x, y, radius + 2, color=SHADOW, fill=True)
    img.draw_circle(x, y, radius, color=color, fill=True)


def draw_skeleton_line(img, x1, y1, x2, y2, color=CYAN,
                       thickness=3):
    width, height, unused_top, unused_bottom = _limits(img)
    x1 = _clip(int(x1), 0, width - 1)
    y1 = _clip(int(y1), 0, height - 1)
    x2 = _clip(int(x2), 0, width - 1)
    y2 = _clip(int(y2), 0, height - 1)
    img.draw_line(x1, y1, x2, y2,
                  color=SHADOW, thickness=thickness + 4)
    img.draw_line(x1, y1, x2, y2,
                  color=color, thickness=thickness)


def draw_arrow(img, x1, y1, x2, y2, color=ORANGE, size=24,
               thickness=4):
    width, height, unused_top, unused_bottom = _limits(img)
    x1 = _clip(int(x1), 0, width - 1)
    y1 = _clip(int(y1), 0, height - 1)
    x2 = _clip(int(x2), 0, width - 1)
    y2 = _clip(int(y2), 0, height - 1)
    img.draw_arrow(x1, y1, x2, y2, color=SHADOW,
                   size=size + 3, thickness=thickness + 4)
    img.draw_arrow(x1, y1, x2, y2, color=color,
                   size=size, thickness=thickness)
    draw_keypoint(img, x1, y1, color=color, radius=3)


def draw_mode_badge(img, text, color=CYAN, x=None):
    """Draw a mode chip at the top-right of the unobscured camera area."""
    width, unused_h, safe_top, unused_bottom = _limits(img)
    if x is None:
        badge_w = _text_units(text) * 18 // 2 + 20
        badge_w = _clip(badge_w, 52, max(52, width - 12))
        x = width - badge_w - 12
    draw_badge(img, text, x, safe_top, color=color, font_size=18)
