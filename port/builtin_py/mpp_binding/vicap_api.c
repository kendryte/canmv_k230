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
#include <unistd.h>
#include <errno.h>

#include "py/runtime.h"
#include "py/obj.h"

#include "k_vicap_comm.h"
#include "mpi_vicap_api.h"
#include "mpi_sensor_api.h"
#include "mpp_vb_mgmt.h"

#define DEF_FUNC_ADD(x) { MP_ROM_QSTR(MP_QSTR_##x), MP_ROM_PTR(&x##_obj) },

STATIC mp_obj_t _kd_mpi_vicap_dump_frame(size_t n_args, const mp_obj_t *args) {
    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(args[3], &bufinfo, MP_BUFFER_READ);
    if (sizeof(k_video_frame_info) != bufinfo.len)
        mp_raise_msg_varg(&mp_type_TypeError,
            MP_ERROR_TEXT("struct expect size: %u, actual size: %u"),
            sizeof(k_video_frame_info), bufinfo.len);
    MP_THREAD_GIL_EXIT();
    size_t ret = kd_mpi_vicap_dump_frame(mp_obj_get_int(args[0]),
        mp_obj_get_int(args[1]), mp_obj_get_int(args[2]),
        (k_video_frame_info *)(bufinfo.buf), mp_obj_get_int(args[4]));
    MP_THREAD_GIL_ENTER();
    return mp_obj_new_int(ret);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(kd_mpi_vicap_dump_frame_obj, 5, 5, _kd_mpi_vicap_dump_frame);

STATIC mp_obj_t _kd_mpi_vicap_set_mclk(size_t n_args, const mp_obj_t *args) {
    size_t ret = kd_mpi_vicap_set_mclk(mp_obj_get_int(args[0]),
        mp_obj_get_int(args[1]), mp_obj_get_int(args[2]),
        mp_obj_get_int(args[3]));
    return mp_obj_new_int(ret);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(kd_mpi_vicap_set_mclk_obj, 4, 4, _kd_mpi_vicap_set_mclk);

STATIC mp_obj_t get_board_default_sensor_csi_num(void) {
    return mp_obj_new_int(CONFIG_MPP_SENSOR_DEFAULT_CSI);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_0(get_board_default_sensor_csi_num_obj, get_board_default_sensor_csi_num);

STATIC mp_obj_t _kd_mpi_auto_focus(size_t n_args, const mp_obj_t *args) {
    int dev_num = mp_obj_get_int(args[0]);

    if ((0x01 == n_args) || (args[1] == mp_const_none)) {
        k_bool status = K_FALSE;
        kd_mpi_vicap_get_af_enable(dev_num, &status);
        return mp_obj_new_bool(K_TRUE == status);
    } else {
        int status = mp_obj_get_int(args[1]);
        if(0x00 == kd_mpi_vicap_set_af_enable(dev_num, status)) {
            return mp_const_true;
        } else {
            return mp_const_false;
        }
    }
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(kd_mpi_auto_focus_obj, 1, 2, _kd_mpi_auto_focus);

STATIC mp_obj_t _kd_mpi_focus_pos(size_t n_args, const mp_obj_t *args) {
    k_sensor_focus_pos pos;
    int sensor_fd = mp_obj_get_int(args[0]);

    if(0 > sensor_fd) {
        mp_raise_ValueError(MP_ERROR_TEXT("Invaild sensor fd"));
    }

    if ((0x01 == n_args) || (args[1] == mp_const_none)) {
        if(0x00 != kd_mpi_sensor_get_focus_pos(sensor_fd, &pos)) {
            return mp_const_none;
        }
        return mp_obj_new_int(pos.pos);
    } else {
        pos.pos = mp_obj_get_int(args[1]);
        if(0x00 != kd_mpi_sensor_set_focus_pos(sensor_fd, &pos)) {
            return mp_const_none;
        }
        return mp_const_true;
    }
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(kd_mpi_focus_pos_obj, 1, 2, _kd_mpi_focus_pos);

STATIC mp_obj_t _kd_mpi_sensor_get_focus_caps(mp_obj_t self_in) {
    k_sensor_autofocus_caps caps;

    int sensor_fd = mp_obj_get_int(self_in);
    if(0 > sensor_fd) {
        mp_raise_ValueError(MP_ERROR_TEXT("Invaild sensor fd"));
    }

    if (0x00 != kd_mpi_sensor_get_focus_caps(sensor_fd, &caps)) {
        return mp_const_none;
    }

    return mp_obj_new_tuple(3, ((mp_obj_t []) {
        mp_obj_new_int(caps.isSupport),
        mp_obj_new_int(caps.minPos),
        mp_obj_new_int(caps.maxPos),
    }));
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(kd_mpi_sensor_get_focus_caps_obj, _kd_mpi_sensor_get_focus_caps);

#define FUNC_IMPL
#define FUNC_FILE "vicap_func_def.h"
#include "func_def.h"

STATIC const mp_rom_map_elem_t vicap_api_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_vicap_api) },
    { MP_ROM_QSTR(MP_QSTR_get_default_sensor), MP_ROM_PTR(&get_board_default_sensor_csi_num_obj) },
    DEF_FUNC_ADD(kd_mpi_vicap_dump_frame)
    DEF_FUNC_ADD(kd_mpi_vicap_set_mclk)
    DEF_FUNC_ADD(kd_mpi_auto_focus)
    DEF_FUNC_ADD(kd_mpi_focus_pos)
    DEF_FUNC_ADD(kd_mpi_sensor_get_focus_caps)
#define FUNC_ADD
#define FUNC_FILE "vicap_func_def.h"
#include "func_def.h"
};
STATIC MP_DEFINE_CONST_DICT(vicap_api_locals_dict, vicap_api_locals_dict_table);

const mp_obj_module_t mp_module_vicap_api = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&vicap_api_locals_dict,
};
