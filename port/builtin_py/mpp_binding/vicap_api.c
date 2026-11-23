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
#include "mpi_isp_api.h"
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

STATIC mp_obj_t _kd_mpi_sensor_get_exposure_time_range(mp_obj_t self_in) {
    k_sensor_exposure_time_range range;

    int sensor_fd = mp_obj_get_int(self_in);
    if(0 > sensor_fd) {
        mp_raise_ValueError(MP_ERROR_TEXT("Invalid sensor fd"));
    }

    if (0x00 != kd_mpi_sensor_get_exposure_time_range(sensor_fd, &range)) {
        return mp_const_none;
    }

    return mp_obj_new_tuple(2, ((mp_obj_t []) {
        mp_obj_new_float(range.max_intg_time_us),
        mp_obj_new_float(range.min_intg_time_us),
    }));
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(kd_mpi_sensor_get_exposure_time_range_obj, _kd_mpi_sensor_get_exposure_time_range);


STATIC mp_obj_t _kd_mpi_sensor_intg_time_get(mp_obj_t self_in) {
    k_sensor_intg_time time;
    int sensor_fd = mp_obj_get_int(self_in);
    
    if(0 > sensor_fd) {
        mp_raise_ValueError(MP_ERROR_TEXT("Invalid sensor fd"));
    }
    
    if (0x00 != kd_mpi_sensor_intg_time_get(sensor_fd, &time)) {
        return mp_const_none;
    }
    
    // Return exposure time in seconds
    return mp_obj_new_float(time.intg_time[SENSOR_LINEAR_PARAS]);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(kd_mpi_sensor_intg_time_get_obj, _kd_mpi_sensor_intg_time_get);

STATIC mp_obj_t _kd_mpi_sensor_intg_time_set(size_t n_args, const mp_obj_t *args) {
    k_sensor_intg_time time;
    int sensor_fd = mp_obj_get_int(args[0]);
    
    if(0 > sensor_fd) {
        mp_raise_ValueError(MP_ERROR_TEXT("Invalid sensor fd"));
    }
    
    if (n_args < 2 || args[1] == mp_const_none) {
        mp_raise_ValueError(MP_ERROR_TEXT("Missing integration time parameter"));
    }
    
    // Support float or int parameter (in seconds)
    if (mp_obj_is_float(args[1]) || mp_obj_is_int(args[1])) {
        time.intg_time[SENSOR_LINEAR_PARAS] = mp_obj_get_float(args[1]);
    } else {
        mp_raise_TypeError(MP_ERROR_TEXT("Time must be a float or int (in seconds)"));
    }
    
    if (0x00 != kd_mpi_sensor_intg_time_set(sensor_fd, time)) {
        return mp_const_false;
    }
    return mp_const_true;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(kd_mpi_sensor_intg_time_set_obj, 1, 2, _kd_mpi_sensor_intg_time_set);


#define FUNC_IMPL
#define FUNC_FILE "vicap_func_def.h"
#include "func_def.h"

STATIC mp_obj_t _kd_mpi_sensor_list_mode(mp_obj_t sensor_name) {
    k_sensor_mode_list list;
    const char *name = mp_obj_str_get_str(sensor_name);
    
    if (0x00 != kd_mpi_sensor_list_mode(name, &list)) {
        return mp_const_none;
    }
    
    mp_obj_list_t *py_list = MP_OBJ_TO_PTR(mp_obj_new_list(list.count, NULL));
    
    for (k_u32 i = 0; i < list.count; i++) {
        mp_obj_t dict = mp_obj_new_dict(3);
        mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_width), 
                          mp_obj_new_int(list.modes[i].width));
        mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_height), 
                          mp_obj_new_int(list.modes[i].height));
        mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_fps), 
                          mp_obj_new_int(list.modes[i].fps));
        py_list->items[i] = dict;
    }
    
    return MP_OBJ_FROM_PTR(py_list);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(kd_mpi_sensor_list_mode_obj, _kd_mpi_sensor_list_mode);

STATIC mp_obj_t _kd_mpi_sensor_get_gain_range(mp_obj_t self_in) {
    k_sensor_gain_info range;
    int sensor_fd = mp_obj_get_int(self_in);
    
    if (0 > sensor_fd) {
        mp_raise_ValueError(MP_ERROR_TEXT("Invalid sensor fd"));
    }
    
    if (0x00 != kd_mpi_sensor_get_gain_range(sensor_fd, &range)) {
        return mp_const_none;
    }
    
    mp_obj_t dict = mp_obj_new_dict(3);
    mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_min), 
                      mp_obj_new_float(range.min));
    mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_max), 
                      mp_obj_new_float(range.max));
    mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_step), 
                      mp_obj_new_float(range.step));
    
    return dict;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(kd_mpi_sensor_get_gain_range_obj, _kd_mpi_sensor_get_gain_range);

STATIC mp_obj_t _kd_mpi_vicap_set_ircut(mp_obj_t dev_in, mp_obj_t mode_in) {
    int ret = kd_mpi_vicap_set_ircut(mp_obj_get_int(dev_in), mp_obj_get_int(mode_in));
    if (ret) {
        mp_raise_msg_varg(&mp_type_RuntimeError,
            MP_ERROR_TEXT("ircut apply failed(%d)"), ret);
    }
    return mp_const_true;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_2(kd_mpi_vicap_set_ircut_obj, _kd_mpi_vicap_set_ircut);

STATIC mp_obj_t _kd_mpi_sensor_ircut_get(mp_obj_t fd_in) {
    k_ircut_mode mode;
    int sensor_fd = mp_obj_get_int(fd_in);
    int ret;

    if (sensor_fd < 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("Invalid sensor fd"));
    }

    ret = kd_mpi_sensor_ircut_get(sensor_fd, &mode);
    if (ret) {
        mp_raise_msg_varg(&mp_type_RuntimeError,
            MP_ERROR_TEXT("ircut get failed(%d)"), ret);
    }
    return mp_obj_new_int(mode);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(kd_mpi_sensor_ircut_get_obj, _kd_mpi_sensor_ircut_get);

STATIC mp_obj_t _kd_mpi_sensor_get_ircut_caps(mp_obj_t fd_in) {
    k_sensor_ircut_caps caps;
    int sensor_fd = mp_obj_get_int(fd_in);
    int ret;
    mp_obj_t dict;

    if (sensor_fd < 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("Invalid sensor fd"));
    }

    memset(&caps, 0, sizeof(caps));
    ret = kd_mpi_sensor_get_ircut_caps(sensor_fd, &caps);
    if (ret) {
        mp_raise_msg_varg(&mp_type_RuntimeError,
            MP_ERROR_TEXT("ircut caps failed(%d)"), ret);
    }

    if (!caps.isSupport || caps.type == K_IRCUT_CTRL_NONE) {
        dict = mp_obj_new_dict(2);
        mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_is_support), mp_const_false);
        mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_type),
            mp_obj_new_int(K_IRCUT_CTRL_NONE));
        return dict;
    }

    if (caps.type == K_IRCUT_CTRL_LEVEL) {
        dict = mp_obj_new_dict(4);
        mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_is_support), mp_const_true);
        mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_type),
            mp_obj_new_int(K_IRCUT_CTRL_LEVEL));
        mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_gpio),
            mp_obj_new_int(caps.level.gpio));
        mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_color_level),
            mp_obj_new_int(caps.level.color_level));
        return dict;
    }

    if (caps.type == K_IRCUT_CTRL_PULSE) {
        dict = mp_obj_new_dict(6);
        mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_is_support), mp_const_true);
        mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_type),
            mp_obj_new_int(K_IRCUT_CTRL_PULSE));
        mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_open_gpio),
            mp_obj_new_int(caps.pulse.open_gpio));
        mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_close_gpio),
            mp_obj_new_int(caps.pulse.close_gpio));
        mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_pulse_ms),
            mp_obj_new_int(caps.pulse.pulse_ms));
        mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_idle_level),
            mp_obj_new_int(caps.pulse.idle_level));
        return dict;
    }

    mp_raise_msg_varg(&mp_type_RuntimeError,
        MP_ERROR_TEXT("ircut caps type %d is unknown"), (int)caps.type);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(kd_mpi_sensor_get_ircut_caps_obj, _kd_mpi_sensor_get_ircut_caps);

STATIC mp_obj_t _kd_mpi_isp_ir_auto_run_once(size_t n_args, const mp_obj_t *args) {
    k_isp_ir_auto_attr attr;
    int ret;

    (void)n_args;
    memset(&attr, 0, sizeof(attr));
    attr.enable = mp_obj_is_true(args[1]) ? K_TRUE : K_FALSE;
    attr.day2night = mp_obj_get_float(args[2]);
    attr.night2day = mp_obj_get_float(args[3]);
    attr.rg_min = mp_obj_get_float(args[4]);
    attr.rg_max = mp_obj_get_float(args[5]);
    attr.bg_min = mp_obj_get_float(args[6]);
    attr.bg_max = mp_obj_get_float(args[7]);
    attr.mode = mp_obj_get_int(args[8]);

    ret = kd_mpi_isp_ir_auto_run_once(mp_obj_get_int(args[0]), &attr);
    if (ret) {
        mp_raise_msg_varg(&mp_type_RuntimeError,
            MP_ERROR_TEXT("ircut check failed(%d)"), ret);
    }
    return mp_obj_new_int(attr.suggest);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(kd_mpi_isp_ir_auto_run_once_obj, 9, 9, _kd_mpi_isp_ir_auto_run_once);

STATIC const mp_rom_map_elem_t vicap_api_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_vicap_api) },
    { MP_ROM_QSTR(MP_QSTR_get_default_sensor), MP_ROM_PTR(&get_board_default_sensor_csi_num_obj) },
    DEF_FUNC_ADD(kd_mpi_vicap_dump_frame)
    DEF_FUNC_ADD(kd_mpi_vicap_set_mclk)
    DEF_FUNC_ADD(kd_mpi_auto_focus)
    DEF_FUNC_ADD(kd_mpi_focus_pos)
    DEF_FUNC_ADD(kd_mpi_sensor_get_focus_caps)
    DEF_FUNC_ADD(kd_mpi_sensor_get_exposure_time_range)
    DEF_FUNC_ADD(kd_mpi_sensor_intg_time_get)
    DEF_FUNC_ADD(kd_mpi_sensor_intg_time_set)
    DEF_FUNC_ADD(kd_mpi_sensor_list_mode)
    DEF_FUNC_ADD(kd_mpi_sensor_get_gain_range)
    DEF_FUNC_ADD(kd_mpi_vicap_set_ircut)
    DEF_FUNC_ADD(kd_mpi_sensor_ircut_get)
    DEF_FUNC_ADD(kd_mpi_sensor_get_ircut_caps)
    DEF_FUNC_ADD(kd_mpi_isp_ir_auto_run_once)
#define FUNC_ADD
#define FUNC_FILE "vicap_func_def.h"
#include "func_def.h"
};
STATIC MP_DEFINE_CONST_DICT(vicap_api_locals_dict, vicap_api_locals_dict_table);

const mp_obj_module_t mp_module_vicap_api = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&vicap_api_locals_dict,
};
