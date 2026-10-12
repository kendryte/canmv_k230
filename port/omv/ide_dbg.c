/*
 * This file is part of the OpenMV project.
 * Copyright (c) 2013/2014 Ibrahim Abdelkader <i.abdalkader@gmail.com>
 * This work is licensed under the MIT license, see the file LICENSE for details.
 *
 * IDE debug protocol handler.
 */

/* System headers */
#include <stdarg.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <pthread.h>
#include <semaphore.h>
#include <sys/time.h>
#include <sys/stat.h>
#include <dirent.h>
#include <errno.h>

/* MicroPython core */
#include "py/mpconfig.h"
#include "py/mpstate.h"
#include "py/mpthread.h"
#include "py/obj.h"
#include "py/objstr.h"
#include "py/runtime.h"
#include "shared/readline/readline.h"

/* Project / driver headers */
#include "mbedtls/version.h"

#if MBEDTLS_VERSION_NUMBER >= 0x03000000
#include "mbedtls/compat-2.x.h"
#endif

#include "mbedtls/sha256.h"

#include "ide_dbg.h"
#include "version.h"
#include "canmv_drivers.h"
#include "drv_uart.h"
#include "hal_rvv_ops.h"

#if MBEDTLS_VERSION_NUMBER < 0x02070000 || MBEDTLS_VERSION_NUMBER >= 0x03000000
#define mbedtls_sha256_starts_ret mbedtls_sha256_starts
#define mbedtls_sha256_update_ret mbedtls_sha256_update
#define mbedtls_sha256_finish_ret mbedtls_sha256_finish
#endif

#if CONFIG_CANMV_IDE_SUPPORT

///////////////////////////////////////////////////////////////////////////////
// Debug logging macros ///////////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////////////

#define COLOR_NONE "\033[0m"
#define RED "\033[1;31;40m"
#define BLUE "\033[1;34;40m"
#define GREEN "\033[1;32;40m"
#define YELLOW "\033[1;33;40m"

#define IDE_DBG_LOG 0

#if IDE_DBG_LOG
#define pr_verb(fmt,...) fprintf(stderr,BLUE "[ide] " fmt "\n" COLOR_NONE,##__VA_ARGS__)
#define pr_dbg(fmt,...) fprintf(stderr,YELLOW "[ide-dbg] " fmt "\n" COLOR_NONE,##__VA_ARGS__)
#else
#define pr_verb(fmt,...)
#define pr_dbg(fmt,...)
#endif
#define pr_info(fmt,...) fprintf(stderr,GREEN fmt "\n"COLOR_NONE,##__VA_ARGS__)
#define pr_warn(fmt,...) fprintf(stderr,YELLOW fmt "\n"COLOR_NONE,##__VA_ARGS__)
#define pr_err(fmt,...) fprintf(stderr,RED fmt " at line %d\n"COLOR_NONE,##__VA_ARGS__, __LINE__)

#define PRINT_ALL 0
#define IDE_DBG_MAX_FRAME_PAYLOAD (8 * 1024 * 1024)
#define IDE_DBG_FRAME_POLL_MS 200
#define IDE_DBG_FRAME_IDLE_TIMEOUT_MS 5000

///////////////////////////////////////////////////////////////////////////////
// Extern declarations & state ////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////////////

pthread_t ide_dbg_task_p;
static struct ide_dbg_svfil_t ide_dbg_sv_file;
static uint8_t ide_dbg_file_io_buffer[USBDBG_FILE_CHUNK_MAX];
static uint8_t ide_dbg_listdir_page_buffer[USBDBG_LISTDIR_PAGE_MAX_PAYLOAD];
static struct {
    DIR *dir;
    char filepath[USBDBG_MAX_PATH_LEN + 64];
    char pending_name[UINT8_MAX + 1];
    uint32_t next_offset;
    bool pending;
} ide_dbg_listdir_page_state;
MP_REGISTER_ROOT_POINTER(mp_obj_exception_t ide_exception);
static mp_obj_str_t ide_exception_str;
static mp_obj_tuple_t* ide_exception_str_tuple = NULL;
static bool ide_dbg_rx_incomplete = false;

extern drv_uart_inst_t *mp_hal_uart_get_instance(void);
extern int mp_hal_uart_tx(const void* buffer, size_t size);
extern bool mp_hal_uart_is_usb(void);
extern void mp_hal_stdin_push(const uint8_t* data, size_t len);
extern void mp_hal_stdin_clear(void);
extern bool is_repl_intr;

static uint64_t sys_mem_total_size = 0;

extern void system_set_exiting_flag(bool exiting);
extern bool in_mp_irq_handler(void);

static pthread_mutex_t vtouch_mutex = PTHREAD_MUTEX_INITIALIZER;
static bool vtouch_enabled = false;
static uint32_t vtouch_range_x = 0;
static uint32_t vtouch_range_y = 0;
static struct ide_dbg_vtouch_event vtouch_queue[USBDBG_VTOUCH_QUEUE_LEN];
static uint32_t vtouch_read_index = 0;
static uint32_t vtouch_count = 0;

///////////////////////////////////////////////////////////////////////////////
// Utility functions //////////////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////////////

static void wait_mp_irq_handler_done(void)
{
    system_set_exiting_flag(true);

    for (int wait_count = 0; wait_count < 500; wait_count++) {

        if (!in_mp_irq_handler()) {
            break;
        }
        usleep(10000);
    }

#if 0
    for (int wait_count = 0; wait_count < 500; wait_count++) {
        mp_uint_t atomic_state = MICROPY_BEGIN_ATOMIC_SECTION();
        bool is_idle = (MP_STATE_VM(sched_state) == MP_SCHED_IDLE);
        MICROPY_END_ATOMIC_SECTION(atomic_state);

        if (is_idle) {
            break;
        }
        usleep(10000); // Sleep 10ms

    }
#endif
}

void print_raw(const uint8_t* data, size_t size) {
#if IDE_DEBUG_PRINT
    fprintf(stderr, "raw: \"");
    for (size_t i = 0; i < size; i++) {
        fprintf(stderr, "\\x%02X", ((unsigned char*)data)[i]);
    }
    fprintf(stderr, "\"\n");
#endif
}

// USBDBG command replies are fixed-size on the host side. A short CDC write is
// recoverable, but dropping the remainder desynchronizes the protocol.
#define IDE_DBG_UART_TX_IDLE_TIMEOUT_MS (900)
#define IDE_DBG_UART_TX_RETRY_US (1000)
static int ide_dbg_uart_tx_all(const void* buffer, size_t size) {
    const uint8_t *ptr = (const uint8_t*)buffer;
    size_t sent = 0;
    uint64_t last_progress_ms = mp_hal_ticks_ms();

    while (sent < size) {
        drv_uart_inst_t *inst = mp_hal_uart_get_instance();
        if (inst == NULL || drv_uart_is_dtr_asserted(inst) <= 0) {
            // Host gone. Report partial progress so the caller can advance its
            // read pointer by exactly what reached the wire and retain the rest.
            return (sent > 0) ? (int)sent : -1;
        }

        int n = mp_hal_uart_tx(ptr + sent, size - sent);
        if (n > 0) {
            sent += (size_t)n;
            last_progress_ms = mp_hal_ticks_ms();
            continue;
        }

        if ((mp_hal_ticks_ms() - last_progress_ms) >= IDE_DBG_UART_TX_IDLE_TIMEOUT_MS) {
            // Give up so the IDE task can return to servicing commands (e.g. a
            // host resync probe). Return the count actually sent rather than -1
            // so the undelivered tail stays buffered instead of being dropped.
            return (int)sent;
        }
        usleep(IDE_DBG_UART_TX_RETRY_US);
    }

    return (int)sent;
}

static int ide_dbg_uart_tx_best_effort(const void* buffer, size_t size) {
    return mp_hal_uart_tx(buffer, size);
}

#define mp_hal_uart_tx ide_dbg_uart_tx_all

static bool ide_dbg_host_attached(void) {
    drv_uart_inst_t *inst = mp_hal_uart_get_instance();
    return inst != NULL && drv_uart_is_dtr_asserted(inst) > 0;
}

///////////////////////////////////////////////////////////////////////////////
// TX ring buffer (stdout -> IDE) /////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////////////

#define TX_BUF_SIZE (1024 * 128)
#define STDOUT_PROBE_GUARD_MS (2000)
static char tx_buf[TX_BUF_SIZE];
static uint32_t tx_buf_w = 0;
static uint32_t tx_buf_r = 0;
static pthread_mutex_t tx_buf_mutex = PTHREAD_MUTEX_INITIALIZER;

// Serializes a whole drain operation (copy into the shared tx_tmp_buf + the
// physical UART write). tx_buf_drain releases tx_buf_mutex during the UART
// write so producers can keep filling the ring; without this second lock two
// threads (the IDE task draining USBDBG_TX_BUF and the stdout raw path) could
// reuse tx_tmp_buf and interleave bytes on the wire. Always acquire this
// BEFORE tx_buf_mutex to keep a consistent lock order.
static pthread_mutex_t tx_drain_mutex = PTHREAD_MUTEX_INITIALIZER;

// Hold early USB CDC stdout briefly so OpenMV IDE's fixed-length reads do not
// consume boot-script text as command responses before USBDBG attaches.
static pthread_mutex_t stdout_probe_mutex = PTHREAD_MUTEX_INITIALIZER;
static bool stdout_probe_dtr = false;
static bool stdout_probe_active = false;
static bool stdout_probe_raw = false;
static uint64_t stdout_probe_start_ms = 0;

static inline uint32_t tx_buf_readable(void) {
    return (tx_buf_w >= tx_buf_r)
        ? (tx_buf_w - tx_buf_r)
        : (TX_BUF_SIZE - tx_buf_r + tx_buf_w);
}

static inline uint32_t tx_buf_writable(void) {
    return TX_BUF_SIZE - 1 - tx_buf_readable();
}

static uint32_t tx_buf_readable_locked(void) {
    uint32_t len;

    pthread_mutex_lock(&tx_buf_mutex);
    len = tx_buf_readable();
    pthread_mutex_unlock(&tx_buf_mutex);

    return len;
}

static void tx_buf_clear_locked(void) {
    tx_buf_w = 0;
    tx_buf_r = 0;
}

static void tx_buf_write(const char* data, size_t len) {
    uint32_t tail = TX_BUF_SIZE - tx_buf_w;
    if (len <= tail) {
        hal_rvv_memcpy(tx_buf + tx_buf_w, data, len);
    } else {
        hal_rvv_memcpy(tx_buf + tx_buf_w, data, tail);
        hal_rvv_memcpy(tx_buf, data + tail, len - tail);
    }
    tx_buf_w = (tx_buf_w + len) % TX_BUF_SIZE;
}

static uint8_t tx_tmp_buf[TX_BUF_SIZE];

// Caller must hold both tx_drain_mutex and tx_buf_mutex. Uses the shared
// tx_tmp_buf and briefly releases tx_buf_mutex during the UART write.
// When `full` is set the bytes are sent with the looping full-write path: the
// USBDBG_TX_BUF command makes the host read exactly `len` bytes, so a short CDC
// write that dropped the tail would desync every later response. The raw
// pre-attach drain passes full=false (no fixed-length host read; must not block).
static void tx_buf_drain(uint32_t len, bool full) {
    // Snapshot the read pointer but DO NOT advance it yet: the pointer is moved
    // only after the UART write, by the number of bytes that actually reached
    // the wire. Leaving it in place keeps the in-flight region reserved (so a
    // producer racing on the released tx_buf_mutex can't overwrite it) and lets
    // a short write retain its undelivered tail for the next drain instead of
    // dropping it. Dropping the tail of a fixed-length USBDBG_TX_BUF reply is
    // exactly what desyncs the host's stream.
    uint32_t start_r = tx_buf_r;
    uint32_t tail = TX_BUF_SIZE - start_r;
    uint8_t *tmp_buf = tx_tmp_buf;
    if (len <= tail) {
        hal_rvv_memcpy(tmp_buf, tx_buf + start_r, len);
    } else {
        hal_rvv_memcpy(tmp_buf, tx_buf + start_r, tail);
        hal_rvv_memcpy(tmp_buf + tail, tx_buf, len - tail);
    }
    pthread_mutex_unlock(&tx_buf_mutex);
    int sent;
    if (full) {
        sent = mp_hal_uart_tx(tmp_buf, len);
    } else {
        sent = ide_dbg_uart_tx_best_effort(tmp_buf, len);
    }
    pthread_mutex_lock(&tx_buf_mutex);
    // The protocol path (full) must not desync the host: advance only by the
    // bytes actually delivered so the undelivered tail is re-sent next time.
    // The raw pre-attach path is best-effort and must keep making forward
    // progress (its caller loops until the ring drains), so it always advances
    // by the full chunk even if the underlying write was short.
    uint32_t advance = len;
    if (full) {
        advance = (sent > 0) ? (uint32_t)sent : 0;
    }
    tx_buf_r = (start_r + advance) % TX_BUF_SIZE;
}

static void tx_buf_drain_all_raw(void) {
    pthread_mutex_lock(&tx_drain_mutex);
    pthread_mutex_lock(&tx_buf_mutex);
    while (tx_buf_readable() > 0) {
        tx_buf_drain(tx_buf_readable(), false);
    }
    pthread_mutex_unlock(&tx_buf_mutex);
    pthread_mutex_unlock(&tx_drain_mutex);
}

void ide_dbg_stdout_tx(const char* data, size_t size) {    
    pthread_mutex_lock(&tx_buf_mutex);
    if (size > tx_buf_writable()) {
        // buffer full, drop to prevent UI stutter/locking
        pr_dbg("tx_buf FULL, dropping %zu bytes (readable=%u)", size, tx_buf_readable());
        pthread_mutex_unlock(&tx_buf_mutex);
        return;
    }
    tx_buf_write(data, size);
    pthread_mutex_unlock(&tx_buf_mutex);
}

static void ide_dbg_stdout_probe_reset_locked(bool clear_buffer) {
    stdout_probe_dtr = false;
    stdout_probe_active = false;
    stdout_probe_raw = false;
    stdout_probe_start_ms = 0;
    if (clear_buffer) {
        pthread_mutex_lock(&tx_buf_mutex);
        tx_buf_clear_locked();
        pthread_mutex_unlock(&tx_buf_mutex);
    }
}

static void ide_dbg_stdout_protocol_attach(void) {
    pthread_mutex_lock(&stdout_probe_mutex);
    stdout_probe_dtr = true;
    stdout_probe_active = false;
    stdout_probe_raw = false;
    pthread_mutex_unlock(&stdout_probe_mutex);
}

static void ide_dbg_stdout_protocol_detach(void) {
    pthread_mutex_lock(&stdout_probe_mutex);
    ide_dbg_stdout_probe_reset_locked(true);
    pthread_mutex_unlock(&stdout_probe_mutex);
}

void ide_dbg_stdout_raw_input(void) {
    if (ide_dbg_attach()) {
        return;
    }

    pthread_mutex_lock(&stdout_probe_mutex);
    stdout_probe_dtr = true;
    stdout_probe_active = false;
    stdout_probe_raw = true;
    pthread_mutex_unlock(&stdout_probe_mutex);

    tx_buf_drain_all_raw();
}

bool ide_dbg_stdout_capture(const char* data, size_t size) {
    if (data == NULL || size == 0) {
        return true;
    }

    if (ide_dbg_attach()) {
        ide_dbg_stdout_tx(data, size);
        return true;
    }

    drv_uart_inst_t *inst = mp_hal_uart_get_instance();
    if (inst == NULL || drv_uart_get_id(inst) >= 0) {
        return false;
    }

    int dtr = drv_uart_is_dtr_asserted(inst);
    pthread_mutex_lock(&stdout_probe_mutex);
    if (dtr <= 0) {
        ide_dbg_stdout_probe_reset_locked(true);
        pthread_mutex_unlock(&stdout_probe_mutex);
        return false;
    }

    uint64_t now_ms = mp_hal_ticks_ms();
    if (!stdout_probe_dtr) {
        stdout_probe_dtr = true;
        stdout_probe_active = true;
        stdout_probe_raw = false;
        stdout_probe_start_ms = now_ms;
        pthread_mutex_lock(&tx_buf_mutex);
        tx_buf_clear_locked();
        pthread_mutex_unlock(&tx_buf_mutex);
    }

    if (stdout_probe_raw) {
        pthread_mutex_unlock(&stdout_probe_mutex);
        return false;
    }

    if (stdout_probe_active && (now_ms - stdout_probe_start_ms) < STDOUT_PROBE_GUARD_MS) {
        pthread_mutex_unlock(&stdout_probe_mutex);
        ide_dbg_stdout_tx(data, size);
        return true;
    }

    stdout_probe_active = false;
    stdout_probe_raw = true;
    pthread_mutex_unlock(&stdout_probe_mutex);

    tx_buf_drain_all_raw();
    return false;
}

static size_t read_until(void* buffer, size_t size) {
    size_t idx = 0;
    uint32_t idle_ms = 0;
    while (idx < size) {
        drv_uart_inst_t *inst = mp_hal_uart_get_instance();
        if (inst == NULL) {
            break;
        }

        int ret = drv_uart_poll(inst, IDE_DBG_FRAME_POLL_MS);
        if (ret < 0) {
            break;
        }
        if (ret == 0) {
            idle_ms += IDE_DBG_FRAME_POLL_MS;
            if (idle_ms >= IDE_DBG_FRAME_IDLE_TIMEOUT_MS) {
                break;
            }
            continue;
        }

        ssize_t recv = drv_uart_read(inst, (uint8_t*)buffer + idx, size - idx);
        if (recv < 0) {
            break;
        }
        if (recv == 0) {
            idle_ms += 1;
            if (idle_ms >= IDE_DBG_FRAME_IDLE_TIMEOUT_MS) {
                break;
            }
            usleep(1000);
            continue;
        }

        idx += recv;
        idle_ms = 0;
    }

    if (idx != size) {
        ide_dbg_rx_incomplete = true;
        pr_err("[ide] frame payload receive incomplete: got %zu of %zu bytes", idx, size);
    }
    return idx;
}

static void print_sha256(const uint8_t sha256[32]) {
    #if IDE_DEBUG_PRINT
    fprintf(stderr, "SHA256: ");
    for (unsigned i = 0; i < 32; i++) {
        fprintf(stderr, "%02x", sha256[i]);
    }
    fprintf(stderr, "\n");
    #endif
}

static uint32_t ide_dbg_vtouch_queue_depth_locked(void) {
    return vtouch_count;
}

void ide_dbg_vtouch_clear(void) {
    pthread_mutex_lock(&vtouch_mutex);
    vtouch_read_index = 0;
    vtouch_count = 0;
    pthread_mutex_unlock(&vtouch_mutex);
}

void ide_dbg_vtouch_open(uint32_t range_x, uint32_t range_y) {
    if (range_x == 0) {
        range_x = 1;
    }
    if (range_y == 0) {
        range_y = 1;
    }

    pthread_mutex_lock(&vtouch_mutex);
    vtouch_enabled = true;
    vtouch_range_x = range_x;
    vtouch_range_y = range_y;
    vtouch_read_index = 0;
    vtouch_count = 0;
    pthread_mutex_unlock(&vtouch_mutex);
}

void ide_dbg_vtouch_close(void) {
    pthread_mutex_lock(&vtouch_mutex);
    vtouch_enabled = false;
    vtouch_range_x = 0;
    vtouch_range_y = 0;
    vtouch_read_index = 0;
    vtouch_count = 0;
    pthread_mutex_unlock(&vtouch_mutex);
}

bool ide_dbg_vtouch_is_enabled(void) {
    bool enabled;

    pthread_mutex_lock(&vtouch_mutex);
    enabled = vtouch_enabled;
    pthread_mutex_unlock(&vtouch_mutex);

    return enabled;
}

uint32_t ide_dbg_vtouch_read(struct ide_dbg_vtouch_event *out, uint32_t max_events) {
    uint32_t read_count = 0;

    if (out == NULL || max_events == 0) {
        return 0;
    }

    pthread_mutex_lock(&vtouch_mutex);
    while (read_count < max_events && vtouch_count > 0) {
        out[read_count++] = vtouch_queue[vtouch_read_index];
        vtouch_read_index = (vtouch_read_index + 1) % USBDBG_VTOUCH_QUEUE_LEN;
        vtouch_count--;
    }
    pthread_mutex_unlock(&vtouch_mutex);

    return read_count;
}

static void ide_dbg_vtouch_status(struct ide_dbg_vtouch_info *info) {
    if (info == NULL) {
        return;
    }

    pthread_mutex_lock(&vtouch_mutex);
    info->supported = 1;
    info->enabled = vtouch_enabled ? 1 : 0;
    info->range_x = vtouch_enabled ? vtouch_range_x : 0;
    info->range_y = vtouch_enabled ? vtouch_range_y : 0;
    info->queue_depth = ide_dbg_vtouch_queue_depth_locked();
    pthread_mutex_unlock(&vtouch_mutex);
}

static bool ide_dbg_vtouch_enqueue(const struct ide_dbg_vtouch_event *event) {
    if (event == NULL) {
        return false;
    }

    pthread_mutex_lock(&vtouch_mutex);
    if (!vtouch_enabled) {
        pthread_mutex_unlock(&vtouch_mutex);
        return false;
    }

    uint32_t write_index = (vtouch_read_index + vtouch_count) % USBDBG_VTOUCH_QUEUE_LEN;
    vtouch_queue[write_index] = *event;
    if (vtouch_count < USBDBG_VTOUCH_QUEUE_LEN) {
        vtouch_count++;
    } else {
        vtouch_read_index = (vtouch_read_index + 1) % USBDBG_VTOUCH_QUEUE_LEN;
    }
    pthread_mutex_unlock(&vtouch_mutex);

    return true;
}

bool repl_script_running = false;

///////////////////////////////////////////////////////////////////////////////
// IDE state management ///////////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////////////

static uint32_t ide_script_running = 0;
static bool ide_soft_reset_requested = false;

void mpy_start_script(char* filepath);
void mpy_stop_script();
void interrupt_repl(void);
static char *exec_payload = NULL;
static exec_type_t exec_type = EXEC_STRING;
static sem_t script_sem;
static bool ide_attached = false;
static bool ide_disconnect = false;
static bool ide_auto_exec_suppressed = false;
static enum {
    FB_FROM_NONE,
    FB_FROM_USER_SET,
    FB_FROM_VO_WRITEBACK
} fb_from = FB_FROM_NONE;

static inline bool ide_dbg_repl_script_running(void) {
    return __atomic_load_n(&repl_script_running, __ATOMIC_ACQUIRE);
}

static inline void ide_dbg_set_repl_script_running(bool running) {
    __atomic_store_n(&repl_script_running, running, __ATOMIC_RELEASE);
}

static inline uint32_t ide_dbg_script_running(void) {
    return __atomic_load_n(&ide_script_running, __ATOMIC_ACQUIRE);
}

static inline bool ide_dbg_python_running(void) {
    return ide_dbg_script_running() != 0 || ide_dbg_repl_script_running();
}

bool ide_dbg_is_script_running(void) {
    return ide_dbg_python_running() ||
           __atomic_load_n(&ide_soft_reset_requested, __ATOMIC_ACQUIRE);
}

bool ide_dbg_has_script(void) {
    return ide_dbg_script_running() != 0;
}

static inline void ide_dbg_set_script_running(uint32_t running) {
    __atomic_store_n(&ide_script_running, running, __ATOMIC_RELEASE);
}

static inline void ide_dbg_set_soft_reset_request(bool requested) {
    __atomic_store_n(&ide_soft_reset_requested, requested, __ATOMIC_RELEASE);
}

bool ide_dbg_take_soft_reset_request(void) {
    return __atomic_load_n(&ide_soft_reset_requested, __ATOMIC_ACQUIRE);
}

void ide_dbg_clear_soft_reset_request(void) {
    ide_dbg_set_soft_reset_request(false);
}

static inline bool ide_dbg_is_attached(void) {
    return __atomic_load_n(&ide_attached, __ATOMIC_ACQUIRE);
}

static void ide_dbg_clear_fb(bool discard_pending);

static inline void ide_dbg_set_auto_exec_suppressed(bool suppressed) {
    __atomic_store_n(&ide_auto_exec_suppressed, suppressed, __ATOMIC_RELEASE);
}

bool ide_dbg_auto_exec_allowed(void) {
    return !__atomic_load_n(&ide_auto_exec_suppressed, __ATOMIC_ACQUIRE);
}

static inline void ide_dbg_set_attached(bool attached) {
    __atomic_store_n(&ide_attached, attached, __ATOMIC_RELEASE);
    if (attached) {
        ide_dbg_set_auto_exec_suppressed(true);
    } else {
        ide_dbg_clear_fb(true);
        ide_dbg_stdout_protocol_detach();
    }
}

static inline bool ide_dbg_should_disconnect(void) {
    return __atomic_load_n(&ide_disconnect, __ATOMIC_ACQUIRE);
}

static inline void ide_dbg_set_disconnect(bool disconnect) {
    __atomic_store_n(&ide_disconnect, disconnect, __ATOMIC_RELEASE);
}

static void ide_dbg_queue_script(char *payload, exec_type_t type) {
    exec_payload = payload;
    exec_type = type;
    ide_dbg_set_script_running(1);
    sem_post(&script_sem);
    interrupt_repl();
}

char* ide_dbg_get_script() {
    while (sem_wait(&script_sem) != 0) {
        if (errno != EINTR) {
            pr_err("sem_wait(script_sem) failed: %s", strerror(errno));
            return NULL;
        }
    }
    return ide_dbg_is_attached() ? exec_payload : NULL;
}

exec_type_t ide_dbg_get_exec_type(void) {
    return exec_type;
}

bool ide_dbg_attach(void) {
    return ide_dbg_is_attached();
}

bool ide_dbg_is_connected(void) {
    drv_uart_inst_t *inst = mp_hal_uart_get_instance();
    return inst != NULL &&
           drv_uart_is_dtr_asserted(inst) > 0 &&
           ide_dbg_is_attached();
}

void ide_dbg_on_script_start(void) {
    ide_dbg_set_repl_script_running(true);
}

void ide_dbg_on_script_end(void) {
    ide_dbg_clear_fb(false);
    ide_dbg_set_repl_script_running(false);
    ide_dbg_vtouch_close();
}

void ide_dbg_on_soft_reset(void) {
    MP_STATE_PORT(ide_exception).traceback_data = NULL;
    MP_STATE_PORT(ide_exception).traceback_alloc = 0;
    MP_STATE_PORT(ide_exception).traceback_len = 0;
    ide_dbg_clear_fb(false);
    ide_dbg_set_repl_script_running(false);
    ide_dbg_vtouch_close();
}

void ide_dbg_on_ide_script_end(void) {
    if (exec_payload) {
        free(exec_payload);
        exec_payload = NULL;
    }
    exec_type = EXEC_STRING;
    // wait print done
    int count = 0;
    while (tx_buf_readable_locked() > 0 && count < 100) {
        usleep(1000);
        count++;
    }
    ide_dbg_set_script_running(0);
    if (ide_dbg_should_disconnect()) {
        ide_dbg_set_disconnect(false);
        ide_dbg_set_attached(false);
    }
    ide_dbg_on_script_end();
}

void interrupt_repl(void) {
    wait_mp_irq_handler_done();
    const uint8_t ctrl_cd[2] = { CHAR_CTRL_C, CHAR_CTRL_D };
    mp_hal_stdin_clear();
    mp_hal_stdin_push(&ctrl_cd[0], 1);
    mp_hal_stdin_push(&ctrl_cd[1], 1);
}

static void ide_dbg_request_soft_reset(void) {
    bool interrupt_running_script = ide_dbg_python_running() && !ide_dbg_take_soft_reset_request();
    ide_dbg_set_soft_reset_request(true);
    mp_hal_stdin_clear();
    wait_mp_irq_handler_done();
    if (interrupt_running_script) {
        mp_thread_set_exception_main(
            MP_OBJ_FROM_PTR(&MP_STATE_PORT(ide_exception)));
    }
    const uint8_t ctrl_d = CHAR_CTRL_D;
    mp_hal_stdin_push(&ctrl_d, 1);
}

static void ide_dbg_disconnect_and_soft_reset(void) {
    pr_verb("[usb] IDE disconnected");
    ide_dbg_set_disconnect(false);
    ide_dbg_set_attached(false);
    ide_dbg_request_soft_reset();
}

void ide_dbg_interrupt(void) {
    pr_verb("[usb] exit IDE mode");
    wait_mp_irq_handler_done();
    ide_dbg_set_attached(false);
    sem_post(&script_sem);
}

static bool enable_pic = true;

///////////////////////////////////////////////////////////////////////////////
// Framebuffer management /////////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////////////

static void* fb_data = NULL;
static uint32_t fb_size = 0, fb_width = 0, fb_height = 0;

// Once FRAME_SIZE advertises a buffer, detach it from the producer and keep it
// alive until FRAME_DUMP. This preserves the fixed-size protocol transaction
// even if the Python thread replaces or clears its framebuffer in between.
static void* fb_pending_data = NULL;
static size_t fb_pending_size = 0;
static uint32_t fb_pending_width = 0, fb_pending_height = 0;
static bool fb_pending_owned = false;

static pthread_mutex_t fb_mutex = PTHREAD_MUTEX_INITIALIZER;

static void ide_dbg_clear_fb_locked(void)
{
    if (fb_data) {
        free(fb_data);
        fb_data = NULL;
    }
    fb_size = 0;
    fb_width = 0;
    fb_height = 0;

    fb_from = FB_FROM_NONE;
}

static void ide_dbg_clear_fb(bool discard_pending)
{
    pthread_mutex_lock(&fb_mutex);
    ide_dbg_clear_fb_locked();
    if (discard_pending) {
        if (fb_pending_owned) {
            free(fb_pending_data);
        }
        fb_pending_data = NULL;
        fb_pending_size = 0;
        fb_pending_width = 0;
        fb_pending_height = 0;
        fb_pending_owned = false;
    }
    pthread_mutex_unlock(&fb_mutex);
}

// FIXME: reuse buf
void ide_set_fb(const void* data, uint32_t size, uint32_t width, uint32_t height) {
    pthread_mutex_lock(&fb_mutex);
    fb_from = FB_FROM_USER_SET;
    if (fb_data) {
        free(fb_data);
        fb_data = NULL;
        fb_size = 0;
    }
    fb_data = malloc(size);
    if(NULL == fb_data) {
        printf("malloc for fb failed");
        pthread_mutex_unlock(&fb_mutex);
        return;
    }
    hal_rvv_memcpy((void*)fb_data, data, size);
    fb_size = size;
    fb_width = width;
    fb_height = height;
    pthread_mutex_unlock(&fb_mutex);
}

void ide_dbg_enable_vo_wbc(void)
{
    pthread_mutex_lock(&fb_mutex);
    fb_from = FB_FROM_VO_WRITEBACK;
    pthread_mutex_unlock(&fb_mutex);
}

///////////////////////////////////////////////////////////////////////////////
// IDE command handlers ////////////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////////////

static bool resolve_filepath(const char* name, char* out, size_t out_size) {
    if (name == NULL || out == NULL || out_size == 0) {
        return false;
    }

    int n;
    if (strlen(name) == 0 || strstr(name, "..")) {
        return false;
    }
    if (name[0] == '/') {
        n = snprintf(out, out_size, "%s", name);
    } else {
        n = snprintf(out, out_size, "/sdcard/%s", name);
    }
    return n >= 0 && (size_t)n < out_size;
}

static size_t read_from_frame(ide_dbg_state_t* state, void* buf, size_t size);
static uint32_t read_u32_from_frame(ide_dbg_state_t* state);


static void discard_from_frame(ide_dbg_state_t* state, size_t size) {
    uint8_t discard_buf[256];
    size_t remaining = size;

    while (remaining > 0) {
        size_t chunk = remaining;
        if (chunk > sizeof(discard_buf)) {
            chunk = sizeof(discard_buf);
        }
        size_t received = read_from_frame(state, discard_buf, chunk);
        if (received == 0) {
            return;
        }
        remaining -= received;
        if (received != chunk) {
            return;
        }
    }
}

static uint32_t file_errno_to_usbdbg(int err) {
    switch (err) {
        case 0: return USBDBG_SVFILE_ERR_NONE;
        case ENOENT: return USBDBG_SVFILE_ERR_FILE_NOT_FOUND;
        case EEXIST: return USBDBG_SVFILE_ERR_FILE_EXISTS;
        case EACCES:
        case EPERM: return USBDBG_SVFILE_ERR_PERM_DENIED;
        case ENOTEMPTY: return USBDBG_SVFILE_ERR_DIR_NOT_EMPTY;
        default: return USBDBG_SVFILE_ERR_IO_ERROR;
    }
}

static void close_active_sv_file(void) {
    if (ide_dbg_sv_file.file != NULL) {
        fclose(ide_dbg_sv_file.file);
        ide_dbg_sv_file.file = NULL;
    }
}

static bool is_dot_or_dotdot(const char *name) {
    return name[0] == '.' &&
        (name[1] == '\0' || (name[1] == '.' && name[2] == '\0'));
}

static void cmd_arch_str(ide_dbg_state_t* state) {
    char buffer[0x40] = {0};
    char unit;
    int value;

    if (state->data_length != sizeof(buffer))
        pr_verb("Warning: USBDBG_ARCH_STR data length %u, expected %lu", state->data_length, sizeof(buffer));

    if (sys_mem_total_size >= (1 << 30)) {
        value = sys_mem_total_size / (1 << 30);
        unit = 'G';
    } else if (sys_mem_total_size >= (1 << 20)) {
        value = sys_mem_total_size / (1 << 20);
        unit = 'M';
    } else if (sys_mem_total_size >= (1 << 10)) {
        value = sys_mem_total_size / (1 << 10);
        unit = 'K';
    } else {
        value = sys_mem_total_size;
        unit = 'B';
    }

    snprintf(buffer, sizeof(buffer), "%s [" OMV_BOARD_TYPE ":%08X%08X%08X]",
        OMV_ARCH_STR, value, unit, 0, 0, 0);
    pr_verb("cmd: USBDBG_ARCH_STR %s", buffer);
    mp_hal_uart_tx(buffer, sizeof(buffer));
}

static void cmd_script_exec(ide_dbg_state_t* state) {
    pr_verb("cmd: USBDBG_SCRIPT_EXEC size %u", state->data_length);
    if (ide_dbg_python_running() && !ide_dbg_take_soft_reset_request()) {
        mp_thread_set_exception_main(
            MP_OBJ_FROM_PTR(&MP_STATE_PORT(ide_exception)));
    }
    usleep(1000);
    if (ide_dbg_is_script_running()) {
        discard_from_frame(state, state->data_length);
        return;
    }
    exec_payload = malloc(state->data_length + 1);
    if (exec_payload == NULL) {
        pr_err("cmd: USBDBG_SCRIPT_EXEC alloc failed, size %u", state->data_length + 1);
        discard_from_frame(state, state->data_length);
        return;
    }
    size_t received = read_from_frame(state, exec_payload, state->data_length);
    if (received != state->data_length) {
        pr_err("cmd: USBDBG_SCRIPT_EXEC incomplete payload: got %zu of %u bytes",
               received, state->data_length);
        free(exec_payload);
        exec_payload = NULL;
        return;
    }
    exec_payload[state->data_length] = '\0';
    ide_dbg_queue_script(exec_payload, EXEC_STRING);
}

#define IDE_CTRL_A (0x01)
#define IDE_CTRL_B (0x02)
#define IDE_CTRL_D (0x04)
#define IDE_CTRL_E (0x05)

static bool is_ide_terminal_control(uint8_t ch) {
    return ch == IDE_CTRL_A
        || ch == IDE_CTRL_B
        || ch == CHAR_CTRL_C
        || ch == IDE_CTRL_D
        || ch == IDE_CTRL_E;
}

static void cmd_tx_input(ide_dbg_state_t* state) {
    pr_dbg("[ide] cmd: USBDBG_TX_INPUT size %u attached=%d script_running=%u repl_running=%d",
            state->data_length,
            ide_dbg_attach(),
            ide_dbg_script_running(),
            ide_dbg_repl_script_running());

    if (state->data_length == 0) {
        return;
    }

    char *input = malloc(state->data_length);
    if (input == NULL) {
        pr_err("cmd: USBDBG_TX_INPUT alloc failed, size %u", state->data_length);
        discard_from_frame(state, state->data_length);
        return;
    }

    size_t received = read_from_frame(state, input, state->data_length);
    if (received != state->data_length) {
        pr_err("cmd: USBDBG_TX_INPUT incomplete payload: got %zu of %u bytes",
               received, state->data_length);
        free(input);
        return;
    }
    if (state->data_length > 0) {
        pr_dbg("[ide] USBDBG_TX_INPUT payload first=0x%02x last=0x%02x len=%u",
                (uint8_t)input[0],
                (uint8_t)input[state->data_length - 1],
                state->data_length);
    }

    if (state->data_length == 1 && is_ide_terminal_control((uint8_t)input[0])) {
        uint8_t ctrl = (uint8_t)input[0];
        pr_dbg("[ide] USBDBG_TX_INPUT control=0x%02x attached=%d script_running=%u repl_running=%d",
                ctrl,
                ide_dbg_attach(),
                ide_dbg_script_running(),
                ide_dbg_repl_script_running());

        if (ctrl == IDE_CTRL_D && ide_dbg_is_script_running()) {
            ide_dbg_request_soft_reset();
            pr_dbg("[ide] USBDBG_TX_INPUT requested soft reset");
        } else if (ctrl == CHAR_CTRL_C && ide_dbg_repl_script_running()) {
            wait_mp_irq_handler_done();
            __atomic_store_n(&is_repl_intr, true, __ATOMIC_RELEASE);
#if MICROPY_KBD_EXCEPTION
            mp_thread_set_exception_main(MP_OBJ_FROM_PTR(&MP_STATE_VM(mp_kbd_exception)));
#endif
            pr_dbg("[ide] USBDBG_TX_INPUT raised keyboard interrupt");
        } else {
            mp_hal_stdin_push(&ctrl, 1);
            pr_dbg("[ide] USBDBG_TX_INPUT pushed control byte to stdin");
        }
        free(input);
        return;
    }

    pr_dbg("[ide] USBDBG_TX_INPUT first=0x%02x attached=%d idle=%d",
            (uint8_t)input[0],
            ide_dbg_attach(),
            ide_dbg_script_running() == 0 && !ide_dbg_repl_script_running());

    if (ide_dbg_repl_script_running() && input[0] == CHAR_CTRL_C) {
        wait_mp_irq_handler_done();
        __atomic_store_n(&is_repl_intr, true, __ATOMIC_RELEASE);
#if MICROPY_KBD_EXCEPTION
        mp_thread_set_exception_main(MP_OBJ_FROM_PTR(&MP_STATE_VM(mp_kbd_exception)));
#endif
        pr_dbg("[ide] USBDBG_TX_INPUT raised keyboard interrupt");
    } else if ((uint8_t)input[0] == IDE_CTRL_D && ide_dbg_is_script_running()) {
        ide_dbg_request_soft_reset();
        pr_dbg("[ide] USBDBG_TX_INPUT requested soft reset");
    } else {
        size_t input_len = state->data_length;
        mp_hal_stdin_push((const uint8_t*)input, input_len);
        pr_dbg("[ide] USBDBG_TX_INPUT pushed %zu bytes to stdin", input_len);
    }
    free(input);
}

static int file_sync(FILE *file) {
    if (file == NULL) {
        return -1;
    }
    if (fflush(file) != 0) {
        return -1;
    }
    return fsync(fileno(file));
}

static void svfile_release_chunk_buffer(void) {
    if (ide_dbg_sv_file.chunk_buffer != NULL) {
        free(ide_dbg_sv_file.chunk_buffer);
        ide_dbg_sv_file.chunk_buffer = NULL;
    }
}

static bool svfile_configure_write_buffer(FILE *file) {
    return file != NULL && ide_dbg_sv_file.chunk_buffer != NULL &&
           setvbuf(file, (char *)ide_dbg_sv_file.chunk_buffer, _IOFBF,
                   USBDBG_FILE_CHUNK_MAX) == 0;
}

static void cmd_verifyfile(void) {
    pr_verb("cmd: USBDBG_VERIFYFILE");
    uint32_t resp = USBDBG_SVFILE_VERIFY_ERR_NONE;

    if (ide_dbg_sv_file.file != NULL) {
        if (file_sync(ide_dbg_sv_file.file) != 0) {
            resp = USBDBG_SVFILE_ERR_WRITE_ERR;
            fclose(ide_dbg_sv_file.file);
            ide_dbg_sv_file.file = NULL;
            svfile_release_chunk_buffer();
            mp_hal_uart_tx(&resp, sizeof(resp));
            return;
        }
        fclose(ide_dbg_sv_file.file);
        ide_dbg_sv_file.file = NULL;
    }

    char filepath[USBDBG_MAX_PATH_LEN + 64];
    if (!resolve_filepath(ide_dbg_sv_file.info.name, filepath, sizeof(filepath))) {
        resp = USBDBG_SVFILE_VERIFY_NOT_OPEN;
        svfile_release_chunk_buffer();
        mp_hal_uart_tx(&resp, sizeof(resp));
        return;
    }

    FILE *f = fopen(filepath, "rb");
    if (f == NULL) {
        resp = USBDBG_SVFILE_VERIFY_NOT_OPEN;
        svfile_release_chunk_buffer();
        mp_hal_uart_tx(&resp, sizeof(resp));
        return;
    }

    mbedtls_sha256_context sha256;
    mbedtls_sha256_init(&sha256);
    mbedtls_sha256_starts_ret(&sha256, 0);

    size_t nbytes;
    do {
        nbytes = fread(ide_dbg_file_io_buffer, 1, sizeof(ide_dbg_file_io_buffer), f);
        mbedtls_sha256_update_ret(&sha256, ide_dbg_file_io_buffer, nbytes);
    } while (nbytes == sizeof(ide_dbg_file_io_buffer));

    fclose(f);

    uint8_t sha256_result[32];
    mbedtls_sha256_finish_ret(&sha256, sha256_result);
    mbedtls_sha256_free(&sha256);
    if (memcmp(sha256_result, ide_dbg_sv_file.info.sha256, sizeof(sha256_result)) != 0) {
        resp = USBDBG_SVFILE_VERIFY_SHA2_ERR;
        pr_verb("file sha256 unmatched");
        print_sha256(sha256_result);
    }

    svfile_release_chunk_buffer();
    mp_hal_uart_tx(&resp, sizeof(resp));
}

static void cmd_createfile(ide_dbg_state_t* state) {
    pr_verb("cmd: USBDBG_CREATEFILE");
    hal_rvv_memset(&ide_dbg_sv_file.info, 0, sizeof(ide_dbg_sv_file.info));
    if (state->data_length != 0 && sizeof(ide_dbg_sv_file.info) != state->data_length) {
        ide_dbg_sv_file.errcode = USBDBG_SVFILE_ERR_PATH_ERR;
        pr_verb("Warning: CREATEFILE expect data length %lu, got %u",
                sizeof(ide_dbg_sv_file.info), state->data_length);
        discard_from_frame(state, state->data_length);
        return;
    }

    close_active_sv_file();
    svfile_release_chunk_buffer();

    size_t received = read_from_frame(state, &ide_dbg_sv_file.info, sizeof(ide_dbg_sv_file.info));
    if (received != sizeof(ide_dbg_sv_file.info)) {
        ide_dbg_sv_file.errcode = USBDBG_SVFILE_ERR_CHUNK_ERR;
        pr_err("cmd: USBDBG_CREATEFILE incomplete payload: got %zu of %zu bytes",
               received, sizeof(ide_dbg_sv_file.info));
        return;
    }
    pr_verb("create file: chunk_size(%d), name(%s)",
            ide_dbg_sv_file.info.chunk_size, ide_dbg_sv_file.info.name);
    print_sha256(ide_dbg_sv_file.info.sha256);

    if (ide_dbg_sv_file.info.chunk_size <= 0 ||
        ide_dbg_sv_file.info.chunk_size > USBDBG_FILE_CHUNK_MAX) {
        ide_dbg_sv_file.errcode = USBDBG_SVFILE_ERR_CHUNK_ERR;
        return;
    }

    char filepath[USBDBG_MAX_PATH_LEN + 64];
    if (!resolve_filepath(ide_dbg_sv_file.info.name, filepath, sizeof(filepath))) {
        ide_dbg_sv_file.errcode = USBDBG_SVFILE_ERR_PATH_ERR;
        return;
    }

    ide_dbg_sv_file.file = fopen(filepath, "wb");
    if (ide_dbg_sv_file.file == NULL) {
        ide_dbg_sv_file.errcode = USBDBG_SVFILE_ERR_OPEN_ERR;
        return;
    }

    ide_dbg_sv_file.chunk_buffer = malloc(USBDBG_FILE_CHUNK_MAX);
    if (ide_dbg_sv_file.chunk_buffer == NULL) {
        fclose(ide_dbg_sv_file.file);
        ide_dbg_sv_file.file = NULL;
        ide_dbg_sv_file.errcode = USBDBG_SVFILE_ERR_CHUNK_ERR;
        return;
    }
    if (!svfile_configure_write_buffer(ide_dbg_sv_file.file)) {
        fclose(ide_dbg_sv_file.file);
        ide_dbg_sv_file.file = NULL;
        svfile_release_chunk_buffer();
        ide_dbg_sv_file.errcode = USBDBG_SVFILE_ERR_CHUNK_ERR;
        return;
    }
    ide_dbg_sv_file.errcode = USBDBG_SVFILE_ERR_NONE;
}

static void cmd_frame_size(void) {
    #if PRINT_ALL
    pr_verb("cmd: USBDBG_FRAME_SIZE");
    #endif
    uint32_t resp[3] = { 0, 0, 0 };

    if (!mp_hal_uart_is_usb()) {
        mp_hal_uart_tx(&resp, sizeof(resp));
        return;
    }

    if (enable_pic) {
        static uint64_t last_frame_ticks_ms = 0;
        uint64_t curr_frame_ticks_ms = mp_hal_ticks_ms();
        if (curr_frame_ticks_ms - last_frame_ticks_ms >= 33) {
            last_frame_ticks_ms = curr_frame_ticks_ms;
            bool capture_vo = false;
            pthread_mutex_lock(&fb_mutex);
            if (fb_pending_data == NULL && FB_FROM_USER_SET == fb_from) {
                if (fb_data && fb_size) {
                    fb_pending_data = fb_data;
                    fb_pending_size = fb_size;
                    fb_pending_width = fb_width;
                    fb_pending_height = fb_height;
                    fb_pending_owned = true;
                    fb_data = NULL;
                    fb_size = 0;
                    fb_width = 0;
                    fb_height = 0;
                }
            } else if (fb_pending_data == NULL && FB_FROM_VO_WRITEBACK == fb_from) {
                capture_vo = true;
            }
            if (fb_pending_data != NULL && fb_pending_size != 0) {
                resp[0] = fb_pending_width;
                resp[1] = fb_pending_height;
                resp[2] = fb_pending_size;
            }
            pthread_mutex_unlock(&fb_mutex);

            if (capture_vo) {
                extern int ide_dbg_vo_wbc_dump_and_encode(
                    void** buffer, size_t* buffer_size,
                    uint32_t* image_width, uint32_t* image_height);
                void *captured_data = NULL;
                size_t captured_size = 0;
                uint32_t captured_width = 0, captured_height = 0;
                if (ide_dbg_vo_wbc_dump_and_encode(
                        &captured_data, &captured_size,
                        &captured_width, &captured_height) == 0) {
                    pthread_mutex_lock(&fb_mutex);
                    if (fb_pending_data == NULL && fb_from == FB_FROM_VO_WRITEBACK) {
                        fb_pending_data = captured_data;
                        fb_pending_size = captured_size;
                        fb_pending_width = captured_width;
                        fb_pending_height = captured_height;
                        fb_pending_owned = false;
                        resp[0] = fb_pending_width;
                        resp[1] = fb_pending_height;
                        resp[2] = fb_pending_size;
                    }
                    pthread_mutex_unlock(&fb_mutex);
                }
            }
        }
    }

    // Use the full-write path: the host reads exactly sizeof(resp) bytes, so a
    // short CDC write that dropped the tail would desync every later response.
    mp_hal_uart_tx(&resp, sizeof(resp));
}

static void cmd_frame_dump(void) {
    if (!mp_hal_uart_is_usb()) {
        return;
    }

    void *dump_data = NULL;
    size_t dump_size = 0;
    bool free_dump_data = false;

    pthread_mutex_lock(&fb_mutex);
    dump_data = fb_pending_data;
    dump_size = fb_pending_size;
    free_dump_data = fb_pending_owned;
    fb_pending_data = NULL;
    fb_pending_size = 0;
    fb_pending_width = 0;
    fb_pending_height = 0;
    fb_pending_owned = false;
    pthread_mutex_unlock(&fb_mutex);

    if (dump_data && dump_size) {
        // Full-write: the host reads exactly dump_size bytes (the value reported
        // by FRAME_SIZE), so a dropped tail would desync the protocol stream.
        mp_hal_uart_tx(dump_data, dump_size);
        if (free_dump_data) {
            free(dump_data);
        }
    }
}

static size_t read_from_frame(ide_dbg_state_t* state, void* buf, size_t size) {
    uint8_t *dst = (uint8_t*)buf;
    size_t avail = 0;
    if (state->frame_offset < state->frame_length) {
        avail = state->frame_length - state->frame_offset;
    }
    size_t from_buf = (avail < size) ? avail : size;
    if (from_buf > 0) {
        hal_rvv_memcpy(dst, state->frame_data + state->frame_offset, from_buf);
        state->frame_offset += from_buf;
        dst += from_buf;
        size -= from_buf;
    }
    if (size > 0) {
        from_buf += read_until(dst, size);
    }
    return from_buf;
}

static bool read_path_nt(ide_dbg_state_t* state, char *out, size_t out_size) {
    if (out == NULL || out_size == 0) {
        return false;
    }

    const uint8_t *p = state->frame_data + state->frame_offset;
    size_t remain = 0;
    size_t idx = 0;
    int found_null = 0;
    bool truncated = false;

    if (state->frame_offset < state->frame_length) {
        remain = state->frame_length - state->frame_offset;
    }
    while (remain > 0) {
        if (*p == 0) {
            p++;
            remain--;
            found_null = 1;
            break;
        }
        if (idx < out_size - 1) {
            out[idx++] = (char)*p;
        } else {
            truncated = true;
        }
        p++;
        remain--;
    }
    state->frame_offset = state->frame_length - remain;

    if (!found_null) {
        uint8_t ch;
        while (true) {
            if (read_until(&ch, 1) != 1) {
                out[idx] = '\0';
                return false;
            }
            if (ch == 0) {
                found_null = 1;
                break;
            }
            if (idx < out_size - 1) {
                out[idx++] = (char)ch;
            } else {
                truncated = true;
            }
        }
    }
    out[idx] = '\0';
    return found_null && !truncated && idx > 0 && strstr(out, "..") == NULL;
}

static uint32_t read_u32_from_frame(ide_dbg_state_t* state) {
    uint32_t val = 0;
    read_from_frame(state, &val, sizeof(val));
    return val;
}

static uint8_t stat_type_from_mode(mode_t mode) {
    if (S_ISDIR(mode)) return 1;
    return 0;
}

static void cmd_query_file_stat(ide_dbg_state_t* state) {
    uint32_t resp[4] = { USBDBG_SVFILE_ERR_FILE_NOT_FOUND, 0, 0, 0 };
    char path[USBDBG_MAX_PATH_LEN + 1];
    char resolved[USBDBG_MAX_PATH_LEN + 64];

    if (!read_path_nt(state, path, sizeof(path)) ||
        !resolve_filepath(path, resolved, sizeof(resolved))) {
        resp[0] = USBDBG_SVFILE_ERR_INVALID_PATH;
        mp_hal_uart_tx(resp, sizeof(resp));
        return;
    }

    struct stat st;
    if (stat(resolved, &st) == 0 && (S_ISREG(st.st_mode) || S_ISDIR(st.st_mode))) {
        resp[0] = 0;
        resp[1] = stat_type_from_mode(st.st_mode);
        resp[2] = S_ISREG(st.st_mode) ? (uint32_t)st.st_size : 0;
        resp[3] = (uint32_t)st.st_mtime;
    } else {
        resp[0] = file_errno_to_usbdbg(errno);
    }
    mp_hal_uart_tx(resp, sizeof(resp));
}

static const char *const listdir_root_names[] = { "sdcard", "data", "udisk" };

static void listdir_page_reset(void) {
    if (ide_dbg_listdir_page_state.dir != NULL) {
        closedir(ide_dbg_listdir_page_state.dir);
    }
    hal_rvv_memset(&ide_dbg_listdir_page_state, 0, sizeof(ide_dbg_listdir_page_state));
}

static void listdir_page_send(uint32_t errcode, uint32_t next_offset,
                              uint32_t count, uint32_t payload_size) {
    if (!ide_dbg_host_attached()) {
        return;
    }
    // The header carries the number of entries; the payload starts with the
    // continuation offset followed by the entry records.
    uint32_t header[3] = { errcode, payload_size, count };
    hal_rvv_memcpy(ide_dbg_listdir_page_buffer, &next_offset, sizeof(next_offset));
    mp_hal_uart_tx(header, sizeof(header));
    mp_hal_uart_tx(ide_dbg_listdir_page_buffer, payload_size);
}

static void listdir_page_send_error(uint32_t errcode) {
    listdir_page_send(errcode, USBDBG_LISTDIR_PAGE_DONE, 0, sizeof(uint32_t));
}

static bool listdir_page_name_length(const char *name, uint8_t *name_len) {
    size_t length = strlen(name);
    if (length > UINT8_MAX) {
        return false;
    }
    *name_len = (uint8_t)length;
    return true;
}

static bool listdir_page_append(const char *name, const struct stat *st,
                                uint32_t payload_limit, uint32_t *payload_size) {
    uint8_t name_len;
    if (!listdir_page_name_length(name, &name_len)) {
        return false;
    }
    uint32_t entry_size = 10 + (uint32_t)name_len;
    if (entry_size > payload_limit || *payload_size > payload_limit - entry_size) {
        return false;
    }

    uint8_t *entry = ide_dbg_listdir_page_buffer + *payload_size;
    uint32_t size = S_ISREG(st->st_mode) ? (uint32_t)st->st_size : 0;
    uint32_t mtime = (uint32_t)st->st_mtime;
    entry[0] = stat_type_from_mode(st->st_mode);
    entry[1] = (uint8_t)name_len;
    hal_rvv_memcpy(entry + 2, &size, sizeof(size));
    hal_rvv_memcpy(entry + 6, &mtime, sizeof(mtime));
    hal_rvv_memcpy(entry + 10, name, name_len);
    *payload_size += entry_size;
    return true;
}

static bool listdir_page_has_space(const char *name, uint32_t payload_limit,
                                   uint32_t payload_size) {
    uint8_t name_len;
    if (!listdir_page_name_length(name, &name_len)) {
        return false;
    }
    uint32_t entry_size = 10 + (uint32_t)name_len;
    return entry_size <= payload_limit && payload_size <= payload_limit - entry_size;
}

static bool listdir_page_set_pending(const char *name) {
    size_t name_len = strlen(name);
    if (name_len >= sizeof(ide_dbg_listdir_page_state.pending_name)) {
        return false;
    }
    hal_rvv_memcpy(ide_dbg_listdir_page_state.pending_name, name, name_len + 1);
    ide_dbg_listdir_page_state.pending = true;
    return true;
}

static DIR *listdir_page_open(const char *filepath, uint32_t offset,
                              uint32_t *entry_index, bool *offset_exhausted,
                              bool *invalid_name) {
    *offset_exhausted = false;
    *invalid_name = false;

    if (ide_dbg_listdir_page_state.dir != NULL &&
        ide_dbg_listdir_page_state.next_offset == offset &&
        strcmp(ide_dbg_listdir_page_state.filepath, filepath) == 0) {
        *entry_index = offset;
        return ide_dbg_listdir_page_state.dir;
    }

    listdir_page_reset();
    const bool host_attached = ide_dbg_host_attached();
    if (!host_attached) {
        return NULL;
    }
    DIR *dir = opendir(filepath);
    if (dir == NULL) {
        return NULL;
    }

    ide_dbg_listdir_page_state.dir = dir;
    snprintf(ide_dbg_listdir_page_state.filepath,
             sizeof(ide_dbg_listdir_page_state.filepath), "%s", filepath);

    uint32_t index = 0;
    struct dirent *ent;
    while (index < offset) {
        ent = readdir(dir);
        if (ent == NULL) {
            listdir_page_reset();
            *entry_index = index;
            *offset_exhausted = true;
            return NULL;
        }
        if (is_dot_or_dotdot(ent->d_name)) {
            continue;
        }
        uint8_t name_len;
        if (!listdir_page_name_length(ent->d_name, &name_len)) {
            listdir_page_reset();
            *invalid_name = true;
            return NULL;
        }
        index++;
    }
    ide_dbg_listdir_page_state.next_offset = index;
    *entry_index = index;
    return dir;
}

static bool parse_listdir_page_request(const char *request, uint32_t *offset,
                                       uint32_t *payload_limit, const char **path) {
    const size_t prefix_len = sizeof(USBDBG_LISTDIR_PAGE_REQUEST_PREFIX) - 1;
    const char *cursor;
    char *end;
    unsigned long value;

    if (strncmp(request, USBDBG_LISTDIR_PAGE_REQUEST_PREFIX, prefix_len) != 0) {
        return false;
    }

    cursor = request + prefix_len;
    errno = 0;
    value = strtoul(cursor, &end, 10);
    if (errno != 0 || end == cursor || *end != '/' || value > UINT32_MAX) {
        return false;
    }
    *offset = (uint32_t)value;

    cursor = end + 1;
    errno = 0;
    value = strtoul(cursor, &end, 10);
    if (errno != 0 || end == cursor || *end != '/' || value > UINT32_MAX) {
        return false;
    }
    *payload_limit = (uint32_t)value;
    *path = end + 1;
    return **path != '\0';
}

static void cmd_listdir_page(const char *path, uint32_t offset,
                             uint32_t payload_limit) {
    const uint32_t min_payload = sizeof(uint32_t) + 10 + UINT8_MAX;
    char filepath[USBDBG_MAX_PATH_LEN + 64];
    uint32_t payload_size = sizeof(uint32_t);
    uint32_t count = 0;
    uint32_t next_offset = USBDBG_LISTDIR_PAGE_DONE;

    if (payload_limit > USBDBG_LISTDIR_PAGE_MAX_PAYLOAD) {
        payload_limit = USBDBG_LISTDIR_PAGE_MAX_PAYLOAD;
    }
    if (payload_limit < min_payload || !resolve_filepath(path, filepath, sizeof(filepath))) {
        listdir_page_reset();
        listdir_page_send_error(USBDBG_SVFILE_ERR_INVALID_PATH);
        return;
    }

    if (strcmp(path, "/") == 0) {
        listdir_page_reset();
        if (!ide_dbg_host_attached()) {
            return;
        }
        uint32_t entry_index = 0;
        for (size_t i = 0; i < sizeof(listdir_root_names) / sizeof(listdir_root_names[0]); i++) {
            char root_path[64];
            struct stat st;
            snprintf(root_path, sizeof(root_path), "/%s", listdir_root_names[i]);
            if (stat(root_path, &st) != 0 || !S_ISDIR(st.st_mode)) {
                continue;
            }
            if (entry_index < offset) {
                entry_index++;
                continue;
            }
            if (!listdir_page_append(listdir_root_names[i], &st, payload_limit, &payload_size)) {
                next_offset = entry_index;
                break;
            }
            count++;
            entry_index++;
        }
        listdir_page_send(0, next_offset, count, payload_size);
        return;
    }

    uint32_t entry_index = 0;
    bool offset_exhausted = false;
    bool invalid_name = false;
    DIR *dir = listdir_page_open(filepath, offset, &entry_index,
                                  &offset_exhausted, &invalid_name);
    if (dir == NULL) {
        if (!ide_dbg_host_attached()) {
            return;
        }
        if (offset_exhausted) {
            listdir_page_send(0, USBDBG_LISTDIR_PAGE_DONE, 0, sizeof(uint32_t));
            return;
        }
        if (invalid_name) {
            listdir_page_send_error(USBDBG_SVFILE_ERR_IO_ERROR);
            return;
        }
        listdir_page_send_error(file_errno_to_usbdbg(errno));
        return;
    }

    const bool host_attached = ide_dbg_host_attached();
    if (!host_attached) {
        listdir_page_reset();
        return;
    }
    struct dirent *ent;
    while (true) {
        const char *name;
        if (ide_dbg_listdir_page_state.pending) {
            name = ide_dbg_listdir_page_state.pending_name;
            ide_dbg_listdir_page_state.pending = false;
        } else {
            ent = readdir(dir);
            if (ent == NULL) {
                break;
            }
            if (is_dot_or_dotdot(ent->d_name)) {
                continue;
            }
            name = ent->d_name;
        }

        uint8_t name_len;
        if (!listdir_page_name_length(name, &name_len)) {
            listdir_page_reset();
            listdir_page_send_error(USBDBG_SVFILE_ERR_IO_ERROR);
            return;
        }
        if (!listdir_page_has_space(name, payload_limit, payload_size)) {
            if (!listdir_page_set_pending(name)) {
                listdir_page_reset();
                listdir_page_send_error(USBDBG_SVFILE_ERR_INVALID_PATH);
                return;
            }
            next_offset = entry_index;
            break;
        }

        char child[USBDBG_MAX_PATH_LEN + 512];
        struct stat st;
        snprintf(child, sizeof(child), "%s/%s", filepath, name);
        if (stat(child, &st) != 0) {
            hal_rvv_memset(&st, 0, sizeof(st));
        }
        if (!listdir_page_append(name, &st, payload_limit, &payload_size)) {
            if (!listdir_page_set_pending(name)) {
                listdir_page_reset();
                listdir_page_send_error(USBDBG_SVFILE_ERR_INVALID_PATH);
                return;
            }
            next_offset = entry_index;
            break;
        }
        count++;
        entry_index++;
    }

    if (next_offset == USBDBG_LISTDIR_PAGE_DONE) {
        listdir_page_reset();
    } else {
        ide_dbg_listdir_page_state.next_offset = next_offset;
    }
    listdir_page_send(0, next_offset, count, payload_size);
}

static void cmd_listdir(ide_dbg_state_t* state) {
    char request[USBDBG_MAX_PATH_LEN + 64];
    uint32_t offset = 0;
    uint32_t payload_limit = 0;
    const char *path = NULL;
    uint32_t header[3] = { USBDBG_SVFILE_ERR_INVALID_PATH, 0, 0 };

    if (!read_path_nt(state, request, sizeof(request)) ||
        !parse_listdir_page_request(request, &offset, &payload_limit, &path)) {
        listdir_page_reset();
        mp_hal_uart_tx(header, sizeof(header));
        return;
    }

    cmd_listdir_page(path, offset, payload_limit);
}

static void cmd_readfile(ide_dbg_state_t* state) {
    uint32_t offset = read_u32_from_frame(state);
    uint32_t req_size = read_u32_from_frame(state);
    uint32_t header[3] = { 0, 0, 0 };
    char path[USBDBG_MAX_PATH_LEN + 1];
    char filepath[USBDBG_MAX_PATH_LEN + 64];

    if (req_size > USBDBG_FILE_CHUNK_MAX) req_size = USBDBG_FILE_CHUNK_MAX;
    if (!read_path_nt(state, path, sizeof(path)) ||
        !resolve_filepath(path, filepath, sizeof(filepath))) {
        header[0] = USBDBG_SVFILE_ERR_INVALID_PATH;
        mp_hal_uart_tx(header, sizeof(header));
        return;
    }

    struct stat st;
    if (stat(filepath, &st) != 0) {
        header[0] = file_errno_to_usbdbg(errno);
        mp_hal_uart_tx(header, sizeof(header));
        return;
    }
    if (!S_ISREG(st.st_mode)) {
        header[0] = USBDBG_SVFILE_ERR_INVALID_PATH;
        mp_hal_uart_tx(header, sizeof(header));
        return;
    }

    FILE *f = fopen(filepath, "rb");
    if (f == NULL) {
        header[0] = file_errno_to_usbdbg(errno);
        mp_hal_uart_tx(header, sizeof(header));
        return;
    }

    header[2] = (uint32_t)st.st_size;
    if (fseek(f, (long)offset, SEEK_SET) != 0) {
        header[0] = file_errno_to_usbdbg(errno);
        fclose(f);
        mp_hal_uart_tx(header, sizeof(header));
        return;
    }

    header[1] = (uint32_t)fread(ide_dbg_file_io_buffer, 1, req_size, f);
    fclose(f);
    mp_hal_uart_tx(header, sizeof(header));
    if (header[1] > 0) {
        mp_hal_uart_tx(ide_dbg_file_io_buffer, header[1]);
    }
}

static void cmd_createfile_ack(ide_dbg_state_t* state) {
    cmd_createfile(state);
    uint32_t errcode = (ide_dbg_sv_file.errcode == USBDBG_SVFILE_ERR_NONE) ? 0 : ide_dbg_sv_file.errcode;
    mp_hal_uart_tx(&errcode, sizeof(errcode));
}

static void cmd_writefile(ide_dbg_state_t* state) {
    pr_verb("cmd: USBDBG_WRITEFILE %u bytes", state->data_length);
    if ((ide_dbg_sv_file.file == NULL) ||
        (ide_dbg_sv_file.chunk_buffer == NULL) ||
        (ide_dbg_sv_file.info.chunk_size < state->data_length)) {
        ide_dbg_sv_file.errcode = USBDBG_SVFILE_ERR_WRITE_ERR;
        discard_from_frame(state, state->data_length);
        return;
    }

    size_t received = read_from_frame(state, ide_dbg_file_io_buffer, state->data_length);
    if (received != state->data_length) {
        close_active_sv_file();
        svfile_release_chunk_buffer();
        ide_dbg_sv_file.errcode = USBDBG_SVFILE_ERR_CHUNK_ERR;
        return;
    }
    if (ide_dbg_sv_file.file == NULL) {
        ide_dbg_sv_file.errcode = USBDBG_SVFILE_ERR_WRITE_ERR;
    } else if (fwrite(ide_dbg_file_io_buffer, 1, state->data_length, ide_dbg_sv_file.file) == state->data_length) {
        ide_dbg_sv_file.errcode = USBDBG_SVFILE_ERR_NONE;
    } else {
        fclose(ide_dbg_sv_file.file);
        ide_dbg_sv_file.file = NULL;
        ide_dbg_sv_file.errcode = USBDBG_SVFILE_ERR_WRITE_ERR;
    }
}

static void cmd_writefile_ack(ide_dbg_state_t* state) {
    uint32_t payload_size = state->data_length;
    uint32_t write_size = payload_size;
    if (write_size == 0) {
        write_size = read_u32_from_frame(state);
        payload_size = write_size;
    }
    if (write_size > USBDBG_FILE_CHUNK_MAX) {
        uint32_t errcode = USBDBG_SVFILE_ERR_CHUNK_ERR;
        discard_from_frame(state, payload_size);
        ide_dbg_sv_file.errcode = errcode;
        mp_hal_uart_tx(&errcode, sizeof(errcode));
        return;
    }

    if (ide_dbg_sv_file.chunk_buffer == NULL ||
        ide_dbg_sv_file.info.chunk_size <= 0 ||
        write_size > (uint32_t)ide_dbg_sv_file.info.chunk_size) {
        uint32_t errcode = USBDBG_SVFILE_ERR_CHUNK_ERR;
        discard_from_frame(state, payload_size);
        ide_dbg_sv_file.errcode = errcode;
        mp_hal_uart_tx(&errcode, sizeof(errcode));
        return;
    }
    size_t received = read_from_frame(state, ide_dbg_file_io_buffer, write_size);
    if (received != write_size) {
        uint32_t errcode = USBDBG_SVFILE_ERR_CHUNK_ERR;
        pr_err("cmd: USBDBG_WRITEFILE2 incomplete payload: got %zu of %u bytes",
               received, write_size);
        close_active_sv_file();
        svfile_release_chunk_buffer();
        ide_dbg_sv_file.errcode = errcode;
        mp_hal_uart_tx(&errcode, sizeof(errcode));
        return;
    }

    if (ide_dbg_sv_file.file == NULL && ide_dbg_sv_file.info.name[0] != '\0') {
        char filepath[USBDBG_MAX_PATH_LEN + 64];
        if (resolve_filepath(ide_dbg_sv_file.info.name, filepath, sizeof(filepath))) {
            ide_dbg_sv_file.file = fopen(filepath, "ab");
            if (!svfile_configure_write_buffer(ide_dbg_sv_file.file)) {
                if (ide_dbg_sv_file.file != NULL) {
                    fclose(ide_dbg_sv_file.file);
                    ide_dbg_sv_file.file = NULL;
                }
            }
        }
    }

    uint32_t errcode = 0;
    if (ide_dbg_sv_file.file == NULL) {
        errcode = USBDBG_SVFILE_ERR_WRITE_ERR;
    } else if (fwrite(ide_dbg_file_io_buffer, 1, write_size, ide_dbg_sv_file.file) != write_size) {
        errcode = USBDBG_SVFILE_ERR_WRITE_ERR;
    }
    ide_dbg_sv_file.errcode = errcode;
    mp_hal_uart_tx(&errcode, sizeof(errcode));
}

static void cmd_deletefile(ide_dbg_state_t* state) {
    uint32_t errcode;
    char path[USBDBG_MAX_PATH_LEN + 1];
    char filepath[USBDBG_MAX_PATH_LEN + 64];

    if (!read_path_nt(state, path, sizeof(path))) {
        errcode = USBDBG_SVFILE_ERR_INVALID_PATH;
    } else if (!resolve_filepath(path, filepath, sizeof(filepath))) {
        errcode = USBDBG_SVFILE_ERR_INVALID_PATH;
    } else {
        close_active_sv_file();
        if (unlink(filepath) == 0) {
            errcode = USBDBG_SVFILE_ERR_NONE;
        } else {
            errcode = file_errno_to_usbdbg(errno);
        }
    }
    mp_hal_uart_tx(&errcode, sizeof(errcode));
}

static void cmd_renamefile(ide_dbg_state_t* state) {
    uint32_t errcode;
    char old_path[USBDBG_MAX_PATH_LEN + 1];
    char new_path[USBDBG_MAX_PATH_LEN + 1];
    char old_resolved[USBDBG_MAX_PATH_LEN + 64];
    char new_resolved[USBDBG_MAX_PATH_LEN + 64];

    if (!read_path_nt(state, old_path, sizeof(old_path)) ||
        !read_path_nt(state, new_path, sizeof(new_path))) {
        errcode = USBDBG_SVFILE_ERR_INVALID_PATH;
    } else if (!resolve_filepath(old_path, old_resolved, sizeof(old_resolved)) ||
               !resolve_filepath(new_path, new_resolved, sizeof(new_resolved))) {
        errcode = USBDBG_SVFILE_ERR_INVALID_PATH;
    } else {
        close_active_sv_file();
        if (rename(old_resolved, new_resolved) == 0) {
            errcode = 0;
        } else {
            pr_dbg("RENAME_FILE %s -> %s errno=%d (%s)", old_resolved, new_resolved, errno, strerror(errno));
            errcode = file_errno_to_usbdbg(errno);
        }
    }
    mp_hal_uart_tx(&errcode, sizeof(errcode));
}

static void cmd_mkdir(ide_dbg_state_t* state) {
    uint32_t errcode;
    char path[USBDBG_MAX_PATH_LEN + 1];
    char filepath[USBDBG_MAX_PATH_LEN + 64];

    if (!read_path_nt(state, path, sizeof(path))) {
        errcode = USBDBG_SVFILE_ERR_INVALID_PATH;
    } else if (!resolve_filepath(path, filepath, sizeof(filepath))) {
        errcode = USBDBG_SVFILE_ERR_INVALID_PATH;
    } else {
        if (mkdir(filepath, 0777) == 0) {
            errcode = USBDBG_SVFILE_ERR_NONE;
        } else {
            errcode = (errno == EEXIST) ? USBDBG_SVFILE_ERR_FILE_EXISTS
                    : (errno == ENOENT) ? USBDBG_SVFILE_ERR_INVALID_PATH
                    : file_errno_to_usbdbg(errno);
        }
    }
    mp_hal_uart_tx(&errcode, sizeof(errcode));
}

static void cmd_rmdir(ide_dbg_state_t* state) {
    uint32_t errcode;
    char path[USBDBG_MAX_PATH_LEN + 1];
    char filepath[USBDBG_MAX_PATH_LEN + 64];

    if (!read_path_nt(state, path, sizeof(path))) {
        errcode = USBDBG_SVFILE_ERR_INVALID_PATH;
    } else if (!resolve_filepath(path, filepath, sizeof(filepath))) {
        errcode = USBDBG_SVFILE_ERR_INVALID_PATH;
    } else {
        close_active_sv_file();
        if (rmdir(filepath) == 0) {
            errcode = USBDBG_SVFILE_ERR_NONE;
        } else {
            errcode = file_errno_to_usbdbg(errno);
        }
    }
    mp_hal_uart_tx(&errcode, sizeof(errcode));
}

static uint32_t remove_tree(const char *path) {
    struct stat st;
    if (lstat(path, &st) != 0) {
        return file_errno_to_usbdbg(errno);
    }
    if (!S_ISDIR(st.st_mode)) {
        return (unlink(path) == 0) ? USBDBG_SVFILE_ERR_NONE
                                  : file_errno_to_usbdbg(errno);
    }

    DIR *dir = opendir(path);
    if (dir == NULL) {
        return file_errno_to_usbdbg(errno);
    }

    uint32_t errcode = USBDBG_SVFILE_ERR_NONE;
    struct dirent *entry;
    errno = 0;
    while ((entry = readdir(dir)) != NULL) {
        if (strcmp(entry->d_name, ".") == 0 || strcmp(entry->d_name, "..") == 0) {
            continue;
        }
        char child[USBDBG_MAX_PATH_LEN + 64];
        int n = snprintf(child, sizeof(child), "%s/%s", path, entry->d_name);
        if (n < 0 || (size_t)n >= sizeof(child)) {
            errcode = USBDBG_SVFILE_ERR_INVALID_PATH;
            break;
        }
        errcode = remove_tree(child);
        if (errcode != USBDBG_SVFILE_ERR_NONE) {
            break;
        }
        errno = 0;
    }
    if (errcode == USBDBG_SVFILE_ERR_NONE && errno != 0) {
        errcode = file_errno_to_usbdbg(errno);
    }
    if (closedir(dir) != 0 && errcode == USBDBG_SVFILE_ERR_NONE) {
        errcode = file_errno_to_usbdbg(errno);
    }

    if (errcode == USBDBG_SVFILE_ERR_NONE && rmdir(path) != 0) {
        errcode = file_errno_to_usbdbg(errno);
    }
    return errcode;
}

static void cmd_rmdir_recursive(ide_dbg_state_t* state) {
    uint32_t errcode;
    char path[USBDBG_MAX_PATH_LEN + 1];
    char filepath[USBDBG_MAX_PATH_LEN + 64];

    if (!read_path_nt(state, path, sizeof(path)) ||
        !resolve_filepath(path, filepath, sizeof(filepath))) {
        errcode = USBDBG_SVFILE_ERR_INVALID_PATH;
    } else if (!((strncmp(filepath, "/sdcard/", 8) == 0 && filepath[8] != '\0' && filepath[8] != '/') ||
               (strncmp(filepath, "/data/", 6) == 0 && filepath[6] != '\0' && filepath[6] != '/') ||
               (strncmp(filepath, "/udisk/", 7) == 0 && filepath[7] != '\0' && filepath[7] != '/'))) {
        errcode = USBDBG_SVFILE_ERR_PERM_DENIED;
    } else {
        close_active_sv_file();
        errcode = remove_tree(filepath);
    }
    mp_hal_uart_tx(&errcode, sizeof(errcode));
}

static void file_exec_error(const char *fmt, ...) {
    char buf[256];
    va_list va;
    va_start(va, fmt);
    int n = vsnprintf(buf, sizeof(buf), fmt, va);
    va_end(va);
    if (n > 0) {
        size_t len = (size_t)n;
        if (len >= sizeof(buf)) {
            len = sizeof(buf) - 1;
        }
        ide_dbg_stdout_tx(buf, len);
    }
}

static void cmd_file_exec(ide_dbg_state_t* state) {
    char path[USBDBG_MAX_PATH_LEN + 1];
    char filepath[USBDBG_MAX_PATH_LEN + 64];

    if (!read_path_nt(state, path, sizeof(path)) ||
        !resolve_filepath(path, filepath, sizeof(filepath)))
        return;

    if (ide_dbg_is_script_running()) {
        file_exec_error("FILE_EXEC ERROR: script already running\n");
        return;
    }

    exec_payload = strdup(filepath);
    if (exec_payload == NULL) {
        file_exec_error("FILE_EXEC ERROR: out of memory\n");
        return;
    }
    ide_dbg_queue_script(exec_payload, EXEC_FILE);
}

static bool ide_dbg_cmd_known(uint8_t cmd) {
    switch ((enum usbdbg_cmd)cmd) {
        case USBDBG_NONE:
        case USBDBG_FW_VERSION:
        case USBDBG_FRAME_SIZE:
        case USBDBG_FRAME_DUMP:
        case USBDBG_ARCH_STR:
        case USBDBG_SCRIPT_EXEC:
        case USBDBG_SCRIPT_STOP:
        case USBDBG_SCRIPT_SAVE:
        case USBDBG_SCRIPT_RUNNING:
        case USBDBG_TEMPLATE_SAVE:
        case USBDBG_DESCRIPTOR_SAVE:
        case USBDBG_ATTR_READ:
        case USBDBG_ATTR_WRITE:
        case USBDBG_SYS_RESET:
        case USBDBG_FB_ENABLE:
        case USBDBG_QUERY_STATUS:
        case USBDBG_TX_BUF_LEN:
        case USBDBG_TX_BUF:
        case USBDBG_SENSOR_ID:
        case USBDBG_FW_VERSION_FULL:
        case USBDBG_TX_INPUT:
        case USBDBG_SET_TIME:
        case USBDBG_CREATEFILE:
        case USBDBG_WRITEFILE:
        case USBDBG_QUERY_FILE_STAT:
        case USBDBG_VERIFYFILE:
        case USBDBG_LIST_DIR:
        case USBDBG_READ_FILE:
        case USBDBG_DELETE_FILE:
        case USBDBG_RENAME_FILE:
        case USBDBG_MKDIR:
        case USBDBG_RMDIR:
        case USBDBG_FILE_EXEC:
        case USBDBG_QUERY_FILE_STAT2:
        case USBDBG_CREATEFILE2:
        case USBDBG_WRITEFILE2:
        case USBDBG_SCRIPT_STATUS:
        case USBDBG_CAPABILITIES:
        case USBDBG_VTOUCH_EVENT:
        case USBDBG_VTOUCH_STATUS:
        case USBDBG_RMDIR_RECURSIVE:
            return true;
        default:
            return false;
    }
}

static bool ide_dbg_frame_header_valid(const uint8_t header[6]) {
    if (header[0] != 0x30 || !ide_dbg_cmd_known(header[1])) {
        return false;
    }

    uint32_t data_length = 0;
    hal_rvv_memcpy(&data_length, header + 2, sizeof(data_length));
    return data_length <= IDE_DBG_MAX_FRAME_PAYLOAD;
}

typedef struct {
    uint8_t pending[6];
    size_t pending_len;
} ide_dbg_rx_router_t;

static void ide_dbg_frame_state_reset(ide_dbg_state_t *state) {
    hal_rvv_memset(state, 0, sizeof(*state));
    state->state = FRAME_HEAD;
}

static void ide_dbg_protocol_fsm_recover(ide_dbg_state_t *state, ide_dbg_rx_router_t *router,
                                         const char *reason) {
    enum frame_state failed_state = state->state;
    enum usbdbg_cmd failed_cmd = state->cmd;

    close_active_sv_file();
    svfile_release_chunk_buffer();
    hal_rvv_memset(&ide_dbg_sv_file.info, 0, sizeof(ide_dbg_sv_file.info));
    ide_dbg_sv_file.errcode = USBDBG_SVFILE_ERR_CHUNK_ERR;
    listdir_page_reset();
    if (router != NULL) {
        router->pending_len = 0;
    }
    ide_dbg_rx_incomplete = false;
    ide_dbg_frame_state_reset(state);

    pr_warn("[ide] protocol FSM recovered: reason=%s state=%d cmd=0x%02x",
            reason, failed_state, failed_cmd);
}

static ide_dbg_status_t ide_dbg_update(ide_dbg_state_t* state, const uint8_t* data, size_t length);

static void ide_dbg_route_repl(const uint8_t *data, size_t size) {
    if (size == 0) {
        return;
    }

    ide_dbg_stdout_raw_input();
    pr_verb("[uart] repl %zu bytes", size);
    print_raw(data, size);
    mp_hal_stdin_push(data, size);
}

static void ide_dbg_route_pending_flush(ide_dbg_rx_router_t *router) {
    if (router->pending_len == 0) {
        return;
    }
    ide_dbg_route_repl(router->pending, router->pending_len);
    router->pending_len = 0;
}

static void ide_dbg_route_protocol_start(ide_dbg_rx_router_t *router, ide_dbg_state_t *state,
                                         const uint8_t *rest, size_t rest_len) {
    size_t frame_len = router->pending_len + rest_len;
    uint8_t *frame = malloc(frame_len);
    if (frame == NULL) {
        ide_dbg_route_repl(router->pending, router->pending_len);
        ide_dbg_route_repl(rest, rest_len);
        router->pending_len = 0;
        return;
    }

    hal_rvv_memcpy(frame, router->pending, router->pending_len);
    if (rest_len > 0) {
        hal_rvv_memcpy(frame + router->pending_len, rest, rest_len);
    }
    router->pending_len = 0;
    ide_dbg_stdout_protocol_attach();
    ide_dbg_set_attached(true);
    if (ide_dbg_repl_script_running()) {
        ide_dbg_request_soft_reset();
    }
    ide_dbg_update(state, frame, frame_len);
    free(frame);
}

static void ide_dbg_route_bytes(ide_dbg_rx_router_t *router, ide_dbg_state_t *state,
                                const uint8_t *data, size_t size) {
    if (ide_dbg_attach()) {
        ide_dbg_route_pending_flush(router);
        ide_dbg_update(state, data, size);
        return;
    }

    for (size_t i = 0; i < size; i++) {
        uint8_t byte = data[i];

        if (router->pending_len == 0 && byte != 0x30) {
            ide_dbg_route_repl(&byte, 1);
            continue;
        }

        router->pending[router->pending_len++] = byte;
        if (router->pending_len < sizeof(router->pending)) {
            continue;
        }

        if (ide_dbg_frame_header_valid(router->pending)) {
            ide_dbg_route_protocol_start(router, state, data + i + 1, size - i - 1);
            return;
        }

        ide_dbg_route_repl(router->pending, router->pending_len);
        router->pending_len = 0;
    }
}

static void cmd_capabilities(ide_dbg_state_t* state) {
    (void)state;
    uint32_t resp[2] = {
        (uint32_t)USBDBG_CAP_PROTOCOL_VERSION,
        (uint32_t)(USBDBG_CAP_LIST_DIR | USBDBG_CAP_READ_FILE |
                    USBDBG_CAP_WRITE_FILE | USBDBG_CAP_DELETE_FILE |
                    USBDBG_CAP_RENAME_FILE | USBDBG_CAP_MKDIR |
                    USBDBG_CAP_RMDIR | USBDBG_CAP_FILE_EXEC |
                    USBDBG_CAP_VIRTUAL_TOUCH | USBDBG_CAP_REPL_INPUT |
                    USBDBG_CAP_LIST_DIR_PAGED | USBDBG_CAP_RMDIR_RECURSIVE)
    };
    mp_hal_uart_tx(resp, sizeof(resp));
}

static void cmd_vtouch_status(ide_dbg_state_t* state) {
    (void)state;
    struct ide_dbg_vtouch_info info;

    ide_dbg_vtouch_status(&info);
    mp_hal_uart_tx(&info, sizeof(info));
}

static void cmd_vtouch_event(ide_dbg_state_t* state) {
    struct ide_dbg_vtouch_event event = {0};
    uint32_t payload_len = state->data_length;

    if (payload_len != sizeof(event)) {
        if (payload_len > 0) {
            discard_from_frame(state, payload_len);
        }
        return;
    }

    if (read_from_frame(state, &event, sizeof(event)) != sizeof(event)) {
        return;
    }
    (void)ide_dbg_vtouch_enqueue(&event);
}

static bool read_fb_enable_legacy_inline(ide_dbg_state_t* state, uint8_t *enable) {
    if (state->frame_offset + 2 > state->frame_length) {
        return false;
    }
    uint8_t lo = state->frame_data[state->frame_offset];
    uint8_t hi = state->frame_data[state->frame_offset + 1];
    if (hi != 0 || (lo != 0 && lo != 1)) {
        return false;
    }
    *enable = lo;
    state->frame_offset += 2;
    return true;
}

static void cmd_fb_enable(ide_dbg_state_t* state) {
    uint8_t enable = 0;
    if (state->data_length > 0) {
        if (read_from_frame(state, &enable, 1) != 1) {
            return;
        }
        if (state->data_length > 1) {
            discard_from_frame(state, state->data_length - 1);
        }
        enable_pic = enable;
    } else if (read_fb_enable_legacy_inline(state, &enable)) {
        enable_pic = enable;
    }
    if (!enable_pic) {
        ide_dbg_clear_fb(true);
    }
    pr_verb("cmd: USBDBG_FB_ENABLE, enable(%u)", enable_pic);
}

///////////////////////////////////////////////////////////////////////////////
// IDE protocol parser ////////////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////////////

static ide_dbg_status_t ide_dbg_update(ide_dbg_state_t* state, const uint8_t* data, size_t length) {
    pr_dbg("update: len=%zu script_running=%u", length, ide_dbg_script_running());
    print_raw(data, length > 32 ? 32 : length);
    for (size_t i = 0; i < length;) {
        switch (state->state) {
            case FRAME_HEAD:
                if (data[i] == 0x30) {
                    state->state = FRAME_CMD;
                } else {
                    pr_dbg("FRAME_HEAD: skip byte 0x%02X at pos %zu", data[i], i);
                }
                i += 1;
                break;
            case FRAME_CMD:
                state->cmd = data[i];
                state->state = FRAME_DATA_LENGTH;
                pr_dbg("FRAME_CMD: cmd=0x%02X", state->cmd);
                i += 1;
                break;
            case FRAME_DATA_LENGTH:
                // recv 4 bytes
                state->recv_lack = 4;
                state->state = FRAME_RECV;
                state->recv_next = FRAME_DISPATCH;
                state->recv_data = &state->data_length;
                break;
            case FRAME_DISPATCH:
                state->frame_data = data;
                state->frame_length = length;
                state->frame_offset = i + 1;
                pr_dbg("DISPATCH cmd=0x%02X data_length=%u script_running=%u",
                       state->cmd, state->data_length, ide_dbg_script_running());
                switch (state->cmd) {
                    case USBDBG_NONE:
                        break;
                    case USBDBG_QUERY_STATUS: {
                        pr_dbg("cmd: USBDBG_QUERY_STATUS -> 0xFFEEBBAA");
                        uint32_t resp = 0xFFEEBBAA;
                        mp_hal_uart_tx(&resp, sizeof(resp));
                        break;
                    }
                    case USBDBG_FW_VERSION: {
                        pr_verb("cmd: USBDBG_FW_VERSION");
                        uint32_t resp[3] = {
                            FIRMWARE_VERSION_MAJOR,
                            FIRMWARE_VERSION_MINOR,
                            FIRMWARE_VERSION_MICRO
                        };
                        mp_hal_uart_tx(&resp, sizeof(resp));
                        break;
                    }
                    case USBDBG_FW_VERSION_FULL: {
                        pr_verb("cmd: USBDBG_FW_VERSION_FULL");
                        // Send git version string like "v1.0-45-g<full-hash>"
                        char ver_buf[128] = {0};
                        snprintf(ver_buf, sizeof(ver_buf), "%s-%s", MICROPY_HW_MCU_NAME, CANMV_VER_FULL);
                        mp_hal_uart_tx(ver_buf, sizeof(ver_buf));
                        break;
                    }
                    case USBDBG_ARCH_STR:
                        cmd_arch_str(state);
                        break;
                    case USBDBG_SCRIPT_EXEC:
                        cmd_script_exec(state);
                        break;
                    case USBDBG_SCRIPT_STOP: {
                        // TODO
                        pr_verb("cmd: USBDBG_SCRIPT_STOP");
                        if (ide_dbg_is_script_running()) {
                            ide_dbg_request_soft_reset();
                        }
                        break;
                    }
                    case USBDBG_SCRIPT_SAVE: {
                        // TODO
                        pr_verb("cmd: USBDBG_SCRIPT_SAVE");
                        break;
                    }
                    case USBDBG_TX_INPUT:
                        pr_dbg("[ide] dispatch USBDBG_TX_INPUT");
                        cmd_tx_input(state);
                        break;
                    case USBDBG_QUERY_FILE_STAT: {
                        pr_verb("cmd: USBDBG_QUERY_FILE_STAT");
                        mp_hal_uart_tx(&ide_dbg_sv_file.errcode, sizeof(ide_dbg_sv_file.errcode));
                        break;
                    }
                    case USBDBG_QUERY_FILE_STAT2:
                        cmd_query_file_stat(state);
                        break;
                    case USBDBG_WRITEFILE:
                        cmd_writefile(state);
                        break;
                    case USBDBG_WRITEFILE2:
                        cmd_writefile_ack(state);
                        break;
                    case USBDBG_VERIFYFILE:
                        cmd_verifyfile();
                        break;
                    case USBDBG_CREATEFILE:
                        cmd_createfile(state);
                        break;
                    case USBDBG_CREATEFILE2:
                        cmd_createfile_ack(state);
                        break;
                    case USBDBG_LIST_DIR:
                        cmd_listdir(state);
                        break;
                    case USBDBG_READ_FILE:
                        cmd_readfile(state);
                        break;
                    case USBDBG_DELETE_FILE:
                        cmd_deletefile(state);
                        break;
                    case USBDBG_RENAME_FILE:
                        cmd_renamefile(state);
                        break;
                    case USBDBG_MKDIR:
                        cmd_mkdir(state);
                        break;
                    case USBDBG_RMDIR:
                        cmd_rmdir(state);
                        break;
                    case USBDBG_RMDIR_RECURSIVE:
                        cmd_rmdir_recursive(state);
                        break;
                    case USBDBG_FILE_EXEC:
                        cmd_file_exec(state);
                        break;
                    case USBDBG_CAPABILITIES:
                        cmd_capabilities(state);
                        break;
                    case USBDBG_VTOUCH_STATUS:
                        cmd_vtouch_status(state);
                        break;
                    case USBDBG_VTOUCH_EVENT:
                        cmd_vtouch_event(state);
                        break;
                    case USBDBG_SCRIPT_RUNNING: {
                        uint32_t running = ide_dbg_script_running();
                        pr_dbg("cmd: USBDBG_SCRIPT_RUNNING -> %u", running);
                        mp_hal_uart_tx(&running, sizeof(running));
                        break;
                    }
                    case USBDBG_SCRIPT_STATUS: {
                        uint32_t running = ide_dbg_is_script_running() ? 1 : 0;
                        pr_dbg("cmd: USBDBG_SCRIPT_STATUS -> %u", running);
                        mp_hal_uart_tx(&running, sizeof(running));
                        break;
                    }
                    case USBDBG_TX_BUF_LEN: {
                        pthread_mutex_lock(&tx_buf_mutex);
                        uint32_t len = tx_buf_readable();
                        pr_dbg("cmd: USBDBG_TX_BUF_LEN -> %u", len);
                        mp_hal_uart_tx((void*)&len, sizeof(len));
                        pthread_mutex_unlock(&tx_buf_mutex);
                        break;
                    }
                    case USBDBG_TX_BUF: {
                        pthread_mutex_lock(&tx_drain_mutex);
                        pthread_mutex_lock(&tx_buf_mutex);
                        uint32_t len = tx_buf_readable();
                        if (len > state->data_length) {
                            len = state->data_length;
                        }
                        pr_dbg("cmd: USBDBG_TX_BUF drain %u (requested %u)", len, state->data_length);
                        tx_buf_drain(len, true);
                        pthread_mutex_unlock(&tx_buf_mutex);
                        pthread_mutex_unlock(&tx_drain_mutex);
                        break;
                    }
                    case USBDBG_FRAME_SIZE:
                        pr_dbg("cmd: USBDBG_FRAME_SIZE");
                        cmd_frame_size();
                        break;
                    case USBDBG_FRAME_DUMP:
                        pr_dbg("cmd: USBDBG_FRAME_DUMP");
                        cmd_frame_dump();
                        break;
                    case USBDBG_SYS_RESET: {
                        // TODO: reset serialport to REPL mode
                        pr_verb("cmd: USBDBG_SYS_RESET");
                        ide_dbg_clear_fb(true);
                        if (ide_dbg_is_script_running()) {
                            ide_dbg_set_disconnect(true);
                            ide_dbg_request_soft_reset();
                        } else {
                            ide_dbg_interrupt();
                        }
                        break;
                    }
                    case USBDBG_FB_ENABLE: {
                        cmd_fb_enable(state);
                        break;
                    }
                    default:
                        // unknown command
                        pr_verb("unknown command %02x", state->cmd);
                        break;
                }
                size_t next_offset = state->frame_offset;
                if (ide_dbg_rx_incomplete) {
                    ide_dbg_protocol_fsm_recover(state, NULL, "incomplete command payload");
                } else {
                    ide_dbg_frame_state_reset(state);
                }
                i = (next_offset > i + 1) ? next_offset : i + 1;
                break;
            case FRAME_RECV: {
                size_t avail = length - i;
                if (avail >= state->recv_lack) {
                    hal_rvv_memcpy(state->recv_data, data + i, state->recv_lack);
                    state->state = state->recv_next;
                    state->recv_data = NULL;
                    /* Advance by recv_lack - 1: the next state (FRAME_DISPATCH)
                       will do i += 1, so total advancement = recv_lack. */
                    i += state->recv_lack - 1;
                    state->recv_lack = 0;
                } else {
                    hal_rvv_memcpy(state->recv_data, data + i, avail);
                    state->recv_data = (uint8_t*)state->recv_data + avail;
                    state->recv_lack -= avail;
                    i = length;
                }
                break;
            }
            default:
                ide_dbg_protocol_fsm_recover(state, NULL, "invalid parser state");
                break;
        }
    }
    return IDE_DBG_STATUS_OK;
}

///////////////////////////////////////////////////////////////////////////////
// IDE task & init ////////////////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////////////

void ide_before_python_run(int input_kind, mp_uint_t exec_flags)
{
    // mp_hal_stdio_mode_orig();
    ide_dbg_set_repl_script_running(true);
}

void ide_afer_python_run(int input_kind, mp_uint_t exec_flags, void *ret_val, int ret)
{
    ide_dbg_set_repl_script_running(false);
}

static void* ide_dbg_task(void* args) {
    ide_dbg_state_t state = { .state = FRAME_HEAD };
    ide_dbg_rx_router_t router = {0};
    uint64_t last_protocol_rx_ms = mp_hal_ticks_ms();
    static uint8_t read_buf[512];
    pthread_setcanceltype(PTHREAD_CANCEL_ASYNCHRONOUS, NULL);
    struct sched_param param;
    // RT-Smart uses lower numeric values for higher priorities. Keep the IDE
    // task above the MicroPython main thread (priority 25) so it can deliver a
    // stop request while Python is executing a CPU-bound loop.
    param.sched_priority = 20;
    int sched_error = pthread_setschedparam(pthread_self(), SCHED_FIFO, &param);
    if (sched_error != 0) {
        pr_warn("[ide] pthread_setschedparam failed: %d", sched_error);
    }
    while (1) {
        drv_uart_inst_t *inst = mp_hal_uart_get_instance();
        if (inst == NULL) {
            if (state.state != FRAME_HEAD) {
                ide_dbg_protocol_fsm_recover(&state, &router, "UART unavailable");
            }
            usleep(100000);
            continue;
        }

        // Poll UART for data (200ms timeout)
        int result = drv_uart_poll(inst, 200);
        if (result == 0) {
            if (state.state != FRAME_HEAD &&
                mp_hal_ticks_ms() - last_protocol_rx_ms >= IDE_DBG_FRAME_IDLE_TIMEOUT_MS) {
                ide_dbg_protocol_fsm_recover(&state, &router, "incomplete frame timeout");
            }
            ide_dbg_route_pending_flush(&router);
            continue;
        } else if (result < 0) {
            // Some USB CDC drivers report a transient poll error while no RX
            // data is available. Only a confirmed DTR drop is a disconnect.
            int dtr = drv_uart_is_dtr_asserted(inst);
            pr_verb("[uart] poll error %d, DTR %d", result, dtr);
            if (dtr == 0) {
                if (ide_dbg_attach()) {
                    ide_dbg_protocol_fsm_recover(&state, &router, "host disconnected");
                    ide_dbg_disconnect_and_soft_reset();
                } else if (state.state != FRAME_HEAD) {
                    ide_dbg_protocol_fsm_recover(&state, &router, "UART receive error");
                }
            } else if (state.state != FRAME_HEAD &&
                       mp_hal_ticks_ms() - last_protocol_rx_ms >= IDE_DBG_FRAME_IDLE_TIMEOUT_MS) {
                ide_dbg_protocol_fsm_recover(&state, &router, "incomplete frame poll timeout");
            }
            usleep(100000);
            continue;
        }
        ssize_t size = drv_uart_read(inst, read_buf, sizeof(read_buf));
        if (size == 0) {
            continue;
        } else if (size < 0) {
            pr_err("[uart] read error");
            ide_dbg_protocol_fsm_recover(&state, &router, "UART read error");
        } else {
            last_protocol_rx_ms = mp_hal_ticks_ms();
            ide_dbg_route_bytes(&router, &state, read_buf, size);
        }
    }
    return NULL;
}

void ide_dbg_start(void) {
    pr_info("IDE debugger built %s %s", __DATE__, __TIME__);

    canmv_misc_dev_ioctl(MISC_DEV_CMD_GET_MEMORY_SIZE, &sys_mem_total_size);

    if (mp_hal_uart_get_instance() == NULL) {
        pr_err("ide_dbg_init: UART not initialized");
        return;
    }

    if (sem_init(&script_sem, 0, 0) != 0) {
        pr_err("sem_init(script_sem) failed: %s", strerror(errno));
        return;
    }
    ide_exception_str.data = (const byte*)"IDE interrupt";
    ide_exception_str.len  = 13;
    ide_exception_str.base.type = &mp_type_str;
    ide_exception_str.hash = qstr_compute_hash(ide_exception_str.data, ide_exception_str.len);
    ide_exception_str_tuple = (mp_obj_tuple_t*)malloc(sizeof(mp_obj_tuple_t)+sizeof(mp_obj_t)*1);
    if(ide_exception_str_tuple==NULL) {
        sem_destroy(&script_sem);
        return;
    }
    ide_exception_str_tuple->base.type = &mp_type_tuple;
    ide_exception_str_tuple->len = 1;
    ide_exception_str_tuple->items[0] = MP_OBJ_FROM_PTR(&ide_exception_str);
    MP_STATE_PORT(ide_exception).base.type = &mp_type_Exception;
    MP_STATE_PORT(ide_exception).traceback_alloc = 0;
    MP_STATE_PORT(ide_exception).traceback_len = 0;
    MP_STATE_PORT(ide_exception).traceback_data = NULL;
    MP_STATE_PORT(ide_exception).args = ide_exception_str_tuple;
    int create_error = pthread_create(&ide_dbg_task_p, NULL, ide_dbg_task, NULL);
    if (create_error != 0) {
        pr_err("pthread_create(ide_dbg_task) failed: %s", strerror(create_error));
        free(ide_exception_str_tuple);
        ide_exception_str_tuple = NULL;
        sem_destroy(&script_sem);
    }
}

#else
#endif
