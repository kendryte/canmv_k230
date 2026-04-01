/* Copyright (c) 2023, Canaan Bright Sight Co., Ltd
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
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "mpprint.h"
#include "py/obj.h"
#include "py/runtime.h"
#include "shared/runtime/mpirq.h"

#include "modmachine.h"

#include "drv_fpioa.h"
#include "drv_gpio.h"
#include "qstr.h"

#include "generated/autoconf.h"

#undef GPIO_MAX_NUM
#if defined (CONFIG_BOARD_NOT_SUPPORT_HW_RTC)
#define GPIO_MAX_NUM (64)
#else
#define GPIO_MAX_NUM (64 + 8)
#endif

extern bool system_is_exiting(void);
extern void mp_irq_enter(void);
extern void mp_irq_exit(void);

#define GPIO_MODE_INPUT     (GPIO_DM_INPUT)
#define GPIO_MODE_OUTPUT    (GPIO_DM_OUTPUT)
#define GPIO_MODE_OUTPUT_OD (GPIO_DM_OUTPUT_OD)
#define GPIO_MODE_PULL_NONE (1 << 2)
#define GPIO_MODE_PULL_UP   (1 << 3)
#define GPIO_MODE_PULL_DOWN (1 << 4)

typedef struct {
    mp_obj_base_t    base;
    drv_gpio_inst_t* inst;
} machine_pin_obj_t;

typedef struct _machine_pin_irq_obj_t {
    mp_irq_obj_t base;
    uint32_t     flags;
    uint32_t     trigger;
} machine_pin_irq_obj_t;

static int gpio_used[GPIO_MAX_NUM] = { 0 };

STATIC const mp_irq_methods_t machine_pin_irq_methods;

int machine_pin_get_pin_numer(mp_obj_t self_in)
{
    machine_pin_obj_t* self = MP_OBJ_TO_PTR(self_in);
    return drv_gpio_get_pin_id(self->inst);
}

void machine_pin_value_set(mp_obj_t self_in, int value)
{
    machine_pin_obj_t* self = MP_OBJ_TO_PTR(self_in);
    drv_gpio_value_set(self->inst, value);
}

int machine_pin_value_get(mp_obj_t self_in)
{
    machine_pin_obj_t* self = MP_OBJ_TO_PTR(self_in);
    return drv_gpio_value_get(self->inst);
}

drv_gpio_inst_t* machine_pin_get_inst(mp_obj_t self_in) { return ((machine_pin_obj_t*)MP_OBJ_TO_PTR(self_in))->inst; }

STATIC void machine_pin_init_helper(machine_pin_obj_t* self, size_t n_args, const mp_obj_t* pos_args, mp_map_t* kw_args)
{
    enum { ARG_mode, ARG_pull, ARG_value, ARG_drive, ARG_alt };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_mode, MP_ARG_INT, { .u_int = -1 } },
        { MP_QSTR_pull, MP_ARG_INT, { .u_int = -1 } },
        { MP_QSTR_value, MP_ARG_KW_ONLY | MP_ARG_INT, { .u_int = -1 } },
        { MP_QSTR_drive, MP_ARG_KW_ONLY | MP_ARG_INT, { .u_int = -1 } },
        { MP_QSTR_alt, MP_ARG_KW_ONLY | MP_ARG_INT, { .u_int = -1 } }, // not used
    };

    mp_arg_val_t parsed_args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args, pos_args, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, parsed_args);

    int alt = parsed_args[ARG_alt].u_int;
    if ((-1) != alt) {
        mp_printf(&mp_plat_print, "unsupport alt\n");
    }

    int pin = drv_gpio_get_pin_id(self->inst);
    if ((0 > pin) || (GPIO_MAX_NUM <= pin)) {
        mp_raise_msg_varg(&mp_type_ValueError, MP_ERROR_TEXT("pin(%d) invalid"), pin);
    }

    int mode = parsed_args[ARG_mode].u_int;
    if (GPIO_DM_MAX <= mode) {
        mp_raise_msg_varg(&mp_type_ValueError, MP_ERROR_TEXT("pin(%d) mode invalid"), pin);
    }

    int pull_up = 0, pull_down = 0;

    int pull = parsed_args[ARG_pull].u_int;
    if (((-1) != pull) && (-1 != mode)) {
        if (GPIO_DM_INPUT == mode) {
            if (GPIO_MODE_PULL_UP == (pull & GPIO_MODE_PULL_UP)) {
                mode = GPIO_DM_INPUT_PULLUP;
            } else if (GPIO_MODE_PULL_DOWN == (pull & GPIO_MODE_PULL_DOWN)) {
                mode = GPIO_DM_INPUT_PULLDOWN;
            }
        } else /* if (GPIO_DM_OUTPUT == mode) */ {
            if (GPIO_MODE_PULL_UP == (pull & GPIO_MODE_PULL_UP)) {
                pull_up = 1;
            }

            if (GPIO_MODE_PULL_DOWN == (pull & GPIO_MODE_PULL_DOWN)) {
                pull_down = 1;
            }
        }
    }

    if ((-1) != mode) {
        drv_gpio_mode_set(self->inst, mode);
    }

    int value = parsed_args[ARG_value].u_int;
    if ((-1) != value) {
        drv_gpio_value_set(self->inst, value);
    }

    fpioa_iomux_cfg_t iomux, new_iomux;

    if (0x00 != drv_fpioa_get_pin_cfg(pin, &iomux.u.value)) {
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("get pin(%d) iomux failed"), pin);
    }
    new_iomux.u.value = iomux.u.value;

    if (pull_up) {
        new_iomux.u.bit.pu = 1;
    }

    if (pull_down) {
        new_iomux.u.bit.pd = 1;
    }

    int drive = parsed_args[ARG_drive].u_int;
    if ((-1) != drive) {
        if ((0 >= drive) || (15 < drive)) {
            mp_raise_msg_varg(&mp_type_ValueError, MP_ERROR_TEXT("invalid drive %d"), drive);
        }
        new_iomux.u.bit.ds = drive;
    }

    if (new_iomux.u.value != iomux.u.value) {
        if (0x00 != drv_fpioa_set_pin_cfg(pin, new_iomux.u.value)) {
            mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("set pin(%d) iomux failed"), pin);
        }
    }
}

STATIC mp_obj_t machine_pin_init(size_t n_args, const mp_obj_t* args, mp_map_t* kw_args)
{
    machine_pin_init_helper(args[0], n_args - 1, args + 1, kw_args);
    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_KW(machine_pin_init_obj, 2, machine_pin_init);

STATIC mp_obj_t machine_pin_value(size_t n, const mp_obj_t* args)
{
    int                value;
    machine_pin_obj_t* self = MP_OBJ_TO_PTR(args[0]);

    if (0x01 == n) {
        /* read value */
        value = drv_gpio_value_get(self->inst);
        return mp_obj_new_int(value);
    } else /* if(0x02 == n) */ { /* set value */
        if (GPIO_DM_OUTPUT == self->inst->curr_mode) {
            value = mp_obj_get_int(args[1]);
            if (0x00 != drv_gpio_value_set(self->inst, value)) {
                mp_printf(&mp_plat_print, "set pin(%d) failed\n", self->inst->pin);
            }
        } else {
            mp_printf(&mp_plat_print, "pin(%d) is INPUT mode, can not set value\n", self->inst->pin);
        }
    }

    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(machine_pin_value_obj, 1, 2, machine_pin_value);

STATIC mp_obj_t machine_pin_on(mp_obj_t self_in)
{
    machine_pin_obj_t* self = MP_OBJ_TO_PTR(self_in);

    int succ = drv_gpio_value_set(self->inst, 1);

    return mp_obj_new_bool(0x00 == succ);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(machine_pin_on_obj, machine_pin_on);

STATIC mp_obj_t machine_pin_off(mp_obj_t self_in)
{
    machine_pin_obj_t* self = MP_OBJ_TO_PTR(self_in);

    int succ = drv_gpio_value_set(self->inst, 0);

    return mp_obj_new_bool(0x00 == succ);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(machine_pin_off_obj, machine_pin_off);

/* irq(handler, trigger)*/
STATIC void machie_pin_irq_handler(void* args)
{
    machine_pin_obj_t* self = MP_OBJ_TO_PTR(args);
    int                pin  = drv_gpio_get_pin_id(self->inst);

    machine_pin_irq_obj_t* irq = MP_STATE_PORT(machine_pin_irq_obj[pin]);
    if (irq != NULL) {
        irq->flags = irq->trigger;
        if (!system_is_exiting()) {
            mp_irq_enter();
            mp_irq_handler(&irq->base);
            mp_irq_exit();
        }
    }
}

STATIC machine_pin_irq_obj_t* machine_pin_get_irq(int pin)
{
    // Get the IRQ object.
    machine_pin_irq_obj_t* irq = MP_STATE_PORT(machine_pin_irq_obj[pin]);

    // Allocate the IRQ object if it doesn't already exist.
    if (irq == NULL) {
        irq                 = m_new_obj(machine_pin_irq_obj_t);
        irq->base.base.type = &mp_irq_type;
        irq->base.methods   = (mp_irq_methods_t*)&machine_pin_irq_methods;
        irq->base.parent    = NULL;
        irq->base.handler   = mp_const_none;
        irq->base.ishard    = false;

        MP_STATE_PORT(machine_pin_irq_obj[pin]) = irq;
    }

    return irq;
}

STATIC mp_obj_t machine_pin_irq(size_t n_args, const mp_obj_t* pos_args, mp_map_t* kw_args)
{
    enum { ARG_handler, ARG_trigger, ARG_priority, ARG_wake, ARG_hard, ARG_debounce };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_handler, MP_ARG_OBJ | MP_ARG_REQUIRED, { .u_obj = mp_const_none } },
        { MP_QSTR_trigger, MP_ARG_INT | MP_ARG_REQUIRED, { .u_int = GPIO_PE_MAX } },
        { MP_QSTR_priority, MP_ARG_INT, { .u_int = -1 } },
        { MP_QSTR_wake, MP_ARG_OBJ, { .u_obj = mp_const_none } },
        { MP_QSTR_hard, MP_ARG_BOOL, { .u_bool = false } },
        { MP_QSTR_debounce, MP_ARG_INT | MP_ARG_KW_ONLY, { .u_int = 10 } },
    };

    // parse args
    machine_pin_obj_t* self = MP_OBJ_TO_PTR(pos_args[0]);
    mp_arg_val_t       args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args - 1, pos_args + 1, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    mp_obj_t handler  = args[ARG_handler].u_obj;
    uint32_t trigger  = args[ARG_trigger].u_int;
    int      debounce = args[ARG_debounce].u_int;

    if ((handler == mp_const_none) || !mp_obj_is_callable(handler)) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid callback"));
    }

    if (GPIO_PE_MAX <= trigger) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid trigger"));
    }

    if (5 > debounce) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid debounce, should >= 5"));
    }

    int pin = drv_gpio_get_pin_id(self->inst);

    machine_pin_irq_obj_t* irq = machine_pin_get_irq(pin);

    irq->base.handler = handler;
    irq->base.ishard  = true;
    irq->base.parent  = self;
    irq->flags        = 0;
    irq->trigger      = trigger;

    if (0x00 != drv_gpio_register_irq(self->inst, trigger, debounce, machie_pin_irq_handler, self)) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("pin register irq failed"));
    }

    drv_gpio_enable_irq(self->inst);

    return MP_OBJ_FROM_PTR(irq);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_KW(machine_pin_irq_obj, 1, machine_pin_irq);

STATIC mp_obj_t machine_pin_mode(size_t n, const mp_obj_t* args)
{
    int                succ;
    gpio_drive_mode_t  mode;
    machine_pin_obj_t* self = MP_OBJ_TO_PTR(args[0]);

    if (0x02 == n) {
        mode = mp_obj_get_int(args[1]);
        if (0x00 != (succ = drv_gpio_mode_set(self->inst, mode))) {
            mp_printf(&mp_plat_print, "set pin(%d) mode failed\n", self->inst->pin);
        }
        return mp_obj_new_bool(0x00 == succ);
    } else {
        mode = drv_gpio_mode_get(self->inst);
        return mp_obj_new_int(mode);
    }
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(machine_pin_mode_obj, 1, 2, machine_pin_mode);

STATIC mp_obj_t machine_pin_pull(size_t n, const mp_obj_t* args)
{
    fpioa_iomux_cfg_t  iomux;
    machine_pin_obj_t* self = MP_OBJ_TO_PTR(args[0]);

    int pin = drv_gpio_get_pin_id(self->inst);

    if (0x00 != drv_fpioa_get_pin_cfg(pin, &iomux.u.value)) {
        mp_printf(&mp_plat_print, "get pin(%d) cfg failed\n", pin);
        return mp_const_none;
    }

    if (0x02 == n) {
        fpioa_iomux_cfg_t new_iomux;
        int               pull = mp_obj_get_int(args[1]);

        new_iomux.u.value = iomux.u.value;

        if (GPIO_MODE_PULL_NONE == (pull & GPIO_MODE_PULL_NONE)) {
            new_iomux.u.bit.pu = 0;
            new_iomux.u.bit.pd = 0;
        } else {
            if (GPIO_MODE_PULL_UP == (pull & GPIO_MODE_PULL_UP)) {
                new_iomux.u.bit.pu = 1;
            }
            if (GPIO_MODE_PULL_DOWN == (pull & GPIO_MODE_PULL_DOWN)) {
                new_iomux.u.bit.pd = 1;
            }
        }

        if (new_iomux.u.value != iomux.u.value) {
            if (0x00 != drv_fpioa_set_pin_cfg(pin, new_iomux.u.value)) {
                mp_printf(&mp_plat_print, "set pin(%d) cfg failed\n", pin);
            }
        }
        return mp_const_none;
    } else {
        int flag = 0;

        if ((0x00 == iomux.u.bit.pu) && (0x00 == iomux.u.bit.pd)) {
            flag = GPIO_MODE_PULL_NONE;
        } else {
            if (iomux.u.bit.pd) {
                flag |= GPIO_MODE_PULL_DOWN;
            }

            if (iomux.u.bit.pu) {
                flag |= GPIO_MODE_PULL_UP;
            }
        }

        return MP_OBJ_NEW_SMALL_INT(flag);
    }
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(machine_pin_pull_obj, 1, 2, machine_pin_pull);

STATIC mp_obj_t machine_pin_drive(size_t n, const mp_obj_t* args)
{
    fpioa_iomux_cfg_t iomux;

    int                succ, drive;
    machine_pin_obj_t* self = MP_OBJ_TO_PTR(args[0]);

    int pin = drv_gpio_get_pin_id(self->inst);

    if (0x00 != drv_fpioa_get_pin_cfg(pin, &iomux.u.value)) {
        mp_printf(&mp_plat_print, "get pin(%d) cfg failed\n", pin);
        return mp_const_none;
    }

    if (0x02 == n) {
        drive = mp_obj_get_int(args[1]);
        if (drive != iomux.u.bit.ds) {
            iomux.u.bit.ds = drive;
            if (0x00 != (succ = drv_fpioa_set_pin_cfg(pin, iomux.u.value))) {
                mp_printf(&mp_plat_print, "set pin(%d) cfg failed\n", self->inst->pin);
            }
        } else {
            succ = 0x00;
        }

        return mp_obj_new_bool(0x00 == succ);
    } else {
        return mp_obj_new_int(iomux.u.bit.ds);
    }
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(machine_pin_drive_obj, 1, 2, machine_pin_drive);

STATIC mp_obj_t machine_pin_toggle(mp_obj_t self_in)
{
    machine_pin_obj_t* self = MP_OBJ_TO_PTR(self_in);

    int succ = drv_gpio_toggle(self->inst);

    return mp_obj_new_bool(0x00 == succ);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(machine_pin_toggle_obj, machine_pin_toggle);

STATIC mp_obj_t machine_pin_destroy(mp_obj_t self_in)
{
    machine_pin_obj_t* self = MP_OBJ_TO_PTR(self_in);

    int pin = drv_gpio_get_pin_id(self->inst);
    if (0 <= pin) {
        gpio_used[pin]                          = 0;
        MP_STATE_PORT(machine_pin_irq_obj[pin]) = NULL;
    }

    drv_gpio_unregister_irq(self->inst);
    drv_gpio_inst_destroy(&self->inst);

    printf("Set pin%d to input\n", pin);

    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(machine_pin_destroy_obj, machine_pin_destroy);

STATIC mp_obj_t machine_pin_make_new(const mp_obj_type_t* type, size_t n_args, size_t n_kw, const mp_obj_t* args)
{
    fpioa_func_t func;

    mp_arg_check_num(n_args, n_kw, 1, 6, true);

    int pin = mp_obj_get_int(args[0]);
    if ((0 > pin) || (GPIO_MAX_NUM <= pin)) {
        mp_raise_msg_varg(&mp_type_ValueError, MP_ERROR_TEXT("pin(%d) invalid"), pin);
    }

    if (gpio_used[pin]) {
        mp_printf(&mp_plat_print, "pin(%d) maybe inuse\n", pin);
    }

    if (0x00 != drv_fpioa_get_pin_func(pin, &func)) {
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("get pin(%d) fpioa func failed"), pin);
    }

    if (GPIO71 < func) {
        mp_printf(&mp_plat_print, "pin(%d) is not a GPIO pin, func=%d, Please notice it.\n", pin, func);

        func = GPIO0 + pin; // Use GPIO0 + pin as the default GPIO function
        if (0x00 != drv_fpioa_set_pin_func(pin, func)) {
            mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("set pin(%d) fpioa func failed"), pin);
        }
    }

    machine_pin_obj_t* self = m_new_obj_with_finaliser(machine_pin_obj_t);
    self->base.type         = &machine_pin_type;

    if (0x00 != drv_gpio_inst_create(pin, &self->inst)) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("create pin obj failed"));
    }

    mp_map_t kw_args;
    mp_map_init_fixed_table(&kw_args, n_kw, args + n_args);
    machine_pin_init_helper(self, n_args - 1, args + 1, &kw_args);

    return MP_OBJ_FROM_PTR(self);
}

STATIC void machine_pin_print(const mp_print_t* print, mp_obj_t self_in, mp_print_kind_t kind)
{
    machine_pin_obj_t* self = MP_OBJ_TO_PTR(self_in);

    mp_printf(print, "{\"Pin\": \"{\"id\":%u, \"mode\":%u}\n", self->inst->pin, self->inst->curr_mode);
}

STATIC mp_obj_t machine_pin_call(mp_obj_t self_in, size_t n_args, size_t n_kw, const mp_obj_t* args)
{
    mp_arg_check_num(n_args, n_kw, 0, 1, false);

    return machine_pin_value(n_args + 1, (mp_obj_t[]) { self_in, args[0] });
}

STATIC mp_obj_t machine_pin_unary_op(mp_unary_op_t op, mp_obj_t self_in)
{
    machine_pin_obj_t* self = MP_OBJ_TO_PTR(self_in);

    switch (op) {
    case MP_UNARY_OP_INT_MAYBE:
        return mp_obj_new_int(self->inst->pin);
    default:
        return MP_OBJ_NULL;
    }
}

void machine_pin_irq_init(void)
{
    for (size_t i = 0; i < GPIO_MAX_NUM; i++) {
        MP_STATE_PORT(machine_pin_irq_obj[i]) = NULL;
    }
}

STATIC const mp_rom_map_elem_t machine_pin_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&machine_pin_destroy_obj) },

    { MP_ROM_QSTR(MP_QSTR_init), MP_ROM_PTR(&machine_pin_init_obj) },
    { MP_ROM_QSTR(MP_QSTR_value), MP_ROM_PTR(&machine_pin_value_obj) },
    { MP_ROM_QSTR(MP_QSTR_on), MP_ROM_PTR(&machine_pin_on_obj) },
    { MP_ROM_QSTR(MP_QSTR_off), MP_ROM_PTR(&machine_pin_off_obj) },
    { MP_ROM_QSTR(MP_QSTR_low), MP_ROM_PTR(&machine_pin_off_obj) },
    { MP_ROM_QSTR(MP_QSTR_high), MP_ROM_PTR(&machine_pin_on_obj) },
    { MP_ROM_QSTR(MP_QSTR_mode), MP_ROM_PTR(&machine_pin_mode_obj) },
    { MP_ROM_QSTR(MP_QSTR_pull), MP_ROM_PTR(&machine_pin_pull_obj) },
    { MP_ROM_QSTR(MP_QSTR_drive), MP_ROM_PTR(&machine_pin_drive_obj) },
    { MP_ROM_QSTR(MP_QSTR_toggle), MP_ROM_PTR(&machine_pin_toggle_obj) },
    { MP_ROM_QSTR(MP_QSTR_irq), MP_ROM_PTR(&machine_pin_irq_obj) },
    // mode
    { MP_ROM_QSTR(MP_QSTR_IN), MP_ROM_INT(GPIO_MODE_INPUT) },
    { MP_ROM_QSTR(MP_QSTR_OUT), MP_ROM_INT(GPIO_MODE_OUTPUT) },
    { MP_ROM_QSTR(MP_QSTR_OPEN_DRAIN), MP_ROM_INT(GPIO_MODE_OUTPUT_OD) },
    // pull
    { MP_ROM_QSTR(MP_QSTR_PULL_NONE), MP_ROM_INT(GPIO_MODE_PULL_NONE) },
    { MP_ROM_QSTR(MP_QSTR_PULL_UP), MP_ROM_INT(GPIO_MODE_PULL_UP) },
    { MP_ROM_QSTR(MP_QSTR_PULL_DOWN), MP_ROM_INT(GPIO_MODE_PULL_DOWN) },
    // irq
    { MP_ROM_QSTR(MP_QSTR_IRQ_FALLING), MP_ROM_INT(GPIO_PE_FALLING) },
    { MP_ROM_QSTR(MP_QSTR_IRQ_RISING), MP_ROM_INT(GPIO_PE_RISING) },
    { MP_ROM_QSTR(MP_QSTR_IRQ_LOW_LEVEL), MP_ROM_INT(GPIO_PE_LOW) },
    { MP_ROM_QSTR(MP_QSTR_IRQ_HIGH_LEVEL), MP_ROM_INT(GPIO_PE_HIGH) },
    { MP_ROM_QSTR(MP_QSTR_IRQ_BOTH), MP_ROM_INT(GPIO_PE_BOTH) },
    // drive
    { MP_ROM_QSTR(MP_QSTR_DRIVE_0), MP_ROM_INT(0) },
    { MP_ROM_QSTR(MP_QSTR_DRIVE_1), MP_ROM_INT(1) },
    { MP_ROM_QSTR(MP_QSTR_DRIVE_2), MP_ROM_INT(2) },
    { MP_ROM_QSTR(MP_QSTR_DRIVE_3), MP_ROM_INT(3) },
    { MP_ROM_QSTR(MP_QSTR_DRIVE_4), MP_ROM_INT(4) },
    { MP_ROM_QSTR(MP_QSTR_DRIVE_5), MP_ROM_INT(5) },
    { MP_ROM_QSTR(MP_QSTR_DRIVE_6), MP_ROM_INT(6) },
    { MP_ROM_QSTR(MP_QSTR_DRIVE_7), MP_ROM_INT(7) },
    { MP_ROM_QSTR(MP_QSTR_DRIVE_8), MP_ROM_INT(8) },
    { MP_ROM_QSTR(MP_QSTR_DRIVE_9), MP_ROM_INT(9) },
    { MP_ROM_QSTR(MP_QSTR_DRIVE_10), MP_ROM_INT(10) },
    { MP_ROM_QSTR(MP_QSTR_DRIVE_11), MP_ROM_INT(11) },
    { MP_ROM_QSTR(MP_QSTR_DRIVE_12), MP_ROM_INT(12) },
    { MP_ROM_QSTR(MP_QSTR_DRIVE_13), MP_ROM_INT(13) },
    { MP_ROM_QSTR(MP_QSTR_DRIVE_14), MP_ROM_INT(14) },
    { MP_ROM_QSTR(MP_QSTR_DRIVE_15), MP_ROM_INT(15) },
};
STATIC MP_DEFINE_CONST_DICT(machine_pin_locals_dict, machine_pin_locals_dict_table);

/* clang-format off */
MP_DEFINE_CONST_OBJ_TYPE(
    machine_pin_type,
    MP_QSTR_Pin,
    MP_TYPE_FLAG_NONE,
    make_new, machine_pin_make_new,
    print, machine_pin_print,
    call, machine_pin_call,
    unary_op, machine_pin_unary_op,
    locals_dict, &machine_pin_locals_dict
);
/* clang-format on */

STATIC mp_uint_t machine_pin_irq_trigger(mp_obj_t self_in, mp_uint_t new_trigger)
{
    machine_pin_obj_t* self = MP_OBJ_TO_PTR(self_in);
    int                pin  = drv_gpio_get_pin_id(self->inst);

    machine_pin_irq_obj_t* irq = MP_STATE_PORT(machine_pin_irq_obj[pin]);

    drv_gpio_disable_irq(self->inst);
    irq->flags   = 0;
    irq->trigger = new_trigger;
    drv_gpio_enable_irq(self->inst);

    return 0;
}

STATIC mp_uint_t machine_pin_irq_info(mp_obj_t self_in, mp_uint_t info_type)
{
    machine_pin_obj_t* self = MP_OBJ_TO_PTR(self_in);
    int                pin  = drv_gpio_get_pin_id(self->inst);

    machine_pin_irq_obj_t* irq = MP_STATE_PORT(machine_pin_irq_obj[pin]);

    if (info_type == MP_IRQ_INFO_FLAGS) {
        return irq->flags;
    } else if (info_type == MP_IRQ_INFO_TRIGGERS) {
        return irq->trigger;
    }

    return 0;
}

STATIC const mp_irq_methods_t machine_pin_irq_methods = {
    .trigger = machine_pin_irq_trigger,
    .info    = machine_pin_irq_info,
};

MP_REGISTER_ROOT_POINTER(void* machine_pin_irq_obj[GPIO_MAX_NUM]);
