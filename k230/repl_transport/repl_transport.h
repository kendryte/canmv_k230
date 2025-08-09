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

#pragma once

#include <sys/types.h>

#include "py/mphal.h"
#include "py/runtime.h"

struct repl_transport_t {
    int (*rx)(void);
    mp_uint_t (*tx)(const char* str, size_t len);
};

extern int repl_transport_register(struct repl_transport_t* repl);

extern int       repl_transport_rx(void);
extern mp_uint_t repl_transport_tx(const char* str, size_t len);

// impl
#if defined(CONFIG_CANMV_MPY_REPL_OVER_STDIN) && CONFIG_CANMV_MPY_REPL_OVER_STDIN

int repl_transport_stdin_init(void);
int repl_transport_stdin_enable_raw_mode(void);
int repl_transport_stdin_disable_raw_mode(void);

#endif

#if (defined(CONFIG_CANMV_MPY_REPL_OVER_UART) && CONFIG_CANMV_MPY_REPL_OVER_UART)                                              \
    || (defined(CONFIG_CANMV_MPY_REPL_OVER_USB_CDC) && CONFIG_CANMV_MPY_REPL_OVER_USB_CDC)

int repl_transport_serial_init(void);

#endif
