def _align_down(value, step):
    return value - (value % step)


def _even(value):
    return value - (value % 2)


class Layout:
    def __init__(self, theme):
        self.theme = theme
        w, h = theme.w, theme.h

        # The video layer wants both stage dimensions 16-aligned, so the stage
        # is sized first and the footer absorbs whatever is left over.
        self.header_h = _even(theme.px(44))
        stage_x = _align_down(theme.px(228) + 15, 16)
        stage_w = _align_down(w - stage_x, 16)
        stage_y = self.header_h
        stage_h = _align_down(h - self.header_h - theme.px(52), 16)
        self.footer_h = h - self.header_h - stage_h

        self.stage = (stage_x, stage_y, stage_w, stage_h)
        self.header = (0, 0, w, self.header_h)
        self.footer = (0, h - self.footer_h, w, self.footer_h)
        self.panel = (0, self.header_h, stage_x, h - self.header_h - self.footer_h)

    # ------------------------------------------------------------ stage --
    @property
    def stage_size(self):
        return (self.stage[2], self.stage[3])

    @property
    def stage_origin(self):
        return (self.stage[0], self.stage[1])

    def in_stage(self, point):
        x, y, w, h = self.stage
        return x <= point[0] < x + w and y <= point[1] < y + h

    def to_stage(self, point):
        return (point[0] - self.stage[0], point[1] - self.stage[1])

    def snap_to_stage_edge(self, point, margin):
        x, y = point
        w, h = self.stage[2], self.stage[3]
        if x <= margin:
            x = 0
        elif x >= w - 1 - margin:
            x = w - 1
        if y <= margin:
            y = 0
        elif y >= h - 1 - margin:
            y = h - 1
        return (int(x), int(y))
