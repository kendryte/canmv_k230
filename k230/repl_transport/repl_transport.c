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
#include <string.h>

#include <pthread.h>

#include "repl_transport/repl_transport.h"

static struct repl_transport_t _repl_transport = {
    .rx = NULL,
    .tx = NULL,
};

static pthread_mutex_t _repl_transport_mutex = PTHREAD_MUTEX_INITIALIZER;

int repl_transport_register(struct repl_transport_t* transport)
{
    pthread_mutex_lock(&_repl_transport_mutex);

    _repl_transport.rx = transport->rx;
    _repl_transport.tx = transport->tx;

    pthread_mutex_unlock(&_repl_transport_mutex);

    return 0;
}

int repl_transport_rx(void)
{
    if (_repl_transport.rx)
        return _repl_transport.rx();

    printf("repl transport have no rx\n");

    return -1;
}

mp_uint_t repl_transport_tx(const char* str, size_t len)
{
    if (_repl_transport.tx)
        return _repl_transport.tx(str, len);

    printf("repl transport have no tx\n");

    return 0;
}
