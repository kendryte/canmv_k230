"""AI libs contracts and fault injection; NumPy is a host numerical reference."""
import ast
import contextlib
import json
from pathlib import Path
import types
import unittest

import numpy as numpy

ROOT = Path(__file__).resolve().parents[2]
LIBS = ROOT / "resources/libs"


def definitions(path, namespace):
    if path.name == "PipeLine.py":
        definitions(LIBS / "DisplayConfig.py", namespace)
    tree = ast.parse(path.read_text())
    nodes = [n for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef))]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


class Native:
    def __init__(self, name, events):
        self.name, self.events = name, events
        self.fail = 0
        self.released = False
    def release(self):
        self.events.append(self.name)
        if self.fail:
            self.fail -= 1
            raise RuntimeError(self.name)
        if self.released:
            raise AssertionError("double release: " + self.name)
        self.released = True
    deinit = release


class Numpy:
    float = numpy.float64
    uint8 = numpy.uint8
    int16 = numpy.int16
    ndarray = staticmethod(numpy.array)
    def __init__(self):
        self.array_calls = 0
        self.fail_ones = False
    def array(self, *args, **kwargs):
        self.array_calls += 1
        return numpy.array(*args, **kwargs)
    def ones(self, *args, **kwargs):
        if self.fail_ones:
            raise MemoryError("output allocation")
        return numpy.ones(*args, **kwargs)
    def __getattr__(self, name):
        return getattr(numpy, name)


class Image:
    def __init__(self, *args, **kwargs):
        self.args, self.kwargs, self.calls = args, kwargs, []
    def clear(self):
        self.calls.append(("clear",))
    def copy_from(self, other):
        self.calls.append(("copy", other))
    def __getattr__(self, name):
        return lambda *args, **kwargs: self.calls.append((name, args, kwargs))


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.events, self.tensors, self.builders, self.pipelines = [], [], [], []
        self.np = Numpy()
        self.fail_dtype = False
        owner = self
        class Builder(Native):
            def run(self, input_tensor, output_tensor):
                if self.fail:
                    self.fail -= 1
                    raise RuntimeError("builder run")
        class Pipeline(Native):
            def __init__(self):
                super().__init__("ai2d", owner.events)
                owner.pipelines.append(self)
            def set_dtype(self, *args):
                if owner.fail_dtype:
                    raise RuntimeError("dtype")
            def build(self, *args):
                b = Builder("builder-" + str(len(owner.builders)), owner.events)
                owner.builders.append(b)
                return b
            def __getattr__(self, name):
                return lambda *args: None
        class Kpu(Native):
            def __init__(self):
                super().__init__("kpu", owner.events)
            def load_kmodel(self, path):
                pass
        def from_numpy(data):
            tensor = Native("tensor-" + str(len(self.tensors)), self.events)
            tensor.data = numpy.array(data, copy=True)
            self.tensors.append(tensor)
            return tensor
        self.nn = types.SimpleNamespace(ai2d=Pipeline, kpu=Kpu, from_numpy=from_numpy,
            shrink_memory_pool=lambda: None,
            ai2d_format=types.SimpleNamespace(NCHW_FMT=0),
            interp_method=types.SimpleNamespace(tf_bilinear=0),
            interp_mode=types.SimpleNamespace(half_pixel=0))
        timing = lambda *args: contextlib.nullcontext()
        common = dict(np=self.np, nn=self.nn, ScopedTiming=timing,
                      gc=types.SimpleNamespace(collect=lambda: None),
                      time=types.SimpleNamespace(sleep_ms=lambda _: None))
        self.base = definitions(LIBS / "AIBase.py", dict(common))["AIBase"]
        self.ai2d = definitions(LIBS / "AI2D.py", dict(common))["Ai2d"]
        utils = definitions(LIBS / "Utils.py", dict(common))
        self.calls = []
        class Postprocess:
            def __getattr__(inner, name):
                def invoke(*args):
                    self.calls.append((name, args))
                    return [[], [], []]
                return invoke
        self.ns = dict(common, AIBase=self.base, Ai2d=self.ai2d,
            ALIGN_UP=lambda v, a: (v + a - 1) // a * a,
            image=types.SimpleNamespace(Image=Image, ARGB8888=4, RGB888=3, ALLOC_REF=0),
            get_colors=lambda n: [(255, 0, 0, 0)] * n,
            center_crop_param=utils["center_crop_param"],
            letterbox_pad_param=utils["letterbox_pad_param"],
            center_pad_param=utils["center_pad_param"],
            softmax=utils["softmax"], sigmoid=utils["sigmoid"],
            aidemo=Postprocess(), aicube=Postprocess())
        self.tasks = definitions(LIBS / "PlatTasks.py", dict(self.ns))
        self.yolos = definitions(LIBS / "YOLO.py", dict(self.ns))

    def test_public_signatures_match_baseline(self):
        expected = json.loads((ROOT / "unit_test/stubs/ai_libs_api.json").read_text())
        actual = {}
        for filename in {key.split(":")[0] for key in expected}:
            for node in ast.parse((LIBS / filename).read_text()).body:
                if isinstance(node, ast.FunctionDef):
                    actual[filename + ":" + node.name] = ast.unparse(node.args)
                elif isinstance(node, ast.ClassDef):
                    for method in node.body:
                        if isinstance(method, ast.FunctionDef):
                            actual[filename + ":" + node.name + "." + method.name] = ast.unparse(method.args)
        expected["PlatTasks.py:DetectionApp.__init__"] = expected[
            "PlatTasks.py:DetectionApp.__init__"].replace("10.13,", "10, 13,")
        for name, signature in expected.items():
            self.assertEqual(actual[name], signature, name)

    def test_scoped_examples_parse_and_explicit_lib_imports_exist(self):
        exports = {}
        for filename in ("AIBase.py", "AI2D.py", "PipeLine.py", "DisplayConfig.py", "Utils.py", "YOLO.py", "PlatTasks.py"):
            names = set()
            for node in ast.parse((LIBS / filename).read_text()).body:
                if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
                    names.add(node.name)
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.Assign):
                    names.update(t.id for t in node.targets if isinstance(t, ast.Name))
            exports["libs." + filename[:-3]] = names
        scanned = 0
        for prefix in ("05", "16", "18", "19", "20", "21", "22", "28"):
            folders = list((ROOT / "resources/examples").glob(prefix + "-*"))
            self.assertTrue(folders, prefix)
            for folder in folders:
                for path in folder.rglob("*.py"):
                    scanned += 1
                    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
                        if isinstance(node, ast.ImportFrom) and node.module in exports:
                            for alias in node.names:
                                if alias.name != "*":
                                    self.assertIn(alias.name, exports[node.module], str(path))
        self.assertGreater(scanned, 100)

    def test_padding_preserves_both_dimensions(self):
        pad = self.ns["center_pad_param"]
        for src in ([2, 5], [5, 2], [641, 479], [640, 480], [800, 480], [480, 854]):
            for dst in ([8, 8], [224, 224], [640, 640], [320, 192]):
                t, b, l, r, scale = pad(src, dst)
                self.assertEqual(int(src[0] * scale) + l + r, dst[0])
                self.assertEqual(int(src[1] * scale) + t + b, dst[1])
                self.assertLessEqual(abs(l-r), 1)
                self.assertLessEqual(abs(t-b), 1)

    def test_default_anchors_and_invalid_anchors(self):
        cls = self.tasks["DetectionApp"]
        model = cls("image", "model", ["one"])
        self.assertEqual(model.anchors[:2], [10, 13])
        self.assertEqual(len(model.anchors), 18)
        model.deinit()
        self.events.clear()
        with self.assertRaises(ValueError):
            cls("image", "model", ["one"], anchors=[1])
        self.assertEqual(self.events.count("kpu"), 1)

    def test_ai2d_dtype_and_failed_build_keep_old_configuration(self):
        obj = self.ai2d()
        obj.set_ai2d_dtype(0, 0, self.np.float, self.np.float)
        obj.build([1, 3, 8, 8], [1, 3, 4, 4])
        old_builder, old_output = obj.ai2d_builder, obj.ai2d_output_tensor
        self.assertEqual(old_output.data.dtype, numpy.float64)
        self.np.fail_ones = True
        with self.assertRaises(MemoryError):
            obj.build([1, 3, 8, 8], [1, 3, 2, 2])
        self.assertIs(obj.ai2d_builder, old_builder)
        self.assertIs(obj.ai2d_output_tensor, old_output)
        self.assertTrue(self.builders[-1].released)
        obj.deinit()

    def test_ai2d_run_failure_releases_only_new_input(self):
        obj = self.ai2d()
        obj.build([1, 3, 8, 8], [1, 3, 4, 4])
        obj.run(numpy.zeros((1, 3, 8, 8)))
        previous = obj.ai2d_input_tensor
        obj.ai2d_builder.fail = 1
        with self.assertRaisesRegex(RuntimeError, "builder run"):
            obj.run(numpy.ones((1, 3, 8, 8)))
        self.assertTrue(self.tensors[-1].released)
        self.assertFalse(previous.released)
        self.assertIs(obj.ai2d_input_tensor, previous)
        obj.deinit()

    def test_ai2d_rebuild_attempts_all_releases_and_retries_failed_one(self):
        obj = self.ai2d()
        obj.build([1, 3, 8, 8], [1, 3, 4, 4])
        obj.run(numpy.zeros((1, 3, 8, 8)))
        old_builder, old_input, old_output = obj.ai2d_builder, obj.ai2d_input_tensor, obj.ai2d_output_tensor
        old_builder.fail = 1
        with self.assertRaises(RuntimeError):
            obj.build([1, 3, 8, 8], [1, 3, 2, 2])
        self.assertTrue(old_input.released)
        self.assertTrue(old_output.released)
        self.assertIn(old_builder, obj._pending_release)
        obj.deinit()
        self.assertTrue(old_builder.released)
        self.assertEqual(obj._pending_release, [])
        obj.deinit()

    def test_ai2d_persistent_release_failure_cannot_grow_pending_list(self):
        obj = self.ai2d()
        data = numpy.zeros((1, 3, 8, 8))
        obj.build(list(data.shape), [1, 3, 4, 4])
        obj.run(data)
        previous = obj.ai2d_input_tensor
        previous.fail = 3
        with self.assertRaises(RuntimeError):
            obj.run(data)
        allocated = len(self.tensors)
        for _ in range(2):
            with self.assertRaises(RuntimeError):
                obj.run(data)
            self.assertEqual(len(self.tensors), allocated)
            self.assertEqual(obj._pending_release, [previous])
        obj.run(data)
        self.assertTrue(previous.released)
        obj.deinit()

    def test_all_task_and_yolo_constructors_release_after_dtype_failure(self):
        self.fail_dtype = True
        options = dict(mode="image", kmodel_path="model", labels=["one", "two"],
                       model_input_size=[8, 8], rgb888p_size=[8, 8],
                       display_size=[16, 16], ocr_dict=["a", ""])
        for namespace, filename in ((self.tasks, "PlatTasks.py"), (self.yolos, "YOLO.py")):
            for node in ast.parse((LIBS / filename).read_text()).body:
                if not isinstance(node, ast.ClassDef) or node.name.startswith("_"):
                    continue
                init = next(n for n in node.body if isinstance(n, ast.FunctionDef) and n.name=="__init__")
                args = {a.arg: options[a.arg] for a in init.args.args if a.arg in options}
                self.events.clear()
                with self.subTest(model=node.name), self.assertRaisesRegex(RuntimeError, "dtype"):
                    namespace[node.name](**args)
                self.assertEqual(self.events.count("kpu"), 1)
                self.assertEqual(self.events.count("ai2d"), 1)

    def metric(self):
        return self.tasks["MetricLearningApp"]("image", "model", model_input_size=[8, 8])

    def test_metric_empty_zero_and_mutable_features(self):
        obj = self.metric()
        self.assertEqual(obj.postprocess([]), {"label": "", "score": 0.0})
        obj.draw_result(Image(), obj.get_cur_result())
        obj.embeddings = [numpy.array([0., 0.]), numpy.array([1., 0.])]
        self.assertEqual(obj.compute_similar(numpy.array([0., 0.])), (-1, 0.0))
        idx, score = obj.compute_similar(numpy.array([-1., 0.]))
        self.assertEqual(idx, 1)
        self.assertEqual(score, -1.)
        obj.embeddings[1][:] = [0., 1.]
        self.assertEqual(obj.compute_similar(numpy.array([0., 1.]))[1], 1.)
        obj.embeddings[1][:] = 0
        self.assertEqual(obj.compute_similar(numpy.array([1., 0.])), (-1, 0.0))
        obj.deinit()

    def test_metric_one_matrix_matches_original_formula(self):
        obj = self.metric()
        rng = numpy.random.default_rng(42)
        obj.embeddings = list(rng.normal(size=(20, 32)))
        emb = rng.normal(size=32)
        expected = numpy.dot(numpy.array(obj.embeddings), emb) / (
            numpy.linalg.norm(numpy.array(obj.embeddings, dtype=float), axis=1) *
            numpy.linalg.norm(emb))
        self.np.array_calls = 0
        index, score = obj.compute_similar(emb)
        self.assertEqual(self.np.array_calls, 1)
        self.assertEqual(index, numpy.argmax(expected))
        self.assertEqual(score, expected[index])
        obj.deinit()

    def test_metric_load_failure_restores_preprocessing_and_original_error(self):
        obj = self.metric()
        obj._preprocess_size = (12, 6)
        restored = []
        obj.config_preprocess = lambda size=None: restored.append(size)
        self.tasks["read_image"] = lambda path: (numpy.zeros((3, 10, 8)), None)
        failure = RuntimeError("inference failed")
        def fail(data):
            raise failure
        obj.preprocess = fail
        with self.assertRaises(RuntimeError) as caught:
            obj.load_image("image", "label")
        self.assertIs(caught.exception, failure)
        self.assertEqual(restored, [[8, 10], (12, 6)])
        self.assertEqual(obj.embeddings, [])
        obj.deinit()

    def test_task_deinit_does_not_clear_external_result_or_feature_lists(self):
        obj = self.metric()
        result, embeddings = obj.cur_result, obj.embeddings
        result["label"] = "retained"
        embeddings.append(numpy.array([1., 2.]))
        obj.deinit()
        self.assertEqual(result["label"], "retained")
        self.assertEqual(len(embeddings), 1)
        self.assertEqual(obj.get_cur_result(), {"label": "", "score": 0.0})
        self.assertEqual(obj.embeddings, [])
        obj.deinit()

    def test_ocr_ctc_join_matches_original_decoding(self):
        obj = self.tasks["OCRRecognitionApp"]("image", "model", [8, 8], ["a", "b", ""])
        for ids in ([0, 0, 2, 0, 1, 1, 2], [2, 2], [1], []):
            values = numpy.full((1, len(ids), 3), -1.)
            for i, value in enumerate(ids):
                values[0, i, value] = 1.
            expected = "".join(obj.ocr_dict[v] for i, v in enumerate(ids)
                               if v != 2 and (i == 0 or ids[i-1] != v))
            self.assertEqual(obj.postprocess([values])["text"], expected)
        obj.deinit()

    def test_yolo_override_geometry_and_default_reset(self):
        for name in ("YOLOv5", "YOLOv8", "YOLO11", "YOLO26"):
            tasks = ("classify", "detect", "segment") if name=="YOLOv5" else (
                "classify", "detect", "segment", "pose", "obb")
            for task in tasks:
                for mode in ("video", "image"):
                    with self.subTest(version=name, task=task, mode=mode):
                        obj = self.yolos[name](task_type=task, mode=mode, kmodel_path="model",
                            labels=["one"], rgb888p_size=[8, 8], model_input_size=[8, 8],
                            display_size=[16, 16])
                        configs = []
                        obj.ai2d.crop = lambda *args: configs.append(("crop", args))
                        obj.ai2d.pad = lambda *args: configs.append(("pad", args))
                        obj.config_preprocess([4, 10])
                        self.assertEqual(obj._active_input_size, [4, 10])
                        if task=="classify":
                            self.assertIn(("crop", (0, 3, 4, 4)), configs)
                        else:
                            self.calls.clear()
                            obj.postprocess([numpy.zeros((1, 6, 6)), numpy.zeros((1, 1, 2, 2))])
                            args = self.calls[-1][1]
                            offset = 2 if task=="segment" else 1
                            self.assertEqual(args[offset], [10, 4])
                            self.assertEqual(args[offset+2], [10, 4] if mode=="image" else [16, 16])
                        if task=="segment" and mode=="image":
                            self.assertEqual(obj.masks.shape, (1, 10, 4, 4))
                        obj.config_preprocess()
                        self.assertEqual(obj._active_input_size, [8, 8] if mode=="image" else [16, 8])
                        obj.deinit()

    def test_yolo_mask_wrapper_reused_and_destination_preserved(self):
        obj = self.yolos["YOLOv8"](task_type="segment", mode="video", kmodel_path="model",
            labels=["one"], model_input_size=[8, 8], display_size=[16, 16])
        dst = Image()
        result = [[[1., 2., 3., 4.]], [0], [0.9]]
        obj.draw_result(result, dst)
        wrapper = obj._mask_image
        obj.draw_result(result, dst)
        self.assertIs(obj._mask_image, wrapper)
        self.assertEqual(sum(c[0]=="copy" for c in dst.calls), 2)
        obj.draw_result([[], [], []], dst)
        self.assertEqual(dst.calls[-1], ("clear",))
        obj.deinit()
        self.assertIsNone(obj._mask_image)


class PipeLineTests(unittest.TestCase):
    def make_pipeline(self, failure=None):
        events, faults = [], {failure: 1} if failure else {}
        def hit(name):
            events.append(name)
            if faults.get(name, 0):
                faults[name] -= 1
                raise RuntimeError(name)
        class Display:
            LT9611,ST7701,HX8399,NT35516,NT35532,GC9503,AML020T,JD9852,ILI9806,VIRT=range(10)
            LAYER_VIDEO1, LAYER_OSD3 = 1, 3
            def init(self, *args, **kwargs):
                self.init_args, self.init_kwargs = args, kwargs
                hit("display init")
            def width(self):
                hit("display width")
                return 640
            def height(self): return 480
            def bind_layer(self, **kwargs): hit("bind")
            def disable_layer(self, layer): hit("disable")
            def deinit(self): hit("display deinit")
        class Sensor:
            YUV420SP=0
            RGBP888=1
            def __init__(self, **kwargs): self.init_kwargs = kwargs
            def reset(self):
                hit("reset")
                self.reset_done = True
            def set_framesize(self, **kwargs): hit("framesize")
            def set_pixformat(self, *args, **kwargs): hit("pixformat")
            def bind_info(self, **kwargs): return {}
            def run(self): hit("sensor run")
            def stop(self, is_del=False):
                if not is_del and not getattr(self, "reset_done", False):
                    raise AssertionError("should call reset first")
                self.reset_done = False
                hit("sensor stop")
            def snapshot(self, **kwargs):
                return types.SimpleNamespace(to_numpy_ref=lambda: "borrowed")
        def image(*args):
            hit("image")
            return Image(*args)
        ns = dict(ScopedTiming=lambda *a: contextlib.nullcontext(),
            ALIGN_UP=lambda v,a: (v+a-1)//a*a,
            Display=Display(), Sensor=Sensor, CAM_CHN_ID_0=0, CAM_CHN_ID_2=2,
            image=types.SimpleNamespace(Image=image, ARGB8888=4),
            os=types.SimpleNamespace(uname=lambda: ("board",), exitpoint=lambda *a: None,
                                     EXITPOINT_ENABLE_SLEEP=0))
        cls = definitions(LIBS / "PipeLine.py", ns)["PipeLine"]
        return cls(display_size=[800, 480]), events, faults

    def test_normal_destroy_order_idempotence_and_frame_ownership(self):
        obj, events, _ = self.make_pipeline()
        obj.create()
        self.assertEqual(obj.get_display_size(), [640, 480])
        self.assertEqual(obj.get_frame(), "borrowed")
        self.assertIsNotNone(obj.cur_frame)
        obj.destroy()
        self.assertLess(events.index("disable"), events.index("sensor stop"))
        self.assertLess(events.index("display deinit"), events.index("sensor stop"))
        self.assertIsNone(obj.sensor)
        self.assertIsNone(obj.cur_frame)
        self.assertIsNone(obj.osd_img)
        before = list(events)
        obj.destroy()
        self.assertEqual(events, before)

    def test_auto_display_board_policy_and_actual_resolution(self):
        boards = {
            "k230_canmv": "LT9611", "k230_canmv_v3p0": "LT9611",
            "k230_evb": "HX8399", "k230d_evb": "HX8399",
            "k230_canmv_rtt_evb": "NT35516",
            "k230_canmv_01studio": "ST7701", "k230_canmv_lckfb": "ST7701",
            "k230_canmv_yahboom": "ST7701", "k230_canmv_mrt": "ST7701",
            "k230_canmv_hiwonder": "ST7701",
            "k230_canmv_dongshanpi": "ILI9806", "k230_canmv_gt6700": "GC9503",
            "k230_canmv_wondermk": "JD9852", "k230_labplus_1956": "ST7701",
            "k230d_canmv_bpi_zero": "ST7701", "k230d_canmv_atk_dnk230d": "ST7701",
            "k230d_canmv_junroc_ai_cam": "ST7701",
            "k230d_canmv_lushanpi_lite": "ST7701", "k230d_canmv_mini": "ST7701",
            "k230d_labplus_ai_camera": "ST7701", "k230d_labplus_ai_camera_v2": "ST7701",
        }
        for board, driver in boards.items():
            with self.subTest(board=board):
                old, _, _ = self.make_pipeline()
                ns = old.create.__globals__
                ns["os"].uname = lambda: (board,)
                obj = type(old)(display_mode="auto")
                obj.create()
                display = ns["Display"]
                self.assertEqual(display.init_args, (getattr(display, driver),))
                self.assertNotIn("width", display.init_kwargs)
                self.assertNotIn("height", display.init_kwargs)
                self.assertEqual(obj.get_display_size(), [640, 480])
                self.assertEqual(obj.osd_img.args[:2], (640, 480))
                if driver == "NT35516":
                    self.assertEqual(obj.sensor.init_kwargs["fps"], 30)
                obj.destroy()

    def test_auto_display_unknown_board_and_explicit_override(self):
        old, events, _ = self.make_pipeline()
        ns = old.create.__globals__
        with self.assertRaisesRegex(ValueError, "set display_mode explicitly"):
            type(old)(display_mode="auto")
        self.assertEqual(events, [])
        for mode, driver in (("hdmi", "LT9611"), ("lcd", "ST7701"), ("virt", "VIRT")):
            obj = type(old)(display_mode=mode, display_size=[800, 480])
            obj.create()
            self.assertEqual(ns["Display"].init_args, (getattr(ns["Display"], driver),))
            self.assertEqual(ns["Display"].init_kwargs["width"], 800)
            self.assertEqual(ns["Display"].init_kwargs["height"], 480)
            self.assertEqual(obj.get_display_size(), [640, 480])
            obj.destroy()

    def test_visual_demos_initialize_auto_display_before_models(self):
        count = 0
        for path in (ROOT / "resources/examples/05-AI-Demo").glob("*.py"):
            tree = ast.parse(path.read_text())
            main = next((n for n in tree.body if isinstance(n, ast.If)
                         and isinstance(n.test, ast.Compare)
                         and isinstance(n.test.left, ast.Name)
                         and n.test.left.id == "__name__"), None)
            if main is None:
                continue
            assignments = {t.id: n for n in main.body if isinstance(n, ast.Assign)
                           for t in n.targets if isinstance(t, ast.Name)}
            if "display_mode" not in assignments:
                continue
            count += 1
            self.assertEqual(assignments["display_mode"].value.value, "auto", path.name)
            calls = [n for n in ast.walk(main) if isinstance(n, ast.Call)]
            pipeline = next(n for n in calls if isinstance(n.func, ast.Name)
                            and n.func.id == "PipeLine")
            kwargs = {k.arg: ast.unparse(k.value) for k in pipeline.keywords}
            self.assertEqual(kwargs["display_size"], "display_size", path.name)
            self.assertTrue(any(isinstance(n, ast.Assign) and n.lineno < pipeline.lineno
                                and any(isinstance(t, ast.Name) and t.id == "display_size"
                                        for t in n.targets)
                                and isinstance(n.value, ast.Constant) and n.value.value is None
                                for n in main.body), path.name)
            create = next(n for n in calls if isinstance(n.func, ast.Attribute)
                          and ast.unparse(n.func) == "pl.create")
            get_size = assignments["display_size"]
            self.assertEqual(ast.unparse(get_size.value), "pl.get_display_size()", path.name)
            self.assertLess(create.lineno, get_size.lineno, path.name)
        self.assertEqual(count, 35)

    def test_create_failure_rolls_back_every_completed_stage(self):
        for stage in ("reset", "display init", "display width", "framesize",
                      "pixformat", "image", "bind", "sensor run"):
            with self.subTest(stage=stage):
                obj, events, _ = self.make_pipeline(stage)
                with self.assertRaisesRegex(RuntimeError, stage):
                    obj.create()
                self.assertIsNone(obj.sensor)
                self.assertIsNone(obj.osd_img)
                self.assertFalse(obj._display_ready)
                before = list(events)
                obj.destroy()
                self.assertEqual(events, before)
                obj.create()
                obj.destroy()

    def test_failed_display_cleanup_retains_scanned_buffers_for_retry(self):
        obj, events, faults = self.make_pipeline()
        obj.create()
        sensor, osd = obj.sensor, obj.osd_img
        faults.update({"disable": 1, "display deinit": 1})
        with self.assertRaises(RuntimeError):
            obj.destroy()
        self.assertIs(obj.sensor, sensor)
        self.assertIs(obj.osd_img, osd)
        self.assertNotIn("sensor stop", events)
        obj.destroy()
        self.assertIsNone(obj.sensor)
        self.assertIsNone(obj.osd_img)

    def test_sensor_stop_failure_retries_without_reclosing_display(self):
        obj, events, faults = self.make_pipeline()
        obj.create()
        faults["sensor stop"] = 1
        with self.assertRaises(RuntimeError):
            obj.destroy()
        self.assertIsNotNone(obj.sensor)
        obj.destroy()
        self.assertEqual(events.count("display deinit"), 1)
        self.assertEqual(events.count("sensor stop"), 2)


if __name__ == "__main__":
    unittest.main()
