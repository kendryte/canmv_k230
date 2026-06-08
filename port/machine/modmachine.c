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
#include <stdint.h>
#include <string.h>

#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>
#include <sys/ioctl.h>

#include "py/mpprint.h"
#include "py/runtime.h"
#include "py/obj.h"

#include "extmod/machine_mem.h"

#if MICROPY_PY_MACHINE_DHT
#include "drivers/dht/dht.h"
#endif

#if MICROPY_PY_MACHINE_BITSTREAM
#include "extmod/machine_bitstream.h"
#endif

#include "drv_tsensor.h"
#include "hal_utils.h"

#include "modmachine.h"

#if MICROPY_PY_MACHINE

NORETURN mp_obj_t machine_reset(void) {
    if(0x00 != utils_reboot()) {
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("reboot failed."));
    }

    for (;;) {
    }
}
STATIC MP_DEFINE_CONST_FUN_OBJ_0(machine_reset_obj, machine_reset);

NORETURN mp_obj_t machine_bootloader(size_t n_args, const mp_obj_t *args) {
    if(0x00 != utils_reboot_to_bootloader()) {
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("enter bootloader failed."));
    }

    for (;;) {
    }
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(machine_bootloader_obj, 0, 1, machine_bootloader);

STATIC mp_obj_t machine_read_chipid(void) {
    uint8_t chip_id[32];

    if(0x00 != utils_read_chipid(chip_id)) {
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("read chip id failed."));
    }

    return mp_obj_new_bytearray(sizeof(chip_id), chip_id);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_0(machine_read_chipid_obj, machine_read_chipid);

void memcpy_fast(void *dst, void *src, size_t size) {
    if (((uint64_t)src & 0x7) != ((uint64_t)dst & 0x7)) {
        memcpy(dst, src, size);
        return;
    }
    uint8_t offset = (uint64_t)dst & 0x7;
    size_t len;
    if (offset) {
        len = 8 - offset;
        if (len > size)
            len = size;
        memcpy(dst, src, len);
        size -= len;
        dst += len;
        src += len;
    }
    uint64_t *pdst = dst;
    uint64_t *psrc = src;
    len = size >> 3;

    uint64_t *pdst_end = pdst + len;
    do {
        *pdst++ = *psrc++;
    } while(pdst < pdst_end);

    if (size & 0x7) {
        len <<= 3;
        dst += len;
        src += len;
        memcpy(dst, src, size & 0x7);
    }
}

STATIC mp_obj_t machine_mem_copy(mp_obj_t dst_obj, mp_obj_t src_obj, mp_obj_t size_obj) {
    void *dst = (void *)mp_obj_get_int(dst_obj);
    void *src = (void *)mp_obj_get_int(src_obj);
    size_t size = mp_obj_get_int(size_obj);
    memcpy_fast(dst, src, size);
    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_3(machine_mem_copy_obj, machine_mem_copy);

STATIC mp_obj_t machine_read_temp(void) {
    double temp = 0.0;

    if (drv_tsensor_read_temperature(&temp) != 0) {
        mp_printf(&mp_plat_print, "read temperature failed.\n");
    }

    return mp_obj_new_float_from_d(temp);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_0(machine_read_temp_obj, machine_read_temp);

STATIC const mp_rom_map_elem_t machine_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_machine) },

    { MP_ROM_QSTR(MP_QSTR_reset), MP_ROM_PTR(&machine_reset_obj) },
    { MP_ROM_QSTR(MP_QSTR_bootloader), MP_ROM_PTR(&machine_bootloader_obj) },
    { MP_ROM_QSTR(MP_QSTR_chipid), MP_ROM_PTR(&machine_read_chipid_obj) },
    { MP_ROM_QSTR(MP_QSTR_mem_copy), MP_ROM_PTR(&machine_mem_copy_obj) },
    { MP_ROM_QSTR(MP_QSTR_temperature), MP_ROM_PTR(&machine_read_temp_obj) },

#if MICROPY_PY_MACHINE_DHT
    { MP_ROM_QSTR(MP_QSTR_dht_readinto), MP_ROM_PTR(&dht_readinto_obj) },
#endif

#if MICROPY_PY_MACHINE_BITSTREAM
    { MP_ROM_QSTR(MP_QSTR_bitstream), MP_ROM_PTR(&machine_bitstream_obj) },
#endif

#if defined(CONFIG_ENABLE_ROTARY_ENCODER) && CONFIG_ENABLE_ROTARY_ENCODER
    { MP_ROM_QSTR(MP_QSTR_ENCODER), MP_ROM_PTR(&machine_encoder_type) },
#endif

    { MP_ROM_QSTR(MP_QSTR_UART), MP_ROM_PTR(&machine_uart_type) },
    { MP_ROM_QSTR(MP_QSTR_PWM), MP_ROM_PTR(&machine_pwm_type) },
    { MP_ROM_QSTR(MP_QSTR_WDT), MP_ROM_PTR(&machine_wdt_type) },
    { MP_ROM_QSTR(MP_QSTR_Pin), MP_ROM_PTR(&machine_pin_type) },
    { MP_ROM_QSTR(MP_QSTR_FPIOA), MP_ROM_PTR(&machine_fpioa_type) },
    { MP_ROM_QSTR(MP_QSTR_I2C), MP_ROM_PTR(&machine_i2c_type) },
    { MP_ROM_QSTR(MP_QSTR_Timer), MP_ROM_PTR(&machine_timer_type) },
    { MP_ROM_QSTR(MP_QSTR_ADC), MP_ROM_PTR(&machine_adc_type) },
    { MP_ROM_QSTR(MP_QSTR_FFT), MP_ROM_PTR(&machine_fft_type) },
    { MP_ROM_QSTR(MP_QSTR_SPI), MP_ROM_PTR(&machine_spi_type) },
    { MP_ROM_QSTR(MP_QSTR_SPI_LCD), MP_ROM_PTR(&machine_spi_lcd_type) },
    { MP_ROM_QSTR(MP_QSTR_RTC), MP_ROM_PTR(&machine_rtc_type) },
    { MP_ROM_QSTR(MP_QSTR_TOUCH), MP_ROM_PTR(&machine_touch_type) },
    { MP_ROM_QSTR(MP_QSTR_LED), MP_ROM_PTR(&machine_led_type) },
    { MP_ROM_QSTR(MP_QSTR_I2C_Slave), MP_ROM_PTR(&machine_i2c_slave_type) },
    { MP_ROM_QSTR(MP_QSTR_LSM6DSM), MP_ROM_PTR(&machine_lsm6dsm_type) },
};

STATIC MP_DEFINE_CONST_DICT(machine_module_globals, machine_module_globals_table);

const mp_obj_module_t mp_module_machine = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&machine_module_globals,
};

MP_REGISTER_EXTENSIBLE_MODULE(MP_QSTR_machine, mp_module_machine);

#endif // MICROPY_PY_MACHINE
