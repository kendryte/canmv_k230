/*
 * This file is part of the MicroPython project, http://micropython.org/
 *
 * The MIT License (MIT)
 *
 * Copyright (c) 2013, 2014 Damien P. George
 * Copyright (c) 2014-2017 Paul Sokolovsky
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */

#include "generated/autoconf.h"

#include <pthread.h>
#include <signal.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "py/builtin.h"
#include "py/compile.h"
#include "py/gc.h"
#include "py/mphal.h"
#include "py/mpthread.h"
#include "py/nlr.h"
#include "py/objstr.h"
#include "py/repl.h"
#include "py/runtime.h"
#include "py/stackctrl.h"
#include "shared/runtime/pyexec.h"
#if MICROPY_USE_READLINE == 1
#include "shared/readline/readline.h"
#endif
#include "extmod/misc.h"
#include "extmod/modnetwork.h"
#include "extmod/modplatform.h"
#include "extmod/vfs.h"
#include "extmod/vfs_posix.h"
#include "genhdr/mpversion.h"

#include "ide_dbg.h"
#include "multimedia_wrap.h"
#include "mpp_vb_mgmt.h"
#include "drivers/drv_canmv_misc_dev.h"

// Compile-time checks

#if !MICROPY_PY_SYS_PATH
#error "The unix port requires MICROPY_PY_SYS_PATH=1"
#endif

#if !MICROPY_PY_SYS_ARGV
#error "The unix port requires MICROPY_PY_SYS_ARGV=1"
#endif

#ifndef MICROPY_GC_SPLIT_HEAP_N_HEAPS
#define MICROPY_GC_SPLIT_HEAP_N_HEAPS (1)
#endif

#ifndef CONFIG_CANMV_REPL_UART_ID
#define CONFIG_CANMV_REPL_UART_ID (-1)
#endif

// Defines

#define SDCARD_MOUNT "/sdcard"
#define PATHLIST_SEP_CHAR ':'
#define FORCED_EXIT (0x100)

// Forward declarations

MP_NOINLINE int main_(int argc, char **argv);

// HAL
void mp_hal_uart_init(int id);
void mp_hal_uart_reader_start(void);
void mp_hal_stdout_tx_str_cooked(const char *str);
void mp_hal_stdin_clear(void);

// K230 subsystem init/deinit
void machine_pin_irq_init(void);
void machine_timer_irq_init(void);
#if defined(CONFIG_ENABLE_MODULE_UART_PERIODIC_TX)
void uart_periodic_tx_deinit_all(void);
#endif
#if defined(CONFIG_ENABLE_MODULE_WEBRTC)
void webrtc_deinit_all(void);
#endif
void fb_alloc_init0(void);
void fb_free_all(void);
void py_display_deinit(void);
void lv_deinit(void);
void freetype_deinit(void);
void py_media_vbmgmt_init(void);
void py_media_vbmgmt_deinit_pre(void);
void py_media_vbmgmt_deinit(void);
#if CONFIG_ENABLE_NETWORK_RT_WLAN
void network_rt_wlan_deinit(void);
#endif
#if MICROPY_PY_BLUETOOTH
void mp_bluetooth_deinit(void);
#endif

// Shared state
#if CONFIG_CANMV_IDE_SUPPORT
extern bool repl_script_running; // defined in ide_dbg.c
#else
bool repl_script_running = false;
#endif

static inline void repl_script_running_store(bool running)
{
    __atomic_store_n(&repl_script_running, running, __ATOMIC_RELEASE);
}

///////////////////////////////////////////////////////////////////////////////
// Global state
///////////////////////////////////////////////////////////////////////////////

static int system_exit;
static int mp_irq_cnt;
bool is_repl_intr = false;

#if MICROPY_ENABLE_GC
long heap_size = 1024 * 1024 * 4;
#endif

///////////////////////////////////////////////////////////////////////////////
// System & IRQ state helpers
///////////////////////////////////////////////////////////////////////////////

void system_set_exiting_flag(bool exiting)
{
    __atomic_store_n(&system_exit, exiting ? 1 : 0, __ATOMIC_RELAXED);
}

bool system_is_exiting(void)
{
    return __atomic_load_n(&system_exit, __ATOMIC_RELAXED) != 0;
}

void mp_irq_enter(void)
{
    __atomic_add_fetch(&mp_irq_cnt, 1, __ATOMIC_RELAXED);
}

void mp_irq_exit(void)
{
    __atomic_sub_fetch(&mp_irq_cnt, 1, __ATOMIC_RELAXED);
}

bool in_mp_irq_handler(void)
{
    return __atomic_load_n(&mp_irq_cnt, __ATOMIC_RELAXED) != 0;
}

static inline bool repl_interrupt_load(void)
{
    return __atomic_load_n(&is_repl_intr, __ATOMIC_ACQUIRE);
}

static inline void repl_interrupt_store(bool interrupted)
{
    __atomic_store_n(&is_repl_intr, interrupted, __ATOMIC_RELEASE);
}

///////////////////////////////////////////////////////////////////////////////
// MicroPython helpers (stderr, exception, execute)
///////////////////////////////////////////////////////////////////////////////

void stderr_print_strn(void *env, const char *str, size_t len) {
    mp_hal_stdout_tx_strn_cooked(str, len);
}

const mp_print_t mp_stderr_print = {NULL, stderr_print_strn};

// If exc is SystemExit, return value where FORCED_EXIT bit set,
// and lower 8 bits are SystemExit value. For all other exceptions,
// return 1.
STATIC int handle_uncaught_exception(mp_obj_base_t *exc) {
    // check for SystemExit
    if (mp_obj_is_subclass_fast(MP_OBJ_FROM_PTR(exc->type), MP_OBJ_FROM_PTR(&mp_type_SystemExit))) {
        // None is an exit value of 0; an int is its value; anything else is 1
        mp_obj_t exit_val = mp_obj_exception_get_value(MP_OBJ_FROM_PTR(exc));
        mp_int_t val = 0;
        if (exit_val != mp_const_none && !mp_obj_get_int_maybe(exit_val, &val)) {
            val = 1;
        }
        return FORCED_EXIT | (val & 255);
    }

    // Report all other exceptions
    mp_obj_print_exception(&mp_stderr_print, MP_OBJ_FROM_PTR(exc));
    return 1;
}

// Returns standard error codes: 0 for success, 1 for all other errors,
// except if FORCED_EXIT bit is set then script raised SystemExit and the
// value of the exit is in the lower 8 bits of the return value
STATIC int execute_from_str(const char *str, size_t len, mp_parse_input_kind_t input_kind) {
    mp_hal_set_interrupt_char(CHAR_CTRL_C);

    nlr_buf_t nlr;
    if (nlr_push(&nlr) == 0) {
        mp_lexer_t *lex = mp_lexer_new_from_str_len(MP_QSTR__lt_stdin_gt_, str, len, false);
        mp_parse_compile_execute(lex, input_kind, mp_globals_get(), mp_locals_get());

        mp_hal_set_interrupt_char(-1);
        mp_handle_pending(true);
        nlr_pop();
        return 0;

    } else {
        // uncaught exception
        mp_hal_set_interrupt_char(-1);
        mp_handle_pending(false);
        return handle_uncaught_exception(nlr.ret_val);
    }
}

#if MICROPY_USE_READLINE != 1
STATIC char *strjoin(const char *s1, int sep_char, const char *s2) {
    int l1 = strlen(s1);
    int l2 = strlen(s2);
    char *s = malloc(l1 + l2 + 2);
    memcpy(s, s1, l1);
    if (sep_char != 0) {
        s[l1] = sep_char;
        l1 += 1;
    }
    memcpy(s + l1, s2, l2);
    s[l1 + l2] = 0;
    return s;
}
#endif

///////////////////////////////////////////////////////////////////////////////
// REPL & script execution
///////////////////////////////////////////////////////////////////////////////

STATIC int do_repl(void) {
    #if MICROPY_USE_READLINE == 1
    // use MicroPython supplied readline
    for (;;) {
      nlr_buf_t nlr;
      if (nlr_push(&nlr) == 0)
      {
        if (pyexec_mode_kind == PYEXEC_MODE_RAW_REPL)
        {
          if (pyexec_raw_repl() != 0)
          {
            break;
          }
        }
        else
        {
          if (pyexec_friendly_repl() != 0)
          {
            break;
          }
        }
      }
      nlr_pop();
    }
    return 0;
    #else
    mp_hal_stdout_tx_str_cooked("CanMV version: "CANMV_VER);
    mp_hal_stdout_tx_str_cooked("\nUse Ctrl-D to exit, Ctrl-E for paste mode\n");

    // use simple readline
    for (;;) {
        char *line = prompt((char *)mp_repl_get_ps1());
        if (line == NULL) {
            // EOF
            return 0;
        }
        while (mp_repl_continue_with_input(line)) {
            char *line2 = prompt((char *)mp_repl_get_ps2());
            if (line2 == NULL) {
                break;
            }
            char *line3 = strjoin(line, '\n', line2);
            free(line);
            free(line2);
            line = line3;
        }

        repl_script_running_store(true);
        int ret = execute_from_str(line, strlen(line), MP_PARSE_SINGLE_INPUT);
        repl_script_running_store(false);
        if (ret & FORCED_EXIT) {
            return ret;
        }
        free(line);
    }

    #endif
}

STATIC int do_str(const char *str) {
    repl_script_running_store(true);
    int ret = execute_from_str(str, strlen(str), MP_PARSE_FILE_INPUT);
    repl_script_running_store(false);
    return ret;
}

STATIC void run_ide_script_once(void) {
    nlr_buf_t nlr;
    if (nlr_push(&nlr) == 0) {
        gc_collect();
        char* script = ide_dbg_get_script();
        if (script) {
            // interrupt_repl() suppresses IRQ callbacks while the previous
            // execution context is being left. The new script has a valid VM.
            system_set_exiting_flag(false);
            exec_type_t etype = ide_dbg_get_exec_type();
            if (etype == EXEC_FILE) {
                char banner[320];
                snprintf(banner, sizeof(banner), "[CanMV] Running: %s\n", script);
                mp_hal_stdout_tx_str(banner);
                int ret = pyexec_file(script);
                mp_hal_stdout_tx_str(ret ? "[CanMV] Script completed\n"
                                          : "[CanMV] Script failed\n");
            } else {
                do_str(script);
            }
        }
        nlr_pop();
    } else {
        mp_obj_print_exception(&mp_plat_print, (mp_obj_t)nlr.ret_val);
    }
    ide_dbg_on_ide_script_end();
}

///////////////////////////////////////////////////////////////////////////////
// Entry point
///////////////////////////////////////////////////////////////////////////////

int main(int argc, char **argv) {
    printf("CanMV K230 start in %ld us\n", mp_hal_ticks_us());

    mp_hal_uart_init(CONFIG_CANMV_REPL_UART_ID);

#if CONFIG_CANMV_IDE_SUPPORT
    ide_dbg_start();
#else
    mp_hal_uart_reader_start();
#endif

    // Capture stack top ASAP. main_ must not be inlined (see MP_NOINLINE).
    return main_(argc, argv);
}

MP_NOINLINE int main_(int argc, char **argv) {
    #ifdef SIGPIPE
    // Do not raise SIGPIPE, instead return EPIPE. Otherwise, e.g. writing
    // to peer-closed socket will lead to sudden termination of MicroPython
    // process. SIGPIPE is particularly nasty, because unix shell doesn't
    // print anything for it, so the above looks like completely sudden and
    // silent termination for unknown reason. Ignoring SIGPIPE is also what
    // CPython does. Note that this may lead to problems using MicroPython
    // scripts as pipe filters, but again, that's what CPython does. So,
    // scripts which want to follow unix shell pipe semantics (where SIGPIPE
    // means "pipe was requested to terminate, it's not an error"), should
    // catch EPIPE themselves.
    signal(SIGPIPE, SIG_IGN);
    signal(SIGINT, SIG_IGN);
    #endif

    struct sched_param param;
    param.sched_priority = 25;
    int sched_error = pthread_setschedparam(pthread_self(), SCHED_FIFO, &param);
    if (sched_error != 0) {
        fprintf(stderr, "[mpy] pthread_setschedparam failed: %d\n", sched_error);
    }

    repl_interrupt_store(false);

    #if MICROPY_ENABLE_GC
    char *gc_heap = NULL;
    if(0x00 != posix_memalign((void **)&gc_heap, 4096, heap_size)) {
        printf("Failed to allocate memory for GC heap of size %ld\n", heap_size);
        exit(1);
    }
    #endif

    // Define a reasonable stack limit to detect stack overflow.
    mp_uint_t stack_limit = CONFIG_RTSMART_LWP_APP_STACK_SIZE - 1024; //128 * 1024 * (sizeof(void *) / 4);
soft_reset:
    // Reset system exit flag on soft reset
    system_set_exiting_flag(false);
    #if MICROPY_PY_THREAD
    mp_thread_init();
    #endif
    mp_stack_ctrl_init();
    mp_stack_set_limit(stack_limit);

    #if MICROPY_ENABLE_GC
    gc_init(gc_heap, gc_heap + heap_size);
    #endif

    #if MICROPY_ENABLE_PYSTACK
    static mp_obj_t pystack[1024];
    mp_pystack_init(pystack, &pystack[MP_ARRAY_SIZE(pystack)]);
    #endif

    mp_init();

    #if MICROPY_VFS_POSIX
    {
        // Mount the host FS at the root of our internal VFS
        mp_obj_t args[2] = {
            MP_OBJ_TYPE_GET_SLOT(&mp_type_vfs_posix, make_new)(&mp_type_vfs_posix, 0, 0, NULL),
            MP_OBJ_NEW_QSTR(MP_QSTR__slash_),
        };
        mp_vfs_mount(2, args, (mp_map_t *)&mp_const_empty_map);
        MP_STATE_VM(vfs_cur) = MP_STATE_VM(vfs_mount_table);
    }
    #endif

    {
        // sys.path starts as [""], then entries from MICROPY_PY_SYS_PATH_DEFAULT
        mp_sys_path = mp_obj_new_list(0, NULL);
        mp_obj_list_append(mp_sys_path, MP_OBJ_NEW_QSTR(MP_QSTR_));

        char *path = MICROPY_PY_SYS_PATH_DEFAULT;
        if (*path == PATHLIST_SEP_CHAR) {
            ++path;
        }
        bool path_remaining = *path;
        while (path_remaining) {
            char *path_entry_end = strchr(path, PATHLIST_SEP_CHAR);
            if (path_entry_end == NULL) {
                path_entry_end = path + strlen(path);
                path_remaining = false;
            }
            mp_obj_list_append(mp_sys_path, mp_obj_new_str_via_qstr(path, path_entry_end - path));
            path = path_entry_end + 1;
        }
    }

    mp_obj_list_init(MP_OBJ_TO_PTR(mp_sys_argv), 0);
    
    fb_alloc_init0();

    #if MICROPY_PY_NETWORK
    mod_network_init();
    #endif

    machine_pin_irq_init();
    machine_timer_irq_init();

    py_media_vbmgmt_init();
    mp_hal_stdin_clear();
    mp_hal_set_interrupt_char(-1);
    ide_dbg_clear_soft_reset_request();

    #if MICROPY_PY_THREAD
    // Initialization is complete and subsequent pending exceptions run inside
    // the normal script/REPL exception boundaries.
    mp_thread_set_main_ready(true);
    #endif

    // Auto-run boot.py/main.py immediately -- never block boot waiting for an IDE
    // that may never connect. Only skip auto-exec if the IDE/extension is already
    // attached right now (e.g. it stayed connected across a soft reset). If it
    // attaches later while a script runs, the attach path soft-resets and
    // ide_dbg_auto_exec_allowed() then keeps boot.py/main.py idle until hard reboot.
    bool ide_connected = ide_dbg_is_connected();

    if (!repl_interrupt_load() && !ide_connected && ide_dbg_auto_exec_allowed()) {
        FILE*      script_file = NULL;
        const int* stage_ptr   = NULL;
        char*      script_str  = NULL;

        char* scripts_to_run[2]   = { SDCARD_MOUNT "/boot.py", SDCARD_MOUNT "/main.py" };
        int   scripts_stage[2][2] = { { STAGE_BOOTPY_START, STAGE_BOOTPY_END }, { STAGE_MAINPY_START, STAGE_MAINPY_END } };

        // Check file conditions
        bool main_exists     = (access(SDCARD_MOUNT "/main.py", F_OK) == 0);
        bool bad_main_exists = (access(SDCARD_MOUNT "/bad_main.py", F_OK) == 0);
        bool use_fallback    = (!main_exists && bad_main_exists);

        if (use_fallback) {
            scripts_to_run[1] = SDCARD_MOUNT "/fallback.py";

            scripts_stage[1][0] = STAGE_FALLBACK_PY_START;
            scripts_stage[1][1] = STAGE_FALLBACK_PY_END;
        }

        // Process both boot.py and main/fallback scripts
        for (size_t i = 0; i < sizeof(scripts_to_run) / sizeof(scripts_to_run[0]); i++) {
            if (ide_dbg_is_connected() || ide_dbg_has_script() || 0x00 != access(scripts_to_run[i], F_OK)) {
                continue;
            }

            script_file = fopen(scripts_to_run[i], "r");
            if (script_file != NULL) {
                stage_ptr = scripts_stage[i];

                // Get file size
                if (fseek(script_file, 0, SEEK_END) == 0) {
                    long script_size = ftell(script_file);
                    if (script_size >= 0 && fseek(script_file, 0, SEEK_SET) == 0) {
                        script_str = malloc(script_size + 1);
                        if (script_str != NULL) {
                            size_t bytes_read = fread(script_str, 1, script_size, script_file);
                            fclose(script_file);
                            script_file = NULL;
                            if (bytes_read == (size_t)script_size) {
                                script_str[script_size] = '\0';

                                // Execute script
                                ide_dbg_on_script_start();
                                int stage = stage_ptr[0];
                                canmv_misc_dev_ioctl(MISC_DEV_CMD_SET_AUTO_EXEC_PY_STAGE, &stage);

                                do_str(script_str);

                                ide_dbg_on_script_end();
                                stage = stage_ptr[1];
                                canmv_misc_dev_ioctl(MISC_DEV_CMD_SET_AUTO_EXEC_PY_STAGE, &stage);
                            } else {
                                printf("read auto boot script failed\n");
                            }
                            free(script_str);
                        }
                    }
                }
            }

            if (script_file != NULL) {
                fclose(script_file);
            }
        }

        if (repl_interrupt_load() && !ide_dbg_has_script()) {
            goto main_thread_exit;
        }
    }

    for (;;) {
        while (ide_dbg_has_script()) {
            repl_interrupt_store(false);
            fprintf(stdout, "[mpy] enter ide script\n");
            run_ide_script_once();
        }

        if (ide_dbg_take_soft_reset_request()) {
            break;
        }

        fprintf(stdout, "[mpy] enter repl\n");
        do_repl();

        repl_interrupt_store(false);

        if (!ide_dbg_has_script()) {
            break;
        }
    }
main_thread_exit:
    fprintf(stderr, "[mpy] exit, reset\n");

    #if MICROPY_PY_THREAD
    // Stop asynchronous IDE exception injection before any VM-owned state or
    // synchronization primitive is torn down.
    mp_thread_set_main_ready(false);
    #endif

    #if defined(CONFIG_ENABLE_MODULE_UART_PERIODIC_TX)
    uart_periodic_tx_deinit_all();
    #endif
    #if defined(CONFIG_ENABLE_MODULE_WEBRTC)
    webrtc_deinit_all();
    #endif
    ide_dbg_on_soft_reset();
    ide_dbg_vo_wbc_stop();
    py_display_deinit();

    // exit other thread
    mp_thread_set_exception_other(mp_obj_new_exception(&mp_type_SystemExit));
    MP_THREAD_GIL_EXIT();

    #if MICROPY_PY_SYS_SETTRACE
    MP_STATE_THREAD(prof_trace_callback) = MP_OBJ_NULL;
    #endif

    mp_hal_stdout_tx_str("MPY: soft reboot\r\n");

    #if MICROPY_PY_SYS_ATEXIT
    // Beware, the sys.settrace callback should be disabled before running sys.atexit.
    if (mp_obj_is_callable(MP_STATE_VM(sys_exitfunc))) {
        mp_call_function_0(MP_STATE_VM(sys_exitfunc));
    }
    #endif

    #if MICROPY_PY_MICROPYTHON_MEM_INFO
    if (mp_verbose_flag) {
        mp_micropython_mem_info(0, NULL);
    }
    #endif
    
    #if MICROPY_PY_THREAD
    mp_thread_shutdown_workers();
    #endif

    // Native RTSP threads and listener sockets are not owned by MicroPython's
    // worker-thread registry, so close them explicitly before network teardown.
    RtspServer_DeInitAll();
    RtspPlayer_DeInitAll();

    #if MICROPY_PY_BLUETOOTH
    mp_bluetooth_deinit();
    #endif
    #if CONFIG_ENABLE_NETWORK_RT_WLAN
    network_rt_wlan_deinit();
    #endif

    lv_deinit();
    py_media_vbmgmt_deinit_pre();
    fb_free_all();

    gc_sweep_all();

    mp_deinit();

    #if MICROPY_PY_THREAD
    mp_thread_deinit();
    #endif

    freetype_deinit();
    py_media_vbmgmt_deinit();
 
    goto soft_reset;
}

///////////////////////////////////////////////////////////////////////////////
// NLR fail handler
///////////////////////////////////////////////////////////////////////////////

void nlr_jump_fail(void *val) {
    #if MICROPY_USE_READLINE == 1
    // mp_hal_stdio_mode_orig();
    #endif
    fprintf(stderr, "FATAL: uncaught NLR %p\n", val);
    exit(1);
}
