#!/usr/bin/env python3
"""Check native TTS output/error contracts with sanitizers, without a board."""

import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

from check_tts_lazy_regex import ROOT, SOURCES, build_runner


def check_binding(directory, includes):
    # Compile the actual binding function; simulate only MicroPython and the
    # native status result. Any attempt to construct a list on error aborts.
    source_path = ROOT / "port/ai_demo/ai_demo.c"
    source = source_path.read_text()
    start_marker = "STATIC mp_obj_t tts_zh_preprocess("
    end_marker = "STATIC MP_DEFINE_CONST_FUN_OBJ_2"
    try:
        start = source.index(start_marker)
        end = source.index(end_marker, start)
    except ValueError as error:
        raise RuntimeError(
            "Cannot extract tts_zh_preprocess from %s; update check_binding's "
            "start/end markers after refactoring the binding: %r, %r"
            % (source_path, start_marker, end_marker)) from error
    (directory / "tts_binding.inc").write_text(source[start:end])
    harness = directory / "binding.c"
    harness.write_text(r'''
#include <assert.h>
#include <setjmp.h>
#include <stdlib.h>
#include <string.h>
#include "aidemo_type.h"

#define STATIC static
#define MP_OBJ_TO_PTR(x) (x)
#define MP_OBJ_FROM_PTR(x) (x)
#define MP_ERROR_TEXT(x) (x)
typedef struct { int unused; } mp_obj_list_t;
typedef struct { int unused; } aidemo_nlr_cleanup_t;
static const mp_obj_type_t mp_type_ValueError = {0};
static const mp_obj_type_t mp_type_MemoryError = {0};
static const mp_obj_type_t mp_type_RuntimeError = {0};
static const mp_obj_type_t *raised;
static const char *message;
static jmp_buf exception;
static TtsZhStatus fake_status;

static _Noreturn void mp_raise_msg(const mp_obj_type_t *type, const char *text) {
    raised = type;
    message = text;
    longjmp(exception, 1);
}
static _Noreturn void mp_raise_ValueError(const char *text) {
    mp_raise_msg(&mp_type_ValueError, text);
}
static const char *mp_obj_str_get_str(mp_obj_t text) { return text; }
static mp_obj_list_t *mp_obj_new_list(size_t count, void *items) { abort(); }
static void mp_obj_list_append(mp_obj_list_t *list, mp_obj_t item) { abort(); }
static mp_obj_t mp_obj_new_float(float value) { abort(); }
static void aidemo_nlr_cleanup_push(aidemo_nlr_cleanup_t *cleanup,
                                   void (*free_output)(void *), void *output) { abort(); }
static void aidemo_nlr_cleanup_finish(aidemo_nlr_cleanup_t *cleanup) { abort(); }
void tts_zh_free_output(void *output) { abort(); }
TtsZhOutput *tts_zh_frontend_preprocess_safe(TtsZh *tts, const char *text, TtsZhStatus *status) {
    *status = fake_status;
    return NULL;
}
#include "tts_binding.inc"

int main(void) {
    const TtsZhStatus statuses[] = {TTS_ZH_NO_PHONEMES, TTS_ZH_INVALID_ARGUMENT,
                                   TTS_ZH_OUT_OF_MEMORY, TTS_ZH_PREPROCESS_FAILED};
    const mp_obj_type_t *types[] = {&mp_type_ValueError, &mp_type_ValueError,
                                   &mp_type_MemoryError, &mp_type_RuntimeError};
    for (size_t i = 0; i < sizeof(statuses) / sizeof(statuses[0]); ++i) {
        fake_status = statuses[i];
        raised = NULL;
        if (setjmp(exception) == 0) {
            tts_zh_preprocess(NULL, "ABCDEFG");
            abort();
        }
        assert(raised == types[i]);
        if (fake_status == TTS_ZH_NO_PHONEMES) assert(strstr(message, "no usable phonemes"));
    }
}
''')
    executable = directory / "binding"
    subprocess.run(shlex.split(os.environ.get("CC", "cc")) + [
        "-std=c11", "-g", "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
        *includes, str(harness), "-o", str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
    print("Native statuses raise the expected Python exceptions before list creation.")


def main():
    cases = json.loads((ROOT / "unit_test/stubs/tts_frontend_cases.json").read_text())
    with tempfile.TemporaryDirectory(prefix="canmv-tts-frontend-") as tmp:
        directory = Path(tmp)
        calls = []
        for case in cases:
            chunks = ", ".join("{" + ",".join(map(str, chunk)) + "}"
                               for chunk in case["sequences"])
            text = json.dumps(case["input"], ensure_ascii=False)
            calls.append(f"expect_output(tts, {text}, {{{chunks}}});")
        (directory / "tts_frontend_fixtures.inc").write_text("\n".join(calls))
        includes = ["-I", str(ROOT / "port/include/ai_demo"),
                    "-I", str(ROOT / "unit_test/stubs")]
        executable = build_runner(
            ROOT / "port", directory,
            source_names=SOURCES + ("zh_frontend", "tone_sanhi", "jieba_utils",
                                    "tts_zh_preprocess", "VoxCommon"),
            harness_text=(ROOT / "unit_test/tests/tts_frontend_check.cpp").read_text(),
            extra_flags=includes,
            link_flags=["-Wl,--wrap=malloc,--wrap=calloc,--wrap=free"])
        subprocess.run([str(executable), str(ROOT / "resources/examples/utils"), tmp], check=True)
        check_binding(directory, includes)


if __name__ == "__main__":
    main()
