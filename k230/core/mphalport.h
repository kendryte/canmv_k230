/*
 * This file is part of the MicroPython project, http://micropython.org/
 *
 * Development of the code in this file was sponsored by Microbric Pty Ltd
 *
 * The MIT License (MIT)
 *
 * Copyright (c) 2014 Damien P. George
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
#pragma once

#include <stdint.h>

#include <pthread.h>

#include "py/obj.h"
#include "py/ringbuf.h"
#include "shared/runtime/interrupt_char.h"

#include "drv_gpio.h"
#include "hal_syscall.h"

extern ringbuf_t stdin_ringbuf;
extern pthread_mutex_t mp_atomic_mux;

static inline mp_uint_t mp_begin_atomic_section(void)
{
#if 1
    pthread_mutex_lock(&mp_atomic_mux);
    return 0;
#else
    uint32_t irq_state = 0;
    // irq_state = rt_hw_interrupt_disable();
    return irq_state;
#endif
}

static inline void mp_end_atomic_section(mp_uint_t state)
{
#if 1
    (void)state;
    pthread_mutex_unlock(&mp_atomic_mux);
#else
    // rt_hw_interrupt_enable(irq_state);
#endif
}

// Note: These atomic macros disable interrupts on the calling CPU, and on SMP
// systems also protect against concurrent access to an atomic section on the
// other CPU.
#define MICROPY_BEGIN_ATOMIC_SECTION()    mp_begin_atomic_section()
#define MICROPY_END_ATOMIC_SECTION(state) mp_end_atomic_section(state)

// This macro is used to implement PEP 475 to retry specified syscalls on EINTR
#define MP_HAL_RETRY_SYSCALL(ret, syscall, raise)                                                                              \
    {                                                                                                                          \
        for (;;) {                                                                                                             \
            MP_THREAD_GIL_EXIT();                                                                                              \
            ret = syscall;                                                                                                     \
            MP_THREAD_GIL_ENTER();                                                                                             \
            if (ret == -1) {                                                                                                   \
                int err = errno;                                                                                               \
                if (err == EINTR) {                                                                                            \
                    mp_handle_pending(true);                                                                                   \
                    continue;                                                                                                  \
                }                                                                                                              \
                raise;                                                                                                         \
            }                                                                                                                  \
            break;                                                                                                             \
        }                                                                                                                      \
    }

uint32_t mp_hal_quiet_timing_enter(void);
void     mp_hal_quiet_timing_exit(uint32_t irq_state);

void mp_hal_delay_us_fast(uint64_t us);

#include "machine/machine.h"

#define MP_HAL_PIN_FMT   "%u"
#define mp_hal_pin_obj_t drv_gpio_inst_t*

mp_hal_pin_obj_t mp_hal_get_pin_obj(mp_obj_t o);
int              mp_hal_pin_name(mp_hal_pin_obj_t pin);

void mp_hal_pin_input(mp_hal_pin_obj_t pin);
void mp_hal_pin_output(mp_hal_pin_obj_t pin);
void mp_hal_pin_open_drain(mp_hal_pin_obj_t pin);

void mp_hal_pin_od_low(mp_hal_pin_obj_t pin);
void mp_hal_pin_od_high(mp_hal_pin_obj_t pin);

int  mp_hal_pin_read(mp_hal_pin_obj_t pin);
void mp_hal_pin_write(mp_hal_pin_obj_t pin, int value);
