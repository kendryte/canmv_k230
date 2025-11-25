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

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "py/mphal.h"
#include "py/mpprint.h"
#include "py/obj.h"
#include "py/runtime.h"

#include "modmachine.h"

#include "drv_i2c.h"
#include "drv_touch.h"

typedef struct _machine_touch_obj_t {
    mp_obj_base_t base;

    int index; // touch device index, 0: system default, others created.
    int rotate;
    int range_x, range_y;

    drv_touch_inst_t*         inst;
    struct drv_touch_info     info;
    struct drv_touch_config_t config_set, config_get;
} machine_touch_obj_t;

// Touch Info /////////////////////////////////////////////////////////////////
typedef struct {
    mp_obj_base_t         base;
    struct drv_touch_data info;
} machine_touch_info_obj_t;

STATIC void machine_touch_info_print(const mp_print_t* print, mp_obj_t self_in, mp_print_kind_t kind)
{
    machine_touch_info_obj_t* self = MP_OBJ_TO_PTR(self_in);
    mp_printf(print, "track_id: %d, event: %d, width: %d, x: %d, y: %d, timestamp: %d", self->info.track_id, self->info.event,
              self->info.width, self->info.x_coordinate, self->info.y_coordinate, self->info.timestamp);
}

STATIC void machine_touch_info_attr(mp_obj_t self_in, qstr attr, mp_obj_t* dest)
{
    machine_touch_info_obj_t* self = MP_OBJ_TO_PTR(self_in);
    if (dest[0] == MP_OBJ_NULL) {
        switch (attr) {
        case MP_QSTR_event:
            dest[0] = mp_obj_new_int(self->info.event);
            break;
        case MP_QSTR_track_id:
            dest[0] = mp_obj_new_int(self->info.track_id);
            break;
        case MP_QSTR_width:
            dest[0] = mp_obj_new_int(self->info.width);
            break;
        case MP_QSTR_x:
            dest[0] = mp_obj_new_int(self->info.x_coordinate);
            break;
        case MP_QSTR_y:
            dest[0] = mp_obj_new_int(self->info.y_coordinate);
            break;
        case MP_QSTR_timestamp:
            dest[0] = mp_obj_new_int(self->info.timestamp);
            break;
        default:
            dest[1] = MP_OBJ_SENTINEL; // continue lookup in locals_dict
            break;
        }
    }
}

/* clang-format off */
MP_DEFINE_CONST_OBJ_TYPE(
    machine_touch_info_type,
    MP_QSTR_TOUCH_INFO,
    MP_TYPE_FLAG_NONE,
    print, machine_touch_info_print,
    attr, machine_touch_info_attr
    );
/* clang-format on */

// APIs ///////////////////////////////////////////////////////////////////////
STATIC void machine_touch_print(const mp_print_t* print, mp_obj_t self_in, mp_print_kind_t kind)
{
    machine_touch_obj_t* self = MP_OBJ_TO_PTR(self_in);

    mp_print_str(print, "Touch(");

    // Print basic information
    mp_printf(print, "index=%d, rotate=%d", self->index, self->rotate);

    // Print range information
    if (self->range_x > 0 && self->range_y > 0) {
        mp_printf(print, ", range=%dx%d", self->range_x, self->range_y);
    }

    // Print touch info if available
    if (self->info.range_x > 0 || self->info.range_y > 0 || self->info.point_num > 0) {
        mp_printf(print, ", info=(");
        mp_printf(print, "type=%u, vendor=%u, points=%u", self->info.type, self->info.vendor, self->info.point_num);
        if (self->info.range_x > 0 && self->info.range_y > 0) {
            mp_printf(print, ", range=%ux%u", self->info.range_x, self->info.range_y);
        }
        mp_print_str(print, ")");
    }

    // Print config_get if it has meaningful values
    bool has_config = false;
    if (self->config_get.touch_dev_index != 0 || self->config_get.range_x != 0 || self->config_get.range_y != 0
        || self->config_get.pin_intr != 0 || self->config_get.pin_reset != 0 || self->config_get.i2c_bus_index != 0) {
        has_config = true;
    }

    if (has_config) {
        mp_printf(print, ", config=(");
        mp_printf(print, "dev_index=%d", self->config_get.touch_dev_index);

        if (self->config_get.range_x > 0 && self->config_get.range_y > 0) {
            mp_printf(print, ", range=%dx%d", self->config_get.range_x, self->config_get.range_y);
        }

        if (self->config_get.pin_intr != 0 || self->config_get.pin_reset != 0) {
            mp_printf(print, ", pins=(intr:%d", self->config_get.pin_intr);
            if (self->config_get.intr_value != 0) {
                mp_printf(print, "[%d]", self->config_get.intr_value);
            }
            mp_printf(print, ", reset:%d", self->config_get.pin_reset);
            if (self->config_get.reset_value != 0) {
                mp_printf(print, "[%d]", self->config_get.reset_value);
            }
            mp_print_str(print, ")");
        }

        if (self->config_get.i2c_bus_index != 0) {
            mp_printf(print, ", i2c=(bus:%d", self->config_get.i2c_bus_index);
            if (self->config_get.i2c_bus_speed > 0) {
                mp_printf(print, ", speed:%dHz", self->config_get.i2c_bus_speed);
            }
            mp_print_str(print, ")");
        }
        mp_print_str(print, ")");
    }

    // Print instance status
    if (self->inst != NULL) {
        mp_print_str(print, ", initialized");
    } else {
        mp_print_str(print, ", uninitialized");
    }

    mp_print_str(print, ")");
}

static inline void rotate_touch_point(machine_touch_obj_t* self, struct drv_touch_data* tdata)
{
    uint8_t  rotate  = self->rotate;
    uint32_t range_x = self->range_x, range_y = self->range_y;
    uint16_t point_x = tdata->x_coordinate, point_y = tdata->y_coordinate;

    switch (rotate) {
    default:
    case DRV_TOUCH_ROTATE_DEGREE_0:
        // do nothing
        break;
    case DRV_TOUCH_ROTATE_DEGREE_90:
        tdata->x_coordinate = range_y - point_y - 1;
        tdata->y_coordinate = point_x;
        break;
    case DRV_TOUCH_ROTATE_DEGREE_180:
        tdata->x_coordinate = range_x - point_x - 1;
        tdata->y_coordinate = range_y - point_y - 1;
        break;
    case DRV_TOUCH_ROTATE_DEGREE_270:
        tdata->x_coordinate = point_y;
        tdata->y_coordinate = range_x - point_x - 1;
        break;
    case DRV_TOUCH_ROTATE_SWAP_XY: {
        tdata->x_coordinate = point_y;
        tdata->y_coordinate = point_x;
    } break;
    }
}

STATIC mp_obj_t machine_touch_read(size_t n_args, const mp_obj_t* args)
{
    machine_touch_obj_t* self = MP_OBJ_TO_PTR(args[0]);

    int                       point_number = 1, result = 0;
    struct drv_touch_data     touch_data[DRV_TOUCH_POINT_NUMBER_MAX];
    machine_touch_info_obj_t* touch_info_obj[DRV_TOUCH_POINT_NUMBER_MAX];

    if (n_args > 1) {
        point_number = mp_obj_get_int(args[1]);

        if ((0 >= point_number) || (DRV_TOUCH_POINT_NUMBER_MAX < point_number)) {
            mp_raise_ValueError(MP_ERROR_TEXT("point_number invalid"));
        }
    }

    result = drv_touch_read(self->inst, touch_data, point_number);
    if (0 > result) {
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("read touch failed, %d"), result);
    }
    point_number = result;

    for (int i = 0; i < point_number; i++) {
        rotate_touch_point(self, &touch_data[i]);

        touch_info_obj[i]       = mp_obj_malloc(machine_touch_info_obj_t, &machine_touch_info_type);
        touch_info_obj[i]->info = touch_data[i];
    }

    return mp_obj_new_tuple(point_number, (mp_obj_t*)touch_info_obj);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(machine_touch_read_obj, 1, 2, machine_touch_read);

STATIC mp_obj_t machine_touch_deinit(mp_obj_t self_in)
{
    machine_touch_obj_t* self = MP_OBJ_TO_PTR(self_in);

    drv_touch_inst_destroy(&self->inst);

    if (0x00 != self->index) {
        canmv_misc_delete_touch_device(self->index);
    }

    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(machine_touch_deinit_obj, machine_touch_deinit);

STATIC mp_obj_t machine_touch_make_new(const mp_obj_type_t* type, size_t n_args, size_t n_kw, const mp_obj_t* args)
{
    // Define argument specs, positional and keyword arguments with defaults
    enum { ARG_dev, ARG_rotate, ARG_range_x, ARG_range_y, ARG_i2c, ARG_rst, ARG_int, ARG_type, ARG_slave_addr };
    static const mp_arg_t machine_touch_allowed_args[] = {
        { MP_QSTR_dev, MP_ARG_REQUIRED | MP_ARG_INT, { .u_int = 0 } }, // required
        { MP_QSTR_rotate, MP_ARG_KW_ONLY | MP_ARG_INT, { .u_int = -1 } }, // optional
        { MP_QSTR_range_x, MP_ARG_KW_ONLY | MP_ARG_INT, { .u_int = -1 } }, // optional
        { MP_QSTR_range_y, MP_ARG_KW_ONLY | MP_ARG_INT, { .u_int = -1 } }, // optional
        { MP_QSTR_i2c, MP_ARG_KW_ONLY | MP_ARG_OBJ, { .u_obj = mp_const_none } }, // optional
        { MP_QSTR_rst, MP_ARG_KW_ONLY | MP_ARG_OBJ, { .u_obj = mp_const_none } }, // optional
        { MP_QSTR_int, MP_ARG_KW_ONLY | MP_ARG_OBJ, { .u_obj = mp_const_none } }, // optional

        { MP_QSTR_type, MP_ARG_KW_ONLY | MP_ARG_INT, { .u_int = -1 } }, // deprcapted
        { MP_QSTR_slave_addr, MP_ARG_KW_ONLY | MP_ARG_OBJ, { .u_obj = mp_const_none } }, // deprcapted
    };

    // Parse all arguments
    mp_arg_val_t args_parsed[MP_ARRAY_SIZE(machine_touch_allowed_args)];
    mp_arg_parse_all_kw_array(n_args, n_kw, args, MP_ARRAY_SIZE(machine_touch_allowed_args), machine_touch_allowed_args,
                              args_parsed);

    // Create a new instance of the Touch object
    machine_touch_obj_t* self = m_new_obj_with_finaliser(machine_touch_obj_t);

    // Extract the dev parameter
    self->index  = args_parsed[ARG_dev].u_int;
    self->rotate = args_parsed[ARG_rotate].u_int;

    if (0x00 != self->index) {
        memset(&self->config_set, 0x00, sizeof(self->config_set));

        self->config_set.touch_dev_index = self->index;

        self->config_set.range_x = 0;
        if (-1 != args_parsed[ARG_range_x].u_int) {
            self->config_set.range_x = args_parsed[ARG_range_x].u_int;
        }

        self->config_set.range_y = 0;
        if (-1 != args_parsed[ARG_range_y].u_int) {
            self->config_set.range_y = args_parsed[ARG_range_y].u_int;
        }

        if (mp_const_none == args_parsed[ARG_i2c].u_obj) {
            mp_raise_ValueError(MP_ERROR_TEXT("Custom Touch Device should set i2c"));
        }
        drv_i2c_inst_t* i2c_inst       = machine_i2c_obj_get_inst(args_parsed[ARG_i2c].u_obj);
        self->config_set.i2c_bus_index = drv_i2c_master_get_id(i2c_inst);

        self->config_set.i2c_bus_speed = 400000;

        self->config_set.pin_reset   = -1;
        self->config_set.reset_value = 0;
        if (mp_const_none != args_parsed[ARG_rst].u_obj) {
            self->config_set.pin_reset = mp_obj_get_int(args_parsed[ARG_rst].u_obj);
        }

        self->config_set.pin_intr   = -1;
        self->config_set.intr_value = 1;
        if (mp_const_none != args_parsed[ARG_int].u_obj) {
            self->config_set.pin_intr = mp_obj_get_int(args_parsed[ARG_int].u_obj);
        }

        if (0x00 != canmv_misc_create_touch_device(&self->config_set)) {
            mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("Custom Touch Device created failed"));
        }
    }

    if (0x00 != drv_touch_inst_create(self->index, &self->inst)) {
        if (0x00 != self->index) {
            canmv_misc_delete_touch_device(self->index);
        }
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("Open Touch Device(%d) failed"), self->index);
    }

    if (0x00 != drv_touch_reset(self->inst)) {
        if (0x00 != self->index) {
            canmv_misc_delete_touch_device(self->index);
        }
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("Reset Touch Device(%d) failed"), self->index);
    }

    if (0x00 != drv_touch_get_info(self->inst, &self->info)) {
        if (0x00 != self->index) {
            canmv_misc_delete_touch_device(self->index);
        }
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("Get Touch Device(%d) Info failed"), self->index);
    }

    int rotate;
    if (0x00 != drv_touch_get_default_rotate(self->inst, &rotate)) {
        if (0x00 != self->index) {
            canmv_misc_delete_touch_device(self->index);
        }
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("Get Touch Device(%d) Default Rotate failed"), self->index);
    }

    if (0x00 != drv_touch_get_config(self->inst, &self->config_get)) {
        if (0x00 != self->index) {
            canmv_misc_delete_touch_device(self->index);
        }
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("Get Touch Device(%d) Config failed"), self->index);
    }

    if (-1 == self->rotate) {
        self->rotate = rotate;
    }
    self->range_x = self->info.range_x;
    self->range_y = self->info.range_y;

    self->base.type = &machine_touch_type;

    return MP_OBJ_FROM_PTR(self);
}

STATIC const mp_rom_map_elem_t machine_touch_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&machine_touch_deinit_obj) },
    { MP_ROM_QSTR(MP_QSTR_deinit), MP_ROM_PTR(&machine_touch_deinit_obj) },
    { MP_ROM_QSTR(MP_QSTR_read), MP_ROM_PTR(&machine_touch_read_obj) },

    { MP_ROM_QSTR(MP_QSTR_EVENT_NONE), MP_ROM_INT(DRV_TOUCH_EVENT_NONE) },
    { MP_ROM_QSTR(MP_QSTR_EVENT_UP), MP_ROM_INT(DRV_TOUCH_EVENT_UP) },
    { MP_ROM_QSTR(MP_QSTR_EVENT_DOWN), MP_ROM_INT(DRV_TOUCH_EVENT_DOWN) },
    { MP_ROM_QSTR(MP_QSTR_EVENT_MOVE), MP_ROM_INT(DRV_TOUCH_EVENT_MOVE) },

    { MP_ROM_QSTR(MP_QSTR_ROTATE_0), MP_ROM_INT(DRV_TOUCH_ROTATE_DEGREE_0) },
    { MP_ROM_QSTR(MP_QSTR_ROTATE_90), MP_ROM_INT(DRV_TOUCH_ROTATE_DEGREE_90) },
    { MP_ROM_QSTR(MP_QSTR_ROTATE_180), MP_ROM_INT(DRV_TOUCH_ROTATE_DEGREE_180) },
    { MP_ROM_QSTR(MP_QSTR_ROTATE_270), MP_ROM_INT(DRV_TOUCH_ROTATE_DEGREE_270) },
    { MP_ROM_QSTR(MP_QSTR_ROTATE_SWAP_XY), MP_ROM_INT(DRV_TOUCH_ROTATE_SWAP_XY) },

    // system touch driver type
    // { MP_ROM_QSTR(MP_QSTR_TYPE_CST128), MP_ROM_INT(TOUCH_TYPE_CST128) },
    // { MP_ROM_QSTR(MP_QSTR_TYPE_FT5x16), MP_ROM_INT(TOUCH_TYPE_FT5x16) },

    // user touch driver type
    { MP_ROM_QSTR(MP_QSTR_TYPE_CST226SE), MP_ROM_INT(0) },
    { MP_ROM_QSTR(MP_QSTR_TYPE_CST328), MP_ROM_INT(0) },

    { MP_ROM_QSTR(MP_QSTR_TYPE_GT911), MP_ROM_INT(0) },
};
STATIC MP_DEFINE_CONST_DICT(machine_touch_locals_dict, machine_touch_locals_dict_table);

/* clang-format off */
MP_DEFINE_CONST_OBJ_TYPE(
    machine_touch_type,
    MP_QSTR_TOUCH,
    MP_TYPE_FLAG_NONE,
    make_new, machine_touch_make_new,
    print, machine_touch_print,
    locals_dict, &machine_touch_locals_dict
);
/* clang-format on */
