/*
 * This file is part of the MicroPython project, http://micropython.org/
 *
 * The MIT License (MIT)
 *
 * Copyright (c) 2014-2018 Paul Sokolovsky
 * Copyright (c) 2017-2022 Damien P. George
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "obj.h"
#include "py/runtime.h"
#include "py/mphal.h"

#include <errno.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <sys/random.h>

#include "canmv_drivers.h"

STATIC mp_obj_t mp_os_getenv(size_t n_args, const mp_obj_t *args) {
    const char *s = getenv(mp_obj_str_get_str(args[0]));
    if (s == NULL) {
        if (n_args == 2) {
            return args[1];
        }
        return mp_const_none;
    }
    return mp_obj_new_str(s, strlen(s));
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mp_os_getenv_obj, 1, 2, mp_os_getenv);

STATIC mp_obj_t mp_os_putenv(mp_obj_t key_in, mp_obj_t value_in) {
    const char *key = mp_obj_str_get_str(key_in);
    const char *value = mp_obj_str_get_str(value_in);
    int ret;

    #if _WIN32
    ret = _putenv_s(key, value);
    #else
    ret = setenv(key, value, 1);
    #endif

    if (ret == -1) {
        mp_raise_OSError(errno);
    }
    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_2(mp_os_putenv_obj, mp_os_putenv);

STATIC mp_obj_t mp_os_unsetenv(mp_obj_t key_in) {
    const char *key = mp_obj_str_get_str(key_in);
    int ret;

    #if _WIN32
    ret = _putenv_s(key, "");
    #else
    ret = unsetenv(key);
    #endif

    if (ret == -1) {
        mp_raise_OSError(errno);
    }
    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(mp_os_unsetenv_obj, mp_os_unsetenv);

STATIC mp_obj_t mp_os_urandom(mp_obj_t num) {
    mp_int_t n = mp_obj_get_int(num);
    vstr_t vstr;
    vstr_init_len(&vstr, n);
    getrandom(vstr.buf, n, GRND_RANDOM);
    return mp_obj_new_bytes_from_vstr(&vstr);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(mp_os_urandom_obj, mp_os_urandom);

STATIC mp_obj_t mp_os_errno(size_t n_args, const mp_obj_t *args) {
    if (n_args == 0) {
        return MP_OBJ_NEW_SMALL_INT(errno);
    }

    errno = mp_obj_get_int(args[0]);
    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mp_os_errno_obj, 0, 1, mp_os_errno);

STATIC mp_obj_t mp_os_exitpoint(size_t n_args, const mp_obj_t *args) {
    int old = mp_thread_get_exitpoint_flag();

    if (n_args == 1) {
        int flag = mp_obj_get_int(args[0]);
        mp_thread_set_exitpoint_flag(flag);
        if (EXITPOINT_DISABLE != flag) {
            return mp_obj_new_int(old);
        }
    }

    mp_thread_exitpoint(EXITPOINT_ANY);

    return mp_obj_new_int(old);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mp_os_exitpoint_obj, 0, 1, mp_os_exitpoint);

STATIC mp_obj_t mp_os_get_cpu_usage(size_t n_args, const mp_obj_t *args) {
    int usage = -1;

    if(0x00 != canmv_misc_dev_ioctl(MISC_DEV_CMD_CPU_USAGE, &usage)) {
        mp_printf(&mp_plat_print, "os get cpu_usage failed.\n");

        usage = -1;
    }

    return MP_OBJ_NEW_SMALL_INT(usage);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mp_os_get_cpu_usage_obj, 0, 1, mp_os_get_cpu_usage);

STATIC mp_obj_t mp_os_log(mp_obj_t log_in)
{
    printf("[py]: %s\n", mp_obj_str_get_str(log_in));

    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(mp_os_log_obj, mp_os_log);
