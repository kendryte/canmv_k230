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
#pragma once

#include <stdint.h>

#include <pthread.h>

#include "py/mpprint.h"
#include "py/obj.h"
#include "py/ringbuf.h"
#include "shared/runtime/interrupt_char.h"

#include "drv_gpio.h"
#include "hal_syscall.h"

extern ringbuf_t       stdin_ringbuf;
extern pthread_mutex_t mp_atomic_mux;

extern const mp_print_t mp_stdout_print;

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

#include "machine/modmachine.h"

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
