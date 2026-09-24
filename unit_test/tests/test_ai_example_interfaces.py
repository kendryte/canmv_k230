"""Host checks for example call compatibility; no board modules are imported."""
import ast
from collections import Counter
from contextlib import nullcontext
from pathlib import Path
import re
import subprocess
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
PREFIXES = ("05-", "16-", "18-", "19-", "20-", "21-")
BINDINGS = {"aidemo": "port/ai_demo/ai_demo.c", "aicube": "port/ai_cube/ai_cube.c"}


def exports(source):
    objects = {}
    for name, count in re.findall(r"MP_DEFINE_CONST_FUN_OBJ_(\d+)\(\s*(\w+)", source):
        objects[count] = (int(name), int(name))
    for name, low, high in re.findall(
            r"MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN\(\s*(\w+)\s*,\s*(\d+)\s*,\s*(\d+)", source):
        objects[name] = (int(low), int(high))
    return {name: objects[obj] for name, obj in re.findall(
        r"MP_ROM_QSTR\(MP_QSTR_(\w+)\).*?MP_ROM_PTR\(&(\w+)\)", source)
        if obj in objects}


def example_files():
    return sorted(p for d in (ROOT / "resources/examples").iterdir()
                  if d.is_dir() and d.name.startswith(PREFIXES) for p in d.rglob("*.py"))


def dependency_files():
    pending = example_files()
    seen = set()
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = ([node.module] if isinstance(node, ast.ImportFrom) else
                     [a.name for a in node.names] if isinstance(node, ast.Import) else [])
            for name in names:
                if name and name.startswith("libs."):
                    dependency = ROOT / "resources" / (name.replace(".", "/") + ".py")
                    if dependency.is_file():
                        pending.append(dependency)
    return sorted(seen)


def calls(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules, functions = {}, {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in BINDINGS:
                    modules[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module in BINDINGS:
            for alias in node.names:
                if alias.name == "*":
                    raise AssertionError("unsupported wildcard AI import: " + str(path))
                functions[alias.asname or alias.name] = (node.module, alias.name)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name) and fn.value.id in modules:
            yield modules[fn.value.id], fn.attr, node
        elif isinstance(fn, ast.Name) and fn.id in functions:
            yield *functions[fn.id], node


def load_class(relative, name, env):
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name)
    namespace = {"AIBase": object, "ScopedTiming": lambda *args: nullcontext(), **env}
    exec(compile(ast.Module(body=[node], type_ignores=[]), relative, "exec"), namespace)
    return namespace[name]


class ExampleInterfaces(unittest.TestCase):
    def test_all_direct_and_indirect_calls_match_exports(self):
        api = {module: exports((ROOT / path).read_text()) for module, path in BINDINGS.items()}
        total = 0
        for path in dependency_files():
            for module, name, node in calls(path):
                with self.subTest(path=str(path.relative_to(ROOT)), line=node.lineno):
                    self.assertIn(name, api[module])
                    self.assertFalse(node.keywords)
                    self.assertFalse(any(isinstance(a, ast.Starred) for a in node.args))
                    low, high = api[module][name]
                    self.assertTrue(low <= len(node.args) <= high)
                    total += 1
        self.assertGreater(total, 90)

    def test_base_public_arities_remain_compatible(self):
        for module, path in BINDINGS.items():
            old = exports(subprocess.check_output(
                ["git", "show", "canmv_k230:" + path], cwd=ROOT, text=True))
            new = exports((ROOT / path).read_text())
            self.assertEqual(old.keys(), new.keys())
            for name, bounds in old.items():
                self.assertEqual(new[name], (7, 8) if name == "nanotracker_postprocess" else bounds)

    def test_detection_uses_instance_labels_for_all_model_types(self):
        captured = []
        capture = lambda *args: captured.append(args) or []
        cls = load_class("resources/examples/16-AI-Cube/DetectionApp.py", "DetectionApp", {
            "aicube": SimpleNamespace(anchorbasedet_post_process=capture,
                                      anchorfreedet_post_process=capture, gfldet_post_process=capture)})
        obj = cls.__new__(cls)
        obj.__dict__.update(debug_mode=0, labels=["a", "b"], model_input_size=[320, 320],
                            rgb888p_size=[640, 480], strides=[8, 16, 32],
                            confidence_threshold=.5, nms_threshold=.3, anchors=list(range(18)), nms_option=False)
        for kind in ("AnchorBaseDet", "AnchorFreeDet", "GFLDet"):
            obj.model_type = kind
            obj.postprocess([object(), object(), object()])
            self.assertEqual(captured[-1][6], 2)

    def test_segmentation_uses_output_grid_not_camera_size(self):
        for path, class_name, module, function in (
            ("resources/examples/05-AI-Demo/body_seg.py", "BodySegmentationApp", "aidemo", "body_seg_postprocess"),
            ("resources/examples/16-AI-Cube/SegmentationApp.py", "SegmentationApp", "aicube", "seg_post_process")):
            captured = []
            capture = lambda *args: captured.append(args) or object()
            cls = load_class(path, class_name, {
                module: SimpleNamespace(**{function: capture}),
                "np": SimpleNamespace(uint8="uint8", array=lambda *a, **kw: SimpleNamespace(reshape=lambda n: [])),
                "image": SimpleNamespace(Image=lambda *a, **kw: kw["data"], ARGB8888=1, ALLOC_REF=1)})
            obj = cls.__new__(cls)
            obj.__dict__.update(debug_mode=0, num_class=2, results=[SimpleNamespace(shape=(1, 64, 96, 2))],
                                rgb888p_size=[640, 480], model_input_size=[192, 128],
                                display_size=[800, 480], colors=[])
            obj.postprocess(None)
            self.assertEqual(captured[0][2], [64, 96])
            self.assertEqual(captured[0][3], [480, 800])

    def test_nanotracker_releases_inputs_on_partial_creation_failure(self):
        released = []
        def from_numpy(value):
            if value == "fail":
                raise RuntimeError("allocation")
            return SimpleNamespace(release=lambda: released.append(value))
        cls = load_class("resources/examples/05-AI-Demo/nanotracker.py", "TrackerApp", {
            "nn": SimpleNamespace(from_numpy=from_numpy)})
        obj = cls.__new__(cls)
        with self.assertRaisesRegex(RuntimeError, "allocation"):
            obj.run("first", "fail", [10, 10, 20, 20])
        self.assertEqual(released, ["first"])

    def test_nanotracker_success_keeps_seven_argument_call_and_result(self):
        released, captured = [], []
        sentinel = [[], []]
        def postprocess(*args):
            captured.append(args)
            return sentinel
        cls = load_class("resources/examples/05-AI-Demo/nanotracker.py", "TrackerApp", {
            "nn": SimpleNamespace(from_numpy=lambda value: SimpleNamespace(
                release=lambda: released.append(value))),
            "aidemo": SimpleNamespace(nanotracker_postprocess=postprocess)})
        obj = cls.__new__(cls)
        obj.__dict__.update(debug_mode=0, rgb888p_size=[640, 480], thresh=.25,
                            crop_input_size=[127, 127], CONTEXT_AMOUNT=.5)
        outputs, state = [object(), object()], [10, 10, 20, 20]
        obj.inference = lambda tensors: outputs
        self.assertIs(obj.run("template", "search", state), sentinel)
        self.assertEqual(captured, [(outputs[0], outputs[1], [480, 640], .25, state, 127, .5)])
        self.assertEqual(released, ["template", "search"])

    def test_search_cleanup_releases_all_pipelines_and_retries_failures(self):
        events = []
        class Base:
            def deinit(self):
                events.append("base")
        class Pipeline:
            def __init__(self, name, fail=False):
                self.name, self.fail = name, fail
            def deinit(self):
                events.append(self.name)
                if self.fail:
                    self.fail = False
                    raise RuntimeError("release")
        cls = load_class("resources/examples/05-AI-Demo/nanotracker.py", "TrackSrcApp", {
            "AIBase": Base, "gc": SimpleNamespace(collect=lambda: None),
            "nn": SimpleNamespace(shrink_memory_pool=lambda: None)})
        obj = cls.__new__(cls)
        obj.debug_mode = 0
        obj.ai2d_pad, obj.ai2d_crop = Pipeline("pad", True), Pipeline("crop")
        with self.assertRaisesRegex(RuntimeError, "release"):
            obj.deinit()
        self.assertEqual(events, ["base", "pad", "crop"])
        self.assertIsNotNone(obj.ai2d_pad)
        self.assertIsNone(obj.ai2d_crop)
        obj.deinit()
        self.assertIsNone(obj.ai2d_pad)
        self.assertEqual(events, ["base", "pad", "crop", "base", "pad"])


if __name__ == "__main__":
    counts = Counter()
    for path in dependency_files():
        count = sum(1 for _ in calls(path))
        if count:
            group = path.relative_to(ROOT / "resources").parts
            counts[group[1] if group[0] == "examples" else "libs (indirect)"] += count
    print("AI call sites:", dict(sorted(counts.items())), flush=True)
    unittest.main()
