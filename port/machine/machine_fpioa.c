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
#include <stdlib.h>
#include <string.h>

#include "mpprint.h"
#include "py/obj.h"
#include "py/runtime.h"

#include "py_assert.h" // use openmv marco, PY_ASSERT_TYPE

#include "modmachine.h"

#include "drv_fpioa.h"
#include "qstr.h"

#define TEMP_STR_LEN 128

#include "generated/autoconf.h"

#undef FPIOA_PIN_MAX_NUM
#if defined (CONFIG_BOARD_NOT_SUPPORT_HW_RTC)
#define FPIOA_PIN_MAX_NUM (64)
#else
#define FPIOA_PIN_MAX_NUM (64 + 8)
#endif

typedef struct {
    mp_obj_base_t base;
} machine_fpioa_obj_t;

static const machine_fpioa_obj_t machine_fpioa_obj = {
    { &machine_fpioa_type },
};

STATIC const mp_obj_type_t machine_pin_cfg_type;

typedef struct _machine_pin_cfg_context {
    int               pin;
    fpioa_iomux_cfg_t cfg;
} machine_pin_cfg_context_t;

typedef struct _machine_pin_cfg_obj {
    mp_obj_base_t             base;
    machine_pin_cfg_context_t _cobj;
} machine_pin_cfg_obj_t;

mp_obj_t machine_pin_cfg_from_struct(machine_pin_cfg_context_t* ctx)
{
    machine_pin_cfg_obj_t* o = m_new_obj(machine_pin_cfg_obj_t);

    o->base.type = &machine_pin_cfg_type;

    if (ctx) {
        memcpy(&o->_cobj, ctx, sizeof(*ctx));
    } else {
        memset(&o->_cobj, 0x00, sizeof(*ctx));
    }

    return MP_OBJ_FROM_PTR(o);
}

void* machine_pin_cfg_cobj(mp_obj_t cfg_obj)
{
    PY_ASSERT_TYPE(cfg_obj, &machine_pin_cfg_type);

    return &((machine_pin_cfg_obj_t*)cfg_obj)->_cobj;
}

STATIC void machine_pin_cfg_print(const mp_print_t* print, mp_obj_t self_in, mp_print_kind_t kind)
{
    machine_pin_cfg_context_t* ctx = machine_pin_cfg_cobj(MP_OBJ_TO_PTR(self_in));
    fpioa_iomux_cfg_t*         cfg = &ctx->cfg;

    mp_printf(print,
              "\"pin\": %d, {\"st\": %d, \"ds\": %d, \"pd\": %d, \"pu\": %d, \"oe\": %d, \"ie\": %d, \"msc\": %d }",
              ctx->pin, cfg->u.bit.st, cfg->u.bit.ds, cfg->u.bit.pd, cfg->u.bit.pu, cfg->u.bit.oe, cfg->u.bit.ie,
              cfg->u.bit.msc);
}

STATIC void machine_pin_cfg_attr(mp_obj_t self_in, qstr attr, mp_obj_t* dest)
{
    machine_pin_cfg_context_t* ctx = machine_pin_cfg_cobj(MP_OBJ_TO_PTR(self_in));
    fpioa_iomux_cfg_t*         cfg = &ctx->cfg;

#define MACHINE_FPIOA_PIN_CFG_GET_ATTR(item)                                                                           \
    case MP_QSTR_##item: {                                                                                             \
        dest[1] = mp_obj_new_int(cfg->u.bit.item);                                                                     \
    } break;

#define MACHINE_FPIOA_PIN_CFG_SET_ATTR(item)                                                                           \
    case MP_QSTR_##item: {                                                                                             \
        cfg->u.bit.item = mp_obj_get_int(dest[1]);                                                                     \
    } break;

    if (MP_OBJ_NULL == dest[0]) {
        // load attribute
        switch (attr) {
            MACHINE_FPIOA_PIN_CFG_GET_ATTR(st);
            MACHINE_FPIOA_PIN_CFG_GET_ATTR(ds);
            MACHINE_FPIOA_PIN_CFG_GET_ATTR(pd);
            MACHINE_FPIOA_PIN_CFG_GET_ATTR(pu);
            MACHINE_FPIOA_PIN_CFG_GET_ATTR(oe);
            MACHINE_FPIOA_PIN_CFG_GET_ATTR(ie);
            MACHINE_FPIOA_PIN_CFG_GET_ATTR(msc);
        default:
            dest[1] = MP_OBJ_SENTINEL; // continue lookup in locals_dict
            break;
        }
    } else if ((MP_OBJ_SENTINEL == dest[0]) && (MP_OBJ_NULL != dest[1])) {
        // store attribute
        switch (attr) {
            MACHINE_FPIOA_PIN_CFG_SET_ATTR(st);
            MACHINE_FPIOA_PIN_CFG_SET_ATTR(ds);
            MACHINE_FPIOA_PIN_CFG_SET_ATTR(pd);
            MACHINE_FPIOA_PIN_CFG_SET_ATTR(pu);
            MACHINE_FPIOA_PIN_CFG_SET_ATTR(oe);
            MACHINE_FPIOA_PIN_CFG_SET_ATTR(ie);
        default: {
            mp_raise_msg_varg(&mp_type_ValueError, MP_ERROR_TEXT("not support set %s"), qstr_str(attr));
        } break;
        }
    }

#undef MACHINE_FPIOA_PIN_CFG_GET_ATTR
#undef MACHINE_FPIOA_PIN_CFG_SET_ATTR
}

/* clang-format off */
STATIC MP_DEFINE_CONST_OBJ_TYPE(
    machine_pin_cfg_type,
    MP_QSTR_machine_pin_cfg,
    MP_TYPE_FLAG_NONE,
    print, machine_pin_cfg_print,
    attr, machine_pin_cfg_attr
);
/* clang-format on */

STATIC mp_obj_t machine_fpioa_get_pin_cfg(mp_obj_t self, mp_obj_t obj)
{
    int pin = 0;

    machine_pin_cfg_context_t ctx;

    pin = mp_obj_get_int(obj);
    if ((0 > pin) || (FPIOA_PIN_MAX_NUM <= pin)) {
        mp_raise_msg_varg(&mp_type_ValueError, MP_ERROR_TEXT("invalid pin number %d"), pin);
    }
    ctx.pin = pin;

    if (0x00 != drv_fpioa_get_pin_cfg(pin, &ctx.cfg.u.value)) {
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("get pin func failed"));
    }

    return machine_pin_cfg_from_struct(&ctx);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_2(machine_fpioa_get_pin_cfg_obj, machine_fpioa_get_pin_cfg);

STATIC mp_obj_t machine_fpioa_set_pin_cfg(mp_obj_t self, mp_obj_t obj)
{
    int                        result;
    machine_pin_cfg_context_t* ctx = machine_pin_cfg_cobj(MP_OBJ_TO_PTR(obj));

    result = drv_fpioa_get_pin_cfg(ctx->pin, &ctx->cfg.u.value);

    return mp_obj_new_bool(0x00 == result);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_2(machine_fpioa_set_pin_cfg_obj, machine_fpioa_set_pin_cfg);

STATIC mp_obj_t machine_fpioa_set_function(size_t n_args, const mp_obj_t* pos_args, mp_map_t* kw_args)
{
    enum { ARG_pin, ARG_func, ARG_ie, ARG_oe, ARG_pu, ARG_pd, ARG_ds, ARG_st, ARG_sl };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_pin, MP_ARG_INT | MP_ARG_REQUIRED, { .u_int = -1 } },
        { MP_QSTR_func, MP_ARG_INT | MP_ARG_REQUIRED, { .u_int = -1 } },

        { MP_QSTR_ie, MP_ARG_INT | MP_ARG_KW_ONLY, { .u_int = -1 } },
        { MP_QSTR_oe, MP_ARG_INT | MP_ARG_KW_ONLY, { .u_int = -1 } },
        { MP_QSTR_pu, MP_ARG_INT | MP_ARG_KW_ONLY, { .u_int = -1 } },
        { MP_QSTR_pd, MP_ARG_INT | MP_ARG_KW_ONLY, { .u_int = -1 } },
        { MP_QSTR_ds, MP_ARG_INT | MP_ARG_KW_ONLY, { .u_int = -1 } },
        { MP_QSTR_st, MP_ARG_INT | MP_ARG_KW_ONLY, { .u_int = -1 } },
        { MP_QSTR_sl, MP_ARG_INT | MP_ARG_KW_ONLY, { .u_int = -1 } },
    };

    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args - 1, pos_args + 1, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    int pin      = args[ARG_pin].u_int;
    int pin_func = args[ARG_func].u_int;

    if ((0 > pin) || (FPIOA_PIN_MAX_NUM <= pin)) {
        mp_raise_msg_varg(&mp_type_ValueError, MP_ERROR_TEXT("invalid pin number %d"), pin);
    }
    if ((0 > pin_func) || (FUNC_MAX <= pin_func)) {
        mp_raise_msg_varg(&mp_type_ValueError, MP_ERROR_TEXT("invalid func %d"), pin_func);
    }

    if (0x00 != drv_fpioa_set_pin_func(pin, pin_func)) {
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("set pin func failed"));
    }

    fpioa_iomux_cfg_t curr_cfg, new_cfg;

    if (0x00 != drv_fpioa_get_pin_cfg(pin, &curr_cfg.u.value)) {
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("get pin cfg failed"));
    }
    new_cfg.u.value = curr_cfg.u.value;

#define MACHINE_FPIOA_PARSE_ARG(item)                                                                                  \
    if ((-1) != args[ARG_##item].u_int) {                                                                              \
        new_cfg.u.bit.item = args[ARG_##item].u_int;                                                                   \
    }
    MACHINE_FPIOA_PARSE_ARG(ie);
    MACHINE_FPIOA_PARSE_ARG(oe);
    MACHINE_FPIOA_PARSE_ARG(pu);
    MACHINE_FPIOA_PARSE_ARG(pd);
    MACHINE_FPIOA_PARSE_ARG(ds);
    MACHINE_FPIOA_PARSE_ARG(st);
#undef MACHINE_FPIOA_PARSE_ARG

    if ((-1) != args[ARG_sl].u_int) {
        mp_printf(&mp_plat_print, "not support set sl");
    }

    if (new_cfg.u.value != curr_cfg.u.value) {
        if (0x00 != drv_fpioa_set_pin_cfg(pin, new_cfg.u.value)) {
            mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("set pin cfg failed"));
        }
    }

    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_KW(machine_fpioa_set_function_obj, 3, machine_fpioa_set_function);

STATIC mp_obj_t machine_fpioa_get_pin_num(mp_obj_t self, mp_obj_t obj)
{
    int          curr_pin = -1;
    fpioa_func_t pin_func;

    pin_func = mp_obj_get_int(obj);
    if ((0 > pin_func) || (FUNC_MAX <= pin_func)) {
        mp_raise_msg_varg(&mp_type_ValueError, MP_ERROR_TEXT("invalid func %d"), pin_func);
    }

    if (0x00 <= (curr_pin = drv_fpioa_find_pin_by_func(pin_func))) {
        return MP_OBJ_NEW_SMALL_INT(curr_pin);
    }

    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_2(machine_fpioa_get_pin_num_obj, machine_fpioa_get_pin_num);

STATIC mp_obj_t machine_fpioa_get_pin_func(mp_obj_t self, mp_obj_t obj)
{
    int          pin = 0;
    fpioa_func_t pin_func;

    pin = mp_obj_get_int(obj);
    if ((0 > pin) || (FPIOA_PIN_MAX_NUM <= pin)) {
        mp_raise_msg_varg(&mp_type_ValueError, MP_ERROR_TEXT("invalid pin number %d"), pin);
    }

    if (0x00 != drv_fpioa_get_pin_func(pin, &pin_func)) {
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("get pin func failed"));
    }

    return MP_OBJ_NEW_SMALL_INT(pin_func);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_2(machine_fpioa_get_pin_func_obj, machine_fpioa_get_pin_func);

STATIC mp_obj_t machine_fpioa_help(size_t n_args, const mp_obj_t* pos_args, mp_map_t* kw_args)
{
    enum { ARG_num, ARG_func };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_num, MP_ARG_INT, { .u_int = -1 } },
        { MP_QSTR_func, MP_ARG_BOOL | MP_ARG_KW_ONLY, { .u_bool = false } },
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args - 1, pos_args + 1, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    int num       = args[ARG_num].u_int;
    int func_mode = args[ARG_func].u_bool;

    char pin_func_name[32];
    char pin_alt_func_names[TEMP_STR_LEN];

    if (func_mode) {
        // func mode
        if ((0 > num) || (FUNC_MAX <= num)) {
            mp_raise_msg_varg(&mp_type_ValueError, MP_ERROR_TEXT("invalid func %d"), num);
        }

        int curr_pin     = -1;
        int alt_pins_cnt = 0;
        int alt_pins[FPIOA_PIN_FUNC_ALT_NUM];

        if (0x00 != drv_fpioa_get_func_name(num, &pin_func_name[0], sizeof(pin_func_name))) {
            mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("get func name failed"));
        }
        alt_pins_cnt = drv_fpioa_func_available_pins(num, &alt_pins[0]);

        mp_printf(&mp_plat_print, "function %s can be set to ", pin_func_name);
        for (int i = 0; i < alt_pins_cnt; i++) {
            mp_printf(&mp_plat_print, "PIN%d%s", alt_pins[i], (i + 1) == alt_pins_cnt ? "" : ", ");
        }
        mp_printf(&mp_plat_print, "\r\n");

        if (0x00 <= (curr_pin = drv_fpioa_find_pin_by_func(num))) {
            mp_printf(&mp_plat_print, "current set PIN%d as %s\r\n", curr_pin, pin_func_name);
        }
    } else {
        if ((-1) == num) {
            /* dump all pin func and funcs */
            int pin_start = 0;
            int pin_end   = FPIOA_PIN_MAX_NUM;

            mp_printf(&mp_plat_print,
                      "| pin  | cur func   |                can be func                              |\r\n");
            mp_printf(&mp_plat_print,
                      "| ---- |------------|---------------------------------------------------------|\r\n");
            for (; pin_start < pin_end; pin_start++) {
                if (0x00 != drv_fpioa_get_pin_func_name(pin_start, &pin_func_name[0], sizeof(pin_func_name))) {
                    mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("get pin func name failed"));
                }

                if (0x00
                    != drv_fpioa_get_pin_alt_func_names(pin_start, &pin_alt_func_names[0],
                                                        sizeof(pin_alt_func_names))) {
                    mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("get pin alt func name failed"));
                }

                mp_printf(&mp_plat_print, "| %-2d   | %-10s | %-56s|\r\n", pin_start, pin_func_name,
                          pin_alt_func_names);
            }
        } else {
            fpioa_iomux_cfg_t cfg;
            char              pin_cfg_string[TEMP_STR_LEN];

            /* dump specify pin func */
            if ((0 > num) || (FPIOA_PIN_MAX_NUM <= num)) {
                mp_raise_msg_varg(&mp_type_ValueError, MP_ERROR_TEXT("invalid pin number %d"), num);
            }

            if (0x00 != drv_fpioa_get_pin_cfg(num, &cfg.u.value)) {
                mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("get pin cfg failed"));
            }

            if (0x00 != drv_fpioa_get_pin_func_name(num, &pin_func_name[0], sizeof(pin_func_name))) {
                mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("get pin func name failed"));
            }

            if (0x00 != drv_fpioa_get_pin_alt_func_names(num, &pin_alt_func_names[0], sizeof(pin_alt_func_names))) {
                mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("get pin alt func name failed"));
            }

            mp_printf(&mp_plat_print, "|%-17s|%-60d|\r\n", "pin num ", num);
            snprintf(pin_cfg_string, sizeof(pin_cfg_string),
                     "%s,ie:%d,oe:%d,pd:%d,pu:%d,msc:0-%s,ds:%d,st:%d,sl:%d,di:%d", pin_func_name, cfg.u.bit.ie,
                     cfg.u.bit.oe, cfg.u.bit.pd, cfg.u.bit.pu, (0x00 == cfg.u.bit.msc) ? "3.3" : "1.8", cfg.u.bit.ds,
                     cfg.u.bit.st, cfg.u.bit.rsv_bit10, cfg.u.bit.di);

            mp_printf(&mp_plat_print, "|%-17s|%-60s|\r\n", "current config", pin_cfg_string);
            mp_printf(&mp_plat_print, "|%-17s|%-60s|\r\n", "can be function", pin_alt_func_names);
        }
    }

    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_KW(machine_fpioa_help_obj, 1, machine_fpioa_help);

STATIC void machine_fpioa_print(const mp_print_t* print, mp_obj_t self_in, mp_print_kind_t kind)
{
    machine_fpioa_help(1, NULL, (mp_map_t*)&mp_const_empty_map);
}

STATIC mp_obj_t machine_fpioa_make_new(const mp_obj_type_t* type, size_t n_args, size_t n_kw, const mp_obj_t* args)
{
    mp_arg_check_num(n_args, n_kw, 0, 0, true);

    return (mp_obj_t)&machine_fpioa_obj;
}

STATIC const mp_rom_map_elem_t machine_fpioa_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR_set_function), MP_ROM_PTR(&machine_fpioa_set_function_obj) },
    { MP_ROM_QSTR(MP_QSTR_get_pin_num), MP_ROM_PTR(&machine_fpioa_get_pin_num_obj) },
    { MP_ROM_QSTR(MP_QSTR_get_pin_func), MP_ROM_PTR(&machine_fpioa_get_pin_func_obj) },

    { MP_ROM_QSTR(MP_QSTR_get_pin_cfg), MP_ROM_PTR(&machine_fpioa_get_pin_cfg_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_pin_cfg), MP_ROM_PTR(&machine_fpioa_set_pin_cfg_obj) },

    { MP_ROM_QSTR(MP_QSTR_help), MP_ROM_PTR(&machine_fpioa_help_obj) },

    { MP_ROM_QSTR(MP_QSTR_GPIO0), MP_ROM_INT(GPIO0) },
    { MP_ROM_QSTR(MP_QSTR_GPIO1), MP_ROM_INT(GPIO1) },
    { MP_ROM_QSTR(MP_QSTR_GPIO2), MP_ROM_INT(GPIO2) },
    { MP_ROM_QSTR(MP_QSTR_GPIO3), MP_ROM_INT(GPIO3) },
    { MP_ROM_QSTR(MP_QSTR_GPIO4), MP_ROM_INT(GPIO4) },
    { MP_ROM_QSTR(MP_QSTR_GPIO5), MP_ROM_INT(GPIO5) },
    { MP_ROM_QSTR(MP_QSTR_GPIO6), MP_ROM_INT(GPIO6) },
    { MP_ROM_QSTR(MP_QSTR_GPIO7), MP_ROM_INT(GPIO7) },
    { MP_ROM_QSTR(MP_QSTR_GPIO8), MP_ROM_INT(GPIO8) },
    { MP_ROM_QSTR(MP_QSTR_GPIO9), MP_ROM_INT(GPIO9) },
    { MP_ROM_QSTR(MP_QSTR_GPIO10), MP_ROM_INT(GPIO10) },
    { MP_ROM_QSTR(MP_QSTR_GPIO11), MP_ROM_INT(GPIO11) },
    { MP_ROM_QSTR(MP_QSTR_GPIO12), MP_ROM_INT(GPIO12) },
    { MP_ROM_QSTR(MP_QSTR_GPIO13), MP_ROM_INT(GPIO13) },
    { MP_ROM_QSTR(MP_QSTR_GPIO14), MP_ROM_INT(GPIO14) },
    { MP_ROM_QSTR(MP_QSTR_GPIO15), MP_ROM_INT(GPIO15) },
    { MP_ROM_QSTR(MP_QSTR_GPIO16), MP_ROM_INT(GPIO16) },
    { MP_ROM_QSTR(MP_QSTR_GPIO17), MP_ROM_INT(GPIO17) },
    { MP_ROM_QSTR(MP_QSTR_GPIO18), MP_ROM_INT(GPIO18) },
    { MP_ROM_QSTR(MP_QSTR_GPIO19), MP_ROM_INT(GPIO19) },
    { MP_ROM_QSTR(MP_QSTR_GPIO20), MP_ROM_INT(GPIO20) },
    { MP_ROM_QSTR(MP_QSTR_GPIO21), MP_ROM_INT(GPIO21) },
    { MP_ROM_QSTR(MP_QSTR_GPIO22), MP_ROM_INT(GPIO22) },
    { MP_ROM_QSTR(MP_QSTR_GPIO23), MP_ROM_INT(GPIO23) },
    { MP_ROM_QSTR(MP_QSTR_GPIO24), MP_ROM_INT(GPIO24) },
    { MP_ROM_QSTR(MP_QSTR_GPIO25), MP_ROM_INT(GPIO25) },
    { MP_ROM_QSTR(MP_QSTR_GPIO26), MP_ROM_INT(GPIO26) },
    { MP_ROM_QSTR(MP_QSTR_GPIO27), MP_ROM_INT(GPIO27) },
    { MP_ROM_QSTR(MP_QSTR_GPIO28), MP_ROM_INT(GPIO28) },
    { MP_ROM_QSTR(MP_QSTR_GPIO29), MP_ROM_INT(GPIO29) },
    { MP_ROM_QSTR(MP_QSTR_GPIO30), MP_ROM_INT(GPIO30) },
    { MP_ROM_QSTR(MP_QSTR_GPIO31), MP_ROM_INT(GPIO31) },
    { MP_ROM_QSTR(MP_QSTR_GPIO32), MP_ROM_INT(GPIO32) },
    { MP_ROM_QSTR(MP_QSTR_GPIO33), MP_ROM_INT(GPIO33) },
    { MP_ROM_QSTR(MP_QSTR_GPIO34), MP_ROM_INT(GPIO34) },
    { MP_ROM_QSTR(MP_QSTR_GPIO35), MP_ROM_INT(GPIO35) },
    { MP_ROM_QSTR(MP_QSTR_GPIO36), MP_ROM_INT(GPIO36) },
    { MP_ROM_QSTR(MP_QSTR_GPIO37), MP_ROM_INT(GPIO37) },
    { MP_ROM_QSTR(MP_QSTR_GPIO38), MP_ROM_INT(GPIO38) },
    { MP_ROM_QSTR(MP_QSTR_GPIO39), MP_ROM_INT(GPIO39) },
    { MP_ROM_QSTR(MP_QSTR_GPIO40), MP_ROM_INT(GPIO40) },
    { MP_ROM_QSTR(MP_QSTR_GPIO41), MP_ROM_INT(GPIO41) },
    { MP_ROM_QSTR(MP_QSTR_GPIO42), MP_ROM_INT(GPIO42) },
    { MP_ROM_QSTR(MP_QSTR_GPIO43), MP_ROM_INT(GPIO43) },
    { MP_ROM_QSTR(MP_QSTR_GPIO44), MP_ROM_INT(GPIO44) },
    { MP_ROM_QSTR(MP_QSTR_GPIO45), MP_ROM_INT(GPIO45) },
    { MP_ROM_QSTR(MP_QSTR_GPIO46), MP_ROM_INT(GPIO46) },
    { MP_ROM_QSTR(MP_QSTR_GPIO47), MP_ROM_INT(GPIO47) },
    { MP_ROM_QSTR(MP_QSTR_GPIO48), MP_ROM_INT(GPIO48) },
    { MP_ROM_QSTR(MP_QSTR_GPIO49), MP_ROM_INT(GPIO49) },
    { MP_ROM_QSTR(MP_QSTR_GPIO50), MP_ROM_INT(GPIO50) },
    { MP_ROM_QSTR(MP_QSTR_GPIO51), MP_ROM_INT(GPIO51) },
    { MP_ROM_QSTR(MP_QSTR_GPIO52), MP_ROM_INT(GPIO52) },
    { MP_ROM_QSTR(MP_QSTR_GPIO53), MP_ROM_INT(GPIO53) },
    { MP_ROM_QSTR(MP_QSTR_GPIO54), MP_ROM_INT(GPIO54) },
    { MP_ROM_QSTR(MP_QSTR_GPIO55), MP_ROM_INT(GPIO55) },
    { MP_ROM_QSTR(MP_QSTR_GPIO56), MP_ROM_INT(GPIO56) },
    { MP_ROM_QSTR(MP_QSTR_GPIO57), MP_ROM_INT(GPIO57) },
    { MP_ROM_QSTR(MP_QSTR_GPIO58), MP_ROM_INT(GPIO58) },
    { MP_ROM_QSTR(MP_QSTR_GPIO59), MP_ROM_INT(GPIO59) },
    { MP_ROM_QSTR(MP_QSTR_GPIO60), MP_ROM_INT(GPIO60) },
    { MP_ROM_QSTR(MP_QSTR_GPIO61), MP_ROM_INT(GPIO61) },
    { MP_ROM_QSTR(MP_QSTR_GPIO62), MP_ROM_INT(GPIO62) },
    { MP_ROM_QSTR(MP_QSTR_GPIO63), MP_ROM_INT(GPIO63) },
    { MP_ROM_QSTR(MP_QSTR_GPIO64), MP_ROM_INT(GPIO64) },
    { MP_ROM_QSTR(MP_QSTR_GPIO65), MP_ROM_INT(GPIO65) },
    { MP_ROM_QSTR(MP_QSTR_GPIO66), MP_ROM_INT(GPIO66) },
    { MP_ROM_QSTR(MP_QSTR_GPIO67), MP_ROM_INT(GPIO67) },
    { MP_ROM_QSTR(MP_QSTR_GPIO68), MP_ROM_INT(GPIO68) },
    { MP_ROM_QSTR(MP_QSTR_GPIO69), MP_ROM_INT(GPIO69) },
    { MP_ROM_QSTR(MP_QSTR_GPIO70), MP_ROM_INT(GPIO70) },
    { MP_ROM_QSTR(MP_QSTR_GPIO71), MP_ROM_INT(GPIO71) },
    { MP_ROM_QSTR(MP_QSTR_BOOT0), MP_ROM_INT(BOOT0) },
    { MP_ROM_QSTR(MP_QSTR_BOOT1), MP_ROM_INT(BOOT1) },
    { MP_ROM_QSTR(MP_QSTR_HSYNC0), MP_ROM_INT(HSYNC0) },
    { MP_ROM_QSTR(MP_QSTR_HSYNC1), MP_ROM_INT(HSYNC1) },
    { MP_ROM_QSTR(MP_QSTR_IIC0_SCL), MP_ROM_INT(IIC0_SCL) },
    { MP_ROM_QSTR(MP_QSTR_IIC0_SDA), MP_ROM_INT(IIC0_SDA) },
    { MP_ROM_QSTR(MP_QSTR_IIC1_SCL), MP_ROM_INT(IIC1_SCL) },
    { MP_ROM_QSTR(MP_QSTR_IIC1_SDA), MP_ROM_INT(IIC1_SDA) },
    { MP_ROM_QSTR(MP_QSTR_IIC2_SCL), MP_ROM_INT(IIC2_SCL) },
    { MP_ROM_QSTR(MP_QSTR_IIC2_SDA), MP_ROM_INT(IIC2_SDA) },
    { MP_ROM_QSTR(MP_QSTR_IIC3_SCL), MP_ROM_INT(IIC3_SCL) },
    { MP_ROM_QSTR(MP_QSTR_IIC3_SDA), MP_ROM_INT(IIC3_SDA) },
    { MP_ROM_QSTR(MP_QSTR_IIC4_SCL), MP_ROM_INT(IIC4_SCL) },
    { MP_ROM_QSTR(MP_QSTR_IIC4_SDA), MP_ROM_INT(IIC4_SDA) },
    { MP_ROM_QSTR(MP_QSTR_IIS_CLK), MP_ROM_INT(IIS_CLK) },
    { MP_ROM_QSTR(MP_QSTR_IIS_D_IN0_PDM_IN3), MP_ROM_INT(IIS_D_IN0_PDM_IN3) },
    { MP_ROM_QSTR(MP_QSTR_IIS_D_IN1_PDM_IN2), MP_ROM_INT(IIS_D_IN1_PDM_IN2) },
    { MP_ROM_QSTR(MP_QSTR_IIS_D_OUT0_PDM_IN1), MP_ROM_INT(IIS_D_OUT0_PDM_IN1) },
    { MP_ROM_QSTR(MP_QSTR_IIS_D_OUT1_PDM_IN0), MP_ROM_INT(IIS_D_OUT1_PDM_IN0) },
    { MP_ROM_QSTR(MP_QSTR_IIS_WS), MP_ROM_INT(IIS_WS) },
    { MP_ROM_QSTR(MP_QSTR_JTAG_RST), MP_ROM_INT(JTAG_RST) },
    { MP_ROM_QSTR(MP_QSTR_JTAG_TCK), MP_ROM_INT(JTAG_TCK) },
    { MP_ROM_QSTR(MP_QSTR_JTAG_TDI), MP_ROM_INT(JTAG_TDI) },
    { MP_ROM_QSTR(MP_QSTR_JTAG_TDO), MP_ROM_INT(JTAG_TDO) },
    { MP_ROM_QSTR(MP_QSTR_JTAG_TMS), MP_ROM_INT(JTAG_TMS) },
    { MP_ROM_QSTR(MP_QSTR_M_CLK1), MP_ROM_INT(M_CLK1) },
    { MP_ROM_QSTR(MP_QSTR_M_CLK2), MP_ROM_INT(M_CLK2) },
    { MP_ROM_QSTR(MP_QSTR_M_CLK3), MP_ROM_INT(M_CLK3) },
    { MP_ROM_QSTR(MP_QSTR_MMC1_CLK), MP_ROM_INT(MMC1_CLK) },
    { MP_ROM_QSTR(MP_QSTR_MMC1_CMD), MP_ROM_INT(MMC1_CMD) },
    { MP_ROM_QSTR(MP_QSTR_MMC1_D0), MP_ROM_INT(MMC1_D0) },
    { MP_ROM_QSTR(MP_QSTR_MMC1_D1), MP_ROM_INT(MMC1_D1) },
    { MP_ROM_QSTR(MP_QSTR_MMC1_D2), MP_ROM_INT(MMC1_D2) },
    { MP_ROM_QSTR(MP_QSTR_MMC1_D3), MP_ROM_INT(MMC1_D3) },
    { MP_ROM_QSTR(MP_QSTR_OSPI_CLK), MP_ROM_INT(OSPI_CLK) },
    { MP_ROM_QSTR(MP_QSTR_OSPI_CS), MP_ROM_INT(OSPI_CS) },
    { MP_ROM_QSTR(MP_QSTR_OSPI_D0), MP_ROM_INT(OSPI_D0) },
    { MP_ROM_QSTR(MP_QSTR_OSPI_D1), MP_ROM_INT(OSPI_D1) },
    { MP_ROM_QSTR(MP_QSTR_OSPI_D2), MP_ROM_INT(OSPI_D2) },
    { MP_ROM_QSTR(MP_QSTR_OSPI_D3), MP_ROM_INT(OSPI_D3) },
    { MP_ROM_QSTR(MP_QSTR_OSPI_D4), MP_ROM_INT(OSPI_D4) },
    { MP_ROM_QSTR(MP_QSTR_OSPI_D5), MP_ROM_INT(OSPI_D5) },
    { MP_ROM_QSTR(MP_QSTR_OSPI_D6), MP_ROM_INT(OSPI_D6) },
    { MP_ROM_QSTR(MP_QSTR_OSPI_D7), MP_ROM_INT(OSPI_D7) },
    { MP_ROM_QSTR(MP_QSTR_OSPI_DQS), MP_ROM_INT(OSPI_DQS) },
    { MP_ROM_QSTR(MP_QSTR_PDM_IN0), MP_ROM_INT(PDM_IN0) },
    { MP_ROM_QSTR(MP_QSTR_PDM_IN1), MP_ROM_INT(PDM_IN1) },
    { MP_ROM_QSTR(MP_QSTR_PDM_IN2), MP_ROM_INT(PDM_IN2) },
    { MP_ROM_QSTR(MP_QSTR_PDM_IN3), MP_ROM_INT(PDM_IN3) },
    { MP_ROM_QSTR(MP_QSTR_PULSE_CNTR0), MP_ROM_INT(PULSE_CNTR0) },
    { MP_ROM_QSTR(MP_QSTR_PULSE_CNTR1), MP_ROM_INT(PULSE_CNTR1) },
    { MP_ROM_QSTR(MP_QSTR_PULSE_CNTR2), MP_ROM_INT(PULSE_CNTR2) },
    { MP_ROM_QSTR(MP_QSTR_PULSE_CNTR3), MP_ROM_INT(PULSE_CNTR3) },
    { MP_ROM_QSTR(MP_QSTR_PULSE_CNTR4), MP_ROM_INT(PULSE_CNTR4) },
    { MP_ROM_QSTR(MP_QSTR_PULSE_CNTR5), MP_ROM_INT(PULSE_CNTR5) },
    { MP_ROM_QSTR(MP_QSTR_PWM0), MP_ROM_INT(PWM0) },
    { MP_ROM_QSTR(MP_QSTR_PWM1), MP_ROM_INT(PWM1) },
    { MP_ROM_QSTR(MP_QSTR_PWM2), MP_ROM_INT(PWM2) },
    { MP_ROM_QSTR(MP_QSTR_PWM3), MP_ROM_INT(PWM3) },
    { MP_ROM_QSTR(MP_QSTR_PWM4), MP_ROM_INT(PWM4) },
    { MP_ROM_QSTR(MP_QSTR_PWM5), MP_ROM_INT(PWM5) },
    { MP_ROM_QSTR(MP_QSTR_QSPI0_CLK), MP_ROM_INT(QSPI0_CLK) },
    { MP_ROM_QSTR(MP_QSTR_QSPI0_CS0), MP_ROM_INT(QSPI0_CS0) },
    { MP_ROM_QSTR(MP_QSTR_QSPI0_CS1), MP_ROM_INT(QSPI0_CS1) },
    { MP_ROM_QSTR(MP_QSTR_QSPI0_CS2), MP_ROM_INT(QSPI0_CS2) },
    { MP_ROM_QSTR(MP_QSTR_QSPI0_CS3), MP_ROM_INT(QSPI0_CS3) },
    { MP_ROM_QSTR(MP_QSTR_QSPI0_CS4), MP_ROM_INT(QSPI0_CS4) },
    { MP_ROM_QSTR(MP_QSTR_QSPI0_D0), MP_ROM_INT(QSPI0_D0) },
    { MP_ROM_QSTR(MP_QSTR_QSPI0_D1), MP_ROM_INT(QSPI0_D1) },
    { MP_ROM_QSTR(MP_QSTR_QSPI0_D2), MP_ROM_INT(QSPI0_D2) },
    { MP_ROM_QSTR(MP_QSTR_QSPI0_D3), MP_ROM_INT(QSPI0_D3) },
    { MP_ROM_QSTR(MP_QSTR_QSPI1_CLK), MP_ROM_INT(QSPI1_CLK) },
    { MP_ROM_QSTR(MP_QSTR_QSPI1_CS0), MP_ROM_INT(QSPI1_CS0) },
    { MP_ROM_QSTR(MP_QSTR_QSPI1_CS1), MP_ROM_INT(QSPI1_CS1) },
    { MP_ROM_QSTR(MP_QSTR_QSPI1_CS2), MP_ROM_INT(QSPI1_CS2) },
    { MP_ROM_QSTR(MP_QSTR_QSPI1_CS3), MP_ROM_INT(QSPI1_CS3) },
    { MP_ROM_QSTR(MP_QSTR_QSPI1_CS4), MP_ROM_INT(QSPI1_CS4) },
    { MP_ROM_QSTR(MP_QSTR_QSPI1_D0), MP_ROM_INT(QSPI1_D0) },
    { MP_ROM_QSTR(MP_QSTR_QSPI1_D1), MP_ROM_INT(QSPI1_D1) },
    { MP_ROM_QSTR(MP_QSTR_QSPI1_D2), MP_ROM_INT(QSPI1_D2) },
    { MP_ROM_QSTR(MP_QSTR_QSPI1_D3), MP_ROM_INT(QSPI1_D3) },
    { MP_ROM_QSTR(MP_QSTR_SPI2AXI_CK), MP_ROM_INT(SPI2AXI_CK) },
    { MP_ROM_QSTR(MP_QSTR_SPI2AXI_CS), MP_ROM_INT(SPI2AXI_CS) },
    { MP_ROM_QSTR(MP_QSTR_SPI2AXI_DI), MP_ROM_INT(SPI2AXI_DI) },
    { MP_ROM_QSTR(MP_QSTR_SPI2AXI_DO), MP_ROM_INT(SPI2AXI_DO) },
    { MP_ROM_QSTR(MP_QSTR_UART0_RXD), MP_ROM_INT(UART0_RXD) },
    { MP_ROM_QSTR(MP_QSTR_UART0_TXD), MP_ROM_INT(UART0_TXD) },
    { MP_ROM_QSTR(MP_QSTR_UART1_CTS), MP_ROM_INT(UART1_CTS) },
    { MP_ROM_QSTR(MP_QSTR_UART1_RTS), MP_ROM_INT(UART1_RTS) },
    { MP_ROM_QSTR(MP_QSTR_UART1_RXD), MP_ROM_INT(UART1_RXD) },
    { MP_ROM_QSTR(MP_QSTR_UART1_TXD), MP_ROM_INT(UART1_TXD) },
    { MP_ROM_QSTR(MP_QSTR_UART2_CTS), MP_ROM_INT(UART2_CTS) },
    { MP_ROM_QSTR(MP_QSTR_UART2_RTS), MP_ROM_INT(UART2_RTS) },
    { MP_ROM_QSTR(MP_QSTR_UART2_RXD), MP_ROM_INT(UART2_RXD) },
    { MP_ROM_QSTR(MP_QSTR_UART2_TXD), MP_ROM_INT(UART2_TXD) },
    { MP_ROM_QSTR(MP_QSTR_UART3_CTS), MP_ROM_INT(UART3_CTS) },
    { MP_ROM_QSTR(MP_QSTR_UART3_DE), MP_ROM_INT(UART3_DE) },
    { MP_ROM_QSTR(MP_QSTR_UART3_RE), MP_ROM_INT(UART3_RE) },
    { MP_ROM_QSTR(MP_QSTR_UART3_RTS), MP_ROM_INT(UART3_RTS) },
    { MP_ROM_QSTR(MP_QSTR_UART3_RXD), MP_ROM_INT(UART3_RXD) },
    { MP_ROM_QSTR(MP_QSTR_UART3_TXD), MP_ROM_INT(UART3_TXD) },
    { MP_ROM_QSTR(MP_QSTR_UART4_RXD), MP_ROM_INT(UART4_RXD) },
    { MP_ROM_QSTR(MP_QSTR_UART4_TXD), MP_ROM_INT(UART4_TXD) },
    { MP_ROM_QSTR(MP_QSTR_PDM_CLK), MP_ROM_INT(PDM_CLK) },
    { MP_ROM_QSTR(MP_QSTR_VSYNC0), MP_ROM_INT(VSYNC0) },
    { MP_ROM_QSTR(MP_QSTR_VSYNC1), MP_ROM_INT(VSYNC1) },
    { MP_ROM_QSTR(MP_QSTR_CTRL_IN_3D), MP_ROM_INT(CTRL_IN_3D) },
    { MP_ROM_QSTR(MP_QSTR_CTRL_O1_3D), MP_ROM_INT(CTRL_O1_3D) },
    { MP_ROM_QSTR(MP_QSTR_CTRL_O2_3D), MP_ROM_INT(CTRL_O2_3D) },
};
STATIC MP_DEFINE_CONST_DICT(machine_fpioa_locals_dict, machine_fpioa_locals_dict_table);

/* clang-format off */
MP_DEFINE_CONST_OBJ_TYPE(
    machine_fpioa_type,
    MP_QSTR_FPIOA,
    MP_TYPE_FLAG_NONE,
    make_new, machine_fpioa_make_new,
    print, machine_fpioa_print,
    locals_dict, &machine_fpioa_locals_dict
);
/* clang-format ob */
