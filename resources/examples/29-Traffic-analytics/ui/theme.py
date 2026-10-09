"""Colours and resolution-independent sizing (designed at 800x480)."""


class Colors:
    WHITE = (255, 255, 255)
    BLACK = (0, 0, 0)

    # Chrome: header / footer / side panel.
    CHROME = (13, 17, 24)
    PANEL = (18, 23, 32)
    TILE_BG = (27, 34, 47)
    BUTTON_BG = (30, 38, 52)
    BORDER = (46, 57, 76)
    TEXT_DIM = (150, 162, 180)
    TEXT_FAINT = (104, 115, 133)
    DISABLED = (86, 94, 108)

    YELLOW = (255, 208, 0)
    ORANGE = (255, 145, 0)
    GREEN = (40, 220, 120)
    CYAN = (0, 200, 255)
    RED = (255, 62, 62)
    MAGENTA = (235, 90, 235)
    BLUE = (70, 140, 255)
    ACCENT = (0, 170, 255)

    VEHICLE = {
        "car": ORANGE,
        "motorcycle": MAGENTA,
        "bicycle": CYAN,
        "bus": GREEN,
        "truck": YELLOW,
    }
    LANE_PALETTE = (CYAN, YELLOW, MAGENTA, GREEN, ORANGE, BLUE)
    DENSITY = {"LOW": GREEN, "MEDIUM": YELLOW, "HIGH": RED}
    CONGESTION = {
        "FREE FLOW": GREEN,
        "NORMAL": CYAN,
        "HEAVY": YELLOW,
        "SLOW": ORANGE,
        "CONGESTED": RED,
    }

    @classmethod
    def lane(cls, index):
        return cls.LANE_PALETTE[index % len(cls.LANE_PALETTE)]


class Theme:
    BASE_W = 800
    BASE_H = 480

    def __init__(self, display_size):
        self.w = int(display_size[0])
        self.h = int(display_size[1])
        self.scale = min(self.w / float(self.BASE_W), self.h / float(self.BASE_H))

    def size(self):
        return (self.w, self.h)

    def px(self, value):
        return max(1, int(value * self.scale + 0.5))

    def font(self, value):
        return max(12, int(value * self.scale + 0.5))
