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
#include "py/runtime.h"

#include "extmod/modmachine.h"

#include "drv_adc.h"

struct _machine_adc_obj_t {
    mp_obj_base_t base;
    int           channel;
    uint32_t      ref_uv;
};

static void mp_machine_adc_print(const mp_print_t* print, mp_obj_t self_in, mp_print_kind_t kind)
{
    machine_adc_obj_t* self = MP_OBJ_TO_PTR(self_in);
    mp_printf(print, "ADC(%d) Ref_uv(%d)", self->channel, self->ref_uv);
}

static mp_obj_t mp_machine_adc_make_new(const mp_obj_type_t* type, size_t n_args, size_t n_kw, const mp_obj_t* all_args)
{
    enum { ARG_channel, ARG_ref_uv };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_channel, MP_ARG_INT, { .u_int = -1 } },
        { MP_QSTR_ref_uv, MP_ARG_KW_ONLY | MP_ARG_INT, { .u_int = DRV_ADC_DEFAULT_REF_UV } },
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all_kw_array(n_args, n_kw, all_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    int channel = args[ARG_channel].u_int;
    if (channel < 0 || channel >= DRV_ADC_MAX_CHANNEL) {
        mp_raise_msg_varg(&mp_type_ValueError, MP_ERROR_TEXT("invalid adc channel"));
    }

    if (drv_adc_init() != 0x00) {
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("adc init failed"));
    }

    machine_adc_obj_t* self = mp_obj_malloc_with_finaliser(machine_adc_obj_t, &machine_adc_type);
    self->channel           = channel;
    self->ref_uv            = args[ARG_ref_uv].u_int;

    return MP_OBJ_FROM_PTR(self);
}

static mp_int_t mp_machine_adc_read(machine_adc_obj_t* self)
{
    uint32_t value = drv_adc_read(self->channel);

    if (__UINT32_MAX__ == value) {
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("adc read failed"));
    }

    return value;
}

static mp_int_t mp_machine_adc_read_u16(machine_adc_obj_t* self)
{
    uint32_t value = drv_adc_read(self->channel);

    if (__UINT32_MAX__ == value) {
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("adc read failed"));
    }

    uint32_t max_code = DRV_ADC_RESOLUTION;
    uint32_t scaled   = (value * 65535 + max_code / 2) / max_code;

    if (scaled > 65535) {
        scaled = 65535;
    }

    return scaled;
}

static void mp_machine_adc_deinit(machine_adc_obj_t* self) { drv_adc_deinit(); }

static mp_int_t mp_machine_adc_read_uv(machine_adc_obj_t* self)
{
    uint32_t value = drv_adc_read_uv(self->channel, self->ref_uv);

    if (__UINT32_MAX__ == value) {
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("adc read failed"));
    }

    return value;
}

static mp_obj_t machine_adc_ref_uv(size_t n, const mp_obj_t* args)
{
    machine_adc_obj_t* self = MP_OBJ_TO_PTR(args[0]);

    if (0x02 == n) {
        self->ref_uv = mp_obj_get_int(args[1]);
    }

    return mp_obj_new_int(self->ref_uv);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(machine_adc_ref_uv_obj, 1, 2, machine_adc_ref_uv);

#define MICROPY_PY_MACHINE_ADC_CLASS_CONSTANTS                                                                                 \
    { MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&machine_adc_deinit_obj) },                                                     \
        { MP_ROM_QSTR(MP_QSTR_ref_uv), MP_ROM_PTR(&machine_adc_ref_uv_obj) },
