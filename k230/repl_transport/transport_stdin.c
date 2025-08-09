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

#include <errno.h>
#include <fcntl.h>
#include <termios.h>
#include <unistd.h>

#include "repl_transport/repl_transport.h"

#if defined(CONFIG_CANMV_MPY_REPL_OVER_STDIN) && CONFIG_CANMV_MPY_REPL_OVER_STDIN
static struct termios orig_termios;
static int            stdin_flags_backup;

static int repl_transport_stdin_rx(void)
{
    int ch;
    ch = getchar();

    if (ch == EOF) {
        return -1;
    }

    if (mp_interrupt_char == ch) {
        mp_sched_keyboard_interrupt();
    } else {
        ringbuf_put(&stdin_ringbuf, ch);
    }

    return 0;
}

static mp_uint_t repl_transport_stdin_tx(const char* str, size_t len)
{
    const char* end = str + len;
    while (str < end) {
        putchar(*str++);
    }
    return len;
}

static struct repl_transport_t _stdin_repl_transport = {
    .rx = repl_transport_stdin_rx,
    .tx = repl_transport_stdin_tx,
};

int repl_transport_stdin_init(void)
{
    // Save terminal attributes
    tcgetattr(STDIN_FILENO, &orig_termios);

    // Save current file descriptor flags
    stdin_flags_backup = fcntl(STDIN_FILENO, F_GETFL, 0);
    return repl_transport_register(&_stdin_repl_transport);
}

int repl_transport_stdin_enable_raw_mode(void)
{
    struct termios raw = orig_termios;

    raw.c_iflag &= ~(BRKINT | ICRNL | INPCK | ISTRIP | IXON);
    raw.c_cflag     = (raw.c_cflag & ~(CSIZE | PARENB)) | CS8;
    raw.c_lflag     = 0;
    raw.c_cc[VMIN]  = 1;
    raw.c_cc[VTIME] = 0;

    // Apply raw mode
    tcsetattr(STDIN_FILENO, TCSAFLUSH, &raw);

    // Set non-blocking
    fcntl(STDIN_FILENO, F_SETFL, stdin_flags_backup | O_NONBLOCK);

    // Disable buffering on stdout
    if (isatty(STDOUT_FILENO)) {
        setvbuf(stdout, NULL, _IONBF, 0);
    }

    return 0;
}

int repl_transport_stdin_disable_raw_mode(void)
{
    // Restore terminal attributes
    tcsetattr(STDIN_FILENO, TCSAFLUSH, &orig_termios);

    // Restore original blocking mode
    fcntl(STDIN_FILENO, F_SETFL, stdin_flags_backup);

    // Restore line buffering on stdout
    if (isatty(STDOUT_FILENO)) {
        setvbuf(stdout, NULL, _IOLBF, 0);
    }

    return 0;
}
#endif
