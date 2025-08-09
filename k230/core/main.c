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

#include "machine/modmachine.h"
#include "repl_transport/repl_transport.h"

#define MICROPYTHON_THREAD_PRIORITY (25)

static int quit_process_flag = 0;

static void sig_int_handler(int signum)
{
    if (signum == SIGINT) {
#if MICROPY_ASYNC_KBD_INTR
#if MICROPY_PY_THREAD_GIL
// Since signals can occur at any time, we may not be holding the GIL when
// this callback is called, so it is not safe to raise an exception here
#error "MICROPY_ASYNC_KBD_INTR and MICROPY_PY_THREAD_GIL are not compatible"
#endif
        mp_obj_exception_clear_traceback(MP_OBJ_FROM_PTR(&MP_STATE_VM(mp_kbd_exception)));
        sigset_t mask;
        sigemptyset(&mask);
        // On entry to handler, its signal is blocked, and unblocked on
        // normal exit. As we instead perform longjmp, unblock it manually.
        sigprocmask(SIG_SETMASK, &mask, NULL);
        nlr_raise(MP_OBJ_FROM_PTR(&MP_STATE_VM(mp_kbd_exception)));
#else
        if (MP_STATE_MAIN_THREAD(mp_pending_exception) == MP_OBJ_FROM_PTR(&MP_STATE_VM(mp_kbd_exception))) {
            // this is the second time we are called, so die straight away
            exit(1);
        }
        quit_process_flag = 1;
        mp_sched_keyboard_interrupt();
#endif
    }
}

MP_NOINLINE int mp_task(void)
{
    volatile uintptr_t stack_top;
    asm volatile("mv %0, sp" : "=r"(stack_top));

#if defined(CONFIG_CANMV_MPY_REPL_OVER_STDIN) && CONFIG_CANMV_MPY_REPL_OVER_STDIN
    repl_transport_stdin_init();
#endif

#if (defined(CONFIG_CANMV_MPY_REPL_OVER_UART) && CONFIG_CANMV_MPY_REPL_OVER_UART)                                              \
    || (defined(CONFIG_CANMV_MPY_REPL_OVER_USB_CDC) && CONFIG_CANMV_MPY_REPL_OVER_USB_CDC)
    repl_transport_serial_init();
#endif

    void* mp_heap = NULL;
    if ((0x00 != posix_memalign(&mp_heap, 64, MICROPY_GC_HEAP_SIZE)) || (NULL == mp_heap)) {
        printf("mp_heap allocation failed!\n");
        while (1) { }
    }

soft_reset:
#if MICROPY_PY_THREAD
    mp_thread_init();
#endif

    // initialise the stack pointer for the main thread
    mp_cstack_init_with_top((void*)stack_top, CONFIG_RTSMART_LWP_APP_STACK_SIZE - 1024);
    gc_init(mp_heap, mp_heap + MICROPY_GC_HEAP_SIZE);
    mp_init();

#if defined(CONFIG_CANMV_MPY_REPL_OVER_STDIN) && CONFIG_CANMV_MPY_REPL_OVER_STDIN
    repl_transport_stdin_enable_raw_mode();
#endif
    readline_init0();

    machine_init();

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
    pyexec_file_if_exists("_boot.py");

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

    {
        nlr_buf_t nlr;
        if (nlr_push(&nlr) == 0) {
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
            nlr_pop();
        } else {
            // swallow exception
        }
    }

soft_reset_exit:
#if defined(CONFIG_CANMV_MPY_REPL_OVER_STDIN) && CONFIG_CANMV_MPY_REPL_OVER_STDIN
    repl_transport_stdin_disable_raw_mode();
#endif

#if MICROPY_PY_THREAD
    mp_thread_deinit();
#endif

    gc_sweep_all();

    mp_hal_stdout_tx_str("MPY: soft reboot\r\n");

    machine_deinit();
    mp_deinit();
    fflush(stdout);

    if (!quit_process_flag) {
        printf("Soft reset.\n");
        goto soft_reset;
    }

    printf("Quit micropython.\n");

    return 0;
}

int main(int argc, char** argv)
{
    printf("MicroPython start in %ld us\n", mp_hal_ticks_us());

    struct sched_param param;
    param.sched_priority = MICROPYTHON_THREAD_PRIORITY;
    pthread_setschedparam(pthread_self(), SCHED_FIFO, &param);

    // enable signal handler
    struct sigaction sa;
    sa.sa_flags   = 0;
    sa.sa_handler = sig_int_handler;
    sigemptyset(&sa.sa_mask);
    sigaction(SIGINT, &sa, NULL);

    return mp_task();
}

void nlr_jump_fail(void* val)
{
    printf("FATAL: uncaught exception %p\n", val);
    mp_obj_print_exception(&mp_stdout_print, MP_OBJ_FROM_PTR(val));
    for (;;) { }
}

// void __assert(const char *file, int line, const char *func, const char *expr) {
void __assert(const char* file, int line, const char* expr)
{
    printf("Assertion '%s' failed, at file %s:%d\n", expr, file, line);
    for (;;) { }
}
