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

#include "py/runtime.h"
#include "py/obj.h"

extern const mp_obj_module_t mp_module_sys_api;
extern const mp_obj_module_t mp_module_vb_api;
extern const mp_obj_module_t mp_module_vo_api;
extern const mp_obj_module_t mp_module_connector_api;
extern const mp_obj_module_t mp_module_vicap_api;
extern const mp_obj_module_t mp_module_ai_api;
extern const mp_obj_module_t mp_module_ao_api;
extern const mp_obj_module_t mp_module_aenc_api;
extern const mp_obj_module_t mp_module_adec_api;
extern const mp_obj_module_t mp_module_venc_api;
extern const mp_obj_module_t mp_module_vdec_api;
extern const mp_obj_module_t mp_module_mp4_format_api;
extern const mp_obj_module_t mp_module_pm_api;
extern const mp_obj_module_t mp_module_libogg_api;

STATIC const mp_rom_map_elem_t mpp_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_mpp) },
    { MP_ROM_QSTR(MP_QSTR_sys_api), MP_ROM_PTR(&mp_module_sys_api) },
    { MP_ROM_QSTR(MP_QSTR_vb_api), MP_ROM_PTR(&mp_module_vb_api) },
    { MP_ROM_QSTR(MP_QSTR_vo_api), MP_ROM_PTR(&mp_module_vo_api) },
    { MP_ROM_QSTR(MP_QSTR_connector_api), MP_ROM_PTR(&mp_module_connector_api) },
    { MP_ROM_QSTR(MP_QSTR_vicap_api), MP_ROM_PTR(&mp_module_vicap_api) },
    { MP_ROM_QSTR(MP_QSTR_ai_api), MP_ROM_PTR(&mp_module_ai_api) },
    { MP_ROM_QSTR(MP_QSTR_ao_api), MP_ROM_PTR(&mp_module_ao_api) },
    { MP_ROM_QSTR(MP_QSTR_aenc_api), MP_ROM_PTR(&mp_module_aenc_api) },
    { MP_ROM_QSTR(MP_QSTR_adec_api), MP_ROM_PTR(&mp_module_adec_api) },
    { MP_ROM_QSTR(MP_QSTR_venc_api), MP_ROM_PTR(&mp_module_venc_api) },
    { MP_ROM_QSTR(MP_QSTR_vdec_api), MP_ROM_PTR(&mp_module_vdec_api) },
    { MP_ROM_QSTR(MP_QSTR_mp4_format_api), MP_ROM_PTR(&mp_module_mp4_format_api) },
    { MP_ROM_QSTR(MP_QSTR_pm_api), MP_ROM_PTR(&mp_module_pm_api) },
    { MP_ROM_QSTR(MP_QSTR_libogg_api), MP_ROM_PTR(&mp_module_libogg_api) },
};

STATIC MP_DEFINE_CONST_DICT(mpp_module_globals, mpp_module_globals_table);

const mp_obj_module_t mp_module_mpp = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&mpp_module_globals,
};

MP_REGISTER_EXTENSIBLE_MODULE(MP_QSTR_mpp, mp_module_mpp);
