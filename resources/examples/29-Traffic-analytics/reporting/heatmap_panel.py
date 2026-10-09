import config
from analytics.heatmap import legend_color
from helper import format_duration
from ui.theme import Colors


class HeatmapPanelRenderer:
    # Draw the heatmap statistics panel
    def __init__(self, theme, rect):
        self.theme = theme
        self.rect = rect

    def render(self, p, stats, ranking, elapsed_ms):
        # Draw all heatmap information on the side panel
        t = self.theme
        x0, y0, w, h = self.rect
        pad = t.px(8)
        p.rect(x0, y0, w, h, Colors.PANEL, fill=True)
        p.vline(x0 + w - t.px(2), y0, h, Colors.RED, t.px(2))

        x = x0 + pad
        inner_w = w - 2 * pad - t.px(2)
        y = y0 + pad
        y = self._section(p, x, y, inner_w, "CONGESTION MAP")
        p.text(x, y, t.font(11), "Accumulated over " + format_duration(elapsed_ms),
               Colors.TEXT_FAINT)
        y += t.px(18)
        y = self._winner(p, x, y, inner_w, stats, ranking)
        y = self._section(p, x, y + t.px(6), inner_w, "LANE RANKING")
        y = self._ranking(p, x, y, inner_w, ranking)
        y = self._section(p, x, y + t.px(6), inner_w, "HEAT SCALE")
        y = self._legend(p, x, y, inner_w)
        self._totals(p, x, y + t.px(4), inner_w, y0 + h - pad, stats)

    def _section(self, p, x, y, w, title):
        t = self.theme
        size = t.font(13)
        p.text(x, y, size, title, Colors.YELLOW)
        p.hline(x, y + size + t.px(3), w, Colors.BORDER, 1)
        return y + size + t.px(8)

    def _winner(self, p, x, y, w, stats, ranking):
        t = self.theme
        h = t.px(64)
        p.rect(x, y, w, h, Colors.TILE_BG, fill=True)
        p.vline(x, y, h, Colors.RED, t.px(3))
        if ranking and ranking[0][1] > 0:
            index = ranking[0][0]
            lane = stats.lanes[index]
            p.text(x + t.px(10), y + t.px(4), t.font(10), "MOST CONGESTED", Colors.TEXT_FAINT)
            p.text(x + t.px(10), y + t.px(16), t.font(24), "LANE {}".format(index + 1),
                   Colors.RED)
            p.text(x + t.px(10), y + t.px(46), t.font(12),
                   "{} | avg {:.0f} km/h".format(lane.congestion, lane.avg_speed_kmh),
                   Colors.CONGESTION.get(lane.congestion, Colors.WHITE))
        else:
            p.text(x + t.px(10), y + t.px(24), t.font(14), "Not enough data yet",
                   Colors.TEXT_DIM)
        return y + h

    def _ranking(self, p, x, y, w, ranking):
        t = self.theme
        bar_x = x + t.px(24)
        bar_w = w - t.px(24) - t.px(44)
        bar_h = t.px(11)
        size = t.font(12)
        for index, score in ranking[:config.LANE_MAX]:
            p.text(x, y, size, "L{}".format(index + 1), Colors.lane(index))
            p.rect(bar_x, y + t.px(2), bar_w, bar_h, Colors.TILE_BG, fill=True)
            fill_w = int(bar_w * score)
            if fill_w > 0:
                p.rect(bar_x, y + t.px(2), fill_w, bar_h, legend_color(score), fill=True)
            p.text_right(x + w, y, size, "{:.0f}%".format(score * 100), Colors.WHITE)
            y += t.px(18)
        return y

    def _legend(self, p, x, y, w):
        t = self.theme
        steps = 24
        step_w = max(1, w // steps)
        for i in range(steps):
            p.rect(x + i * step_w, y, step_w + 1, t.px(10),
                   legend_color(i / float(steps - 1)), fill=True)
        y += t.px(13)
        p.text(x, y, t.font(10), "LOW", Colors.TEXT_FAINT)
        p.text_right(x + w, y, t.font(10), "HIGH", Colors.TEXT_FAINT)
        y += t.px(16)
        p.text(x, y, t.font(10), "Heat = time spent there;", Colors.TEXT_FAINT)
        y += t.px(13)
        p.text(x, y, t.font(10), "slow vehicles weigh more.", Colors.TEXT_FAINT)
        return y + t.px(16)

    def _totals(self, p, x, y, w, bottom, stats):
        t = self.theme
        size = t.font(12)
        rows = (("Passed", str(stats.passed_total)),
                ("Avg speed", "{:.1f} km/h".format(stats.avg_speed_kmh)),
                ("Congestion", stats.congestion))
        for label, value in rows:
            if y + t.px(16) > bottom:
                break
            p.text(x, y, size, label, Colors.TEXT_DIM)
            p.text_right(x + w, y, size, value, Colors.WHITE)
            y += t.px(16)
