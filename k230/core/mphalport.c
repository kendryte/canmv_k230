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

#include <sys/time.h>

#include "py/mphal.h"
#include "py/mpstate.h"
#include "py/obj.h"
#include "py/objstr.h"
#include "py/stream.h"

#include "extmod/misc.h"

#include "shared/runtime/pyexec.h"
#include "shared/timeutils/timeutils.h"

#include "hal_syscall.h"
#include "hal_utils.h"

#include "repl_transport/repl_transport.h"

#if MICROPY_PY_STRING_TX_GIL_THRESHOLD < 0
#error "MICROPY_PY_STRING_TX_GIL_THRESHOLD must be positive"
#endif

static uint8_t stdin_ringbuf_array[8192];
ringbuf_t      stdin_ringbuf = { stdin_ringbuf_array, sizeof(stdin_ringbuf_array), 0, 0 };

pthread_mutex_t mp_atomic_mux = PTHREAD_MUTEX_INITIALIZER;

int mp_hal_stdin_rx_chr(void)
{
    for (;;) {
        repl_transport_rx();

        int c = ringbuf_get(&stdin_ringbuf);
        if (c != -1) {
            return c;
        }
        MICROPY_EVENT_POLL_HOOK
    }
}

mp_uint_t mp_hal_stdout_tx_strn(const char* str, size_t len)
{
    // Only release the GIL if many characters are being sent
    mp_uint_t ret         = len;
    bool      did_write   = false;
    bool      release_gil = len > MICROPY_PY_STRING_TX_GIL_THRESHOLD;

#if MICROPY_DEBUG_PRINTERS && MICROPY_DEBUG_VERBOSE && MICROPY_PY_THREAD_GIL
    // If verbose debug output is enabled some strings are printed before the
    // GIL mutex is set up.  When that happens, no Python code is running and
    // therefore the interpreter doesn't care about the GIL not being ready.
    release_gil = release_gil && (MP_STATE_VM(gil_mutex).handle != NULL);
#endif // MICROPY_DEBUG_PRINTERS && MICROPY_DEBUG_VERBOSE && MICROPY_PY_THREAD_GIL

    if (release_gil) {
        MP_THREAD_GIL_EXIT();
    }

    ret = repl_transport_tx(str, len);

    if (release_gil) {
        MP_THREAD_GIL_ENTER();
    }

    did_write = true;

#if MICROPY_PY_OS_DUPTERM
    int dupterm_res = mp_os_dupterm_tx_strn(str, len);
    if (dupterm_res >= 0) {
        did_write = true;
        ret       = MIN((mp_uint_t)dupterm_res, ret);
    }
#endif

    return did_write ? ret : 0;
}

///////////////////////////////////////////////////////////////////////////////
// for debug //////////////////////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////////////
static void stdout_tx_strn(const char* str, size_t len)
{
    for (size_t i = 0; i < len; ++i) {
        putchar(str[i]);
    }
}

static void stdout_print_strn(void* env, const char* str, size_t len)
{
    const char* last = str;
    while (len--) {
        if (*str == '\n') {
            if (str > last) {
                stdout_tx_strn(last, str - last);
            }
            stdout_tx_strn("\r\n", 2);
            ++str;
            last = str;
        } else {
            ++str;
        }
    }
    if (str > last) {
        stdout_tx_strn(last, str - last);
    }
}

const mp_print_t mp_stdout_print = { NULL, stdout_print_strn };
///////////////////////////////////////////////////////////////////////////////
// mp_hal delay ///////////////////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////////////
void mp_hal_delay_ms(mp_uint_t ms)
{
    uint64_t us = (uint64_t)ms * 1000ULL;
    uint64_t dt;
    uint64_t t0 = utils_cpu_ticks_us();
    for (;;) {
        mp_handle_pending(true);
        // other handle
        MP_THREAD_GIL_EXIT();
        uint64_t t1 = utils_cpu_ticks_us();
        dt          = t1 - t0;
        if (dt + 1000ULL * 1000ULL >= us) {
            // doing a msleep would take us beyond requested delay time
            usleep(1000); // sleep 1ms, will make a schedule
            MP_THREAD_GIL_ENTER();
            t1 = utils_cpu_ticks_us();
            dt = t1 - t0;
            break;
        } else {
            MP_THREAD_GIL_ENTER();
        }
    }
    if (dt < us) {
        // do the remaining delay accurately
        mp_hal_delay_us(us - dt);
    }
}

void mp_hal_delay_us(mp_uint_t us)
{
    /* not tested time */
    const uint32_t this_overhead = 2;
    const uint32_t pend_overhead = 30;

    // return if requested delay is less than calling overhead
    if (us < this_overhead) {
        return;
    }
    us -= this_overhead;

    uint64_t t0 = utils_cpu_ticks_us();
    for (;;) {
        uint64_t dt = utils_cpu_ticks_us() - t0;
        if (dt >= us) {
            return;
        }
        if (dt + pend_overhead < us) {
            // we have enough time to service pending events
            // (don't use MICROPY_EVENT_POLL_HOOK because it also yields)
            mp_handle_pending(true);
        }
    }
}

void mp_hal_delay_us_fast(uint64_t us)
{
    uint64_t end = utils_cpu_ticks_us() + us;
    while (utils_cpu_ticks_us() < end) { }
}

///////////////////////////////////////////////////////////////////////////////
// mp_hal tick ////////////////////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////////////
mp_uint_t mp_hal_ticks_ms(void) { return utils_cpu_ticks_ms(); }

mp_uint_t mp_hal_ticks_us(void) { return utils_cpu_ticks_us(); }

mp_uint_t mp_hal_ticks_cpu(void) { return utils_cpu_ticks(); }

uint64_t mp_hal_time_ns(void)
{
    struct timeval tv;
    gettimeofday(&tv, NULL);
    uint64_t ns = tv.tv_sec * 1000000000ULL;
    ns += (uint64_t)tv.tv_usec * 1000ULL;
    return ns;
}

///////////////////////////////////////////////////////////////////////////////
// C-level pin HAL ////////////////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////////////
mp_hal_pin_obj_t mp_hal_get_pin_obj(mp_obj_t o) { return machine_pin_get_inst(o); }

int mp_hal_pin_name(mp_hal_pin_obj_t pin) { return pin->pin; }

void mp_hal_pin_input(mp_hal_pin_obj_t pin) { drv_gpio_mode_set(pin, GPIO_DM_INPUT); }

void mp_hal_pin_output(mp_hal_pin_obj_t pin) { drv_gpio_mode_set(pin, GPIO_DM_OUTPUT); }

void mp_hal_pin_open_drain(mp_hal_pin_obj_t pin) { drv_gpio_mode_set(pin, GPIO_DM_OUTPUT_OD); }

void mp_hal_pin_od_low(mp_hal_pin_obj_t pin) { drv_gpio_value_set(pin, 0); }

void mp_hal_pin_od_high(mp_hal_pin_obj_t pin) { drv_gpio_value_set(pin, 1); }

int mp_hal_pin_read(mp_hal_pin_obj_t pin) { return drv_gpio_value_get(pin); }

void mp_hal_pin_write(mp_hal_pin_obj_t pin, int value) { drv_gpio_value_set(pin, value); }

///////////////////////////////////////////////////////////////////////////////
// Irq Releated ///////////////////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////////////
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
