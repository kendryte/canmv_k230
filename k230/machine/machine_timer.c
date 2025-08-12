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

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "py/mpprint.h"
#include "py/obj.h"
#include "py/runtime.h"

#include "drv_timer.h"

#include "machine/modmachine.h"

/** soft timer wrap **********************************************************/

/** timer python binding *****************************************************/
typedef struct {
    mp_obj_base_t base;

    int      type; // 0: hard, 1: soft
    int      mode;
    uint64_t period;

    mp_obj_t callback;
    mp_obj_t callback_args;

    union {
        drv_soft_timer_inst_t* soft;
        drv_hard_timer_inst_t* hard;
    } inst;
} machine_timer_obj_t;

static void machine_timer_handler(void* args)
{
    machine_timer_obj_t* self = MP_OBJ_TO_PTR(args);

    if (self && (&machine_timer_type == self->base.type)) {
        mp_sched_schedule(self->callback, MP_OBJ_FROM_PTR(self->callback_args));
    } else {
        printf("invalid timer callback\n");
    }
}

static mp_obj_t machine_timer_deinit(mp_obj_t self_in)
{
    machine_timer_obj_t* self = MP_OBJ_TO_PTR(self_in);

    if (0x00 == self->type) { /* hard */
        if (NULL == self->inst.hard) {
            return mp_const_none;
        }

        drv_hard_timer_stop(self->inst.hard);
        drv_hard_timer_unregister_irq(self->inst.hard);
        drv_hard_timer_inst_destroy(&self->inst.hard);
    } else { /* soft */
        if (NULL == self->inst.soft) {
            return mp_const_none;
        }

        drv_soft_timer_stop(self->inst.soft);
        drv_soft_timer_unregister_irq(self->inst.soft);
        drv_soft_timer_destroy(&self->inst.soft);
    }

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(machine_timer_deinit_obj, machine_timer_deinit);

static void machine_timer_init_helper(machine_timer_obj_t* self, mp_uint_t n_args, const mp_obj_t* pos_args, mp_map_t* kw_args)
{
    enum { ARG_mode, ARG_freq, ARG_period, ARG_callback };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_mode, MP_ARG_INT, { .u_int = HWTIMER_MODE_PERIOD } },
        { MP_QSTR_freq, MP_ARG_INT, { .u_int = -1 } },
        { MP_QSTR_period, MP_ARG_INT, { .u_int = -1 } },
        { MP_QSTR_callback, MP_ARG_OBJ, { .u_obj = mp_const_none } },
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args, pos_args, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    int      mode    = args[ARG_mode].u_int;
    int      freq    = args[ARG_freq].u_int;
    int      period  = args[ARG_period].u_int;
    mp_obj_t handler = args[ARG_callback].u_obj;

    int period_ms = period;
    if ((-1) != freq) {
        period_ms = 1000 / freq;
    }

    if ((mp_const_none == handler) || !mp_obj_is_callable(handler)) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid callback"));
    }

    if (5 > period_ms) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid period or freq, period should >= 5"));
    }

    if ((HWTIMER_MODE_PERIOD != mode) && (HWTIMER_MODE_ONESHOT != mode)) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid mode"));
    }

    self->mode     = mode;
    self->period   = period_ms;
    self->callback = handler;

    if (0x00 == self->type) { /* hard */
        if (0x00 != drv_hard_timer_is_started(self->inst.hard)) {
            drv_hard_timer_stop(self->inst.hard);
        }

        if (0x00 != drv_hard_timer_set_mode(self->inst.hard, mode)) {
            mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("set timer mode failed"));
        }

        if (0x00 != drv_hard_timer_set_period(self->inst.hard, period_ms)) {
            mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("set timer period failed"));
        }

        if (0x00 != drv_hard_timer_register_irq(self->inst.hard, machine_timer_handler, self)) {
            mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("register timer callback failed"));
        }

        if (0x00 != drv_hard_timer_start(self->inst.hard)) {
            mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("start timer failed"));
        }
    } else { /* soft */
        if (0x00 != drv_soft_timer_is_started(self->inst.soft)) {
            drv_soft_timer_stop(self->inst.soft);
        }

        if (0x00 != drv_soft_timer_set_mode(self->inst.soft, mode)) {
            mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("set timer mode failed"));
        }

        if (0x00 != drv_soft_timer_set_period(self->inst.soft, period_ms)) {
            mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("set timer period failed"));
        }

        if (0x00 != drv_soft_timer_register_irq(self->inst.soft, machine_timer_handler, self)) {
            mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("register timer callback failed"));
        }

        if (0x00 != drv_soft_timer_start(self->inst.soft)) {
            mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("start timer failed"));
        }
    }
}

static mp_obj_t machine_timer_init(mp_uint_t n_args, const mp_obj_t* args, mp_map_t* kw_args)
{
    machine_timer_obj_t* self = MP_OBJ_TO_PTR(args[0]);

    machine_timer_init_helper(self, n_args - 1, args + 1, kw_args);

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_KW(machine_timer_init_obj, 0, machine_timer_init);

static mp_obj_t machine_timer_make_new(const mp_obj_type_t* type, size_t n_args, size_t n_kw, const mp_obj_t* args)
{
    mp_arg_check_num(n_args, n_kw, 1, 5, true);

    int index = mp_obj_get_int(args[0]);
    if (((-1) != index) && ((0 > index) || (KD_TIMER_MAX_NUM <= index))) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid timer number"));
    }

    machine_timer_obj_t* self = mp_obj_malloc_with_finaliser(machine_timer_obj_t, &machine_timer_type);

    self->type     = -1;
    self->callback = MP_OBJ_NULL;
    self->mode     = HWTIMER_MODE_ONESHOT;
    self->period   = 100;

    if ((-1) == index) {
        self->type = 1;

        if (0x00 != drv_soft_timer_create(&self->inst.soft)) {
            mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("create soft timer obj failed"));
        }
    } else {
        self->type = 0;

        if (0x00 != drv_hard_timer_inst_create(index, &self->inst.hard)) {
            mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("create hard timer(%d) obj failed"), index);
        }
    }

    if ((n_args + n_kw) > 1) {
        mp_map_t kw_args;
        mp_map_init_fixed_table(&kw_args, n_kw, args + n_args);
        machine_timer_init_helper(self, n_args - 1, args + 1, &kw_args);
    }

    return MP_OBJ_FROM_PTR(self);
}

static void machine_timer_print(const mp_print_t* print, mp_obj_t self_in, mp_print_kind_t kind)
{
    int                  timer_id = -1;
    machine_timer_obj_t* self     = self_in;

    if (0x00 == self->type) { /* hard timer */
        timer_id = drv_hard_timer_get_id(self->inst.hard);
    }

    mp_printf(print, "Timer %d: period=%u ms, mode=%s, callback=%p\n", timer_id, self->period,
              self->mode == HWTIMER_MODE_ONESHOT ? "oneshot" : "periodic", self->callback);
}

static const mp_rom_map_elem_t machine_timer_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&machine_timer_deinit_obj) },
    { MP_ROM_QSTR(MP_QSTR_deinit), MP_ROM_PTR(&machine_timer_deinit_obj) },
    { MP_ROM_QSTR(MP_QSTR_init), MP_ROM_PTR(&machine_timer_init_obj) },

    { MP_ROM_QSTR(MP_QSTR_ONE_SHOT), MP_ROM_INT(HWTIMER_MODE_ONESHOT) },
    { MP_ROM_QSTR(MP_QSTR_PERIODIC), MP_ROM_INT(HWTIMER_MODE_PERIOD) },
};
static MP_DEFINE_CONST_DICT(machine_timer_locals_dict, machine_timer_locals_dict_table);

/* clang-format off */
MP_DEFINE_CONST_OBJ_TYPE(
    machine_timer_type,
    MP_QSTR_Timer,
    MP_TYPE_FLAG_NONE,
    make_new, machine_timer_make_new,
    print, machine_timer_print,
    locals_dict, &machine_timer_locals_dict
);
/* clang-format on */
