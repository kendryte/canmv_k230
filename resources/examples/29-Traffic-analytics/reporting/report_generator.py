import gc
import image
import cv_lite
from helper import display_timestamp, file_timestamp, format_duration
from helper import Storage
from reporting.heatmap_panel import HeatmapPanelRenderer
from ui.chrome import Footer, Header
from ui.dashboard import DashboardPanel
from ui.painter import Painter
from ui.theme import Colors


class ImageWriter:
    @staticmethod
    def save(frame, path):
        """frame: contiguous (h, w, 3) uint8 array. Returns the path written."""
        cv_lite.save_image(path, [frame.shape[0], frame.shape[1]], frame)
        return path


class SceneCapture:
    def __init__(self, camera):
        self._camera = camera
        self.size = camera.display_size

    def grab(self):
        """Returns (frame_array, canvas_image) of the current camera view."""
        snapshot = self._camera.capture_scene()
        frame = snapshot.to_numpy_ref().copy()
        snapshot = None
        canvas = image.Image(self.size[0], self.size[1], image.RGB888,
                             alloc=image.ALLOC_REF, data=frame)
        return frame, canvas


class ReportGenerator:
    def __init__(self, camera, theme, layout, scene_painter):
        self.capture = SceneCapture(camera)
        self.theme = theme
        self.layout = layout
        self.scene_painter = scene_painter
        self.size = self.capture.size
        self.header = Header(theme, layout.header)
        self.footer = Footer(theme, layout.footer)
        self.panel = DashboardPanel(theme, layout.panel)
        self.heatmap_panel = HeatmapPanelRenderer(theme, layout.panel)

    def generate(self, scene, stats, tracks, heatmap, now_ms):
        folder = Storage.base_dir()
        stamp = file_timestamp()
        shown_time = display_timestamp()
        scale = scene.scale_to(self.size)
        grid = heatmap.smoothed_grid()
        paths = []

        frame, canvas = self.capture.grab()
        self._dashboard_report(canvas, scene, stats, tracks, now_ms, shown_time, scale)
        paths.append(ImageWriter.save(frame, "{}/{}_dashboard.jpg".format(folder, stamp)))
        frame = None
        canvas = None
        gc.collect()

        frame, canvas = self.capture.grab()
        self._heatmap_report(frame, canvas, scene, stats, heatmap, grid, now_ms,
                             shown_time, scale)
        paths.append(ImageWriter.save(frame, "{}/{}_heatmap.jpg".format(folder, stamp)))
        frame = None
        canvas = None
        gc.collect()
        return paths

    def _scene_painter_for(self, canvas, scene, scale):
        sx, sy = scale
        clip = (int(self.layout.panel[2] / sx) + self.theme.px(6),
                int(self.layout.header_h / sy) + self.theme.px(4),
                scene.stage_size[0],
                int((self.size[1] - self.layout.footer_h) / sy) - self.theme.px(4))
        return Painter(canvas, self.theme, scale=scale, bounds=scene.stage_size, clip=clip)

    def _dashboard_report(self, canvas, scene, stats, tracks, now_ms, shown_time, scale):
        t = self.theme
        p = self._scene_painter_for(canvas, scene, scale)
        self.scene_painter.draw_lanes(p, scene.lanes, thickness=t.px(2))
        self.scene_painter.draw_count_line(p, scene.count_line, scene.in_side,
                                           show_direction=False)
        self.scene_painter.draw_tracks(p, tracks, now_ms)

        chrome = Painter(canvas, t)
        self.panel.render(chrome, stats, scene)
        self.header.render(chrome, stats, len(scene.lanes), shown_time, "SNAPSHOT REPORT")
        self.footer.render(chrome, (), stats, now_ms, self._caption(stats))

    def _heatmap_report(self, frame, canvas, scene, stats, heatmap, grid, now_ms,
                        shown_time, scale):
        t = self.theme
        painted = heatmap.render(frame, self.size, scene.lanes, grid)
        scores = heatmap.lane_scores(scene.lanes, grid) if painted else [0.0] * len(scene.lanes)
        ranking = sorted([(i, scores[i]) for i in range(len(scores))],
                         key=lambda item: item[1], reverse=True)
        hottest = ranking[0][0] if ranking and ranking[0][1] > 0 else -1

        p = self._scene_painter_for(canvas, scene, scale)
        self.scene_painter.draw_lanes(p, scene.lanes, thickness=t.px(2), highlight=hottest)
        self.scene_painter.draw_count_line(p, scene.count_line, scene.in_side,
                                           show_direction=False)
        hotspot = heatmap.hotspot(grid) if painted else None
        if hotspot:
            p.circle(hotspot[0], hotspot[1], t.px(20), Colors.WHITE, thickness=t.px(3))
            p.tag(p.clamp_x(hotspot[0] + t.px(22), t.px(70)),
                  p.clamp_y(hotspot[1] - t.px(8), t.px(16)),
                  "HOTSPOT", Colors.WHITE, Colors.BLACK, t.font(12))

        chrome = Painter(canvas, t)
        self.heatmap_panel.render(chrome, stats, ranking, heatmap.elapsed_ms())
        self.header.render(chrome, stats, len(scene.lanes), shown_time,
                           "CONGESTION HEATMAP", accent=Colors.RED)
        self.footer.render(chrome, (), stats, now_ms, self._caption(stats),
                           accent=Colors.RED)
        return ranking

    @staticmethod
    def _caption(stats):
        return "{} vehicles passed in {}  |  {} speeding, {} stops, {} incidents".format(
            stats.passed_total, format_duration(stats.elapsed_ms),
            stats.speeding_total, stats.stops_total, stats.incidents_total)