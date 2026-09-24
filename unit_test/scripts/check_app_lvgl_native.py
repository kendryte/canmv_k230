import importlib.util
from pathlib import Path
import subprocess
import sys

if len(sys.argv) != 2:
    raise SystemExit('usage: check_app_lvgl_native.py path/to/native_layout_check')
path = Path(__file__).resolve().parents[2] / 'resources/examples/28-APP_CENTER/ui_layout.py'
spec = importlib.util.spec_from_file_location('layout', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
sizes = ((240,240), (320,240), (480,272), (480,320), (640,480), (800,480),
         (854,480), (1024,600), (1280,720), (1920,1080), (480,480), (240,320),
         (480,800), (720,1280))
cases = 0
for width, height in sizes:
    layout = module.UILayout(width, height)
    for connected in (False, True):
        for stats in (False, True):
            values = [width, height, layout.card_w, layout.card_h, layout.icon_y,
                      layout.text_h, layout.text_y, layout.font_size, layout.footer_h]
            rects = layout.footer_rects(stats, connected)
            for key in ('dot', 'status', 'fps', 'result', 'wifi'):
                values.extend(rects[key])
            result = subprocess.run([sys.argv[1]],
                input=' '.join(map(str, values)), text=True, capture_output=True, timeout=10)
            if result.returncode:
                raise AssertionError((width, height, connected, stats, result.stdout, result.stderr))
            cases += 1
print('Native LVGL card/footer layout cases passed:', cases)
