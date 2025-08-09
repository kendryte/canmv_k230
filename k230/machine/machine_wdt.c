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
#include "py/runtime.h"

#include "extmod/modmachine.h"

#include "drv_wdt.h"

struct _machine_wdt_obj_t {
    mp_obj_base_t base;
    int           id; // WDT ID
    mp_int_t      timeout_sec; // WDT timeout in seconds
};

static machine_wdt_obj_t* mp_machine_wdt_make_new_instance(mp_int_t id, mp_int_t timeout_ms)
{
    machine_wdt_obj_t* self = mp_obj_malloc(machine_wdt_obj_t, &machine_wdt_type);

    self->id          = id;
    self->timeout_sec = timeout_ms / 1000;

    if (0 >= self->timeout_sec) {
        mp_raise_ValueError(MP_ERROR_TEXT("timeout must be greater than 0 seconds"));
    }

    wdt_set_timeout(self->timeout_sec);

    wdt_start();

    return self;
}

static void mp_machine_wdt_feed(machine_wdt_obj_t* self) { wdt_feed(); }

static void mp_machine_wdt_timeout_ms_set(machine_wdt_obj_t* self_in, mp_int_t timeout_ms)
{
    machine_wdt_obj_t* self = MP_OBJ_TO_PTR(self_in);
    self->timeout_sec       = timeout_ms / 1000;

    if (0 >= self->timeout_sec) {
        mp_raise_ValueError(MP_ERROR_TEXT("timeout must be greater than 0 seconds"));
    }

    wdt_stop();

    wdt_set_timeout(self->timeout_sec);

    wdt_start();
}
