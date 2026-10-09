import config
from helper import distance, line_normal, midpoint, polygon_centroid
from ui.theme import Colors


class ScenePainter:
    def __init__(self, theme):
        self.theme = theme

    def draw_calibration_line(self, p, line, meters=0.0):
        t = self.theme
        for point in line:
            p.circle(point[0], point[1], t.px(6), Colors.CYAN, fill=True)
        if len(line) < 2:
            return
        p.line(line[0], line[1], Colors.CYAN, t.px(3))
        label = "{:.0f} px".format(distance(line[0], line[1]))
        if meters > 0:
            label += " = {:.1f} m".format(meters)
        mid = midpoint(line[0], line[1])
        size = t.font(14)
        x = p.clamp_x(mid[0] + t.px(8), p.text_width(size, label) + t.px(8))
        p.tag(x, p.clamp_y(mid[1] - t.px(24), size), label, Colors.CYAN, Colors.BLACK, size)

    def draw_count_line(self, p, line, in_side, show_direction=True):
        t = self.theme
        for point in line:
            p.circle(point[0], point[1], t.px(5), Colors.RED, fill=True)
        if len(line) < 2:
            return
        a, b = line
        p.line(a, b, Colors.RED, t.px(3))
        mid = midpoint(a, b)
        size = t.font(15)
        label = "COUNTING LINE"
        p.text(p.clamp_x(mid[0] - t.px(48), p.text_width(size, label)),
               p.clamp_y(mid[1] - t.px(24), size), size, label, Colors.RED)
        if not show_direction:
            return
        nx, ny = line_normal(a, b)
        nx, ny = nx * in_side, ny * in_side
        reach = t.px(40)
        start = (mid[0] - nx * reach, mid[1] - ny * reach)
        end = (mid[0] + nx * reach, mid[1] + ny * reach)
        p.arrow(start, end, Colors.GREEN, t.px(3))
        tag = t.font(14)
        p.tag(p.clamp_x(end[0] + nx * t.px(10) - t.px(10), t.px(30)),
              p.clamp_y(end[1] + ny * t.px(10) - tag // 2, tag),
              "IN", Colors.GREEN, Colors.BLACK, tag)
        p.tag(p.clamp_x(start[0] - nx * t.px(14) - t.px(14), t.px(40)),
              p.clamp_y(start[1] - ny * t.px(14) - tag // 2, tag),
              "OUT", Colors.ORANGE, Colors.BLACK, tag)

    def draw_lanes(self, p, lanes, thickness=2, highlight=-1, labels=True):
        t = self.theme
        for i, lane in enumerate(lanes):
            is_hot = (i == highlight)
            color = Colors.RED if is_hot else Colors.lane(i)
            p.polyline(lane, color, thickness + (t.px(3) if is_hot else 0), closed=True)
            if not labels:
                continue
            cx, cy = polygon_centroid(lane)
            size = t.font(15)
            p.tag(p.clamp_x(cx - t.px(12), t.px(30)), p.clamp_y(cy - size // 2, size),
                  "L{}".format(i + 1), color, Colors.BLACK, size)
            if is_hot:
                text = "MOST CONGESTED"
                p.tag(p.clamp_x(cx - t.px(56), p.text_width(size, text) + t.px(8)),
                      p.clamp_y(cy + size + t.px(4), size), text, Colors.RED, Colors.WHITE, size)

    def draw_tracks(self, p, tracks, now_ms, show_trails=config.SHOW_TRAILS):
        t = self.theme
        size = t.font(13)
        blink = (now_ms // 350) % 2 == 0
        for track in tracks:
            if not track.is_confirmed() or not track.is_visible(now_ms):
                continue
            x, y, w, h = track.box
            alert = track.is_alert()
            color = Colors.RED if alert else Colors.VEHICLE.get(track.vtype, Colors.WHITE)
            thickness = t.px(4) if (alert and blink) else (t.px(3) if alert else t.px(2))

            if show_trails and len(track.history) > 2:
                trail = [(s[1], s[2]) for s in track.history[-config.TRAIL_POINTS:]]
                p.polyline(trail, color, t.px(2))
            p.rect(x, y, w, h, color, thickness=thickness)

            name = "{} #{}".format(config.VEHICLE_DISPLAY_NAMES.get(track.vtype, track.vtype),
                                   track.id)
            tag_h = size + t.px(3)
            p.tag(p.clamp_x(x, p.text_width(size, name) + t.px(8)),
                  p.clamp_y(y - tag_h if y >= tag_h else y + h, tag_h),
                  name, color, Colors.BLACK, size)

            info = self._track_info(track)
            info_y = y + h + t.px(2)
            if info_y + size > p.clip[3]:
                info_y = y - size - tag_h - t.px(2)
            p.text(p.clamp_x(x, p.text_width(size, info)), p.clamp_y(info_y, size),
                   size, info, color)

    @staticmethod
    def _track_info(track):
        lane = "L{}".format(track.lane + 1) if track.lane >= 0 else "--"
        if track.is_incident:
            return "{} | INCIDENT".format(lane)
        if track.is_abnormal:
            return "{} | STOPPED {}s".format(lane, track.still_ms // 1000)
        speed = "{:.0f} km/h".format(track.speed_kmh) if track.speed_valid else "..."
        if track.is_speeding:
            return "{} | {} OVER".format(lane, speed)
        return "{} | {}".format(lane, speed)
