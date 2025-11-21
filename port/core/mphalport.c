/*
 * This file is part of the MicroPython project, http://micropython.org/
 *
 * The MIT License (MIT)
 *
 * Copyright (c) 2015 Damien P. George
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

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <unistd.h>
#include <fcntl.h>
#include <signal.h>
#include <time.h>
#include <sys/time.h>
#include <sys/ioctl.h>
#include <sys/select.h>

#include "py/mphal.h"
#include "py/mpthread.h"
#include "py/runtime.h"
#include "extmod/misc.h"
#include "hal_utils.h"

#if defined(__GLIBC__) && defined(__GLIBC_PREREQ)
#if __GLIBC_PREREQ(2, 25)
#include <sys/random.h>
#define _HAVE_GETRANDOM
#endif
#endif

extern bool process_exit;
extern bool ide_dbg_attach(void);
extern void interrupt_repl(void);
extern void interrupt_ide(void);

STATIC void sigint_handler_other(int signum) {
    if (signum == SIGINT) {
        process_exit = true;
        if (ide_dbg_attach()) {
            interrupt_ide();
        } else {
            interrupt_repl();
        }
    }
}

STATIC void sigint_handler_ctrl_c(int signum) {
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
        process_exit = true;
        mp_thread_set_exception_main(MP_OBJ_FROM_PTR(&MP_STATE_VM(mp_kbd_exception)));
        if (!ide_dbg_attach())
            interrupt_repl();
        #endif
    }
}

void mp_hal_set_interrupt_char(int c) {
    if (c == CHAR_CTRL_C) {
        struct sigaction sa;
        sa.sa_flags = 0;
        sa.sa_handler = sigint_handler_ctrl_c;
        sigemptyset(&sa.sa_mask);
        sigaction(SIGINT, &sa, NULL);
    } else {
        struct sigaction sa;
        sa.sa_flags = 0;
        sa.sa_handler = sigint_handler_other;
        sigemptyset(&sa.sa_mask);
        sigaction(SIGINT, &sa, NULL);
    }
}

#if MICROPY_USE_READLINE == 1

#include <termios.h>

static struct termios orig_termios;

void mp_hal_stdio_mode_raw(void) {
    // save and set terminal settings
    tcgetattr(0, &orig_termios);
    static struct termios termios;
    termios = orig_termios;
    termios.c_iflag &= ~(BRKINT | ICRNL | INPCK | ISTRIP | IXON);
    termios.c_cflag = (termios.c_cflag & ~(CSIZE | PARENB)) | CS8;
    termios.c_lflag = 0;
    termios.c_cc[VMIN] = 1;
    termios.c_cc[VTIME] = 0;
    tcsetattr(0, TCSAFLUSH, &termios);
}

void mp_hal_stdio_mode_orig(void) {
    // restore terminal settings
    tcsetattr(0, TCSAFLUSH, &orig_termios);
}

#endif
///////////////////////////////////////////////////////////////////////////////
// mp_hal stdin & stdout //////////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////////////
// uintptr_t mp_hal_stdio_poll(uintptr_t poll_flags)
// {

// }

int mp_hal_stdin_rx_chr(void) {
    int c;
    extern int usb_rx(void);
    while (1) {
        MP_THREAD_GIL_EXIT();
        c = usb_rx();
        MP_THREAD_GIL_ENTER();
        if (c != -1)
            break;
        mp_handle_pending(true);
    }
    return c;
}

void mp_hal_stdout_tx_str(const char *str) {
    mp_hal_stdout_tx_strn(str, strlen(str));
}

void mp_hal_stdout_tx_strn(const char *str, size_t len) {
    extern bool ide_dbg_attach(void);
    extern bool command_line_mode;
    if (command_line_mode) {
        fwrite(str, 1, len, stdout);
        return;
    }
    if (ide_dbg_attach()) {
        extern void mpy_stdout_tx(const char* data, size_t size);
        mpy_stdout_tx(str, len);
    } else {
        extern int usb_tx(const void* buffer, size_t size);
        extern int usb_cdc_get_dtr(void);

        if (usb_cdc_get_dtr()) {
            usb_tx(str, len);
        }
    }
    mp_os_dupterm_tx_strn(str, len);
}

// replace \n to \r\n
void mp_hal_stdout_tx_strn_cooked(const char *str, size_t len) {
    size_t last_seg = 0;

    for (size_t i = 0; i < len; i++) {
        if (str[i] == '\n') {
            mp_hal_stdout_tx_strn(str + last_seg, i - last_seg);
            mp_hal_stdout_tx_strn("\r\n", 2);
            last_seg = i + 1;
        }
    }
    if (last_seg < len)
        mp_hal_stdout_tx_strn(str + last_seg, len - last_seg);
}

// k230 added
void mp_hal_stdout_tx_str_cooked(const char* str) {
    mp_hal_stdout_tx_strn_cooked(str, strlen(str));
}
///////////////////////////////////////////////////////////////////////////////
// mp_hal delay ///////////////////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////////////
void mp_hal_delay_us(mp_uint_t us) {
    mp_uint_t start = mp_hal_ticks_us();
    mp_uint_t stop = start + us;

    while ((start + 5000) < stop) {
        MP_THREAD_GIL_EXIT();
        usleep(5000);
        MP_THREAD_GIL_ENTER();
        mp_thread_exitpoint(EXITPOINT_ENABLE_SLEEP);
        mp_handle_pending(true);
        start = mp_hal_ticks_us();
    }

    if (stop > start) {
        MP_THREAD_GIL_EXIT();
        usleep(stop - start);
        MP_THREAD_GIL_ENTER();
        mp_thread_exitpoint(EXITPOINT_ENABLE_SLEEP);
        mp_handle_pending(true);
    }
}

void mp_hal_delay_ms(mp_uint_t ms) {
    mp_hal_delay_us(ms * 1000);
}
///////////////////////////////////////////////////////////////////////////////
// mp_hal tick ////////////////////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////////////
#include "hal_utils.h"

mp_uint_t mp_hal_ticks_ms(void) {
    return (mp_uint_t)utils_cpu_ticks_ms();
}

mp_uint_t mp_hal_ticks_us(void) {
    return (mp_uint_t)utils_cpu_ticks_us();
}

uint64_t mp_hal_time_ns(void) {
    return (mp_uint_t)utils_cpu_ticks_ns();
}

mp_uint_t mp_hal_ticks_cpu(void) {
    return (mp_uint_t)utils_cpu_ticks();
}

void mp_hal_delay_us_fast(uint64_t us)
{
    uint64_t end = utils_cpu_ticks_us() + us;
    while (utils_cpu_ticks_us() < end) { }
}

///////////////////////////////////////////////////////////////////////////////
// C-level pin HAL ////////////////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////////////
#include "modmachine.h"

mp_hal_pin_obj_t mp_hal_get_pin_obj(mp_obj_t o)
{
    return machine_pin_get_inst(o);
}

int mp_hal_pin_name(mp_hal_pin_obj_t pin)
{
    return pin->pin;
}

void mp_hal_pin_input(mp_hal_pin_obj_t pin)
{
    drv_gpio_mode_set(pin, GPIO_DM_INPUT);
}

void mp_hal_pin_output(mp_hal_pin_obj_t pin)
{
    drv_gpio_mode_set(pin, GPIO_DM_OUTPUT);
}

void mp_hal_pin_open_drain(mp_hal_pin_obj_t pin)
{
    drv_gpio_mode_set(pin, GPIO_DM_OUTPUT_OD);
}

void mp_hal_pin_od_low(mp_hal_pin_obj_t pin)
{
    drv_gpio_value_set(pin, 0);
}

void mp_hal_pin_od_high(mp_hal_pin_obj_t pin)
{
    drv_gpio_value_set(pin, 1);
}

int mp_hal_pin_read(mp_hal_pin_obj_t pin)
{
    return drv_gpio_value_get(pin);
}

void mp_hal_pin_write(mp_hal_pin_obj_t pin, int value)
{
    drv_gpio_value_set(pin, value);
}

///////////////////////////////////////////////////////////////////////////////
// Irq Releated ///////////////////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////////////
#include "hal_syscall.h"

uint32_t mp_hal_quiet_timing_enter(void)
{
    uint32_t irq_state = 0;
    // irq_state = rt_hw_interrupt_disable();
    return irq_state;
}

void mp_hal_quiet_timing_exit(uint32_t irq_state)
{
    // rt_hw_interrupt_enable(irq_state);
}
