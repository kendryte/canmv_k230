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
#include "py/mperrno.h"
#include "py/runtime.h"
#include "py/stream.h"

#include "extmod/modmachine.h"

#include "drv_fpioa.h"
#include "drv_uart.h"

struct _machine_uart_obj_t {
    mp_obj_base_t base;
    int           index;
    int           status;
    int           timeout;

    int baudrate, bitwidth, parity, stop;

    drv_uart_inst_t* inst;
};

static void mp_machine_uart_print(const mp_print_t* print, mp_obj_t self_in, mp_print_kind_t kind)
{
    machine_uart_obj_t* self = MP_OBJ_TO_PTR(self_in);
    mp_printf(print, "UART(%d, baudrate=%d, bitwidth=%d, parity=%d, stop=%d)", self->index, self->baudrate, self->bitwidth,
              self->parity, self->stop);
}

static void mp_machine_uart_init_helper(machine_uart_obj_t* self, size_t n_args, const mp_obj_t* pos_args, mp_map_t* kw_args)
{
    enum { ARG_baudrate, ARG_bits, ARG_parity, ARG_stop, ARG_timeout, ARG_tx, ARG_rx };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_baudrate, MP_ARG_INT, { .u_int = 115200 } },
        { MP_QSTR_bits, MP_ARG_INT, { .u_int = 8 } },
        { MP_QSTR_parity, MP_ARG_INT, { .u_obj = MP_OBJ_NULL } }, // None, 0: even, 1: odd
        { MP_QSTR_stop, MP_ARG_INT, { .u_int = 1 } }, // 1 or 2
        { MP_QSTR_timeout, MP_ARG_KW_ONLY | MP_ARG_INT, { .u_int = 10 } },
        { MP_QSTR_tx, MP_ARG_KW_ONLY | MP_ARG_OBJ, { .u_obj = MP_OBJ_NULL } },
        { MP_QSTR_rx, MP_ARG_KW_ONLY | MP_ARG_OBJ, { .u_obj = MP_OBJ_NULL } },
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args, pos_args, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    mp_int_t pin_tx = -1, pin_rx = -1;

    // Set SCL/SDA pins if given
    if (args[ARG_tx].u_obj != MP_OBJ_NULL) {
        pin_tx = mp_obj_get_int(args[ARG_tx].u_obj);
    }
    if (args[ARG_rx].u_obj != MP_OBJ_NULL) {
        pin_rx = mp_obj_get_int(args[ARG_rx].u_obj);
    }

    {
        int uart_id = self->index;

#define UART_TXD_FUNC(id)                                                                                                      \
    ((id) == 0 ? UART0_TXD : (id) == 1 ? UART1_TXD : (id) == 2 ? UART2_TXD : (id) == 3 ? UART3_TXD : (id) == 4 ? UART4_TXD : -1)

#define UART_RXD_FUNC(id)                                                                                                      \
    ((id) == 0 ? UART0_RXD : (id) == 1 ? UART1_RXD : (id) == 2 ? UART2_RXD : (id) == 3 ? UART3_RXD : (id) == 4 ? UART4_RXD : -1)

        fpioa_func_t func_tx = UART_TXD_FUNC(uart_id);
        fpioa_func_t func_rx = UART_RXD_FUNC(uart_id);

#undef UART_TXD_FUNC
#undef UART_RXD_FUNC

        // TX validation
        if (pin_tx != -1) {
            if (!drv_fpioa_is_func_supported_by_pin(pin_tx, func_tx)) {
                mp_raise_msg_varg(&mp_type_AssertionError, MP_ERROR_TEXT("Pin(%d) can not set to UART(%d) tx"), pin_tx,
                                  uart_id);
            }
            if (0x00 != drv_fpioa_set_pin_func(pin_tx, func_tx)) {
                mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("set Pin(%d) to fpioa func %d failed"), pin_tx, func_tx);
            }
        } else {
            if (drv_fpioa_find_pin_by_func(func_tx) < 0) {
                mp_raise_msg_varg(&mp_type_AssertionError, MP_ERROR_TEXT("UART(%d) tx not configured, see machine.FPIOA"),
                                  uart_id);
            }
        }

        // RX validation
        if (pin_rx != -1) {
            if (!drv_fpioa_is_func_supported_by_pin(pin_rx, func_rx)) {
                mp_raise_msg_varg(&mp_type_AssertionError, MP_ERROR_TEXT("Pin(%d) can not set to UART(%d) rx"), pin_rx,
                                  uart_id);
            }
            if (0x00 != drv_fpioa_set_pin_func(pin_rx, func_rx)) {
                mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("set Pin(%d) to fpioa func %d failed"), pin_rx, func_rx);
            }
        } else {
            if (drv_fpioa_find_pin_by_func(func_rx) < 0) {
                mp_raise_msg_varg(&mp_type_AssertionError, MP_ERROR_TEXT("UART(%d) rx not configured, see machine.FPIOA"),
                                  uart_id);
            }
        }
    }

    self->baudrate = args[ARG_baudrate].u_int;
    self->bitwidth = args[ARG_bits].u_int;

    self->parity = PARITY_NONE;
    if (args[ARG_parity].u_obj != MP_OBJ_NULL) {
        int party = mp_obj_get_int(args[ARG_parity].u_obj);
        if (0x00 == party) {
            self->parity = PARITY_EVEN;
        } else if (0x01 == party) {
            self->parity = PARITY_ODD;
        } else {
            mp_raise_ValueError(MP_ERROR_TEXT("invalid parity value, must be None, 0 (even) or 1 (odd)"));
        }
    }

    int stop_bit = args[ARG_stop].u_int;
    if (0x01 == stop_bit) {
        self->stop = STOP_BITS_1;
    } else if (0x02 == stop_bit) {
        self->stop = STOP_BITS_2;
    } else {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid stop bit value, must be 1 or 2"));
    }

    if (args[ARG_timeout].u_int != -1) {
        self->timeout = args[ARG_timeout].u_int;
    }

    struct uart_configure cfg = {
        .baud_rate = self->baudrate,
        .data_bits = self->bitwidth,
        .stop_bits = self->stop,
        .parity    = self->parity,
        .bit_order = BIT_ORDER_LSB,
        .invert    = NRZ_NORMAL,
        .bufsz     = 0x400, // default
        .reserved  = 0,
    };

    if (0x00 != drv_uart_set_config(self->inst, &cfg)) {
        mp_printf(&mp_plat_print, "uart%d set config failed", self->index);
    }
}

static mp_obj_t mp_machine_uart_make_new(const mp_obj_type_t* type, size_t n_args, size_t n_kw, const mp_obj_t* args)
{
    mp_arg_check_num(n_args, n_kw, 1, MP_OBJ_FUN_ARGS_MAX, true);

    int index = mp_obj_get_int(args[0]);
    if (index < 0 || index >= KD_HARD_UART_MAX_NUM) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid UART index"));
    }

    drv_uart_inst_t* inst = NULL;
    if (drv_uart_inst_create(index, &inst) < 0) {
        mp_raise_msg_varg(&mp_type_OSError, MP_ERROR_TEXT("cannot create UART %u"), index);
    }

    machine_uart_obj_t* self = mp_obj_malloc_with_finaliser(machine_uart_obj_t, &machine_uart_type);
    self->index              = index;
    self->inst               = inst;
    self->status             = 1;
    self->timeout            = 0;

    mp_map_t kw_args;
    mp_map_init_fixed_table(&kw_args, n_kw, args + n_args);
    mp_machine_uart_init_helper(self, n_args - 1, args + 1, &kw_args);

    self->status = 2;
    return MP_OBJ_FROM_PTR(self);
}

static void mp_machine_uart_deinit(machine_uart_obj_t* self)
{
    if (self->status == 0) {
        return;
    }

    drv_uart_inst_destroy(&self->inst);
    self->status = 0;
}

static mp_int_t mp_machine_uart_any(machine_uart_obj_t* self) { return drv_uart_poll(self->inst, 0); }

static bool mp_machine_uart_txdone(machine_uart_obj_t* self) { return true; }

static void mp_machine_uart_sendbreak(machine_uart_obj_t* self)
{
    if (0x00 != drv_uart_send_break(self->inst)) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("failed to send break"));
    }
}

static mp_uint_t mp_machine_uart_read(mp_obj_t self_in, void* buf_in, mp_uint_t size, int* errcode)
{
    machine_uart_obj_t* self = MP_OBJ_TO_PTR(self_in);

    // If timeout is -1, treat as non-blocking read (timeout = 0)
    mp_uint_t effective_timeout = (self->timeout == (mp_uint_t)-1) ? 0 : self->timeout;

    size_t    read_bytes = 0;
    mp_uint_t start      = mp_hal_ticks_ms();
    while (read_bytes < size && (mp_hal_ticks_ms() - start < effective_timeout)) {
        MICROPY_EVENT_POLL_HOOK

        int r = drv_uart_read(self->inst, (uint8_t*)buf_in + read_bytes, size - read_bytes);
        if (r <= 0) {
            break;
        }
        read_bytes += r;

        // If timeout == 0, only attempt once
        if (effective_timeout == 0) {
            break;
        }
    }

    if (read_bytes == 0) {
        *errcode = MP_EAGAIN;
        return MP_STREAM_ERROR;
    }

    return read_bytes;
}

static mp_uint_t mp_machine_uart_write(mp_obj_t self_in, const void* buf_in, mp_uint_t size, int* errcode)
{
    machine_uart_obj_t* self = MP_OBJ_TO_PTR(self_in);

    int w = drv_uart_write(self->inst, (uint8_t*)buf_in, size);
    if (w < 0) {
        *errcode = MP_EAGAIN;
        return MP_STREAM_ERROR;
    }

    return w;
}

static mp_uint_t mp_machine_uart_ioctl(mp_obj_t self_in, mp_uint_t request, uintptr_t arg, int* errcode)
{
    machine_uart_obj_t* self = MP_OBJ_TO_PTR(self_in);

    *errcode      = 0;
    mp_uint_t ret = 0;

    switch (request) {
    case MP_STREAM_POLL: {
        mp_uint_t flags = arg;
        ret             = 0;
        if ((flags & MP_STREAM_POLL_RD) && drv_uart_poll(self->inst, 0) > 0) {
            ret |= MP_STREAM_POLL_RD;
        }
        if ((flags & MP_STREAM_POLL_WR)) { // assume always writable
            ret |= MP_STREAM_POLL_WR;
        }
        return ret;
    }
    case MP_STREAM_FLUSH:
        // Not implemented
        return 0;
    default:
        *errcode = MP_EINVAL;
        return MP_STREAM_ERROR;
    }
}

#define MICROPY_PY_MACHINE_UART_CLASS_CONSTANTS { MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&machine_uart_deinit_obj) },
