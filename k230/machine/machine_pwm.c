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
#include "py/obj.h"
#include "py/runtime.h"

#include "extmod/modmachine.h"

#include "drv_fpioa.h"
#include "drv_pwm.h"

struct _machine_pwm_obj_t {
    mp_obj_base_t base;
    uint8_t       channel;
    uint8_t       pin;
    bool          active;
    bool          invert;
};

// Print PWM info
static void mp_machine_pwm_print(const mp_print_t* print, mp_obj_t self_in, mp_print_kind_t kind)
{
    machine_pwm_obj_t* self = MP_OBJ_TO_PTR(self_in);

    mp_int_t freq = mp_obj_get_int(mp_machine_pwm_freq_get(self));
    mp_int_t duty = mp_obj_get_int(mp_machine_pwm_duty_get(self));

    mp_printf(print, "PWM(channel=%u, pin=%d, freq=%d, duty=%d)", self->channel, self->pin, freq, duty);
}

// Initialize PWM with settings
static void mp_machine_pwm_init_helper(machine_pwm_obj_t* self, size_t n_args, const mp_obj_t* pos_args, mp_map_t* kw_args)
{
    enum { ARG_freq, ARG_duty, ARG_duty_u16, ARG_duty_ns, ARG_invert };

    const mp_arg_t allowed_args[] = {
        { MP_QSTR_freq, MP_ARG_KW_ONLY | MP_ARG_INT, { .u_int = -1 } },
        { MP_QSTR_duty, MP_ARG_KW_ONLY | MP_ARG_INT, { .u_int = -1 } },
        { MP_QSTR_duty_u16, MP_ARG_KW_ONLY | MP_ARG_INT, { .u_int = -1 } },
        { MP_QSTR_duty_ns, MP_ARG_KW_ONLY | MP_ARG_INT, { .u_int = -1 } },

        /* not support */
        { MP_QSTR_invert, MP_ARG_KW_ONLY | MP_ARG_BOOL, { .u_bool = false } },
    };

    mp_arg_val_t vals[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args, pos_args, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, vals);

    // Set frequency if provided
    if (vals[ARG_freq].u_int != -1) {
        mp_machine_pwm_freq_set(self, vals[ARG_freq].u_int);
    }

    // Check for multiple duty specifications
    int duty_specs = 0;
    if (vals[ARG_duty].u_int != -1)
        duty_specs++;
    if (vals[ARG_duty_u16].u_int != -1)
        duty_specs++;
    if (vals[ARG_duty_ns].u_int != -1)
        duty_specs++;

    if (duty_specs > 1) {
        mp_raise_ValueError(MP_ERROR_TEXT("only one of duty, duty_u16, or duty_ns can be specified"));
    }

    // Set duty cycle if provided
    if (vals[ARG_duty].u_int != -1) {
        mp_machine_pwm_duty_set(self, vals[ARG_duty].u_int);
    } else if (vals[ARG_duty_u16].u_int != -1) {
        mp_machine_pwm_duty_set_u16(self, vals[ARG_duty_u16].u_int);
    } else if (vals[ARG_duty_ns].u_int != -1) {
        mp_machine_pwm_duty_set_ns(self, vals[ARG_duty_ns].u_int);
    }
}

static mp_obj_t mp_machine_pwm_make_new(const mp_obj_type_t* type, size_t n_args, size_t n_kw, const mp_obj_t* args)
{
    mp_arg_check_num(n_args, n_kw, 1, MP_OBJ_FUN_ARGS_MAX, true);

    int arg     = mp_obj_get_int(args[0]);
    int channel = -1;
    int pin     = -1;

    if (arg >= 0 && arg <= 5) {
        // It's a valid PWM channel
        channel = arg;
        pin     = drv_fpioa_find_pin_by_func(PWM0 + channel);
        if (pin < 0) {
            mp_raise_msg_varg(&mp_type_AssertionError, MP_ERROR_TEXT("PWM(%d) not configured to any pin, see machine.FPIOA"),
                              channel);
        }
    } else {
        // Treat as pin number
        pin        = arg;
        bool found = false;
        for (int ch = 0; ch <= 5; ++ch) {
            fpioa_func_t func = PWM0 + ch;
            if (drv_fpioa_is_func_supported_by_pin(pin, func)) {
                if (drv_fpioa_set_pin_func(pin, func) != 0) {
                    mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("failed to assign pin %d to PWM(%d)"), pin, ch);
                }
                channel = ch;
                found   = true;
                break;
            }
        }
        if (!found) {
            mp_raise_msg_varg(&mp_type_ValueError, MP_ERROR_TEXT("Pin %d does not support any PWM function"), pin);
        }
    }

    machine_pwm_obj_t* self = mp_obj_malloc_with_finaliser(machine_pwm_obj_t, &machine_pwm_type);
    self->channel           = channel;
    self->pin               = pin;
    self->active            = false;
    self->invert            = false;

    if (drv_pwm_init() != 0) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("PWM init failed"));
    }

    mp_map_t kw_args;
    mp_map_init_fixed_table(&kw_args, n_kw, args + n_args);
    mp_machine_pwm_init_helper(self, n_args - 1, args + 1, &kw_args);

    return MP_OBJ_FROM_PTR(self);
}

// Deinitialize PWM
static void mp_machine_pwm_deinit(machine_pwm_obj_t* self)
{
    if (self->active) {
        drv_pwm_disable(self->channel);
        self->active = false;
    }
}

// Get frequency
static mp_obj_t mp_machine_pwm_freq_get(machine_pwm_obj_t* self)
{
    uint32_t freq;
    if (drv_pwm_get_freq(self->channel, &freq) != 0) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("failed to get frequency"));
    }
    return MP_OBJ_NEW_SMALL_INT(freq);
}

// Set frequency
static void mp_machine_pwm_freq_set(machine_pwm_obj_t* self, mp_int_t freq)
{
    if (freq <= 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("frequency must be > 0"));
    }

    if (drv_pwm_set_freq(self->channel, freq) != 0) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("failed to set frequency"));
    }

    if (!self->active) {
        drv_pwm_enable(self->channel);
        self->active = true;
    }
}

// Get duty cycle as percentage (0-100)
static mp_obj_t mp_machine_pwm_duty_get(machine_pwm_obj_t* self)
{
    uint32_t duty;
    if (drv_pwm_get_duty(self->channel, &duty) != 0) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("Failed to get duty cycle"));
    }
    return MP_OBJ_NEW_SMALL_INT(duty); // duty is already in 0-100 range
}

// Set duty cycle as percentage (0-100)
static void mp_machine_pwm_duty_set(machine_pwm_obj_t* self, mp_int_t duty)
{
    // Validate input range
    if (duty < 0 || duty > 100) {
        mp_raise_ValueError(MP_ERROR_TEXT("duty must be 0-100"));
    }

    // Set duty cycle through driver
    if (drv_pwm_set_duty(self->channel, (uint32_t)duty) != 0) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("Failed to set duty cycle"));
    }

    // Auto-enable PWM if not already active
    if (!self->active) {
        if (drv_pwm_enable(self->channel) != 0) {
            mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("Failed to enable PWM"));
        }
        self->active = true;
    }
}

// Set duty cycle (16-bit)
static void mp_machine_pwm_duty_set_u16(machine_pwm_obj_t* self, mp_int_t duty_u16)
{
    if (duty_u16 < 0 || duty_u16 > 65535) {
        mp_raise_ValueError(MP_ERROR_TEXT("duty_u16 must be 0-65535"));
    }

    if (drv_pwm_set_duty_u16(self->channel, duty_u16) != 0) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("failed to set duty"));
    }

    if (!self->active) {
        drv_pwm_enable(self->channel);
        self->active = true;
    }
}

// Get duty cycle (16-bit)
static mp_obj_t mp_machine_pwm_duty_get_u16(machine_pwm_obj_t* self)
{
    uint32_t freq;
    uint16_t duty_u16;

    if (drv_pwm_get_freq(self->channel, &freq) != 0) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("failed to get PWM frequency"));
    }
    if (drv_pwm_get_duty_u16(self->channel, &duty_u16) != 0) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("failed to get PWM duty"));
    }

    if (freq == 0) {
        return MP_OBJ_NEW_SMALL_INT(0);
    }

    return mp_obj_new_int(duty_u16); // Return duty in 0-65535 range
}

// Set duty cycle (nanoseconds)
static void mp_machine_pwm_duty_set_ns(machine_pwm_obj_t* self, mp_int_t duty_ns)
{
    if (duty_ns < 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("duty_ns must be >= 0"));
    }
    uint32_t freq;
    if (drv_pwm_get_freq(self->channel, &freq) != 0) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("failed to get frequency"));
    }
    if (freq == 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("cannot set duty_ns when frequency is 0"));
    }

    if (drv_pwm_set_duty_ns(self->channel, duty_ns) != 0) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("failed to set duty"));
    }

    if (!self->active) {
        drv_pwm_enable(self->channel);
        self->active = true;
    }
}

// Get duty cycle (nanoseconds)
static mp_obj_t mp_machine_pwm_duty_get_ns(machine_pwm_obj_t* self)
{
    uint32_t freq, duty;
    if (drv_pwm_get_freq(self->channel, &freq) != 0 || drv_pwm_get_duty_ns(self->channel, &duty) != 0) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("failed to get duty_ns"));
    }
    if (freq == 0) {
        return MP_OBJ_NEW_SMALL_INT(0);
    }
    return mp_obj_new_int(duty); // Return duty in nanoseconds
}
