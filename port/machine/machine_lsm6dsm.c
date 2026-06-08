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
#include <fcntl.h>
#include <unistd.h>

#include "py/mphal.h"
#include "py/mpprint.h"
#include "py/obj.h"
#include "py/runtime.h"

#include "modmachine.h"
#include "hal_syscall.h"

/*
 * LSM6DSM MicroPython binding.
 *
 * Usage:
 *   imu = LSM6DSM(LSM6DSM.ACCE)   # or LSM6DSM('acce')
 *   data = imu.read()             # returns (x, y, z) for acce/gyro
 *                                  # returns float for temp
 *                                  # returns int for step
 *   imu.deinit()
 *
 * We bypass the VFS read() path and use rt_device_read() syscalls directly,
 * which is the same code path used by the working 'sensor' FINSH command.
 * The VFS read() doesn't correctly handle the sensor framework's item-count
 * based read semantics.
 */

/* RT-Thread sensor framework constants (matching sensor.h) */
#define RT_SENSOR_CLASS_ACCE     1
#define RT_SENSOR_CLASS_GYRO     2
#define RT_SENSOR_CLASS_TEMP     4
#define RT_SENSOR_CLASS_STEP     12

#define RT_DEVICE_FLAG_RDWR      0x003

/* Sensor type identifiers for this module */
#define LSM6DSM_TYPE_ACCE  1
#define LSM6DSM_TYPE_GYRO  2
#define LSM6DSM_TYPE_TEMP  3
#define LSM6DSM_TYPE_STEP  4

/* Sensor data buf size — kernel struct rt_sensor_data is 24 bytes */
#define SENSOR_BUF_SIZE  32

typedef struct _machine_lsm6dsm_obj_t {
    mp_obj_base_t base;
    rt_device_t   dev;     /* RT-Thread device handle */
    int           type;    /* LSM6DSM_TYPE_* */
} machine_lsm6dsm_obj_t;

STATIC void machine_lsm6dsm_print(const mp_print_t *print, mp_obj_t self_in, mp_print_kind_t kind)
{
    machine_lsm6dsm_obj_t *self = MP_OBJ_TO_PTR(self_in);
    const char *tname = "unknown";
    switch (self->type) {
        case LSM6DSM_TYPE_ACCE: tname = "acce"; break;
        case LSM6DSM_TYPE_GYRO: tname = "gyro"; break;
        case LSM6DSM_TYPE_TEMP: tname = "temp"; break;
        case LSM6DSM_TYPE_STEP: tname = "step"; break;
    }
    mp_printf(print, "LSM6DSM(%s)", tname);
}

/*
 * Syscall wrappers for rt_device_open/read/close.
 * These are not exposed in hal_syscall.h, but the syscall numbers exist
 * (_NRSYS_rt_device_open=62, _NRSYS_rt_device_read=65,
 *  _NRSYS_rt_device_close=64).
 */
static inline int _rt_device_open(rt_device_t dev, int oflag)
{
    return (int)syscall(_NRSYS_rt_device_open, (long)dev, (long)oflag);
}

static inline int _rt_device_read(rt_device_t dev, void *buf, int len)
{
    /* pos=0, len=1 item (sensor framework treats len as item count) */
    return (int)syscall(_NRSYS_rt_device_read, (long)dev, (long)0, (long)buf, (long)len);
}

static inline int _rt_device_close(rt_device_t dev)
{
    return (int)syscall(_NRSYS_rt_device_close, (long)dev);
}

static inline int32_t read_i32(const uint8_t *buf, int offset)
{
    int32_t val;
    memcpy(&val, buf + offset, sizeof(val));
    return val;
}

static inline uint32_t read_u32(const uint8_t *buf, int offset)
{
    uint32_t val;
    memcpy(&val, buf + offset, sizeof(val));
    return val;
}

/*
 * Read one rt_sensor_data item from the device via syscall.
 * Retries up to 5 times if the sensor isn't ready yet (status.xlda/gda=0).
 * The LSM6DSM at 12.5Hz ODR produces a new sample every 80ms.
 */
static int sensor_read(rt_device_t dev, uint8_t *buf, size_t buf_size)
{
    memset(buf, 0, buf_size);
    for (int retry = 0; retry < 5; retry++) {
        int ret = _rt_device_read(dev, buf, 1);
        if (ret > 0) {
            return 0;
        }
        /* Not ready yet — wait for next sample period then retry */
        if (retry < 4) {
            mp_hal_delay_ms(100);
        }
    }
    return -1;
}

/* ------------------------------------------------------------------ */
/* MicroPython: read()                                                 */
/* ------------------------------------------------------------------ */

STATIC mp_obj_t machine_lsm6dsm_read(mp_obj_t self_in)
{
    machine_lsm6dsm_obj_t *self = MP_OBJ_TO_PTR(self_in);
    uint8_t buf[SENSOR_BUF_SIZE];

    if (sensor_read(self->dev, buf, sizeof(buf)) != 0) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("Sensor read failed"));
    }

    switch (self->type) {
    case LSM6DSM_TYPE_ACCE: {
        /* Accelerometer: offset 8=x, 12=y, 16=z, unit: mG */
        mp_obj_t items[3] = {
            mp_obj_new_int(read_i32(buf, 8)),
            mp_obj_new_int(read_i32(buf, 12)),
            mp_obj_new_int(read_i32(buf, 16)),
        };
        return mp_obj_new_tuple(3, items);
    }
    case LSM6DSM_TYPE_GYRO: {
        /*
         * Gyroscope: offset 8=x, 12=y, 16=z.
         * Driver stores real_gyro * 1000 (lsm6dsm.c:696), where
         * real_gyro is already mdps. Divide by 1000 for mdps.
         */
        mp_obj_t items[3] = {
            mp_obj_new_int(read_i32(buf, 8) / 1000),
            mp_obj_new_int(read_i32(buf, 12) / 1000),
            mp_obj_new_int(read_i32(buf, 16) / 1000),
        };
        return mp_obj_new_tuple(3, items);
    }
    case LSM6DSM_TYPE_TEMP:
        /* Temperature: offset 8=temp, unit: dCelsius (10x C) */
        return mp_obj_new_float(read_i32(buf, 8) / 10.0);

    case LSM6DSM_TYPE_STEP:
        /* Step counter: offset 8=step, uint32 */
        return mp_obj_new_int_from_uint(read_u32(buf, 8));

    default:
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("Unknown sensor type"));
    }
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(machine_lsm6dsm_read_obj, machine_lsm6dsm_read);

/* ------------------------------------------------------------------ */
/* MicroPython: deinit()                                               */
/* ------------------------------------------------------------------ */

STATIC mp_obj_t machine_lsm6dsm_deinit(mp_obj_t self_in)
{
    machine_lsm6dsm_obj_t *self = MP_OBJ_TO_PTR(self_in);
    if (self->dev != NULL) {
        _rt_device_close(self->dev);
        self->dev = NULL;
    }
    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(machine_lsm6dsm_deinit_obj, machine_lsm6dsm_deinit);

/* ------------------------------------------------------------------ */
/* MicroPython: constructor                                           */
/* ------------------------------------------------------------------ */

/* Map sensor name string to type and device path */
static const struct {
    int type;
    const char *dev_name;
} lsm6dsm_devices[] = {
    { LSM6DSM_TYPE_ACCE, "acce_lsm6dsm" },
    { LSM6DSM_TYPE_GYRO, "gyro_lsm6dsm" },
    { LSM6DSM_TYPE_TEMP, "temp_lsm6dsm" },
    { LSM6DSM_TYPE_STEP, "step_lsm6dsm" },
};

STATIC mp_obj_t machine_lsm6dsm_make_new(const mp_obj_type_t *type, size_t n_args, size_t n_kw, const mp_obj_t *args)
{
    enum { ARG_type };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_type, MP_ARG_REQUIRED | MP_ARG_OBJ, { .u_obj = mp_const_none } },
    };
    mp_arg_val_t parsed[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all_kw_array(n_args, n_kw, args, MP_ARRAY_SIZE(allowed_args), allowed_args, parsed);

    int sensor_type = -1;

    /* Parse type argument: can be int constant or string name */
    mp_obj_t type_arg = parsed[ARG_type].u_obj;
    if (mp_obj_is_str(type_arg)) {
        const char *name = mp_obj_str_get_str(type_arg);
        for (size_t i = 0; i < MP_ARRAY_SIZE(lsm6dsm_devices); i++) {
            if (lsm6dsm_devices[i].dev_name != NULL &&
                (strncmp(name, lsm6dsm_devices[i].dev_name, 4) == 0)) {
                sensor_type = lsm6dsm_devices[i].type;
                break;
            }
        }
        if (sensor_type < 0) {
            mp_raise_msg_varg(&mp_type_ValueError,
                MP_ERROR_TEXT("Unknown sensor type '%s', expected 'acce','gyro','temp','step'"), name);
        }
    } else if (mp_obj_is_int(type_arg)) {
        sensor_type = mp_obj_get_int(type_arg);
        if (sensor_type < LSM6DSM_TYPE_ACCE || sensor_type > LSM6DSM_TYPE_STEP) {
            mp_raise_msg_varg(&mp_type_ValueError,
                MP_ERROR_TEXT("Invalid sensor type %d, use LSM6DSM.ACCE/.GYRO/.TEMP/.STEP"), sensor_type);
        }
    } else {
        mp_raise_msg(&mp_type_ValueError,
            MP_ERROR_TEXT("Type must be a string ('acce','gyro','temp','step') or constant (LSM6DSM.ACCE, etc.)"));
    }

    /* Find the device name */
    const char *dev_name = NULL;
    for (size_t i = 0; i < MP_ARRAY_SIZE(lsm6dsm_devices); i++) {
        if (lsm6dsm_devices[i].type == sensor_type) {
            dev_name = lsm6dsm_devices[i].dev_name;
            break;
        }
    }
    if (dev_name == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("Sensor device not found"));
    }

    /* Find the RT-Thread device */
    rt_device_t dev = rt_device_find(dev_name);
    if (dev == NULL) {
        mp_raise_msg_varg(&mp_type_RuntimeError,
            MP_ERROR_TEXT("Device '%s' not found"), dev_name);
    }

    /* Open the device (triggers rt_sensor_open → set mode + power) */
    if (_rt_device_open(dev, RT_DEVICE_FLAG_RDWR) != 0) {
        mp_raise_msg_varg(&mp_type_RuntimeError,
            MP_ERROR_TEXT("Failed to open device '%s'"), dev_name);
    }

    /*
     * Give the sensor time to power up and start producing data.
     * - Accel: LSM6DSM has analog + LPF1 + LPF2 filter chain. The LPF2
     *   cutoff is ODR/100, so settling takes several seconds. Use a 1s
     *   delay to get past the worst of the transient.
     * - Gyro: needs ~200ms to stabilize MEMS structure.
     * - Temp/Step: just a small delay for the register interface.
     *
     * We do NOT read warmup samples here because the sensor may not
     * have data ready yet (status.xlda/gda = 0), which would cause
     * rt_device_read to return 0 (not an error, just no data).
     * The test script's read loop naturally discards settling samples.
     */
    int startup_delay_ms;
    switch (sensor_type) {
        case LSM6DSM_TYPE_ACCE:
            startup_delay_ms = 2000;  /* LPF2 filter settling: ODR/100 = 0.125Hz */
            break;
        case LSM6DSM_TYPE_GYRO:
            startup_delay_ms = 500;
            break;
        default:
            startup_delay_ms = 100;
            break;
    }
    mp_hal_delay_ms(startup_delay_ms);

    machine_lsm6dsm_obj_t *self = m_new_obj_with_finaliser(machine_lsm6dsm_obj_t);
    self->base.type = &machine_lsm6dsm_type;
    self->dev = dev;
    self->type = sensor_type;

    return MP_OBJ_FROM_PTR(self);
}

/* ------------------------------------------------------------------ */
/* Module registration                                                */
/* ------------------------------------------------------------------ */

STATIC const mp_rom_map_elem_t machine_lsm6dsm_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&machine_lsm6dsm_deinit_obj) },
    { MP_ROM_QSTR(MP_QSTR_deinit), MP_ROM_PTR(&machine_lsm6dsm_deinit_obj) },
    { MP_ROM_QSTR(MP_QSTR_read), MP_ROM_PTR(&machine_lsm6dsm_read_obj) },

    /* Sensor type constants */
    { MP_ROM_QSTR(MP_QSTR_ACCE), MP_ROM_INT(LSM6DSM_TYPE_ACCE) },
    { MP_ROM_QSTR(MP_QSTR_GYRO), MP_ROM_INT(LSM6DSM_TYPE_GYRO) },
    { MP_ROM_QSTR(MP_QSTR_TEMP), MP_ROM_INT(LSM6DSM_TYPE_TEMP) },
    { MP_ROM_QSTR(MP_QSTR_STEP), MP_ROM_INT(LSM6DSM_TYPE_STEP) },
};
STATIC MP_DEFINE_CONST_DICT(machine_lsm6dsm_locals_dict, machine_lsm6dsm_locals_dict_table);

MP_DEFINE_CONST_OBJ_TYPE(
    machine_lsm6dsm_type,
    MP_QSTR_LSM6DSM,
    MP_TYPE_FLAG_NONE,
    make_new, machine_lsm6dsm_make_new,
    print, machine_lsm6dsm_print,
    locals_dict, &machine_lsm6dsm_locals_dict
);
