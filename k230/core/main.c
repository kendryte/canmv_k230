/* Copyright (c) 2025, Canaan Bright Sight Co., Ltd
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 * 1. Redistributions of source code must retain the above copyright
 * notice, this list of conditions and the following disclaimer.
 * 2. Redistributions in binary form must reproduce the above copyright
 * notice, this list of conditions and the following disclaimer in the
 * documentation and/or other materials provided with the distribution.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND
 * CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
 * INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF
 * MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
 * DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
 * CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
 * SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
 * BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
 * SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
 * INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
 * WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
 * NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */

#include <stdio.h>
#include <string.h>

#include <pthread.h>
#include <signal.h>

#include "py/builtin.h"
#include "py/compile.h"
#include "py/cstack.h"
#include "py/gc.h"
#include "py/mphal.h"
#include "py/nlr.h"
#include "py/repl.h"
#include "py/runtime.h"

#include "extmod/vfs.h"
#include "extmod/vfs_posix.h"

#include "shared/readline/readline.h"
#include "shared/runtime/pyexec.h"
#include "shared/timeutils/timeutils.h"

#include "repl/repl.h"

#define MICROPYTHON_THREAD_PRIORITY (25)

// defined by lwp
#define USER_STACK_VSTART 0x270000000UL
#define USER_STACK_VEND   0x300000000UL

int main(int argc, char** argv)
{
    int                stack_dummy;
    volatile uintptr_t stack_top = (char*)&stack_dummy;

    // signal(SIGPIPE, SIG_IGN);
    // signal(SIGINT, SIG_IGN);

    struct sched_param param;
    param.sched_priority = MICROPYTHON_THREAD_PRIORITY;
    pthread_setschedparam(pthread_self(), SCHED_FIFO, &param);

    // repl init uart or usb cdc
#if defined(CONFIG_CANMV_MPY_REPL_OVER_STDIN) && CONFIG_CANMV_MPY_REPL_OVER_STDIN
    repl_stdin_init();
#endif

    void* mp_heap = malloc(MICROPY_GC_HEAP_SIZE);
    if (mp_heap == NULL) {
        printf("mp_heap allocation failed!\n");
        while (1) { }
    }

soft_reset:
    // initialise the stack pointer for the main thread
    mp_cstack_init_with_top((void*)stack_top, MICROPY_STACK_SIZE);
    gc_init(mp_heap, mp_heap + MICROPY_GC_HEAP_SIZE);
    mp_init();

#if defined(CONFIG_CANMV_MPY_REPL_OVER_STDIN) && CONFIG_CANMV_MPY_REPL_OVER_STDIN
    repl_stdin_enable_raw_mode();
#endif
    readline_init0();

#if MICROPY_VFS_POSIX
    {
        // Mount the host FS at the root of our internal VFS
        mp_obj_t args[2] = {
            MP_OBJ_TYPE_GET_SLOT(&mp_type_vfs_posix, make_new)(&mp_type_vfs_posix, 0, 0, NULL),
            MP_OBJ_NEW_QSTR(MP_QSTR__slash_),
        };
        mp_vfs_mount(2, args, (mp_map_t*)&mp_const_empty_map);
        MP_STATE_VM(vfs_cur) = MP_STATE_VM(vfs_mount_table);
    }
#endif

    // Run frozen _boot.py
    pyexec_frozen_module("_boot.py", false);

    // Run /sdcard/boot.py
    int ret = pyexec_file_if_exists("/sdcard/boot.py");
    if (ret & PYEXEC_FORCED_EXIT) {
        goto soft_reset_exit;
    }

    if (pyexec_mode_kind == PYEXEC_MODE_FRIENDLY_REPL) {
        // If /sdcard/bad_main.py exists, skip main.py and run fallback.py
        if (mp_import_stat("/sdcard/bad_main.py") == MP_IMPORT_STAT_FILE) {
            ret = pyexec_file_if_exists("/sdcard/fallback.py");
            if (ret & PYEXEC_FORCED_EXIT) {
                goto soft_reset_exit;
            }
        } else {
            // Otherwise run main.py
            ret = pyexec_file_if_exists("/sdcard/main.py");
            if (ret & PYEXEC_FORCED_EXIT) {
                goto soft_reset_exit;
            }
        }
    }

    for (;;) {
        if (pyexec_mode_kind == PYEXEC_MODE_RAW_REPL) {
            if (pyexec_raw_repl() != 0) {
                break;
            }
        } else {
            if (pyexec_friendly_repl() != 0) {
                break;
            }
        }
    }

soft_reset_exit:
#if defined(CONFIG_CANMV_MPY_REPL_OVER_STDIN) && CONFIG_CANMV_MPY_REPL_OVER_STDIN
    repl_stdin_disable_raw_mode();
#endif

#if MICROPY_PY_THREAD
    mp_thread_deinit();
#endif

    gc_sweep_all();

    mp_hal_stdout_tx_str("MPY: soft reboot\r\n");

    mp_deinit();
    fflush(stdout);
    goto soft_reset;

    printf("Quit micropython.\n");

    return 0;
}

void nlr_jump_fail(void* val)
{
    printf("NLR jump failed\n");
    for (;;) { }
}

// void __assert(const char *file, int line, const char *func, const char *expr) {
void __assert(const char* file, int line, const char* expr)
{
    printf("Assertion '%s' failed, at file %s:%d\n", expr, file, line);
    for (;;) { }
}

#if !MICROPY_DEBUG_PRINTERS
// With MICROPY_DEBUG_PRINTERS disabled DEBUG_printf is not defined but it
// is still needed by esp-open-lwip for debugging output, so define it here.
#include <stdarg.h>
int mp_vprintf(const mp_print_t* print, const char* fmt, va_list args);

int DEBUG_printf(const char* fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    int ret = mp_vprintf(MICROPY_DEBUG_PRINTER, fmt, ap);
    va_end(ap);
    return ret;
}
#endif
