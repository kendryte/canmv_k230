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
#include "py/obj.h"
#include "shared/timeutils/timeutils.h"

#include "canmv_misc.h"

///////////////////////////////////////////////////////////////////////////////
// mp standard ////////////////////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////////////
// Return the localtime as an 8-tuple.
static mp_obj_t mp_time_localtime_get(void)
{
    struct tm _tm;

    if (0x00 != canmv_misc_dev_ioctl(MISC_DEV_CMD_GET_LOCAL_TIME, &_tm)) {
        mp_printf(&mp_plat_print, "time get localtime failed.\n");
    }

    mp_obj_t tuple[8] = {
        tuple[0] = mp_obj_new_int(_tm.tm_year + 1900), tuple[1] = mp_obj_new_int(_tm.tm_mon + 1),
        tuple[2] = mp_obj_new_int(_tm.tm_mday),        tuple[3] = mp_obj_new_int(_tm.tm_hour),
        tuple[4] = mp_obj_new_int(_tm.tm_min),         tuple[5] = mp_obj_new_int(_tm.tm_sec),
        tuple[6] = mp_obj_new_int(_tm.tm_wday),        tuple[7] = mp_obj_new_int(_tm.tm_yday),
    };
    return mp_obj_new_tuple(8, tuple);
}

// Return the number of seconds since the Epoch.
static mp_obj_t mp_time_time_get(void)
{
    time_t tm;

    if (0x00 != canmv_misc_dev_ioctl(MISC_DEV_CMD_GET_UTC_TIMESTAMP, &tm)) {
        tm = 0;
        mp_printf(&mp_plat_print, "rtc get timestamp failed 1.\n");
    }

    return mp_obj_new_int(tm);
}

#define MICROPY_PY_TIME_EXTRA_GLOBALS
