from helper import distance, Storage
import json
import config

_last_scene = None

def _scene_path():
    return Storage.base_dir() + "/" + config.SCENE_SAVE_FILE

def _save_to_disk(scene):
    try:
        with open(_scene_path(), "w") as f:
            json.dump({
                "stage_size": scene.stage_size,
                "calib_line": scene.calib_line,
                "calib_meters": scene.calib_meters,
                "speed_limit_kmh": scene.speed_limit_kmh,
                "count_line": scene.count_line,
                "in_side": scene.in_side,
                "lanes": scene.lanes,
            }, f)
    except Exception as err:
        print("[scene_config] save failed:", err)


def _load_from_disk():
    try:
        with open(_scene_path()) as f:
            data = json.load(f)
    except Exception:
        return None
    scene = SceneConfig(data["stage_size"])
    scene.calib_line = [tuple(p) for p in data["calib_line"]]
    scene.calib_meters = data["calib_meters"]
    scene.speed_limit_kmh = data["speed_limit_kmh"]
    scene.count_line = [tuple(p) for p in data["count_line"]]
    scene.in_side = data["in_side"]
    scene.lanes = [[tuple(p) for p in lane] for lane in data["lanes"]]
    return scene

def remember(scene):
    global _last_scene
    if scene is not None and scene.is_complete():
        _last_scene = scene.copy()
        _save_to_disk(_last_scene)


def recall(stage_size):
    global _last_scene
    if _last_scene is None:
        _last_scene = _load_from_disk()
    if _last_scene is None:
        return None
    scene = _last_scene.copy(stage_size)
    return scene if scene.is_complete() else None

class SceneConfig:
    def __init__(self, stage_size):
        self.stage_size = [int(stage_size[0]), int(stage_size[1])]
        self.calib_line = []        # [(x, y), (x, y)] in stage pixels
        self.calib_meters = 0.0     # real length of calib_line
        self.speed_limit_kmh = 0.0
        self.count_line = []        # [(x, y), (x, y)]
        self.in_side = 1            # crossing TO this side counts as IN
        self.lanes = []             # [[(x, y), ...], ...] polygons

    @property
    def calib_pixels(self):
        if len(self.calib_line) != 2:
            return 0.0
        return distance(self.calib_line[0], self.calib_line[1])

    @property
    def meters_per_pixel(self):
        px = self.calib_pixels
        if px <= 0 or self.calib_meters <= 0:
            return 0.0
        return self.calib_meters / px

    def is_complete(self):
        return (self.meters_per_pixel > 0 and self.speed_limit_kmh > 0
                and len(self.count_line) == 2 and len(self.lanes) > 0)

    def scale_to(self, target_size):
        return (target_size[0] / float(self.stage_size[0]),
                target_size[1] / float(self.stage_size[1]))

    def copy(self, stage_size=None):
        target = stage_size or self.stage_size
        sx = target[0] / float(self.stage_size[0])
        sy = target[1] / float(self.stage_size[1])

        def scale(points):
            return [(int(p[0] * sx + 0.5), int(p[1] * sy + 0.5)) for p in points]

        clone = SceneConfig(target)
        clone.calib_line = scale(self.calib_line)
        clone.calib_meters = self.calib_meters
        clone.speed_limit_kmh = self.speed_limit_kmh
        clone.count_line = scale(self.count_line)
        clone.in_side = self.in_side
        clone.lanes = [scale(lane) for lane in self.lanes]
        return clone
