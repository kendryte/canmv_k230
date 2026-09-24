import ast
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[2]
if len(sys.argv) != 2:
    raise SystemExit('usage: check_app_lvgl_bindings.py path/to/lv_mpy.c')
binding = Path(sys.argv[1]).read_text()
globals_body = binding.split('lvgl_globals_table[] = {', 1)[1].split('\n};', 1)[0]
exports = set(re.findall(r'MP_QSTR_(\w+)', globals_body))
all_members = set(re.findall(r'MP_QSTR_(\w+)', binding))
count = 0
errors = []
for path in (root / 'resources/examples/28-APP_CENTER').glob('*.py'):
    tree = ast.parse(path.read_text())
    aliases = {a.asname or a.name for n in ast.walk(tree) if isinstance(n, ast.Import)
               for a in n.names if a.name == 'lvgl'}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        chain, base = [], node
        while isinstance(base, ast.Attribute):
            chain.insert(0, base.attr)
            base = base.value
        if isinstance(base, ast.Name) and base.id in aliases:
            count += 1
            if chain[0] not in exports or any(part not in all_members for part in chain):
                errors.append(f'{path.name}:{node.lineno}: {".".join(chain)}')
print('Checked LVGL attribute expressions:', count)
print('\n'.join(errors) if errors else 'All referenced names are present in the generated binding.')
sys.exit(bool(errors))
