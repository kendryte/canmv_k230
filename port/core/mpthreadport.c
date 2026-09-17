/*
 * This file is part of the MicroPython project, http://micropython.org/
 *
 * The MIT License (MIT)
 *
 * Copyright (c) 2016 Damien P. George on behalf of Pycom Ltd
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <sched.h>
#include <semaphore.h>

#include "py/gc.h"
#include "py/mpthread.h"
#include "py/runtime.h"
#include "shared/runtime/gchelper.h"

#if MICROPY_PY_THREAD

#define THREAD_DEFAULT_STACK_SIZE    (CONFIG_RTSMART_LWP_APP_STACK_SIZE)
#define THREAD_MAIN_STACK_MARGIN     (1024)
#define THREAD_STACK_OVERFLOW_MARGIN (8192)
#define THREAD_MIN_STACK_SIZE        (2 * THREAD_STACK_OVERFLOW_MARGIN)
#define THREAD_GIL_YIELD_INTERVAL    (8)

typedef struct _mp_thread_entry_t {
    pthread_t                  id;
    mp_state_thread_t*         state;
    void*                      entry_arg;
    mp_obj_t                   startup_exception;
#if MICROPY_PY_THREAD_GIL
    gc_helper_regs_t           gc_regs;
    bool                       gc_regs_valid;
#endif
    size_t                     stack_limit;
    bool                       ready;
    struct _mp_thread_entry_t* next;
} mp_thread_entry_t;

static pthread_key_t tls_key;

static pthread_mutex_t    thread_list_mutex;
static pthread_once_t     thread_list_mutex_once = PTHREAD_ONCE_INIT;
static sem_t              thread_finished_sem;
static mp_thread_entry_t  main_thread;
static mp_thread_entry_t* thread_list;
static bool               deinit_waiting;

#if MICROPY_PY_THREAD_GIL
static unsigned int active_thread_count;
static unsigned int gil_yield_count;
#endif

static void thread_fatal_error(const char* operation, int error)
{
    fprintf(stderr, "[mpthread] %s failed: %d\n", operation, error);
    abort();
}

static void thread_check_error(const char* operation, int error)
{
    if (error != 0) {
        thread_fatal_error(operation, error);
    }
}

static bool thread_id_equal(pthread_t lhs, pthread_t rhs) { return pthread_equal(lhs, rhs) != 0; }

static void thread_list_mutex_init_once(void)
{
    pthread_mutexattr_t mutex_attr;

    thread_check_error("pthread_mutexattr_init", pthread_mutexattr_init(&mutex_attr));
    thread_check_error("pthread_mutexattr_settype", pthread_mutexattr_settype(&mutex_attr, PTHREAD_MUTEX_RECURSIVE));
    thread_check_error("pthread_mutex_init", pthread_mutex_init(&thread_list_mutex, &mutex_attr));
    thread_check_error("pthread_mutexattr_destroy", pthread_mutexattr_destroy(&mutex_attr));
}

static void thread_list_lock(void)
{
    thread_check_error("pthread_once", pthread_once(&thread_list_mutex_once, thread_list_mutex_init_once));
    thread_check_error("pthread_mutex_lock", pthread_mutex_lock(&thread_list_mutex));
}

static void thread_list_unlock(void) { thread_check_error("pthread_mutex_unlock", pthread_mutex_unlock(&thread_list_mutex)); }

static mp_thread_entry_t* thread_find_locked(pthread_t id)
{
    for (mp_thread_entry_t* entry = thread_list; entry != NULL; entry = entry->next) {
        if (thread_id_equal(entry->id, id)) {
            return entry;
        }
    }
    return NULL;
}

static void thread_set_pending_exception(mp_state_thread_t* state, mp_obj_t exception)
{
    mp_obj_exception_t* exception_obj = MP_OBJ_TO_PTR(exception);
    exception_obj->traceback_data     = NULL;
    state->mp_pending_exception       = exception;
}

void mp_thread_begin_atomic_section(void) { thread_list_lock(); }

void mp_thread_end_atomic_section(void) { thread_list_unlock(); }

void mp_thread_init(void)
{
    MP_STATIC_ASSERT(THREAD_DEFAULT_STACK_SIZE > THREAD_MAIN_STACK_MARGIN);

    thread_check_error("pthread_key_create", pthread_key_create(&tls_key, NULL));
    thread_check_error("pthread_setspecific", pthread_setspecific(tls_key, &mp_state_ctx.thread));

    if (sem_init(&thread_finished_sem, 0, 0) != 0) {
        thread_fatal_error("sem_init", errno);
    }

    thread_list_lock();
    memset(&main_thread, 0, sizeof(main_thread));
    main_thread.id                = pthread_self();
    main_thread.state             = &mp_state_ctx.thread;
    main_thread.startup_exception = MP_OBJ_NULL;
    main_thread.stack_limit       = THREAD_DEFAULT_STACK_SIZE - THREAD_MAIN_STACK_MARGIN;
    // mp_init() has not initialized VM state yet. The main loop publishes
    // readiness after mp_init() and withdraws it before soft-reset teardown.
    main_thread.ready             = false;
    thread_list                   = &main_thread;
    deinit_waiting                = false;
    MP_STATE_THREAD(user_data)    = &main_thread;
    thread_list_unlock();

#if MICROPY_PY_THREAD_GIL
    MP_STATIC_ASSERT((THREAD_GIL_YIELD_INTERVAL & (THREAD_GIL_YIELD_INTERVAL - 1)) == 0);
    __atomic_store_n(&active_thread_count, 1, __ATOMIC_RELAXED);
    __atomic_store_n(&gil_yield_count, 0, __ATOMIC_RELAXED);
#endif
}

void mp_thread_set_main_ready(bool ready)
{
    thread_list_lock();
    if (main_thread.state != NULL) {
        main_thread.ready = ready;
    }
    thread_list_unlock();
}

void mp_thread_shutdown_workers(void)
{
    pthread_t current_id = pthread_self();

    thread_list_lock();
    deinit_waiting = true;
    thread_list_unlock();

    for (;;) {
        bool worker_active = false;
        thread_list_lock();
        for (mp_thread_entry_t* entry = thread_list; entry != NULL; entry = entry->next) {
            if (!thread_id_equal(entry->id, current_id)) {
                worker_active = true;
                break;
            }
        }
        thread_list_unlock();

        if (!worker_active) {
            break;
        }

        int result;
        do {
            result = sem_wait(&thread_finished_sem);
        } while (result != 0 && errno == EINTR);
        if (result != 0) {
            thread_fatal_error("sem_wait", errno);
        }
    }

    // mp_thread_finish() removes a worker before thread_entry releases the GIL.
    // Reacquire it so VM teardown runs with exclusive access and so mp_deinit()
    // can perform the matching final release.
    MP_THREAD_GIL_ENTER();
}

void mp_thread_deinit(void)
{
    thread_list_lock();
    assert(thread_list == &main_thread && main_thread.next == NULL);
    main_thread.ready = false;
    main_thread.state = NULL;
    MP_STATE_THREAD(user_data) = NULL;
    thread_list = NULL;
    thread_list_unlock();

#if MICROPY_PY_THREAD_GIL
    assert(__atomic_load_n(&active_thread_count, __ATOMIC_RELAXED) == 1);
#endif

    mp_thread_set_state(NULL);
    if (sem_destroy(&thread_finished_sem) != 0) {
        thread_fatal_error("sem_destroy", errno);
    }
#if MICROPY_PY_THREAD_GIL
    thread_check_error("pthread_mutex_destroy(gil)", pthread_mutex_destroy(&MP_STATE_VM(gil_mutex)));
#else
    thread_check_error("pthread_mutex_destroy(gc)", pthread_mutex_destroy(&MP_STATE_MEM(gc_mutex)));
#endif

    thread_check_error("pthread_key_delete", pthread_key_delete(tls_key));
}

static void thread_gc_stack(mp_thread_entry_t* entry)
{
    if (entry->state == NULL || entry->state->stack_top == NULL || entry->stack_limit == 0) {
        return;
    }

    uintptr_t stack_top = (uintptr_t)entry->state->stack_top & ~(sizeof(uintptr_t) - 1);
    if (stack_top <= entry->stack_limit) {
        return;
    }
    uintptr_t stack_bottom = (stack_top - entry->stack_limit + sizeof(uintptr_t) - 1) & ~(sizeof(uintptr_t) - 1);
    gc_collect_root((void**)stack_bottom, (stack_top - stack_bottom) / sizeof(uintptr_t));
}

#if MICROPY_ENABLE_PYSTACK
static void thread_gc_pystack(mp_thread_entry_t* entry)
{
    if (entry->state != NULL && entry->state->pystack_start != NULL) {
        void** pystack = (void**)(void*)entry->state->pystack_start;
        size_t count   = (entry->state->pystack_cur - entry->state->pystack_start) / sizeof(void*);
        gc_collect_root(pystack, count);
    }
}
#endif

// The GIL keeps other Python threads from mutating VM state. Scan their full
// stacks instead of using POSIX signals, whose context restore is unsafe on
// RT-Smart.
void mp_thread_gc_others(void)
{
    pthread_t current_id = pthread_self();

    thread_list_lock();
    for (mp_thread_entry_t* entry = thread_list; entry != NULL; entry = entry->next) {
        gc_collect_root(&entry->entry_arg, 1);
        gc_collect_root(&entry->startup_exception, 1);
        if (!thread_id_equal(entry->id, current_id) && entry->ready) {
#if MICROPY_PY_THREAD_GIL
            if (entry->gc_regs_valid) {
                size_t gc_regs_size = sizeof(entry->gc_regs);
                gc_collect_root((void**)(void*)&entry->gc_regs,
                                gc_regs_size / sizeof(void*));
            }
#endif
            thread_gc_stack(entry);
#if MICROPY_ENABLE_PYSTACK
            thread_gc_pystack(entry);
#endif
        }
    }
    thread_list_unlock();
}

mp_state_thread_t* mp_thread_get_state(void) { return (mp_state_thread_t*)pthread_getspecific(tls_key); }

void mp_thread_set_state(mp_state_thread_t* state)
{
    thread_check_error("pthread_setspecific", pthread_setspecific(tls_key, state));
}

mp_uint_t mp_thread_get_id(void) { return (mp_uint_t)pthread_self(); }

void mp_thread_start(void)
{
    pthread_t          current_id = pthread_self();
    mp_state_thread_t* state      = mp_thread_get_state();

    thread_list_lock();
    mp_thread_entry_t* entry = thread_find_locked(current_id);
    assert(entry != NULL && state != NULL);
    if (entry != NULL && state != NULL) {
        entry->state               = state;
        entry->ready               = true;
        MP_STATE_THREAD(user_data) = entry;
        if (entry->startup_exception != MP_OBJ_NULL) {
            thread_set_pending_exception(state, entry->startup_exception);
            entry->startup_exception = MP_OBJ_NULL;
        }
    }
    thread_list_unlock();
}

static size_t thread_normalize_stack_size(size_t requested_size)
{
    size_t stack_size = requested_size == 0 ? THREAD_DEFAULT_STACK_SIZE : requested_size;
    if (stack_size < PTHREAD_STACK_MIN) {
        stack_size = PTHREAD_STACK_MIN;
    }
    if (stack_size < THREAD_MIN_STACK_SIZE) {
        stack_size = THREAD_MIN_STACK_SIZE;
    }
    return stack_size;
}

mp_uint_t mp_thread_create(void* (*entry)(void*), void* arg, size_t* stack_size)
{
    pthread_attr_t     attr;
    mp_thread_entry_t* new_thread         = NULL;
    bool               attr_initialized   = false;
    size_t             pthread_stack_size = thread_normalize_stack_size(*stack_size);
    size_t             stack_limit        = pthread_stack_size - THREAD_STACK_OVERFLOW_MARGIN;
    int                error              = pthread_attr_init(&attr);
    if (error != 0) {
        goto fail;
    }
    attr_initialized = true;

    error = pthread_attr_setstacksize(&attr, pthread_stack_size);
    if (error != 0) {
        goto fail;
    }
    error = pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED);
    if (error != 0) {
        goto fail;
    }

    new_thread = calloc(1, sizeof(*new_thread));
    if (new_thread == NULL) {
        error = ENOMEM;
        goto fail;
    }
    new_thread->state             = NULL;
    new_thread->entry_arg         = arg;
    new_thread->startup_exception = MP_OBJ_NULL;
    new_thread->stack_limit       = stack_limit;
    new_thread->ready             = false;

    // The child reads this field before taking the GIL, so publish it before
    // pthread_create() can start the child.
    *stack_size = stack_limit;

    thread_list_lock();
    error = pthread_create(&new_thread->id, &attr, entry, arg);
    if (error == 0) {
        new_thread->next = thread_list;
        thread_list      = new_thread;

#if MICROPY_PY_THREAD_GIL
        __atomic_fetch_add(&active_thread_count, 1, __ATOMIC_RELEASE);
        // Let a newly created thread run at the parent's next GIL release.
        __atomic_store_n(&gil_yield_count, THREAD_GIL_YIELD_INTERVAL - 1, __ATOMIC_RELAXED);
#endif
    }
    thread_list_unlock();

    if (error != 0) {
        goto fail;
    }
    thread_check_error("pthread_attr_destroy", pthread_attr_destroy(&attr));

    MP_STATIC_ASSERT(sizeof(mp_uint_t) >= sizeof(pthread_t));
    return (mp_uint_t)new_thread->id;

fail:
    if (attr_initialized) {
        pthread_attr_destroy(&attr);
    }
    free(new_thread);
    mp_raise_OSError(error);
}

void mp_thread_finish(void)
{
    pthread_t          current_id    = pthread_self();
    mp_thread_entry_t* finished      = NULL;
    mp_thread_entry_t* previous      = NULL;
    bool               notify_deinit = false;

    thread_list_lock();
    for (mp_thread_entry_t* entry = thread_list; entry != NULL; entry = entry->next) {
        if (thread_id_equal(entry->id, current_id)) {
            entry->ready = false;
            entry->state = NULL;
            if (previous == NULL) {
                thread_list = entry->next;
            } else {
                previous->next = entry->next;
            }
            finished      = entry;
            notify_deinit = deinit_waiting;
            break;
        }
        previous = entry;
    }
    assert(finished != NULL && finished != &main_thread);

#if MICROPY_PY_THREAD_GIL
    assert(__atomic_load_n(&active_thread_count, __ATOMIC_RELAXED) > 1);
    __atomic_fetch_sub(&active_thread_count, 1, __ATOMIC_RELEASE);
#endif
    thread_list_unlock();

    MP_STATE_THREAD(user_data) = NULL;
    mp_thread_set_state(NULL);
    free(finished);
    if (notify_deinit && sem_post(&thread_finished_sem) != 0) {
        thread_fatal_error("sem_post", errno);
    }
}

void mp_thread_mutex_init(mp_thread_mutex_t* mutex)
{
    thread_check_error("pthread_mutex_init", pthread_mutex_init(mutex, NULL));
}

int mp_thread_mutex_lock(mp_thread_mutex_t* mutex, int wait)
{
    int error = wait ? pthread_mutex_lock(mutex) : pthread_mutex_trylock(mutex);
    if (error == 0) {
        return 1;
    }
    if (!wait && error == EBUSY) {
        return 0;
    }
    return -error;
}

void mp_thread_mutex_unlock(mp_thread_mutex_t* mutex)
{
#if MICROPY_PY_THREAD_GIL
    if (mutex == &MP_STATE_VM(gil_mutex)) {
        mp_state_thread_t* state = mp_thread_get_state();
        if (state != NULL && state->user_data != NULL) {
            mp_thread_entry_t* entry = state->user_data;
            // A collector on another Python thread cannot see suspended registers.
            setjmp(entry->gc_regs);
            entry->gc_regs_valid = true;
        }
    }
#endif

    thread_check_error("pthread_mutex_unlock", pthread_mutex_unlock(mutex));

#if MICROPY_PY_THREAD_GIL
    // A sleeping peer cannot become a GIL waiter until RT-Smart schedules it.
    // Periodically yield while peers exist, without paying for a syscall on
    // every GIL release when all peers are blocked or sleeping.
    if (mutex == &MP_STATE_VM(gil_mutex) &&
        __atomic_load_n(&active_thread_count, __ATOMIC_ACQUIRE) > 1 &&
        (__atomic_add_fetch(&gil_yield_count, 1, __ATOMIC_RELAXED) &
         (THREAD_GIL_YIELD_INTERVAL - 1)) == 0 &&
        sched_yield() != 0) {
        thread_fatal_error("sched_yield", errno);
    }
#endif
}

void mp_thread_set_exception_main(mp_obj_t exception)
{
    thread_list_lock();
    if (main_thread.ready && main_thread.state != NULL) {
        thread_set_pending_exception(main_thread.state, exception);
    }
    thread_list_unlock();
}

void mp_thread_set_exception_other(mp_obj_t exception)
{
    const mp_obj_type_t* exception_type = mp_obj_get_type(exception);
    pthread_t            current_id     = pthread_self();

    thread_list_lock();
    for (mp_thread_entry_t* entry = thread_list; entry != NULL; entry = entry->next) {
        if (thread_id_equal(entry->id, current_id)) {
            continue;
        }

        // Tracebacks are mutable, so each target thread needs its own instance.
        mp_obj_t thread_exception = mp_obj_new_exception(exception_type);
        if (entry->ready && entry->state != NULL) {
            thread_set_pending_exception(entry->state, thread_exception);
            entry->startup_exception = MP_OBJ_NULL;
        } else {
            entry->startup_exception = thread_exception;
        }
    }
    thread_list_unlock();
}

#endif // MICROPY_PY_THREAD
