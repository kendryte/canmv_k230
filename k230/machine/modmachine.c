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

#include "drv_wdt.h"
#include "hal_utils.h"

#include "modmachine.h"

#define MICROPY_PY_MACHINE_EXTRA_GLOBALS                                                                                       \
    { MP_ROM_QSTR(MP_QSTR_Pin), MP_ROM_PTR(&machine_pin_type) }, { MP_ROM_QSTR(MP_QSTR_RTC), MP_ROM_PTR(&machine_rtc_type) },

void machine_init(void)
{
    extern void machine_pin_init0(void);
    machine_pin_init0();
}

void machine_deinit(void)
{
    wdt_stop(); // if start the wdt, we stop it.
}

NORETURN void mp_machine_bootloader(size_t n_args, const mp_obj_t* args)
{
    if (0x00 != utils_reboot_to_bootloader()) {
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("enter bootloader failed."));
    }

    for (;;) { }
}

NORETURN static void mp_machine_reset(void)
{
    if (0x00 != utils_reboot()) {
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("reboot failed."));
    }

    for (;;) { }
}

static mp_obj_t mp_machine_unique_id(void)
{
    uint8_t chip_id[32];

    if (0x00 != utils_read_chipid(chip_id)) {
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("read chip id failed."));
    }

    return mp_obj_new_bytearray(sizeof(chip_id), chip_id);
}

static mp_int_t mp_machine_reset_cause(void)
{
    mp_printf(&mp_plat_print, "K230 not support machine.reset_cause()");
    return 0;
}

static mp_obj_t mp_machine_get_freq(void)
{
    mp_printf(&mp_plat_print, "K230 not support machine.get_freq()");

    return mp_obj_new_int(0);
}

static void mp_machine_set_freq(size_t n_args, const mp_obj_t* args)
{
    mp_printf(&mp_plat_print, "K230 not support machine.set_freq()");
}

static void mp_machine_idle(void) { mp_printf(&mp_plat_print, "K230 not support machine.idle()"); }

static void mp_machine_lightsleep(size_t n_args, const mp_obj_t* args)
{
    mp_printf(&mp_plat_print, "K230 not support machine.lightsleep()");
}

NORETURN static void mp_machine_deepsleep(size_t n_args, const mp_obj_t* args)
{
    mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("K230 not support machine.deepsleep()"));

    for (;;) { }
}
