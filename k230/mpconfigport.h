// Options to control how MicroPython is built for this port,
// overriding defaults in py/mpconfig.h.

#include <stdint.h>
#include <stdlib.h>

#include "generated/autoconf.h"

// Board-specific definitions
#include "mpconfigboard.h"

#ifndef MICROPY_CONFIG_ROM_LEVEL
#define MICROPY_CONFIG_ROM_LEVEL                (MICROPY_CONFIG_ROM_LEVEL_EXTRA_FEATURES)
#endif

/*****************************************************************************/
/* Object representation                                                     */
#define MICROPY_OBJ_REPR                        (MICROPY_OBJ_REPR_C)

/*****************************************************************************/
/* Memory allocation policy                                                  */
#define MICROPY_ALLOC_PATH_MAX                  (128)

/*****************************************************************************/
/* Internal debugging stuff                                                  */
#define MICROPY_MEM_STATS                       (0)
#define MICROPY_DEBUG_PRINTERS                  (1)
#define MICROPY_DEBUG_PRINTER                   (&mp_stdout_print)

/*****************************************************************************/
/* Optimisations                                                             */
#define MICROPY_OPT_COMPUTED_GOTO               (1)

/*****************************************************************************/
/* Python internal features                                                  */
#define MICROPY_READER_POSIX                    (1)
#define MICROPY_ENABLE_GC                       (1)
#define MICROPY_STACK_CHECK                     (1)
#define MICROPY_STACK_CHECK_MARGIN              (1024)
#define MICROPY_ENABLE_EMERGENCY_EXCEPTION_BUF  (1)
#define MICROPY_LONGINT_IMPL                    (MICROPY_LONGINT_IMPL_MPZ)
#define MICROPY_ERROR_REPORTING                 (MICROPY_ERROR_REPORTING_NORMAL)
#define MICROPY_WARNINGS                        (1)
#define MICROPY_FLOAT_IMPL                      (MICROPY_FLOAT_IMPL_FLOAT)
#define MICROPY_TIMESTAMP_IMPL                  (MICROPY_TIMESTAMP_IMPL_TIME_T)
#define MICROPY_STREAMS_POSIX_API               (1)
#define MICROPY_USE_INTERNAL_ERRNO              (0)
#define MICROPY_USE_INTERNAL_PRINTF             (0)
#define MICROPY_SCHEDULER_DEPTH                 (8)
#define MICROPY_VFS                             (1)
#define MICROPY_VFS_POSIX                       (1)
#define MICROPY_READER_VFS                      (1)

/*****************************************************************************/
/* Fine control over Python builtins, classes, modules, etc                  */

#define MICROPY_PY_STR_BYTES_CMP_WARN           (1)
#define MICROPY_PY_TIME                         (1)
#define MICROPY_PY_TIME_INCLUDEFILE             "core/modtime.c"
#define MICROPY_PY_SYS_STDFILES                 (0)
#define MICROPY_PY_TIME_GMTIME_LOCALTIME_MKTIME (1)
#define MICROPY_PY_TIME_TIME_TIME_NS            (1)

#define MICROPY_PY_THREAD                       (1)
#define MICROPY_PY_THREAD_GIL                   (1)
#define MICROPY_PY_THREAD_RECURSIVE_MUTEX       (1)

#define MICROPY_PY_RE_MATCH_GROUPS              (1)
#define MICROPY_PY_RE_MATCH_SPAN_START_END      (1)

#define MICROPY_PY_OS                           (1)
#define MICROPY_PY_OS_INCLUDEFILE               "core/modos.c"
#define MICROPY_PY_OS_UNAME                     (1)
#define MICROPY_PY_OS_ERRNO                     (1)
#define MICROPY_PY_OS_DUPTERM                   (1)
#define MICROPY_PY_OS_DUPTERM_NOTIFY            (1)
#define MICROPY_PY_OS_URANDOM                   (1)
#define MICROPY_PY_OS_GETENV_PUTENV_UNSETENV    (1)

#define MICROPY_PY_HASHLIB_MD5                  (1)
#define MICROPY_PY_HASHLIB_SHA1                 (1)
#define MICROPY_PY_CRYPTOLIB                    (1)
#define MICROPY_PY_CRYPTOLIB_CTR                (1)
#define MICROPY_PY_CRYPTOLIB_CONSTS             (1)

#define MICROPY_PY_MACHINE                      (1)
#define MICROPY_PY_MACHINE_PIN_MAKE_NEW         machine_pin_make_new
#define MICROPY_PY_MACHINE_INCLUDEFILE          "machine/modmachine.c"
#define MICROPY_PY_MACHINE_BARE_METAL_FUNCS     (1)
#define MICROPY_PY_MACHINE_BOOTLOADER           (1)
#define MICROPY_PY_MACHINE_RESET                (1)
#define MICROPY_PY_MACHINE_DISABLE_IRQ_ENABLE_IRQ   (1)
#define MICROPY_PY_MACHINE_BITSTREAM            (1)
#define MICROPY_PY_MACHINE_DHT_READINTO         (1)
#define MICROPY_PY_MACHINE_PULSE                (1)
#define MICROPY_PY_MACHINE_SIGNAL               (1)
// #define MICROPY_PY_MACHINE_SOFTI2C              (1)
// #define MICROPY_PY_MACHINE_SOFTSPI              (1)
// #define MICROPY_PY_MACHINE_ADC                  (1)
// #define MICROPY_PY_MACHINE_ADC_BLOCK            (1)
// #define MICROPY_PY_MACHINE_DAC                  (1)
// #define MICROPY_PY_MACHINE_I2C                  (1)
// #define MICROPY_PY_MACHINE_I2S                  (1)
#define MICROPY_PY_MACHINE_PWM                  (1)
#define MICROPY_PY_MACHINE_PWM_INCLUDEFILE      "machine/machine_pwm.c"
#define MICROPY_PY_MACHINE_PWM_DUTY             (1)
// #define MICROPY_PY_MACHINE_SPI                  (1)
// #define MICROPY_PY_MACHINE_UART                 (1)
// #define MICROPY_HW_ENABLE_USB_RUNTIME_DEVICE    (1)
#define MICROPY_PY_MACHINE_WDT                  (1)
#define MICROPY_PY_MACHINE_WDT_INCLUDEFILE      "machine/machine_wdt.c"
#define MICROPY_PY_MACHINE_WDT_TIMEOUT_MS       (1)
// #define MICROPY_PY_MACHINE_TIMER            (1)

// #define MICROPY_PY_NETWORK                      (1)
// #define MICROPY_PY_NETWORK_INCLUDEFILE          (1)

// #define MICROPY_PY_ONEWIRE                      (1)

#define MICROPY_PY_SSL                          (1)
#define MICROPY_SSL_MBEDTLS                     (1)
// #define MICROPY_PY_WEBSOCKET                (1)

#define MICROPY_PORT_BUILTINS
#define MICROPY_PORT_EXTRA_BUILTINS
#define MICROPY_PORT_CONSTANTS

/*****************************************************************************/
/* Miscellaneous settings                                                    */
#define MICROPY_BANNER_NAME_AND_VERSION "MicroPython " MICROPY_GIT_TAG " on " MICROPY_BUILD_DATE

/*****************************************************************************/
/* K230 port settings                                                        */
#define MP_STATE_PORT MP_STATE_VM

#define MICROPY_GC_HEAP_SIZE (4 * 1024 * 1024)

#define UINT_FMT "%u"
#define INT_FMT  "%d"

typedef long          mp_int_t; // must be pointer size
typedef unsigned long mp_uint_t; // must be pointer size
typedef long long     mp_off_t;
// ssize_t, off_t as required by POSIX-signatured functions in stream.h
#include <sys/types.h>

// board specifics
#define MICROPY_PY_SYS_PLATFORM                     "k230"

#if MICROPY_PY_THREAD
#define MICROPY_EVENT_POLL_HOOK                                                                                                \
    do {                                                                                                                       \
        extern void mp_handle_pending(bool);                                                                                   \
        mp_handle_pending(true);                                                                                               \
        MP_THREAD_GIL_EXIT();                                                                                                  \
        usleep(1000);                                                                                                          \
        MP_THREAD_GIL_ENTER();                                                                                                 \
    } while (0);
#else
#define MICROPY_EVENT_POLL_HOOK                                                                                                \
    do {                                                                                                                       \
        extern void mp_handle_pending(bool);                                                                                   \
        mp_handle_pending(true);                                                                                               \
        usleep(1000);                                                                                                          \
    } while (0);
#endif

// The minimum string length threshold for string printing to stdout operations to be GIL-aware.
#ifndef MICROPY_PY_STRING_TX_GIL_THRESHOLD
#define MICROPY_PY_STRING_TX_GIL_THRESHOLD      (50)
#endif
