"""Host regressions for the AI port and display geometry (no board imports)."""
import ast
import contextlib
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "resources/examples/28-APP_CENTER"


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_class(path, name, namespace):
    tree = ast.parse(path.read_text())
    cls = next(node for node in tree.body
               if isinstance(node, ast.ClassDef) and node.name == name)
    exec(compile(ast.Module(body=[cls], type_ignores=[]), str(path), "exec"),
         namespace)
    return namespace[name]


def overlaps(a, b):
    x, y, w, h = a
    bx, by, bw, bh = b
    return x < bx + bw and bx < x + w and y < by + bh and by < y + h


class LayoutTests(unittest.TestCase):
    sizes = ((240, 240), (320, 240), (480, 272), (480, 320), (640, 480),
             (800, 480), (854, 480), (1024, 600), (1280, 720), (1920, 1080),
             (480, 480), (240, 320), (480, 800), (720, 1280))

    @classmethod
    def setUpClass(cls):
        cls.Layout = load_module(APP / "ui_layout.py", "layout").UILayout

    def assert_inside(self, rect, width, height):
        x, y, w, h = rect
        self.assertGreater(w, 0)
        self.assertGreater(h, 0)
        self.assertGreaterEqual(x, 0)
        self.assertGreaterEqual(y, 0)
        self.assertLessEqual(x + w, width)
        self.assertLessEqual(y + h, height)

    def test_home_grid_and_labels_fit(self):
        for width, height in self.sizes:
            with self.subTest(size=(width, height)):
                layout = self.Layout(width, height)
                cards = []
                for row in range(layout.rows):
                    for col in range(layout.cols):
                        rect = (layout.grid_x + col * (layout.card_w + layout.gap_x),
                                layout.card_area_y + layout.grid_y +
                                row * (layout.card_h + layout.gap_y),
                                layout.card_w, layout.card_h)
                        self.assert_inside(rect, width, height)
                        self.assertGreaterEqual(rect[1], layout.status_h)
                        self.assertLessEqual(rect[1] + rect[3],
                                             layout.card_area_y + layout.card_area_h)
                        self.assertFalse(any(overlaps(rect, old) for old in cards))
                        cards.append(rect)
                self.assertEqual(layout.icon_size, 48)
                self.assertGreaterEqual(layout.icon_y, 12)
                self.assertLessEqual(layout.icon_y + layout.icon_size + layout.icon_text_gap,
                                     layout.card_h - layout.text_h + layout.text_y)
                self.assertEqual(layout.px(0), 0)
                self.assertEqual(layout.px(-20), -layout.px(20))

    def test_footer_edges_and_slots_are_symmetric(self):
        for width, height in self.sizes:
            layout = self.Layout(width, height)
            edge = layout.clamp_px(16, 8, 32)
            for connected in (False, True):
                for show_stats in (False, True):
                    rects = layout.footer_rects(show_stats, connected)
                    visible = ["dot", "status"]
                    if show_stats:
                        visible += ["fps", "result"]
                    if connected:
                        visible.append("wifi")
                    for i, key in enumerate(visible):
                        with self.subTest(size=(width, height), key=key,
                                          wifi=connected, stats=show_stats):
                            self.assert_inside(rects[key], width, layout.footer_h)
                            self.assertFalse(any(overlaps(rects[key], rects[other])
                                                 for other in visible[:i]))
                    if show_stats:
                        result_right = sum((rects["result"][0], rects["result"][2]))
                        if not connected or layout.narrow:
                            self.assertEqual(result_right, width - edge)
                        else:
                            self.assertEqual(result_right, rects["wifi"][0])
                        if not layout.narrow:
                            self.assertLessEqual(abs(rects["fps"][0] * 2 +
                                                     rects["fps"][2] - width), 1)

    def test_actions_fit_between_header_and_footer(self):
        for width, height in self.sizes:
            layout = self.Layout(width, height)
            for database in (False, True):
                rectangles = layout.action_rects(database)
                for i, rect in enumerate(rectangles):
                    with self.subTest(size=(width, height), database=database):
                        self.assert_inside(rect, width, height)
                        self.assertGreaterEqual(rect[1], layout.header_h)
                        self.assertLessEqual(rect[1] + rect[3], height - layout.footer_h)
                        self.assertFalse(any(overlaps(rect, other)
                                             for other in rectangles[:i]))

    def test_text_entry_and_keyboard_do_not_overlap(self):
        for width, height in self.sizes:
            layout = self.Layout(width, height)
            for preferred in (520, 560):
                with self.subTest(size=(width, height), preferred=preferred):
                    entry = layout.text_entry_geometry(preferred)
                    self.assert_inside(entry["panel"], width, height)
                    x, y, pw, ph = entry["panel"]
                    self.assertLessEqual(y + ph, height - entry["keyboard_h"])
                    self.assertGreaterEqual(entry["keyboard_h"], 80)
                    rects = [entry[key] for key in ("field", "cancel", "submit")]
                    for i, rect in enumerate(rects):
                        self.assert_inside(rect, pw, ph)
                        self.assertFalse(any(overlaps(rect, other) for other in rects[:i]))
                    self.assertGreaterEqual(entry["field"][2], 100)

    def test_invalid_resolutions(self):
        for size in ((0, 480), (-1, 480), (800, 0), (160, 120)):
            with self.assertRaises(ValueError):
                self.Layout(*size)

    def test_all_app_sources_parse(self):
        for path in APP.glob("*.py"):
            with self.subTest(path=path.name):
                ast.parse(path.read_text(), str(path))

    def test_registry_matches_home(self):
        def assignment(path, name):
            for node in ast.parse(path.read_text()).body:
                if isinstance(node, ast.Assign) and any(
                        isinstance(t, ast.Name) and t.id == name for t in node.targets):
                    return ast.literal_eval(node.value)
            raise AssertionError(name)
        registry = assignment(APP / "runner.py", "DEMO_REGISTRY")
        sections = assignment(APP / "config.py", "HOME_SECTIONS")
        keys = [item[0] for _, items in sections for item in items]
        self.assertEqual(set(keys), set(registry))
        self.assertEqual(len(keys), len(set(keys)))
        for module, cls in registry.values():
            tree = ast.parse((APP / (module + ".py")).read_text())
            self.assertTrue(any(isinstance(n, ast.ClassDef) and n.name == cls
                                for n in tree.body))


class OverlayTests(unittest.TestCase):
    def test_card_uses_exported_content_height_constant(self):
        class Widget:
            FLAG = types.SimpleNamespace(CLICKABLE=1, EVENT_BUBBLE=2)
            def __init__(self, *args):
                self.calls = []
            def __getattr__(self, name):
                return lambda *args: self.calls.append((name, args))
        enum = types.SimpleNamespace(MAIN=0, CENTER=1, BOTTOM_MID=2,
                                     NONE=3, CLICKED=4, LONG_PRESSED=5, WRAP=6)
        # This binding exports SIZE_CONTENT directly, not a SIZE namespace.
        lv = types.SimpleNamespace(obj=Widget, label=types.SimpleNamespace(LONG=enum),
                                   PART=enum, ALIGN=enum, TEXT_ALIGN=enum, DIR=enum,
                                   EVENT=enum, SIZE_CONTENT=2001)
        labels = []
        def make_label(*args):
            label = Widget()
            labels.append(label)
            return label
        cls = load_class(APP / "center.py", "HomeScreen", {
            "lv": lv, "config": types.SimpleNamespace(THEME_CARD=1, THEME_TEXT=2),
            "gui": types.SimpleNamespace(font_cn=None, font_en=None,
                                         lv_color=lambda c: c, make_label=make_label)})
        home = cls.__new__(cls)
        home._card_area = Widget()
        home._make_app_icon = lambda *args: None
        layout_cls = load_module(APP / "ui_layout.py", "card_layout").UILayout
        for width, height in LayoutTests.sizes:
            home.layout = layout_cls(width, height)
            home._make_card(0, 0, "face", "Face detection", 1)
            self.assertIn(("set_height", (lv.SIZE_CONTENT,)), labels[-1].calls)
            self.assertIn(("set_style_max_height", (home.layout.text_h, 0)),
                          labels[-1].calls)
            self.assertIn(("align", (enum.BOTTOM_MID, 0, home.layout.text_y)),
                          labels[-1].calls)


    def test_footer_constructor_alignment_and_status_cache(self):
        class Widget:
            FLAG = types.SimpleNamespace(SCROLLABLE=1, HIDDEN=2)
            LONG = types.SimpleNamespace(DOT=1)
            def __init__(self, *args):
                self.calls = []
                self.children = []
                if args:
                    args[0].children.append(self)
                self.anchor = None
                self.position = (0, 0)
                self.size = (0, 0)
                self.line_height = 16
            def align(self, anchor, x, y):
                self.anchor = anchor
                self.position = (x, y)
                self.calls.append(("align", (anchor, x, y)))
            def set_pos(self, x, y):
                # LVGL preserves the alignment anchor when changing offsets.
                self.position = (x, y)
                self.calls.append(("set_pos", (x, y)))
            def get_style_text_font(self, part):
                return types.SimpleNamespace(get_line_height=lambda: self.line_height)
            def set_size(self, width, height):
                self.size = (width, height)
                self.calls.append(("set_size", (width, height)))
            def __getattr__(self, name):
                return lambda *args: self.calls.append((name, args))
        enum = types.SimpleNamespace(MAIN=0, LEFT=1, CENTER=2, RIGHT=3,
                                     LEFT_MID=4, RIGHT_MID=5, TOP_RIGHT=6, STOP=7, WIFI=8, TOP_LEFT=9, VER=10, CLICKED=11, PRESSED=12)
        lv = types.SimpleNamespace(obj=Widget, label=Widget, btn=Widget, PART=enum, DIR=enum, EVENT=enum,
                                   ALIGN=enum, TEXT_ALIGN=enum, SYMBOL=enum,
                                   scr_load=lambda screen: None)
        layout_cls = load_module(APP / "ui_layout.py", "footer_layout").UILayout
        cfg = types.SimpleNamespace(ui_layout=None, wifi_connected=False,
                                    THEME_GREEN=1, THEME_TEXT=2, THEME_SUBTEXT=3,
                                    THEME_ACCENT=4, THEME_RED=5, THEME_CARD=6)
        gui = types.SimpleNamespace(font_cn=None, font_en=None, lv_color=lambda c: c,
                                    make_label=lambda *args: Widget())
        cls = load_class(APP / "overlay.py", "DemoOverlay", {
            "lv": lv, "config": cfg, "gui": gui,
            "i18n": types.SimpleNamespace(text=lambda *args: str(args))})
        for width, height in LayoutTests.sizes:
            cfg.ui_layout = layout_cls(width, height)
            overlay = cls("Demo", lambda: None, lambda: None)
            for label in (overlay.status_label, overlay.fps_label, overlay.det_label):
                label.line_height = 24
            buttons = overlay.screen.children[0].children[:2]
            for button in buttons:
                self.assertIn(("clear_flag", (Widget.FLAG.SCROLLABLE,)), button.calls)
                self.assertTrue(any(name == "set_ext_click_area" and args[0] >= 6
                                    for name, args in button.calls))
                events = [args for name, args in button.calls if name == "add_event"]
                self.assertEqual(events[0][1], enum.PRESSED)
                events[0][0](None)
            self.assertIn(("set_style_text_align", (enum.RIGHT, 0)), overlay.det_label.calls)
            overlay.set_status("running", 1)
            updates = len(overlay.status_label.calls)
            overlay.set_status("running", 1)
            self.assertEqual(len(overlay.status_label.calls), updates)
            overlay.set_status("running", 5)
            self.assertGreater(len(overlay.status_label.calls), updates)
            for connected in (False, True, False):
                overlay.set_wifi_connected(connected)
                rects = cfg.ui_layout.footer_rects(True, connected)
                for key, widget in (("dot", overlay.status_dot),
                                    ("status", overlay.status_label),
                                    ("fps", overlay.fps_label),
                                    ("result", overlay.det_label),
                                    ("wifi", overlay.wifi_label)):
                    with self.subTest(size=(width, height), wifi=connected, widget=key):
                        self.assertEqual(widget.anchor, enum.TOP_LEFT)
                        self.assertEqual(widget.position, rects[key][:2])
                        self.assertEqual(widget.size, rects[key][2:])
                        if key != "dot" and connected:
                            expected = max(0, (rects[key][3] - widget.line_height) // 2)
                            self.assertIn(("set_style_pad_top", (expected, 0)), widget.calls)

            layout = cfg.ui_layout
            content_h = height - layout.header_h - layout.footer_h
            overlay._build_phrase_menu(0, layout.header_h, width, content_h,
                                       ["A long phrase"] * 6, lambda text: None)
            menu = overlay.screen.children[-1]
            self.assertEqual(menu.size, (width, content_h))
            self.assertEqual(menu.anchor, enum.TOP_LEFT)
            for button in menu.children:
                self.assertGreaterEqual(button.size[1], layout.line_h + 8)
                self.assertGreaterEqual(button.position[0], 0)
                self.assertLessEqual(button.position[0] + button.size[0], width)
            bottom = menu.children[-1].position[1] + menu.children[-1].size[1]
            if bottom > content_h:
                self.assertIn(("add_flag", (Widget.FLAG.SCROLLABLE,)), menu.calls)


class WiFiRowTests(unittest.TestCase):
    def test_long_ssid_signal_and_status_have_separate_slots(self):
        class Widget:
            FLAG = types.SimpleNamespace(SCROLLABLE=1)
            def __init__(self, parent=None):
                self.parent, self.children = parent, []
                self.w, self.h, self.x, self.y, self.anchor = 80, 24, 0, 0, 1
                if parent is not None:
                    parent.children.append(self)
            def set_size(self, w, h):
                self.w, self.h = w, h
            def set_width(self, w):
                self.w = w
            def set_pos(self, x, y):
                self.x, self.y = x, y
            def align(self, anchor, x, y):
                self.anchor, self.x, self.y = anchor, x, y
            def clean(self):
                self.children = []
            def rect(self):
                x, y = self.x, self.y
                if self.anchor in (6, 8):
                    x += self.parent.w - self.w
                if self.anchor in (4, 6):
                    y += self.parent.h - self.h
                elif self.anchor in (7, 8):
                    y += (self.parent.h - self.h) // 2
                return x, y, self.w, self.h
            def __getattr__(self, name):
                return lambda *args: None
        enum = types.SimpleNamespace(MAIN=0, TOP_LEFT=1, BOTTOM_LEFT=4,
                                     BOTTOM_RIGHT=6, LEFT_MID=7, RIGHT_MID=8,
                                     CLICKED=0, DOT=1, RIGHT=3)
        lv = types.SimpleNamespace(obj=Widget, PART=enum, ALIGN=enum,
                                   EVENT=enum, TEXT_ALIGN=enum,
                                   label=types.SimpleNamespace(LONG=enum))
        cls = load_class(APP / "demo_wifi.py", "WiFiUI", {
            "lv": lv, "config": types.SimpleNamespace(THEME_TEXT=1, THEME_ACCENT=2,
                                                       THEME_GREEN=3, THEME_ORANGE=4),
            "gui": types.SimpleNamespace(font_cn=None, font_en=None, lv_color=lambda c: c,
                                         make_label=lambda parent, *args: Widget(parent)),
            "i18n": types.SimpleNamespace(is_chinese=lambda: False), "_t": lambda key: key})
        layout_cls = load_module(APP / "ui_layout.py", "wifi_layout").UILayout
        for width in (190, 240, 319, 320, 440):
            obj = cls.__new__(cls)
            obj.layout = layout_cls(800, 480)
            obj._network_list_width = width + obj.layout.clamp_px(10, 6, 18)
            obj._networks = [("a" * 32, -100, True), ("b" * 32, -40, False)]
            obj._connected_ssid = "a" * 32
            obj.network_list = Widget()
            obj._render_networks()
            for row in obj.network_list.children:
                rects = [child.rect() for child in row.children]
                for i, rect in enumerate(rects):
                    x, y, w, h = rect
                    self.assertGreaterEqual(x, 0)
                    self.assertGreaterEqual(y, 0)
                    self.assertLessEqual(x + w, row.w)
                    self.assertLessEqual(y + h, row.h)
                    self.assertFalse(any(overlaps(rect, other) for other in rects[:i]))


class FontCleanupTests(unittest.TestCase):
    def test_splash_uses_bound_font_and_image_cache_methods(self):
        events = []
        font = types.SimpleNamespace(freetype_font_del=lambda: events.append("font"))
        screen = types.SimpleNamespace(clean=lambda: events.append("clean"),
                                       delete=lambda: events.append("delete"))
        cls = load_class(APP / "splash.py", "SplashScreen", {
            "lv": types.SimpleNamespace(img=types.SimpleNamespace(
                cache_invalidate_src=lambda path: events.append(path))),
            "gui": types.SimpleNamespace(font_cn=None, font_en=None),
            "config": types.SimpleNamespace(ICON_LV_PATH="A:/icons/")})
        obj = cls.__new__(cls)
        obj.screen, obj._large_font, obj._brand_font = screen, font, None
        obj.clean()
        self.assertEqual(events, ["clean", "delete",
                                  "A:/icons/app_center_splash.png", "font"])

    def test_system_page_deletes_font_users_before_fonts(self):
        events = []
        cls = load_class(APP / "demo_system_info.py", "SystemInfoUI", {})
        obj = cls.__new__(cls)
        obj.root = types.SimpleNamespace(delete=lambda: events.append("root"))
        obj._large_fonts = [types.SimpleNamespace(
            freetype_font_del=lambda: events.append("font"))]
        obj.clean()
        obj.clean()
        self.assertEqual(events, ["root", "font"])

    def test_bitmap_fonts_use_object_free_method(self):
        events = []
        lv = types.SimpleNamespace(freetype_uninit=lambda: events.append("freetype"),
                                   deinit=lambda: events.append("lvgl"))
        with patch.dict(sys.modules, {
            "lvgl": lv, "uctypes": types.SimpleNamespace(), "image": types.SimpleNamespace(),
            "config": types.SimpleNamespace(THEME_TEXT=0),
            "media": types.ModuleType("media"),
            "media.display": types.SimpleNamespace(Display=object)}):
            module = load_module(APP / "lvgl_utils.py", "font_cleanup_gui")
        module._lvgl_ready = True
        module._font_en_via_load = module._font_cn_via_load = True
        module.font_en = types.SimpleNamespace(free=lambda: events.append("en"))
        module.font_cn = types.SimpleNamespace(free=lambda: events.append("cn"))
        module.lvgl_deinit()
        self.assertEqual(events, ["en", "cn", "freetype", "lvgl"])


class Resource:
    def __init__(self, name, events, fail=False):
        self.name, self.events, self.fail = name, events, fail

    def release(self):
        self.events.append(self.name)
        if self.fail:
            raise RuntimeError(self.name)

    deinit = release


class LifecycleTests(unittest.TestCase):
    def test_segmentation_preserves_native_mask_and_reuses_display_image(self):
        events = []
        class Base:
            def run(self, frame):
                self.masks[0] = 17
                return [[], [], []]
        class App:
            def start(self):
                self.running = True
        class SensorStub:
            YUV420SP = 1
            RGBP888 = 2
            def __init__(self, **kwargs):
                pass
            def __getattr__(self, name):
                return lambda *args, **kwargs: {}
        class ImageStub:
            def __init__(self, w, h, fmt, alloc=None, data=None):
                events.append((alloc, data))
                self.data = data
            def clear(self):
                raise AssertionError("native output must not be cleared after inference")
        cls = load_class(APP / "demo_yolo_seg.py", "YOLOSegDemo", {
            "Application": App, "AIBase": Base, "Sensor": SensorStub,
            "CAM_CHN_ID_0": 0, "CAM_CHN_ID_2": 2,
            "Display": types.SimpleNamespace(LAYER_VIDEO1=1, bind_layer=lambda **kw: None),
            "config": types.SimpleNamespace(KMODEL_DIR="", CAM_WIN_X=0, CAM_WIN_Y=0),
            "demo_common": types.SimpleNamespace(COCO_LABELS=[]),
            "image": types.SimpleNamespace(Image=ImageStub, ARGB8888=1, ALLOC_REF=2)})
        model = cls.__new__(cls)
        model.__dict__.update(_opened=False, stop_req=False, display_size=[800, 480], masks=[0])
        model.config_preprocess = lambda: None
        model.open()
        self.assertEqual(len(events), 1)
        self.assertIs(events[0][1], model.masks)
        self.assertEqual(events[0][0], 2)
        model.sensor.snapshot = lambda **kw: types.SimpleNamespace(to_numpy_ref=lambda: object())
        shown = []
        model.display = types.SimpleNamespace(show=lambda image: shown.append(image))
        self.assertEqual(model.run_once(), 0)
        self.assertEqual(model.masks[0], 17)
        self.assertIs(shown[0], model._osd_img)
        self.assertEqual(len(events), 1)


    def test_app_tracker_partial_input_allocation_releases_first_tensor(self):
        released = []
        def from_numpy(value):
            if value == "fail":
                raise MemoryError("tensor")
            return types.SimpleNamespace(release=lambda: released.append(value))
        cls = load_class(APP / "demo_nanotracker.py", "_NanoTrackerHead", {
            "AIBase": object, "nn": types.SimpleNamespace(from_numpy=from_numpy)})
        model = cls.__new__(cls)
        with self.assertRaises(MemoryError):
            model.run("template", "fail", [1, 2, 3, 4])
        self.assertEqual(released, ["template"])

    def test_app_tracker_failed_deinit_can_be_retried(self):
        attempts = []
        class Base:
            def deinit(self):
                attempts.append(True)
                if len(attempts) == 1:
                    raise RuntimeError("release")
        cls = load_class(APP / "demo_nanotracker.py", "_NanoTrackerHead", {"AIBase": Base})
        model = cls.__new__(cls)
        model._deinited = False
        with self.assertRaises(RuntimeError):
            model.deinit()
        self.assertFalse(model._deinited)
        model.deinit()
        self.assertTrue(model._deinited)

    def setUp(self):
        self.events = []
        self.nn = types.SimpleNamespace(
            shrink_memory_pool=lambda: self.events.append("shrink"))
        self.namespace = {
            "ScopedTiming": lambda *args: contextlib.nullcontext(),
            "nn": self.nn,
            "gc": types.SimpleNamespace(collect=lambda: self.events.append("gc")),
            "time": types.SimpleNamespace(sleep_ms=lambda _: None),
        }
        self.Base = load_class(ROOT / "resources/libs/AIBase.py", "AIBase",
                               self.namespace)

    def model(self):
        model = self.Base.__new__(self.Base)
        model.debug_mode = 0
        model.kpu = Resource("kpu", self.events)
        model.ai2d = Resource("ai2d", self.events)
        model.results, model.tensors = [1], [2]
        model.masks = bytearray(4)
        return model

    def test_base_release_order_and_idempotence(self):
        model = self.model()
        model.deinit()
        self.assertLess(self.events.index("kpu"), self.events.index("ai2d"))
        self.assertLess(self.events.index("ai2d"), self.events.index("shrink"))
        self.assertIsNone(model.masks)
        events = list(self.events)
        model.deinit()
        self.assertEqual(events, self.events)

    def test_base_continues_cleanup_and_can_retry(self):
        model = self.model()
        model.kpu.fail = True
        with self.assertRaises(RuntimeError):
            model.deinit()
        self.assertIn("ai2d", self.events)
        self.assertIsNone(model.ai2d)
        model.kpu.fail = False
        model.deinit()
        self.assertEqual(self.events.count("ai2d"), 1)
        self.assertTrue(model._deinitialized)

    def test_inference_releases_tensor_when_conversion_fails(self):
        model = self.model()
        tensor = Resource("output", self.events)
        def fail():
            raise MemoryError("ndarray")
        tensor.to_numpy = fail
        model.kpu = types.SimpleNamespace(inputs_size=lambda: 0,
            outputs_size=lambda: 1, run=lambda: None, get_output_tensor=lambda _: tensor)
        with self.assertRaises(MemoryError):
            model.inference([])
        self.assertEqual(self.events, ["output"])

    def test_extra_pipelines_and_tensors_release_after_kpu(self):
        module = types.ModuleType("libs.AIBase")
        module.AIBase = self.Base
        with patch.dict(sys.modules, {"nncase_runtime": self.nn, "libs.AIBase": module}):
            cleanup = load_module(APP / "model_cleanup.py", "model_cleanup")
        model = self.model()
        model.extra = Resource("extra", self.events)
        model.inputs = [Resource("input", self.events)]
        cleanup.deinit_model(model, ("extra",), ("inputs",))
        self.assertLess(self.events.index("kpu"), self.events.index("input"))
        self.assertLess(self.events.index("input"), self.events.index("extra"))
        self.assertIsNone(model.extra)
        self.assertEqual(model.inputs, [])
        cleanup.deinit_model(model, ("extra",), ("inputs",))
        self.assertEqual(self.events.count("extra"), 1)

    def test_model_load_failure_releases_kpu_and_preserves_error(self):
        failure = ValueError("bad model")
        kpu = Resource("kpu", self.events)
        def load(path):
            raise failure
        kpu.load_kmodel = load
        self.nn.kpu = lambda: kpu
        with self.assertRaises(ValueError) as caught:
            self.Base("bad.kmodel")
        self.assertIs(caught.exception, failure)
        self.assertEqual(self.events.count("kpu"), 1)

    def cleanup_module(self):
        module = types.ModuleType("libs.AIBase")
        module.AIBase = self.Base
        with patch.dict(sys.modules, {"nncase_runtime": self.nn, "libs.AIBase": module}):
            return load_module(APP / "model_cleanup.py", "cleanup_fault_test")

    def test_second_ai2d_constructor_failure_releases_first_and_kpu(self):
        cleanup = self.cleanup_module()
        kpu = Resource("kpu", self.events)
        kpu.load_kmodel = lambda path: None
        self.nn.kpu = lambda: kpu
        self.nn.ai2d_format = types.SimpleNamespace(NCHW_FMT=0)
        pipeline = Resource("first-ai2d", self.events)
        pipeline.set_ai2d_dtype = lambda *args: None
        created = []
        def ai2d(*args):
            if created:
                raise MemoryError("second ai2d")
            created.append(pipeline)
            return pipeline
        cls = load_class(APP / "demo_nanotracker.py", "_NanoBackbone", {
            "AIBase": self.Base, "Ai2d": ai2d, "nn": self.nn,
            "np": types.SimpleNamespace(uint8=0), "deinit_model": cleanup.deinit_model})
        with self.assertRaisesRegex(MemoryError, "second ai2d"):
            cls("model", [127, 127], [640, 480])
        self.assertEqual(self.events.count("kpu"), 1)
        self.assertEqual(self.events.count("first-ai2d"), 1)
        self.assertLess(self.events.index("kpu"), self.events.index("first-ai2d"))

    def test_tts_frontend_construction_failure_releases_model(self):
        kpu = Resource("kpu", self.events)
        kpu.load_kmodel = lambda path: None
        self.nn.kpu = lambda: kpu
        def fail(*args):
            raise MemoryError("frontend")
        cls = load_class(APP / "demo_tts_zh.py", "_EncoderApp", {
            "AIBase": self.Base, "aidemo": types.SimpleNamespace(tts_zh_create=fail)})
        with self.assertRaisesRegex(MemoryError, "frontend"):
            cls("model", "dict", "phase", "map")
        self.assertEqual(self.events.count("kpu"), 1)

    def test_tts_frontend_destroy_error_does_not_skip_kpu_release(self):
        def fail(handle):
            raise RuntimeError("frontend destroy")
        cls = load_class(APP / "demo_tts_zh.py", "_EncoderApp", {
            "AIBase": self.Base, "aidemo": types.SimpleNamespace(tts_zh_destroy=fail)})
        obj = cls.__new__(cls)
        obj.ttszh = object()
        obj.kpu = Resource("kpu", self.events)
        with self.assertRaisesRegex(RuntimeError, "frontend destroy"):
            obj.deinit()
        self.assertEqual(self.events.count("kpu"), 1)
        self.assertIsNotNone(obj.ttszh)

    def test_failed_model_cleanup_retries_without_double_releasing_ai2d(self):
        cleanup = self.cleanup_module()
        model = self.model()
        attempts = []
        def release():
            attempts.append(1)
            if len(attempts) == 1:
                raise RuntimeError("transient release")
            self.events.append("kpu")
        model.kpu.release = release
        cleanup.deinit_with_retry(model)
        self.assertEqual(len(attempts), 2)
        self.assertEqual(self.events.count("ai2d"), 1)
        self.assertTrue(model._deinitialized)

    def tts_class(self, **overrides):
        namespace = {name: "" for name in
                     ("KW_ENCODER", "KW_DECODER", "KW_HIFIGAN", "KW_DICT", "KW_PHASE", "KW_MAP")}
        namespace.update(Application=object, gc=types.SimpleNamespace(collect=lambda: None))
        namespace.update(overrides)
        return load_class(APP / "demo_tts_zh.py", "TTSZHDemo", namespace)

    def test_tts_stop_failure_still_closes_stream_and_audio(self):
        events = self.events
        def fail_stop():
            events.append("stop")
            raise RuntimeError("stop failed")
        stream = types.SimpleNamespace(stop_stream=fail_stop,
                                       close=lambda: events.append("close"))
        audio = types.SimpleNamespace(open=lambda **kw: stream,
                                      terminate=lambda: events.append("terminate"))
        def fail_open(*args):
            raise OSError("bad wav")
        cls = self.tts_class(PyAudio=lambda: audio, paInt16=1, SAVE_WAV="bad.wav",
                             wave=types.SimpleNamespace(open=fail_open))
        app = cls.__new__(cls)
        app._play_wav()
        self.assertEqual(events, ["stop", "close", "terminate"])

    def test_tts_clears_all_buffers_even_when_one_tensor_release_fails(self):
        cls = self.tts_class()
        app = cls.__new__(cls)
        tensors = [Resource("encoder", self.events), Resource("decoder", self.events)]
        tensors[0].fail = True
        app.encoder = types.SimpleNamespace(cur_img=object(), results=[1],
                                             tensors=[tensors[0]], data=[1])
        app.decoder = types.SimpleNamespace(cur_img=object(), results=[1],
                                             tensors=[tensors[1]])
        app.hifigan = types.SimpleNamespace(cur_img=object(), results=[1],
                                             tensors=[], hifi_input=object(), mel_data=[1])
        app._clear_synthesis_buffers()
        self.assertEqual(app.encoder.tensors, [tensors[0]])
        self.assertEqual(app.decoder.tensors, [])
        self.assertIsNone(app.encoder.data)
        self.assertIsNone(app.hifigan.hifi_input)
        self.assertEqual(app.hifigan.mel_data, [])
        self.assertTrue(all(model.cur_img is None and not model.results
                            for model in (app.encoder, app.decoder, app.hifigan)))
        tensors[0].fail = False
        app._clear_synthesis_buffers()
        self.assertEqual(app.encoder.tensors, [])
        self.assertEqual(self.events.count("decoder"), 1)

    def test_all_app_model_constructors_have_local_rollback(self):
        count = 0
        for path in APP.glob("*.py"):
            for cls in ast.parse(path.read_text()).body:
                if not isinstance(cls, ast.ClassDef) or not any(
                        isinstance(base, ast.Name) and base.id == "AIBase"
                        for base in cls.bases):
                    continue
                init = next(n for n in cls.body
                            if isinstance(n, ast.FunctionDef) and n.name == "__init__")
                self.assertIsInstance(init.body[0], ast.Try, (path, cls.name))
                self.assertTrue(any(isinstance(n, ast.Raise)
                                    for n in init.body[0].handlers[0].body))
                count += 1
        self.assertGreaterEqual(count, 30)

    def test_application_close_runs_final_hook_on_error(self):
        Application = load_module(APP / "app_contract.py", "contract").Application
        events = self.events
        class Demo(Application):
            def stop(self):
                events.append("stop")
                raise RuntimeError("stop")
            def deinit(self):
                events.append("deinit")
                raise RuntimeError("deinit")
            def _release_owned_resources(self):
                events.append("final")
        app = Demo.create(object())
        app.close()
        app.close()
        self.assertEqual(events, ["stop", "deinit", "final"])
        self.assertIsNone(app.display)


if __name__ == "__main__":
    unittest.main()
