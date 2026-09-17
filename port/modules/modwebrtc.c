/* Copyright (c) 2026, Canaan Bright Sight Co., Ltd
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 * 1. Redistributions of source code must retain the above copyright notice,
 *    this list of conditions and the following disclaimer.
 * 2. Redistributions in binary form must reproduce the above copyright notice,
 *    this list of conditions and the following disclaimer in the documentation
 *    and/or other materials provided with the distribution.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
 * AND ANY EXPRESS OR IMPLIED WARRANTIES ARE DISCLAIMED.
 */

#include <errno.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "py/mperrno.h"
#include "py/mpthread.h"
#include "py/obj.h"
#include "py/runtime.h"

#include "peer.h"

typedef struct {
    mp_obj_base_t base;
    pthread_mutex_t mutex;
    pthread_t worker;
    PeerConnection* pc;
    char* ice_url;
    char* ice_username;
    char* ice_credential;
    char* local_ip;
    uint32_t stop_requested;
    uint32_t worker_started;
    uint32_t closed;
    uint32_t state;
    uint32_t active_calls;
} webrtc_peer_obj_t;

MP_REGISTER_ROOT_POINTER(void* webrtc_active_objs[4]);

#define WEBRTC_MAX_PEERS 4
#define WEBRTC_NEGOTIATION_POLL_US 1000
#define WEBRTC_CONNECTED_POLL_US 10000
#define WEBRTC_IDLE_POLL_US 50000
static pthread_mutex_t webrtc_registry_mutex = PTHREAD_MUTEX_INITIALIZER;
static unsigned int webrtc_peer_count;

static int webrtc_register_peer(webrtc_peer_obj_t* self)
{
    int error = MP_EBUSY;
    pthread_mutex_lock(&webrtc_registry_mutex);
    for (unsigned int i = 0; i < WEBRTC_MAX_PEERS; i++) {
        if (MP_STATE_PORT(webrtc_active_objs)[i] == NULL) {
            if (webrtc_peer_count == 0 && peer_init() != 0) {
                error = MP_EIO;
                break;
            }
            MP_STATE_PORT(webrtc_active_objs)[i] = self;
            webrtc_peer_count++;
            error = 0;
            break;
        }
    }
    pthread_mutex_unlock(&webrtc_registry_mutex);
    return error;
}

static void webrtc_unregister_peer(webrtc_peer_obj_t* self)
{
    pthread_mutex_lock(&webrtc_registry_mutex);
    for (unsigned int i = 0; i < WEBRTC_MAX_PEERS; i++) {
        if (MP_STATE_PORT(webrtc_active_objs)[i] == self) {
            if (--webrtc_peer_count == 0) {
                peer_deinit();
            }
            MP_STATE_PORT(webrtc_active_objs)[i] = NULL;
            break;
        }
    }
    pthread_mutex_unlock(&webrtc_registry_mutex);
}

static char* webrtc_strdup_value(const char* value)
{
    if (value == NULL) {
        return NULL;
    }
    return strdup(value);
}

static void webrtc_state_changed(PeerConnectionState state, void* userdata)
{
    webrtc_peer_obj_t* self = userdata;
    __atomic_store_n(&self->state, (uint32_t)state, __ATOMIC_RELEASE);
}

static void* webrtc_worker(void* arg)
{
    webrtc_peer_obj_t* self = arg;

    while (!__atomic_load_n(&self->stop_requested, __ATOMIC_ACQUIRE)) {
        unsigned int poll_delay_us = WEBRTC_IDLE_POLL_US;

        pthread_mutex_lock(&self->mutex);
        if (self->pc != NULL) {
            peer_connection_loop(self->pc);
        }
        pthread_mutex_unlock(&self->mutex);

        PeerConnectionState state = (PeerConnectionState)__atomic_load_n(
            &self->state, __ATOMIC_ACQUIRE);
        if (state == PEER_CONNECTION_CHECKING || state == PEER_CONNECTION_CONNECTED) {
            poll_delay_us = WEBRTC_NEGOTIATION_POLL_US;
        } else if (state == PEER_CONNECTION_COMPLETED) {
            poll_delay_us = WEBRTC_CONNECTED_POLL_US;
        }

        usleep(poll_delay_us);
    }
    return NULL;
}

static bool webrtc_close_internal(webrtc_peer_obj_t* self)
{
    if (__atomic_exchange_n(&self->closed, 1, __ATOMIC_ACQ_REL)) {
        return false;
    }

    __atomic_store_n(&self->stop_requested, 1, __ATOMIC_RELEASE);
    while (__atomic_load_n(&self->active_calls, __ATOMIC_ACQUIRE) != 0) {
        usleep(1000);
    }
    if (__atomic_exchange_n(&self->worker_started, 0, __ATOMIC_ACQ_REL)) {
        pthread_join(self->worker, NULL);
    }

    pthread_mutex_lock(&self->mutex);
    if (self->pc != NULL) {
        peer_connection_close(self->pc);
        peer_connection_destroy(self->pc);
        self->pc = NULL;
    }
    pthread_mutex_unlock(&self->mutex);
    pthread_mutex_destroy(&self->mutex);

    free(self->ice_url);
    free(self->ice_username);
    free(self->ice_credential);
    free(self->local_ip);
    self->ice_url = NULL;
    self->ice_username = NULL;
    self->ice_credential = NULL;
    self->local_ip = NULL;
    __atomic_store_n(&self->state, PEER_CONNECTION_CLOSED, __ATOMIC_RELEASE);
    return true;
}

void webrtc_deinit_all(void)
{
    for (unsigned int i = 0; i < WEBRTC_MAX_PEERS; i++) {
        pthread_mutex_lock(&webrtc_registry_mutex);
        webrtc_peer_obj_t* self = MP_STATE_PORT(webrtc_active_objs)[i];
        pthread_mutex_unlock(&webrtc_registry_mutex);
        if (self != NULL) {
            if (webrtc_close_internal(self)) {
                webrtc_unregister_peer(self);
            }
        }
    }
}

static webrtc_peer_obj_t* webrtc_begin_call(mp_obj_t self_in)
{
    webrtc_peer_obj_t* self = MP_OBJ_TO_PTR(self_in);
    __atomic_fetch_add(&self->active_calls, 1, __ATOMIC_ACQ_REL);
    if (__atomic_load_n(&self->closed, __ATOMIC_ACQUIRE) || self->pc == NULL) {
        __atomic_fetch_sub(&self->active_calls, 1, __ATOMIC_ACQ_REL);
        mp_raise_ValueError(MP_ERROR_TEXT("PeerConnection is closed"));
    }
    return self;
}

static void webrtc_end_call(webrtc_peer_obj_t* self)
{
    __atomic_fetch_sub(&self->active_calls, 1, __ATOMIC_ACQ_REL);
}

static mp_obj_t webrtc_peer_make_new(const mp_obj_type_t* type, size_t n_args, size_t n_kw,
                                     const mp_obj_t* all_args)
{
    enum {
        ARG_video_codec,
        ARG_audio_codec,
        ARG_audio_sample_rate,
        ARG_ice_server,
        ARG_ice_username,
        ARG_ice_credential,
        ARG_local_ip,
    };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_video_codec, MP_ARG_INT, { .u_int = CODEC_H265 } },
        { MP_QSTR_audio_codec, MP_ARG_INT, { .u_int = CODEC_NONE } },
        { MP_QSTR_audio_sample_rate, MP_ARG_INT, { .u_int = 48000 } },
        { MP_QSTR_ice_server, MP_ARG_OBJ, { .u_obj = mp_const_none } },
        { MP_QSTR_ice_username, MP_ARG_OBJ, { .u_obj = mp_const_none } },
        { MP_QSTR_ice_credential, MP_ARG_OBJ, { .u_obj = mp_const_none } },
        { MP_QSTR_local_ip, MP_ARG_OBJ, { .u_obj = mp_const_none } },
    };
    mp_map_t kw_args;
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    PeerConfiguration config = { 0 };
    webrtc_peer_obj_t* self;
    const char* ice_url;
    const char* ice_username;
    const char* ice_credential;
    const char* local_ip;
    int error;

    mp_arg_check_num(n_args, n_kw, 0, 3, true);
    mp_map_init_fixed_table(&kw_args, n_kw, all_args + n_args);
    mp_arg_parse_all(n_args, all_args, &kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    if (args[ARG_video_codec].u_int != CODEC_NONE && args[ARG_video_codec].u_int != CODEC_H264 &&
        args[ARG_video_codec].u_int != CODEC_H265) {
        mp_raise_ValueError(MP_ERROR_TEXT("video_codec must be CODEC_NONE, CODEC_H264, or CODEC_H265"));
    }
    if (args[ARG_audio_codec].u_int != CODEC_NONE && args[ARG_audio_codec].u_int != CODEC_OPUS &&
        args[ARG_audio_codec].u_int != CODEC_PCMA && args[ARG_audio_codec].u_int != CODEC_PCMU) {
        mp_raise_ValueError(MP_ERROR_TEXT("unsupported audio_codec"));
    }
    if (args[ARG_audio_sample_rate].u_int <= 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("audio_sample_rate must be positive"));
    }
    ice_url = args[ARG_ice_server].u_obj == mp_const_none
                  ? NULL
                  : mp_obj_str_get_str(args[ARG_ice_server].u_obj);
    ice_username = args[ARG_ice_username].u_obj == mp_const_none
                       ? NULL
                       : mp_obj_str_get_str(args[ARG_ice_username].u_obj);
    ice_credential = args[ARG_ice_credential].u_obj == mp_const_none
                         ? NULL
                         : mp_obj_str_get_str(args[ARG_ice_credential].u_obj);
    local_ip = args[ARG_local_ip].u_obj == mp_const_none
                   ? NULL
                   : mp_obj_str_get_str(args[ARG_local_ip].u_obj);

    self = m_new_obj_with_finaliser(webrtc_peer_obj_t);
    memset(self, 0, sizeof(*self));
    self->ice_url = webrtc_strdup_value(ice_url);
    self->ice_username = webrtc_strdup_value(ice_username);
    self->ice_credential = webrtc_strdup_value(ice_credential);
    self->local_ip = webrtc_strdup_value(local_ip);
    if ((ice_url != NULL && self->ice_url == NULL) ||
        (ice_username != NULL && self->ice_username == NULL) ||
        (ice_credential != NULL && self->ice_credential == NULL) ||
        (local_ip != NULL && self->local_ip == NULL)) {
        free(self->ice_url);
        free(self->ice_username);
        free(self->ice_credential);
        free(self->local_ip);
        mp_raise_OSError(MP_ENOMEM);
    }
    __atomic_store_n(&self->state, PEER_CONNECTION_CLOSED, __ATOMIC_RELAXED);

    error = pthread_mutex_init(&self->mutex, NULL);
    if (error != 0) {
        free(self->ice_url);
        free(self->ice_username);
        free(self->ice_credential);
        free(self->local_ip);
        mp_raise_OSError(error);
    }
    error = webrtc_register_peer(self);
    if (error != 0) {
        pthread_mutex_destroy(&self->mutex);
        free(self->ice_url);
        free(self->ice_username);
        free(self->ice_credential);
        free(self->local_ip);
        mp_raise_OSError(error);
    }

    config.video_codec = (MediaCodec)args[ARG_video_codec].u_int;
    config.audio_codec = (MediaCodec)args[ARG_audio_codec].u_int;
    config.audio_sample_rate = (uint32_t)args[ARG_audio_sample_rate].u_int;
    config.datachannel = DATA_CHANNEL_NONE;
    config.user_data = self;
    config.ice_servers[0].urls = self->ice_url;
    config.ice_servers[0].username = self->ice_username;
    config.ice_servers[0].credential = self->ice_credential;
    /* Bind separately so an invalid/unavailable address is not reported as
     * an allocation failure. All failure paths release this peer's share. */
    self->base.type = type;
    errno = 0;
    self->pc = peer_connection_create(&config);
    if (self->pc == NULL) {
        error = errno ? errno : MP_ENOMEM;
        if (webrtc_close_internal(self)) {
            webrtc_unregister_peer(self);
        }
        mp_raise_OSError(error);
    }
    errno = 0;
    if (peer_connection_set_local_ip(self->pc, self->local_ip) != 0) {
        error = errno ? errno : MP_EINVAL;
        if (webrtc_close_internal(self)) {
            webrtc_unregister_peer(self);
        }
        mp_raise_OSError(error);
    }
    peer_connection_oniceconnectionstatechange(self->pc, webrtc_state_changed);
    __atomic_store_n(&self->state, PEER_CONNECTION_NEW, __ATOMIC_RELEASE);

    error = pthread_create(&self->worker, NULL, webrtc_worker, self);
    if (error != 0) {
        if (webrtc_close_internal(self)) {
            webrtc_unregister_peer(self);
        }
        mp_raise_OSError(error);
    }
    __atomic_store_n(&self->worker_started, 1, __ATOMIC_RELEASE);
    return MP_OBJ_FROM_PTR(self);
}

static mp_obj_t webrtc_create_description(mp_obj_t self_in, SdpType type,
                                          const char* local_ip)
{
    webrtc_peer_obj_t* self = webrtc_begin_call(self_in);
    const char* description;
    char* description_copy;
    const char* bind_ip = local_ip != NULL ? local_ip : self->local_ip;
    char* local_ip_copy = bind_ip == NULL ? NULL : strdup(bind_ip);
    int local_ip_result = 0;
    int bind_error = 0;

    if (bind_ip != NULL && local_ip_copy == NULL) {
        webrtc_end_call(self);
        mp_raise_OSError(MP_ENOMEM);
    }

    MP_THREAD_GIL_EXIT();
    pthread_mutex_lock(&self->mutex);
    if (type == SDP_TYPE_OFFER && peer_connection_get_state(self->pc) != PEER_CONNECTION_NEW &&
        peer_connection_get_state(self->pc) != PEER_CONNECTION_CLOSED) {
        peer_connection_close(self->pc);
    }
    if (type == SDP_TYPE_OFFER) {
        errno = 0;
        local_ip_result = peer_connection_set_local_ip(self->pc, local_ip_copy);
        bind_error = errno ? errno : MP_EINVAL;
    }
    description = local_ip_result == 0
                      ? (type == SDP_TYPE_OFFER ? peer_connection_create_offer(self->pc)
                                                : peer_connection_create_answer(self->pc))
                      : NULL;
    description_copy = description == NULL ? NULL : strdup(description);
    pthread_mutex_unlock(&self->mutex);
    webrtc_end_call(self);
    MP_THREAD_GIL_ENTER();
    free(local_ip_copy);

    if (local_ip_result != 0) {
        mp_raise_OSError(bind_error);
    }
    if (description_copy == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("SDP creation failed"));
    }
    mp_obj_t result = mp_obj_new_str(description_copy, strlen(description_copy));
    free(description_copy);
    return result;
}

static mp_obj_t webrtc_create_offer(size_t n_args, const mp_obj_t* args)
{
    const char* local_ip = n_args > 1 && args[1] != mp_const_none
                               ? mp_obj_str_get_str(args[1])
                               : NULL;
    return webrtc_create_description(args[0], SDP_TYPE_OFFER, local_ip);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(webrtc_create_offer_obj, 1, 2,
                                           webrtc_create_offer);

static mp_obj_t webrtc_create_answer(mp_obj_t self_in)
{
    return webrtc_create_description(self_in, SDP_TYPE_ANSWER, NULL);
}
static MP_DEFINE_CONST_FUN_OBJ_1(webrtc_create_answer_obj, webrtc_create_answer);

static mp_obj_t webrtc_set_remote_description(size_t n_args, const mp_obj_t* args)
{
    webrtc_peer_obj_t* self;
    SdpType type = n_args > 2 ? (SdpType)mp_obj_get_int(args[2]) : SDP_TYPE_ANSWER;
    const char* value = mp_obj_str_get_str(args[1]);
    char* description;

    if (type != SDP_TYPE_OFFER && type != SDP_TYPE_ANSWER) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid SDP type"));
    }
    self = webrtc_begin_call(args[0]);
    description = strdup(value);
    if (description == NULL) {
        webrtc_end_call(self);
        mp_raise_OSError(MP_ENOMEM);
    }

    MP_THREAD_GIL_EXIT();
    pthread_mutex_lock(&self->mutex);
    peer_connection_set_remote_description(self->pc, description, type);
    pthread_mutex_unlock(&self->mutex);
    webrtc_end_call(self);
    MP_THREAD_GIL_ENTER();
    free(description);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(webrtc_set_remote_description_obj, 2, 3,
                                           webrtc_set_remote_description);

static mp_obj_t webrtc_add_ice_candidate(mp_obj_t self_in, mp_obj_t candidate_in)
{
    const char* value = mp_obj_str_get_str(candidate_in);
    webrtc_peer_obj_t* self = webrtc_begin_call(self_in);
    char* candidate = strdup(value);
    int result;

    if (candidate == NULL) {
        webrtc_end_call(self);
        mp_raise_OSError(MP_ENOMEM);
    }
    MP_THREAD_GIL_EXIT();
    pthread_mutex_lock(&self->mutex);
    result = peer_connection_add_ice_candidate(self->pc, candidate);
    pthread_mutex_unlock(&self->mutex);
    webrtc_end_call(self);
    MP_THREAD_GIL_ENTER();
    free(candidate);
    return mp_obj_new_int(result);
}
static MP_DEFINE_CONST_FUN_OBJ_2(webrtc_add_ice_candidate_obj, webrtc_add_ice_candidate);

static mp_obj_t webrtc_send_media(size_t n_args, const mp_obj_t* args, bool video)
{
    webrtc_peer_obj_t* self;
    mp_buffer_info_t buffer;
    uint64_t timestamp_us = (uint64_t)mp_obj_get_int_truncated(args[2]);
    int result;

    mp_get_buffer_raise(args[1], &buffer, MP_BUFFER_READ);
    self = webrtc_begin_call(args[0]);

    MP_THREAD_GIL_EXIT();
    pthread_mutex_lock(&self->mutex);
    result = video ? peer_connection_send_video(self->pc, buffer.buf, buffer.len, timestamp_us)
                   : peer_connection_send_audio(self->pc, buffer.buf, buffer.len, timestamp_us);
    pthread_mutex_unlock(&self->mutex);
    webrtc_end_call(self);
    MP_THREAD_GIL_ENTER();
    return mp_obj_new_int(result);
}

static mp_obj_t webrtc_send_video(size_t n_args, const mp_obj_t* args)
{
    return webrtc_send_media(n_args, args, true);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(webrtc_send_video_obj, 3, 3, webrtc_send_video);

static mp_obj_t webrtc_send_audio(size_t n_args, const mp_obj_t* args)
{
    return webrtc_send_media(n_args, args, false);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(webrtc_send_audio_obj, 3, 3, webrtc_send_audio);

static mp_obj_t webrtc_state(mp_obj_t self_in)
{
    webrtc_peer_obj_t* self = MP_OBJ_TO_PTR(self_in);
    return mp_obj_new_int_from_uint(__atomic_load_n(&self->state, __ATOMIC_ACQUIRE));
}
static MP_DEFINE_CONST_FUN_OBJ_1(webrtc_state_obj, webrtc_state);

static mp_obj_t webrtc_state_name(mp_obj_t self_in)
{
    webrtc_peer_obj_t* self = MP_OBJ_TO_PTR(self_in);
    PeerConnectionState state = (PeerConnectionState)__atomic_load_n(&self->state, __ATOMIC_ACQUIRE);
    const char* name = peer_connection_state_to_string(state);
    return mp_obj_new_str(name, strlen(name));
}
static MP_DEFINE_CONST_FUN_OBJ_1(webrtc_state_name_obj, webrtc_state_name);

static mp_obj_t webrtc_is_connected(mp_obj_t self_in)
{
    webrtc_peer_obj_t* self = MP_OBJ_TO_PTR(self_in);
    return mp_obj_new_bool(__atomic_load_n(&self->state, __ATOMIC_ACQUIRE) == PEER_CONNECTION_COMPLETED);
}
static MP_DEFINE_CONST_FUN_OBJ_1(webrtc_is_connected_obj, webrtc_is_connected);

static mp_obj_t webrtc_close(mp_obj_t self_in)
{
    webrtc_peer_obj_t* self = MP_OBJ_TO_PTR(self_in);
    bool closed_here;

    MP_THREAD_GIL_EXIT();
    closed_here = webrtc_close_internal(self);
    MP_THREAD_GIL_ENTER();
    if (closed_here) {
        // MP_STATE_PORT roots must only change while the VM lock is held.
        webrtc_unregister_peer(self);
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(webrtc_close_obj, webrtc_close);

static mp_obj_t webrtc_random_bytes(mp_obj_t size_in)
{
    mp_int_t size = mp_obj_get_int(size_in);
    if (size < 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("size must be non-negative"));
    }
    vstr_t buffer;
    vstr_init_len(&buffer, size);
    if (peer_random_bytes((uint8_t*)buffer.buf, size) != 0) {
        vstr_clear(&buffer);
        mp_raise_OSError(MP_EIO);
    }
    return mp_obj_new_bytes_from_vstr(&buffer);
}
static MP_DEFINE_CONST_FUN_OBJ_1(webrtc_random_bytes_obj, webrtc_random_bytes);

//| module: webrtc
//| MAX_PEERS: int = 4
//| def random_bytes(size: int) -> bytes: ...
//| class PeerConnection:
//|     """A native libpeer WebRTC connection with a background protocol worker."""
//|     def __init__(self, video_codec: int = CODEC_H265, audio_codec: int = CODEC_NONE, audio_sample_rate: int = 48000, *, ice_server: str | None = None, ice_username: str | None = None, ice_credential: str | None = None, local_ip: str | None = None) -> None: ...
//|     def create_offer(self, local_ip: str | None = None) -> str: ...
//|     def create_answer(self) -> str: ...
//|     def set_remote_description(self, sdp: str, type: int = SDP_TYPE_ANSWER) -> None: ...
//|     def add_ice_candidate(self, candidate: str) -> int: ...
//|     def send_video(self, data: Any, timestamp_us: int) -> int: ...
//|     def send_audio(self, data: Any, timestamp_us: int) -> int: ...
//|     def state(self) -> int: ...
//|     def state_name(self) -> str: ...
//|     def is_connected(self) -> bool: ...
//|     def close(self) -> None: ...

static const mp_rom_map_elem_t webrtc_peer_locals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&webrtc_close_obj) },
    { MP_ROM_QSTR(MP_QSTR_close), MP_ROM_PTR(&webrtc_close_obj) },
    { MP_ROM_QSTR(MP_QSTR_create_offer), MP_ROM_PTR(&webrtc_create_offer_obj) },
    { MP_ROM_QSTR(MP_QSTR_create_answer), MP_ROM_PTR(&webrtc_create_answer_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_remote_description), MP_ROM_PTR(&webrtc_set_remote_description_obj) },
    { MP_ROM_QSTR(MP_QSTR_add_ice_candidate), MP_ROM_PTR(&webrtc_add_ice_candidate_obj) },
    { MP_ROM_QSTR(MP_QSTR_send_video), MP_ROM_PTR(&webrtc_send_video_obj) },
    { MP_ROM_QSTR(MP_QSTR_send_audio), MP_ROM_PTR(&webrtc_send_audio_obj) },
    { MP_ROM_QSTR(MP_QSTR_state), MP_ROM_PTR(&webrtc_state_obj) },
    { MP_ROM_QSTR(MP_QSTR_state_name), MP_ROM_PTR(&webrtc_state_name_obj) },
    { MP_ROM_QSTR(MP_QSTR_is_connected), MP_ROM_PTR(&webrtc_is_connected_obj) },
};
static MP_DEFINE_CONST_DICT(webrtc_peer_locals, webrtc_peer_locals_table);

MP_DEFINE_CONST_OBJ_TYPE(
    webrtc_peer_type,
    MP_QSTR_PeerConnection,
    MP_TYPE_FLAG_NONE,
    make_new, webrtc_peer_make_new,
    locals_dict, &webrtc_peer_locals
);

static const mp_rom_map_elem_t webrtc_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_webrtc) },
    { MP_ROM_QSTR(MP_QSTR_PeerConnection), MP_ROM_PTR(&webrtc_peer_type) },
    { MP_ROM_QSTR(MP_QSTR_MAX_PEERS), MP_ROM_INT(WEBRTC_MAX_PEERS) },
    { MP_ROM_QSTR(MP_QSTR_random_bytes), MP_ROM_PTR(&webrtc_random_bytes_obj) },
    { MP_ROM_QSTR(MP_QSTR_SDP_TYPE_OFFER), MP_ROM_INT(SDP_TYPE_OFFER) },
    { MP_ROM_QSTR(MP_QSTR_SDP_TYPE_ANSWER), MP_ROM_INT(SDP_TYPE_ANSWER) },
    { MP_ROM_QSTR(MP_QSTR_CODEC_NONE), MP_ROM_INT(CODEC_NONE) },
    { MP_ROM_QSTR(MP_QSTR_CODEC_H264), MP_ROM_INT(CODEC_H264) },
    { MP_ROM_QSTR(MP_QSTR_CODEC_H265), MP_ROM_INT(CODEC_H265) },
    { MP_ROM_QSTR(MP_QSTR_CODEC_OPUS), MP_ROM_INT(CODEC_OPUS) },
    { MP_ROM_QSTR(MP_QSTR_CODEC_PCMA), MP_ROM_INT(CODEC_PCMA) },
    { MP_ROM_QSTR(MP_QSTR_CODEC_PCMU), MP_ROM_INT(CODEC_PCMU) },
    { MP_ROM_QSTR(MP_QSTR_STATE_CLOSED), MP_ROM_INT(PEER_CONNECTION_CLOSED) },
    { MP_ROM_QSTR(MP_QSTR_STATE_NEW), MP_ROM_INT(PEER_CONNECTION_NEW) },
    { MP_ROM_QSTR(MP_QSTR_STATE_CHECKING), MP_ROM_INT(PEER_CONNECTION_CHECKING) },
    { MP_ROM_QSTR(MP_QSTR_STATE_CONNECTED), MP_ROM_INT(PEER_CONNECTION_CONNECTED) },
    { MP_ROM_QSTR(MP_QSTR_STATE_COMPLETED), MP_ROM_INT(PEER_CONNECTION_COMPLETED) },
    { MP_ROM_QSTR(MP_QSTR_STATE_FAILED), MP_ROM_INT(PEER_CONNECTION_FAILED) },
    { MP_ROM_QSTR(MP_QSTR_STATE_DISCONNECTED), MP_ROM_INT(PEER_CONNECTION_DISCONNECTED) },
};
static MP_DEFINE_CONST_DICT(webrtc_module_globals, webrtc_module_globals_table);

const mp_obj_module_t webrtc_module = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t*)&webrtc_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_webrtc, webrtc_module);
