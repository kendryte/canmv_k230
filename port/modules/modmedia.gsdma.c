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
#include "k_vb_comm.h"
#include "k_vo_comm.h"
#include "mpi_gsdma_api.h"
#include "mpi_vb_api.h"

#include "py/obj.h"
#include "py/runtime.h"

#include "py_assert.h" // use openmv marco, PY_ASSERT_TYPE
#include "py_image.h"

#include "mpprint.h"

#include "py_modules.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/*
    args[0]: phys_addr_obj
    args[1]: phys_size_obj
    args[2]: data
    args[3]: data_size
*/
STATIC mp_obj_t gsdma_sdma_memset(size_t n, const mp_obj_t* args)
{
    int result = 1;

    k_sdma_memset_t cfg;
    k_u32           data_size = SDMA_DATA_SIZE_1_BYTE;

    cfg.phys_addr = mp_obj_get_int(args[0]);
    cfg.size      = mp_obj_get_int(args[1]);
    cfg.data      = mp_obj_get_int(args[2]);

    if (4 <= n) {
        data_size = mp_obj_get_int(args[3]);

        switch (data_size) {
        case 4:
        case 32:
            cfg.data_size = SDMA_DATA_SIZE_4_BYTE;

            if (cfg.size % 4) {
                mp_raise_msg_varg(&mp_type_ValueError, MP_ERROR_TEXT("invalid data size %d"), data_size);
            }
            break;
        case 2:
        case 16:
            cfg.data_size = SDMA_DATA_SIZE_2_BYTE;

            if (cfg.size % 2) {
                mp_raise_msg_varg(&mp_type_ValueError, MP_ERROR_TEXT("invalid data size %d"), data_size);
            }
            break;
        case 1:
        case 8:
            cfg.data_size = SDMA_DATA_SIZE_1_BYTE;
            break;
        default:
            mp_raise_msg_varg(&mp_type_ValueError, MP_ERROR_TEXT("invalid data size %d"), data_size);
            break;
        }
    }

    MP_THREAD_GIL_EXIT();
    if (0x00 != kd_mpi_gsdma_sdma_memset(&cfg)) {
        result = 0x00;

        mp_printf(&mp_plat_print, "sdma memset failed\n");
    }
    MP_THREAD_GIL_ENTER();

    return result ? mp_const_true : mp_const_false;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(gsdma_sdma_memset_obj, 3, 4, gsdma_sdma_memset);
STATIC MP_DEFINE_CONST_STATICMETHOD_OBJ(gsdma_sdma_memset_method, MP_ROM_PTR(&gsdma_sdma_memset_obj));

STATIC mp_obj_t gsdma_sdma_memcpy(mp_obj_t dst_addr_obj, mp_obj_t src_addr_obj, mp_obj_t size_obj)
{
    int result = 1;

    k_sdma_memcpy_t cfg;

    cfg.dst_phys_addr = mp_obj_get_int(dst_addr_obj);
    cfg.src_phys_addr = mp_obj_get_int(src_addr_obj);
    cfg.size          = mp_obj_get_int(size_obj);
    cfg.timeout_ms    = 1000;

    MP_THREAD_GIL_EXIT();
    if (0x00 != kd_mpi_gsdma_sdma_memcpy(&cfg)) {
        result = 0x00;

        mp_printf(&mp_plat_print, "sdma memcpy failed\n");
    }
    MP_THREAD_GIL_ENTER();

    return result ? mp_const_true : mp_const_false;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_3(gsdma_sdma_memcpy_obj, gsdma_sdma_memcpy);
STATIC MP_DEFINE_CONST_STATICMETHOD_OBJ(gsdma_sdma_memcpy_method, MP_ROM_PTR(&gsdma_sdma_memcpy_obj));

/**
    args[0]: src_vf_info_obj
    args[1]: dst_phys_addr_obj
    args[2]: dst_phys_size_obj
    args[3]: rotate_flag
*/
STATIC mp_obj_t gsdma_gdma_convert(size_t n, const mp_obj_t* args)
{
    int result = 1;

    mp_buffer_info_t bufinfo;

    k_video_frame_info* src_vf_obj = NULL;

    k_u64 dst_phys_addr;
    k_u64 dst_phys_size;

    (void)dst_phys_size;

    k_gdma_chn_cfg_t chn_cfg = { 0, 0 };

    if (4 > n) {
        mp_raise_msg_varg(&mp_type_AssertionError, MP_ERROR_TEXT("Invalid args"));
    }

    if (mp_obj_is_type(args[0], &py_media_video_frame_info_type)) {
        src_vf_obj = py_video_frame_info_cobj(args[0]);
    } else {
        mp_get_buffer_raise(args[0], &bufinfo, MP_BUFFER_READ);

        if (sizeof(k_video_frame_info) != bufinfo.len) {
            mp_raise_msg_varg(&mp_type_TypeError, MP_ERROR_TEXT("expect size: %u, actual size: %u"), sizeof(k_video_frame_info),
                              bufinfo.len);
        }

        src_vf_obj = (k_video_frame_info*)bufinfo.buf;
    }

    dst_phys_addr    = mp_obj_get_int(args[1]);
    dst_phys_size    = mp_obj_get_int(args[2]);
    chn_cfg.rotation = mp_obj_get_int(args[3]);

    MP_THREAD_GIL_EXIT();
    if (0x00 != kd_mpi_gsdma_send_buffer(&chn_cfg, src_vf_obj, dst_phys_addr, dst_phys_size, 1000)) {
        result = 0;

        mp_printf(&mp_plat_print, "gdma rotate failed\n");
    }
    MP_THREAD_GIL_ENTER();

    return result ? mp_const_true : mp_const_false;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(gsdma_gdma_convert_obj, 4, 4, gsdma_gdma_convert);
STATIC MP_DEFINE_CONST_STATICMETHOD_OBJ(gsdma_gdma_convert_method, MP_ROM_PTR(&gsdma_gdma_convert_obj));

STATIC const mp_rom_map_elem_t gsdma_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR_sdma_memcpy), MP_ROM_PTR(&gsdma_sdma_memcpy_method) },
    { MP_ROM_QSTR(MP_QSTR_sdma_memset), MP_ROM_PTR(&gsdma_sdma_memset_method) },
    { MP_ROM_QSTR(MP_QSTR_gdma_convert), MP_ROM_PTR(&gsdma_gdma_convert_method) },

    { MP_ROM_QSTR(MP_QSTR_DEGREE_0), MP_ROM_INT(GDMA_ROTATE_DEGREE_0) },
    { MP_ROM_QSTR(MP_QSTR_DEGREE_90), MP_ROM_INT(GDMA_ROTATE_DEGREE_90) },
    { MP_ROM_QSTR(MP_QSTR_DEGREE_180), MP_ROM_INT(GDMA_ROTATE_DEGREE_180) },
    { MP_ROM_QSTR(MP_QSTR_DEGREE_270), MP_ROM_INT(GDMA_ROTATE_DEGREE_270) },

    { MP_ROM_QSTR(MP_QSTR_MIRROR_HOR), MP_ROM_INT(GDMA_ROTATE_MIRROR_HOR) },
    { MP_ROM_QSTR(MP_QSTR_MIRROR_VER), MP_ROM_INT(GDMA_ROTATE_MIRROR_VER) },
};
STATIC MP_DEFINE_CONST_DICT(gsdma_locals_dict, gsdma_locals_dict_table);

/* clang-format off */
MP_DEFINE_CONST_OBJ_TYPE(
    py_media_gsdma_type,
    MP_QSTR_GSDMA,
    MP_TYPE_FLAG_NONE,
    locals_dict, &gsdma_locals_dict
);
/* clang-format on */
