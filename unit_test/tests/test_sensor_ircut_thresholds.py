"""Host checks for Sensor._ircut_thresholds. Does not import board modules."""
import ast
import math
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SENSOR_PY = ROOT / "port/builtin_py/media/sensor.py"


def load_ircut_thresholds():
    tree = ast.parse(SENSOR_PY.read_text(encoding="utf-8"))
    sensor = next(node for node in tree.body
                  if isinstance(node, ast.ClassDef) and node.name == "Sensor")
    function = next(node for node in sensor.body
                    if isinstance(node, ast.FunctionDef) and node.name == "_ircut_thresholds")
    function.decorator_list = []
    function.args.args = function.args.args[1:]
    module = ast.Module(body=[function], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {}
    exec(compile(module, str(SENSOR_PY), "exec"), namespace)
    return namespace["_ircut_thresholds"]


CHECK = load_ircut_thresholds()


class IrcutThresholdTests(unittest.TestCase):
    def call(self, day2night, night2day, rg_min, rg_max, bg_min, bg_max):
        return CHECK(day2night, night2day, rg_min, rg_max, bg_min, bg_max)

    def test_accepts_legal_values_and_coerces_numbers(self):
        self.assertEqual(
            self.call(0.75, 0.20, 1.2, 2.5, 1.2, 2.5),
            (0.75, 0.20, 1.2, 2.5, 1.2, 2.5),
        )
        self.assertEqual(self.call(1, 1e-6, 1, 2, 1, 2), (1.0, 1e-6, 1.0, 2.0, 1.0, 2.0))

    def test_rejects_missing_hysteresis_and_endpoints(self):
        for day2night, night2day in (
            (0.20, 0.20),
            (0.20, 0.30),
            (0.0, 0.0),
            (1.0, 0.0),
            (1.0, 1.0),
            (1.1, 0.2),
        ):
            with self.assertRaises(ValueError):
                self.call(day2night, night2day, 0.1, 0.2, 0.1, 0.2)

    def test_rejects_nan_and_inf(self):
        for bad in (math.nan, math.inf, -math.inf):
            with self.assertRaises(ValueError):
                self.call(bad, 0.2, 0.1, 0.2, 0.1, 0.2)
            with self.assertRaises(ValueError):
                self.call(0.75, bad, 0.1, 0.2, 0.1, 0.2)
            with self.assertRaises(ValueError):
                self.call(0.75, 0.2, bad, 0.3, 0.1, 0.2)

    def test_rejects_closed_or_non_positive_windows(self):
        for window in (
            (0.5, 0.5, 0.1, 0.2),
            (0.4, 0.3, 0.1, 0.2),
            (0.0, 0.2, 0.1, 0.2),
            (0.1, 0.2, 0.2, 0.2),
        ):
            with self.assertRaises(ValueError):
                self.call(0.75, 0.2, *window)

    def test_rejects_non_numeric_input(self):
        for bad in (None, "fast", object()):
            with self.assertRaises(ValueError):
                self.call(bad, 0.2, 0.1, 0.2, 0.1, 0.2)


if __name__ == "__main__":
    unittest.main()
