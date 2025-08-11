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
#include "py/mpprint.h"
#include "py/obj.h"
#include "py/runtime.h"

#include "shared/timeutils/timeutils.h"

#include "canmv_misc.h"

#include "modmachine.h"

typedef struct {
    mp_obj_base_t base;
} machine_rtc_obj_t;

static const machine_rtc_obj_t machine_rtc_obj = { { &machine_rtc_type } };

static mp_obj_t machine_rtc_make_new(const mp_obj_type_t* type, size_t n_args, size_t n_kw, const mp_obj_t* args)
{
    mp_arg_check_num(n_args, n_kw, 0, 0, false);
    return (mp_obj_t)&machine_rtc_obj;
}

static mp_obj_t machine_rtc_timezone(mp_uint_t n_args, const mp_obj_t* args)
{
    int    timezone        = 0;
    time_t timezone_offset = 0;

    if (0x01 == n_args) {
        // get timezone
        if (0x00 != canmv_misc_dev_ioctl(MISC_DEV_CMD_GET_TIMEZONE, &timezone_offset)) {
            mp_printf(&mp_plat_print, "rtc get timezone failed.\n");

            return mp_obj_new_int(-1);
        }
        timezone = timezone_offset / 3600;

        return mp_obj_new_int(timezone);
    } else {
        // set timezone
        timezone = mp_obj_get_int(args[1]);
        if ((-12 > timezone) || (12 < timezone)) {
            mp_raise_msg_varg(&mp_type_ValueError, MP_ERROR_TEXT("timezone should be -12 to 12, not %d"), timezone);
        }
        timezone_offset = timezone * 3600;

        if (0x00 != canmv_misc_dev_ioctl(MISC_DEV_CMD_SET_TIMEZONE, &timezone_offset)) {
            mp_printf(&mp_plat_print, "rtc set timezone failed.\n");
            return mp_const_false;
        }

        return mp_const_true;
    }
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(machine_rtc_timezone_obj, 1, 2, machine_rtc_timezone);

static mp_obj_t machine_rtc_datetime_helper(mp_uint_t n_args, const mp_obj_t* args)
{
    if (n_args == 1) {
        struct tm tm;

        // get local time
        if (0x00 != canmv_misc_dev_ioctl(MISC_DEV_CMD_GET_LOCAL_TIME, &tm)) {
            mp_printf(&mp_plat_print, "rtc get timestamp failed.\n");
        }

        mp_obj_t tuple[8] = { mp_obj_new_int(tm.tm_year + 1900), mp_obj_new_int(tm.tm_mon + 1),
                              mp_obj_new_int(tm.tm_mday),        mp_obj_new_int(tm.tm_wday),
                              mp_obj_new_int(tm.tm_hour),        mp_obj_new_int(tm.tm_min),
                              mp_obj_new_int(tm.tm_sec),         mp_obj_new_int(0) };

        return mp_obj_new_tuple(8, tuple);
    } else {
        mp_obj_t* items;
        size_t    items_count = 0;
        mp_obj_get_array(args[1], &items_count, &items);

        if ((8 != items_count) && (9 != items_count)) {
            mp_raise_msg_varg(&mp_type_ValueError, MP_ERROR_TEXT("requested length 8 or 9 but object has length %d"),
                              (int)items_count);
        }

        time_t timestamp
            = timeutils_seconds_since_epoch(mp_obj_get_int(items[0]), mp_obj_get_int(items[1]), mp_obj_get_int(items[2]),
                                            mp_obj_get_int(items[4]), mp_obj_get_int(items[5]), mp_obj_get_int(items[6]));
        time_t timezone_offset = 8 * 3600; // default GMT+8

        // timezone
        if (0x09 == items_count) {
            mp_obj_t call_args[2] = { args[0], items[8] };

            machine_rtc_timezone(2, call_args);

            timezone_offset = mp_obj_get_int(items[8]) * 3600;
        }
        timestamp -= timezone_offset;

        if (0x00 != canmv_misc_dev_ioctl(MISC_DEV_CMD_SET_UTC_TIMESTAMP, &timestamp)) {
            mp_printf(&mp_plat_print, "rtc set timestamp failed 1.\n");
        }

        return mp_const_none;
    }
}

static mp_obj_t machine_rtc_datetime(size_t n_args, const mp_obj_t* args) { return machine_rtc_datetime_helper(n_args, args); }
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(machine_rtc_datetime_obj, 1, 2, machine_rtc_datetime);

static mp_obj_t machine_rtc_init(mp_obj_t self_in, mp_obj_t date)
{
    mp_obj_t args[2];

    mp_obj_t        arr_o = machine_rtc_datetime_helper(1, NULL);
    mp_obj_tuple_t* arr   = MP_OBJ_TO_PTR(arr_o);

    mp_obj_t* items;
    size_t    items_count = 0;
    mp_obj_get_array(date, &items_count, &items);

    if (3 > items_count) {
        mp_raise_ValueError(MP_ERROR_TEXT("tuple/list has wrong length"));
    }

    arr->items[0] = items[0]; // yease
    arr->items[1] = items[1]; // month
    arr->items[2] = items[2]; // day

    // hour
    if (4 <= items_count) {
        arr->items[3] = mp_const_none;
        arr->items[4] = items[3];
    }
    // minute
    if (5 <= items_count) {
        arr->items[5] = items[4];
    }
    // second
    if (6 <= items_count) {
        arr->items[6] = items[5];
    }
    // microsecond
    if (7 <= items_count) {
        arr->items[7] = items[6];
    }
    // tzinfo
    if (8 <= items_count) {
        arr->items[8] = items[7];
    }

    args[0] = self_in;
    args[1] = arr_o;
    machine_rtc_datetime_helper(2, args);

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(machine_rtc_init_obj, machine_rtc_init);

static mp_obj_t machine_rtc_now(mp_obj_t self_in)
{
    mp_obj_t args[1] = { self_in };
    return machine_rtc_datetime_helper(1, args);
}
static MP_DEFINE_CONST_FUN_OBJ_1(machine_rtc_now_obj, machine_rtc_now);

static mp_obj_t machine_rtc_ntp_sync(mp_obj_t self_in)
{
    int result = 0;

    if (0x00 != canmv_misc_dev_ioctl(MISC_DEV_CMD_NTP_SYNC, &result)) {
        result = -1;
        mp_printf(&mp_plat_print, "ntp sync time failed.\n");
    }

    return mp_obj_new_bool(0x00 < result);
}
static MP_DEFINE_CONST_FUN_OBJ_1(machine_rtc_ntp_sync_obj, machine_rtc_ntp_sync);

static const mp_rom_map_elem_t machine_rtc_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR_init), MP_ROM_PTR(&machine_rtc_init_obj) },
    { MP_ROM_QSTR(MP_QSTR_datetime), MP_ROM_PTR(&machine_rtc_datetime_obj) },
    { MP_ROM_QSTR(MP_QSTR_now), MP_ROM_PTR(&machine_rtc_now_obj) },
    { MP_ROM_QSTR(MP_QSTR_ntp_sync), MP_ROM_PTR(&machine_rtc_ntp_sync_obj) },
    { MP_ROM_QSTR(MP_QSTR_timezone), MP_ROM_PTR(&machine_rtc_timezone_obj) },
};
static MP_DEFINE_CONST_DICT(machine_rtc_locals_dict, machine_rtc_locals_dict_table);

MP_DEFINE_CONST_OBJ_TYPE(machine_rtc_type, MP_QSTR_RTC, MP_TYPE_FLAG_NONE, make_new, machine_rtc_make_new, locals_dict,
                         &machine_rtc_locals_dict);
