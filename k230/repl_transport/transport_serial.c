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
#include <stdio.h>

#include "repl_transport/repl_transport.h"

#include "drv_uart.h"

#if (defined(CONFIG_CANMV_MPY_REPL_OVER_UART) && CONFIG_CANMV_MPY_REPL_OVER_UART)                                              \
    || (defined(CONFIG_CANMV_MPY_REPL_OVER_USB_CDC) && CONFIG_CANMV_MPY_REPL_OVER_USB_CDC)

static drv_uart_inst_t* uart_inst = NULL;

#define UART_RECV_BUFFER_SIZE (512) // a usb mps
static uint8_t uart_recv_buffer[UART_RECV_BUFFER_SIZE];

static int repl_transport_serial_rx(void)
{
    if (NULL == uart_inst) {
        return -1;
    }

    if (0 < drv_uart_poll(uart_inst, 0)) {
        size_t req_len = ringbuf_free(&stdin_ringbuf);
        if (req_len > sizeof(uart_recv_buffer)) {
            req_len = sizeof(uart_recv_buffer);
        }

        size_t len = drv_uart_read(uart_inst, uart_recv_buffer, req_len);

        // check if exists interrupt character
        for (size_t i = 0; i < len; i++) {
            uint8_t ch = uart_recv_buffer[i];

            if (mp_interrupt_char == ch) {
                mp_sched_keyboard_interrupt();
            }
        }

        ringbuf_memcpy_put_internal(&stdin_ringbuf, uart_recv_buffer, len);
    }

    return 0;
}

static mp_uint_t repl_transport_serial_tx(const char* str, size_t len)
{
    if (NULL == uart_inst) {
        return 0;
    }

    if (0x01 == drv_uart_is_dtr_asserted(uart_inst)) {
        // DTR is asserted, we can send data
        return drv_uart_write(uart_inst, (uint8_t*)str, len);
    }

    return 0;
}

static struct repl_transport_t _serial_repl_transport = {
    .rx = repl_transport_serial_rx,
    .tx = repl_transport_serial_tx,
};

int repl_transport_serial_init(void)
{
#if (defined(CONFIG_CANMV_MPY_REPL_OVER_UART) && CONFIG_CANMV_MPY_REPL_OVER_UART)
    if (0x00 != NULL, (CONFIG_CANMV_MPY_REPL_OVER_UART_NUM, &uart_inst))
#elif (defined(CONFIG_CANMV_MPY_REPL_OVER_USB_CDC) && CONFIG_CANMV_MPY_REPL_OVER_USB_CDC)
    if (0x00 != drv_uart_inst_create_usb("/dev/ttyUSB", &uart_inst))
#endif
    {
        printf("Failed to create UART instance\n");
        return -1;
    }

    return repl_transport_register(&_serial_repl_transport);
}
#endif
