# CANMV unit_test

This directory contains a host-side GoogleTest scaffold for CANMV source validation.

## Current coverage
- Functional unit tests for C sources:
  - `port/omv/common/array.c`
  - `port/omv/common/ringbuf.c`
  - `port/omv/alloc/unaligned_memcpy.c`
  - `port/omv/common/mutex.c`
  - `port/omv/common/ff_wrapper.c`
- Source-wide catalog-driven tests for all `*.c`, `*.cc`, `*.cpp`, `*.h`, `*.hpp`, and `*.py` files under the CANMV root:
  - catalog completeness and metadata validation
  - file readability/non-empty checks
  - Python file catalog coverage checks
- Static source contract tests for upgraded high-risk areas:
  - MPP binding module dictionary/object coverage
  - `modmpp.c` API module references
  - MicroPython binding include-shape checks
  - board `mpconfigboard.h` / `manifest.py` pairing
- Auto-generated catalog:
  - `ALL_SOURCE_UNIT_TEST_SUGGESTIONS.md`

## Run
```bash
cd unit_test
./compile_run.sh
./build/canmv_unit_tests
```

`compile_run.sh` always performs a clean build and verifies/installs gtest when missing.
- Some environment will not auto trigger unit test, hence manually run it.

## AI Port Regressions

Run `python3 -B unit_test/tests/test_ai_port.py` from the repository root for
display geometry, registry consistency, and mocked Python resource lifecycles.
The GTest target also includes RVV scalar-reference and segmentation ownership
tests. The latter injects allocation and drawing failures into the production
output helper; it does not emulate OpenCV algorithms.

For memory checks, configure CMake with
`-DCMAKE_C_FLAGS="-fsanitize=address,undefined -fno-omit-frame-pointer"` and
the same `CMAKE_CXX_FLAGS`. Native RVV execution and real media/LVGL resources
require the target board.


### AI Shared Library Regressions

The following host tests need NumPy as a numerical reference. Install it in a
test environment, not in the board's MicroPython filesystem:

```sh
python3 -m venv /tmp/canmv-ai-libs-tests
/tmp/canmv-ai-libs-tests/bin/python -m pip install numpy
/tmp/canmv-ai-libs-tests/bin/python -B unit_test/tests/test_ai_libs.py
```

The suite checks the 89 pre-change public signatures (allowing only the corrected
default anchors), scoped example imports, padding, model and Ai2d rollback,
PipeLine cleanup, YOLO geometry and mask-wrapper reuse, metric-learning results,
and OCR decoding. The API snapshot is in `stubs/ai_libs_api.json`; do not update
it merely to silence a compatibility failure. Device modules are mocked, and
NumPy does not emulate all ulab behavior. K230 output and timing checks remain
required before claiming board performance or long-term memory stability.

### Example Interface Compatibility

Run `python3 -B unit_test/tests/test_ai_example_interfaces.py` from the repository root.
The test checks all Python files in examples 05/16/18/19/20/21 and their local
library dependencies against the native aidemo/aicube export tables. It also
checks base-branch argument compatibility and exercises selected example
postprocessors with mock device modules.

Native NanoTracker behavior is covered by
`canmv_unit_tests --gtest_filter='NanoTrackerPostprocess.*'`: legacy/explicit
scale equivalence, unchanged inputs, independent calls, extreme logits,
threshold behavior and invalid candidates. These host checks do not replace
end-to-end inference on K230.


### App Center LVGL Compatibility

Check the actual generated MicroPython exports after building the firmware:

```sh
python3 -B unit_test/scripts/check_app_lvgl_bindings.py /data/rtos_sdk_0810/output/k230_canmv_01studio_defconfig/canmv/lvgl/lv_mpy.c
python3 -B unit_test/tests/test_ai_port.py
```

For native layout checks, run these commands from the repository root. The host
build uses the same LVGL source, software rendering and built-in 16/20 px fonts;
it does not emulate the panel, touch controller, Chinese FreeType glyphs or OSD
scanout. It verifies actual CONTENT sizing, maximum heights, alignment anchors
and card/footer coordinates for 56 resolution/state combinations.

```sh
cmake -S port/3rd-party/lv_bindings/lvgl -B /tmp/canmv-lvgl-host -DLV_CONF_PATH="$PWD/unit_test/stubs/lvgl_layout_conf.h" -DLV_CONF_BUILD_DISABLE_EXAMPLES=ON -DLV_CONF_BUILD_DISABLE_DEMOS=ON -DBUILD_SHARED_LIBS=ON
cmake --build /tmp/canmv-lvgl-host -j8
cc unit_test/tests/lvgl_native_layout_check.c -Iport/3rd-party/lv_bindings/lvgl -DLV_CONF_PATH="$PWD/unit_test/stubs/lvgl_layout_conf.h" -L/tmp/canmv-lvgl-host/lib -Wl,-rpath,/tmp/canmv-lvgl-host/lib -llvgl -lm -o /tmp/canmv_native_layout_check
python3 -B unit_test/scripts/check_app_lvgl_native.py /tmp/canmv_native_layout_check
```

### AI 显示适配回归

`python3 -B unit_test/tests/test_ai_display.py` 验证共享显示策略、实际尺寸传递、双摄窗口、LVGL 侧栏、UVC/MP4 缩放与资源生命周期。该测试仅需主机 Python 标准库，不能替代实板显示和帧率验证。
