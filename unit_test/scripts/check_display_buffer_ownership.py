#!/usr/bin/env python3
"""Compile production display helpers as C with simulated VO ownership."""

from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / "port/modules/modmedia.display.c").read_text()


def extract_region(name):
    begin, end = f"/* BEGIN {name} */", f"/* END {name} */"
    if source.count(begin) != 1 or source.count(end) != 1:
        raise RuntimeError(f"Expected one BEGIN/END marker pair for {name}")
    start = source.index(begin) + len(begin)
    stop = source.index(end)
    if stop <= start:
        raise RuntimeError(f"Reversed markers for {name}")
    return source[start:stop]


helpers = extract_region("display-buffer-ownership helpers")
disable = extract_region("display-buffer-disable helper")

prefix = r"""
#include <assert.h>
#include <errno.h>
#include <setjmp.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef int k_vo_layer_id;
typedef int32_t k_s32;
typedef uint64_t k_u64;
enum { K_VO_LAYER_VIDEO0 = 0, K_VO_LAYER_OSD0 = 4, K_MAX_VO_LAYER_NR = 8,
       VIRTUAL_DISPLAY_DEVICE = 1 };
typedef struct { int id; } Frame;
typedef struct {
    uint32_t pclk_khz, hactive, hsync_len, hback_porch, hfront_porch;
    uint32_t vactive, vsync_len, vback_porch, vfront_porch;
} k_vo_timing;
typedef struct { int type; k_vo_timing resolution; } k_connector_info;
typedef struct {
    int valid;
    unsigned buffer_size;
    Frame vf_info;
} py_display_buffer_t;
typedef struct {
    int rotated, osd_layer_num, osd_layer_vb_pool_id;
    unsigned osd_buffer_size;
    py_display_buffer_t share_buffer;
    int share_buffer_layer;
    py_display_buffer_t layer_buffer[K_MAX_VO_LAYER_NR];
    int layer_configed[K_MAX_VO_LAYER_NR];
} py_display_inst_t;
static py_display_inst_t py_display_inst;
static k_connector_info connector;
static int current[K_MAX_VO_LAYER_NR], pending[K_MAX_VO_LAYER_NR];
static int allocated, next_id, wait_error, wait_count, last_timeout;
static int disable_error, disable_calls, unbind_calls, info_error;
static const int mp_type_RuntimeError = 0;
static jmp_buf exception;
#define MP_ERROR_TEXT(s) s
_Noreturn static void mp_raise_OSError(int error) { longjmp(exception, error); }
_Noreturn static void mp_raise_msg_varg(const int *type, const char *message, int layers) {
    (void)type; (void)message; (void)layers;
    longjmp(exception, ENOMEM);
}
static int kd_display_get_connector_info(k_connector_info *info) {
    *info = connector;
    return info_error;
}
static bool held(int id) {
    for (int layer = K_VO_LAYER_OSD0; layer < K_MAX_VO_LAYER_NR; ++layer)
        if (current[layer] == id || pending[layer] == id) return true;
    return false;
}
static void vsync(void) {
    for (int layer = K_VO_LAYER_OSD0; layer < K_MAX_VO_LAYER_NR; ++layer) {
        if (pending[layer]) {
            current[layer] = pending[layer];
            pending[layer] = 0;
        }
    }
}
static int kd_mpi_vo_wait_frame_release(int layer, Frame *frame, int timeout) {
    assert(timeout > 0);
    last_timeout = timeout;
    ++wait_count;
    if (wait_error) { errno = wait_error; return -1; }
    if (current[layer] == frame->id || pending[layer] == frame->id) {
        assert(pending[layer] && pending[layer] != frame->id);
        vsync();
    }
    assert(!held(frame->id));
    return 0;
}
static int py_display_alloc_single_buffer(py_display_buffer_t *buffer, int pool, unsigned size) {
    (void)pool;
    assert(++allocated <= py_display_inst.osd_layer_num + 1);
    assert(size == 1920u * 1080u * 4u);
    *buffer = (py_display_buffer_t){1, size, {++next_id}};
    return 0;
}
static int py_display_free_single_buffer(py_display_buffer_t *buffer) {
    if (!buffer->valid) return -1;
    assert(!held(buffer->vf_info.id));
    buffer->valid = 0;
    --allocated;
    return 0;
}
static int kd_display_layer_disable(int layer) {
    ++disable_calls;
    if (disable_error) return -1;
    current[layer] = pending[layer] = 0;
    return 0;
}
static int py_display_unbind_layer_inst(int layer) {
    assert(layer > K_VO_LAYER_VIDEO0 && layer < K_MAX_VO_LAYER_NR);
    ++unbind_calls;
    return 0;
}
"""

tests = r"""
static void reset(int layers) {
    memset(&py_display_inst, 0, sizeof(py_display_inst));
    memset(current, 0, sizeof(current));
    memset(pending, 0, sizeof(pending));
    allocated = next_id = wait_error = wait_count = last_timeout = 0;
    disable_error = disable_calls = unbind_calls = info_error = 0;
    connector = (k_connector_info){.type = VIRTUAL_DISPLAY_DEVICE,
                                  .resolution = {.pclk_khz = 60}};
    py_display_inst.osd_layer_num = layers;
    py_display_inst.osd_buffer_size = 1920u * 1080u * 4u;
    py_display_inst.share_buffer_layer = -1;
}
static py_display_buffer_t *writable(int layer) {
    py_display_buffer_t *buffer = py_display_get_draw_buffer(layer);
    assert(buffer->valid && !held(buffer->vf_info.id));
    assert(buffer->buffer_size >= 1920u * 1080u * 4u);
    return buffer;
}
static void submit(int layer) {
    pending[layer] = writable(layer)->vf_info.id;
    py_display_swap_layer_buffer(layer);
    py_display_inst.layer_configed[layer] = 1;
}
static void expect_error(int layer, int error) {
    py_display_inst_t before = py_display_inst;
    int actual = setjmp(exception);
    if (actual == 0) {
        py_display_get_draw_buffer(layer);
        assert(false && "expected an exception");
    }
    assert(actual == error);
    assert(memcmp(&before, &py_display_inst, sizeof(before)) == 0);
}
static void test_timeouts(void) {
    reset(1);
    const unsigned fps[] = {1, 2, 3, 60};
    const int expected[] = {3000, 1500, 1000, 1000};
    for (unsigned i = 0; i < sizeof(fps) / sizeof(fps[0]); ++i) {
        connector.resolution.pclk_khz = fps[i];
        assert(py_display_frame_release_timeout_ms() == expected[i]);
    }
    connector = (k_connector_info){.resolution = {.pclk_khz = 1000,
        .hactive = 800, .hsync_len = 100, .hback_porch = 50, .hfront_porch = 50,
        .vactive = 800, .vsync_len = 100, .vback_porch = 50, .vfront_porch = 50}};
    assert(py_display_frame_release_timeout_ms() == 3000);
    connector.resolution.pclk_khz = 1001;
    assert(py_display_frame_release_timeout_ms() == 2998);
    connector.resolution.pclk_khz = 500;
    assert(py_display_frame_release_timeout_ms() == 6000);
    connector.resolution.pclk_khz = 60000;
    assert(py_display_frame_release_timeout_ms() == 1000);
    connector.resolution.pclk_khz = 0;
    assert(py_display_frame_release_timeout_ms() == 1000);
    connector.resolution.pclk_khz = 1;
    connector.resolution.hactive = 100000;
    connector.resolution.vactive = 100000;
    assert(py_display_frame_release_timeout_ms() == INT32_MAX - 1);
    connector.resolution = (k_vo_timing){.pclk_khz = 1, .hactive = UINT32_MAX,
        .hsync_len = UINT32_MAX, .vactive = UINT32_MAX};
    assert(py_display_frame_release_timeout_ms() == 1000);
    info_error = -1;
    assert(py_display_frame_release_timeout_ms() == 1000);

    reset(1);
    connector.resolution.pclk_khz = 1;
    submit(K_VO_LAYER_OSD0);
    vsync();
    submit(K_VO_LAYER_OSD0);
    writable(K_VO_LAYER_OSD0);
    assert(last_timeout == 3000);
    puts("PASS timeout policy: virtual/physical timings, rounding, fallback, limits and wait propagation");
}
static void test_disable(void) {
    reset(1);
    submit(K_VO_LAYER_OSD0);
    vsync();
    submit(K_VO_LAYER_OSD0);
    py_display_inst_t before = py_display_inst;
    disable_error = 1;
    assert(py_display_disable_layer_inst(K_VO_LAYER_OSD0) == -1);
    assert(memcmp(&before, &py_display_inst, sizeof(before)) == 0);
    assert(allocated == 2 && unbind_calls == 0);
    disable_error = 0;
    assert(py_display_disable_layer_inst(K_VO_LAYER_OSD0) == 0);
    assert(py_display_inst.share_buffer_layer == -1 && allocated == 1);
    assert(!py_display_inst.layer_configed[K_VO_LAYER_OSD0]);
    assert(unbind_calls == 1 && disable_calls == 2);
    int waits = wait_count, spare = py_display_inst.share_buffer.vf_info.id;
    wait_error = EINTR;
    assert(writable(K_VO_LAYER_OSD0 + 1)->vf_info.id == spare);
    assert(wait_count == waits && allocated == 1);
    assert(py_display_disable_layer_inst(K_VO_LAYER_OSD0) == 0);
    assert(disable_calls == 2 && allocated == 1);

    reset(2);
    submit(K_VO_LAYER_OSD0);
    submit(K_VO_LAYER_OSD0 + 1);
    vsync();
    submit(K_VO_LAYER_OSD0);
    assert(py_display_disable_layer_inst(K_VO_LAYER_OSD0 + 1) == 0);
    assert(py_display_inst.share_buffer_layer == K_VO_LAYER_OSD0);
    assert(held(py_display_inst.share_buffer.vf_info.id));
    writable(K_VO_LAYER_OSD0);
    assert(wait_count == 1);
    puts("PASS production disable: failure/retry, cached spare reuse without waiting, unrelated owner preserved");
}
int main(void) {
    for (int count = 1; count <= 4; ++count) {
        reset(count);
        for (int frame = 0; frame < 1000; ++frame) {
            for (int layer = K_VO_LAYER_OSD0; layer < K_VO_LAYER_OSD0 + count; ++layer)
                submit(layer);
            if (frame % 7 == 0) vsync();
        }
        assert(allocated == count + 1 && wait_count > 0);
        if (count < 4) expect_error(K_VO_LAYER_OSD0 + count, ENOMEM);
        printf("PASS %d layers: 1000 update rounds, %d buffers\n", count, allocated);
    }

    reset(1);
    submit(K_VO_LAYER_OSD0);
    vsync();
    submit(K_VO_LAYER_OSD0);
    const int errors[] = {ETIMEDOUT, EINTR};
    for (unsigned i = 0; i < sizeof(errors) / sizeof(errors[0]); ++i) {
        wait_error = errors[i];
        expect_error(K_VO_LAYER_OSD0, errors[i]);
        assert(held(py_display_inst.share_buffer.vf_info.id));
    }
    wait_error = 0;
    int spare = writable(K_VO_LAYER_OSD0)->vf_info.id;
    assert(writable(K_VO_LAYER_OSD0)->vf_info.id == spare);
    submit(K_VO_LAYER_OSD0);
    assert(py_display_inst.layer_buffer[K_VO_LAYER_OSD0].vf_info.id == spare);
    puts("PASS timeout/interruption preserve ownership; retry and failed-submit recovery");

    test_disable();
    test_timeouts();
    reset(0);
    expect_error(K_VO_LAYER_OSD0, ENOMEM);
    puts("PASS zero-layer budget");
}
"""

with tempfile.TemporaryDirectory(prefix="canmv-display-ownership-") as directory:
    c_file = Path(directory) / "test.c"
    binary = Path(directory) / "test"
    c_file.write_text(prefix + helpers + disable + tests)
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=address,undefined", "-g", str(c_file), "-o", str(binary)],
                   check=True)
    subprocess.run([str(binary)], check=True)
