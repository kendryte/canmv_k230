import config
from ui.theme import Colors

TILES = (("car", "CARS"), ("bus", "BUSES"), ("truck", "TRUCKS"),
         ("motorcycle", "MOTOR"), ("bicycle", "BIKES"), (None, "TOTAL"))
SHORT_STATUS = {"FREE FLOW": "FREE", "NORMAL": "NORMAL", "HEAVY": "HEAVY",
                "SLOW": "SLOW", "CONGESTED": "JAM"}


class DashboardPanel:
    def __init__(self, theme, rect):
        self.theme = theme
        self.rect = rect

    def render(self, p, stats, scene):
        t = self.theme
        x0, y0, w, h = self.rect
        pad = t.px(8)
        p.rect(x0, y0, w, h, Colors.PANEL, fill=True)
        p.vline(x0 + w - t.px(2), y0, h, Colors.BORDER, t.px(2))

        x = x0 + pad
        inner_w = w - 2 * pad - t.px(2)
        bottom = y0 + h - pad
        y = y0 + pad

        y = self._section(p, x, y, inner_w, "VEHICLE COUNT")
        y = self._tiles(p, x, y, inner_w, stats)
        y = self._section(p, x, y + t.px(6), inner_w, "TRAFFIC STATISTICS")
        y = self._statistics(p, x, y, inner_w, stats)
        y = self._section(p, x, y + t.px(6), inner_w, "LANE STATUS")
        self._lanes(p, x, y, inner_w, bottom, stats)

    def _section(self, p, x, y, w, title):
        t = self.theme
        size = t.font(13)
        p.text(x, y, size, title, Colors.YELLOW)
        p.hline(x, y + size + t.px(3), w, Colors.BORDER, 1)
        return y + size + t.px(8)

    def _tiles(self, p, x, y, w, stats):
        t = self.theme
        gap = t.px(4)
        tile_w = (w - gap) // 2
        tile_h = t.px(42)
        for i in range(len(TILES)):
            key, label = TILES[i]
            row, col = divmod(i, 2)
            tx = x + col * (tile_w + gap)
            ty = y + row * (tile_h + gap)
            if key is None:
                color, live, passed = Colors.WHITE, stats.live_total, stats.passed_total
            else:
                color = Colors.VEHICLE[key]
                live = stats.live_by_type.get(key, 0)
                passed = stats.passed_by_type.get(key, 0)
            p.rect(tx, ty, tile_w, tile_h, Colors.TILE_BG, fill=True)
            p.vline(tx, ty, tile_h, color, t.px(3))
            p.text(tx + t.px(8), ty + t.px(3), t.font(10), label, Colors.TEXT_FAINT)
            p.text(tx + t.px(8), ty + t.px(15), t.font(21), str(live), color)
            p.text_right(tx + tile_w - t.px(6), ty + t.px(26), t.font(10),
                         "{} pass".format(passed), Colors.TEXT_DIM)
        return y + 3 * tile_h + 2 * gap

    def _statistics(self, p, x, y, w, stats):
        t = self.theme
        size = t.font(13)
        rows = (
            ("Avg Speed", "{:.1f} km/h".format(stats.avg_speed_kmh), Colors.WHITE),
            ("Flow Rate", "{:.1f} /min".format(stats.flow_rate_vpm), Colors.GREEN),
            ("In / Out", "{} / {}".format(stats.count_in, stats.count_out), Colors.CYAN),
            ("Speeding", "{} ({})".format(stats.speeding_now, stats.speeding_total),
             Colors.RED if stats.speeding_now else Colors.WHITE),
            ("Stopped", "{} ({})".format(stats.stopped_now, stats.stops_total),
             Colors.RED if stats.stopped_now else Colors.WHITE),
            ("Incidents", "{} ({})".format(stats.incidents_now, stats.incidents_total),
             Colors.RED if stats.incidents_now else Colors.WHITE),
        )
        for label, value, color in rows:
            p.text(x, y, size, label, Colors.TEXT_DIM)
            p.text_right(x + w, y, size, value, color)
            y += t.px(16)
        return y

    def _lanes(self, p, x, y, w, bottom, stats):
        t = self.theme
        head = t.font(10)
        columns = (t.px(28), t.px(62), t.px(96))
        p.text(x, y, head, "LANE", Colors.TEXT_FAINT)
        p.text(x + columns[0], y, head, "LIVE", Colors.TEXT_FAINT)
        p.text(x + columns[1], y, head, "PASS", Colors.TEXT_FAINT)
        p.text(x + columns[2], y, head, "KM/H", Colors.TEXT_FAINT)
        p.text_right(x + w, y, head, "STATUS", Colors.TEXT_FAINT)
        y += t.px(14)
        if not stats.lanes:
            p.text(x, y, t.font(12), "No lanes configured", Colors.TEXT_DIM)
            return
        size = t.font(12)
        step = t.px(15)
        for lane in stats.lanes[:config.LANE_MAX]:
            if y + step > bottom:
                break
            color = Colors.lane(lane.index)
            p.rect(x, y + t.px(3), t.px(7), t.px(7), color, fill=True)
            p.text(x + t.px(11), y, size, lane.name, Colors.WHITE)
            p.text(x + columns[0], y, size, str(lane.live), Colors.WHITE)
            p.text(x + columns[1], y, size, str(lane.passed), Colors.WHITE)
            p.text(x + columns[2], y, size, "{:.0f}".format(lane.avg_speed_kmh), Colors.WHITE)
            p.text_right(x + w, y, size, SHORT_STATUS.get(lane.congestion, lane.congestion),
                         Colors.CONGESTION.get(lane.congestion, Colors.WHITE))
            y += step
