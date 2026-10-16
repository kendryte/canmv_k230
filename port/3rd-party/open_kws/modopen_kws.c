/* Copyright (c) 2026, Canaan Bright Sight Co., Ltd
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * MicroPython binding of the Open-KWS core (open-vocabulary keyword
 * spotting): streaming log-Mel frontend, KPU sliding-window inference,
 * CTC keyword scoring with two-stage verification, and on-device enrollment.
 * Usage: resources/examples/31-OPEN-KWS/README.md.
 */
#include <math.h>
#include <stdio.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include "py/obj.h"
#include "py/objstr.h"
#include "py/runtime.h"
#include "ndarray.h"
#include "okws_bridge.h"

#define OKWS_MAX_EVENTS 8
#define OKWS_N_MELS_PY 40
#define OKWS_N_UNITS_PY 59

typedef struct {
    mp_obj_base_t base;
    okws_engine_t *eng;
    mp_obj_t kw_ids; // list: kw_id of each registered keyword (event index -> id)
    int enroll_err;   // last enroll_step() error code
    bool enroll_done; // enroll_step() reported completion
} okws_obj_t;

static const mp_obj_type_t okws_engine_type;

static okws_obj_t *get_engine(mp_obj_t self_in)
{
    okws_obj_t *self = MP_OBJ_TO_PTR(self_in);
    if (self->eng == NULL)
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("open_kws engine is deinitialized"));
    return self;
}

// int16 PCM view of any buffer object; copies only if misaligned.
static const int16_t *pcm_arg(mp_obj_t obj, size_t *n)
{
    mp_buffer_info_t info;
    mp_get_buffer_raise(obj, &info, MP_BUFFER_READ);
    *n = info.len / 2;
    if (((uintptr_t)info.buf & 1) == 0)
        return (const int16_t *)info.buf;
    int16_t *copy = m_new(int16_t, *n ? *n : 1);
    memcpy(copy, info.buf, *n * 2);
    return copy;
}

static mp_obj_t round_float(double x, double scale)
{
    return mp_obj_new_float((mp_float_t)(round(x * scale) / scale));
}

static mp_obj_t metrics_dict(const okws_audio_metrics_t *m)
{
    mp_obj_t d = mp_obj_new_dict(4);
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_dur), round_float(m->dur, 1e3));
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_peak), round_float(m->peak, 1e4));
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_clip_ratio), round_float(m->clip_ratio, 1e5));
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_snr_db), round_float(m->snr_db, 1e2));
    return d;
}

static mp_obj_t events_list(okws_obj_t *self, const okws_event_t *ev, int n)
{
    mp_obj_t list = mp_obj_new_list(0, NULL);
    for (int i = 0; i < n; i++) {
        size_t n_ids;
        mp_obj_t *ids;
        mp_obj_list_get(self->kw_ids, &n_ids, &ids);
        mp_obj_t t[5] = {
            (size_t)ev[i].kw < n_ids ? ids[ev[i].kw] : MP_OBJ_NEW_SMALL_INT(ev[i].kw),
            mp_obj_new_float(ev[i].score),
            mp_obj_new_float(ev[i].threshold),
            mp_obj_new_float(ev[i].start_ms),
            mp_obj_new_float(ev[i].end_ms),
        };
        mp_obj_list_append(list, mp_obj_new_tuple(5, t));
    }
    return list;
}

// ---------------------------------------------------------------- Engine

// Engine(kmodel, assets)
static mp_obj_t okws_make_new(const mp_obj_type_t *type, size_t n_args, size_t n_kw,
                              const mp_obj_t *all_args)
{
    enum { ARG_kmodel, ARG_assets };
    static const mp_arg_t allowed[] = {
        { MP_QSTR_kmodel, MP_ARG_REQUIRED | MP_ARG_OBJ, {.u_obj = MP_OBJ_NULL} },
        { MP_QSTR_assets, MP_ARG_REQUIRED | MP_ARG_OBJ, {.u_obj = MP_OBJ_NULL} },
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed)];
    mp_arg_parse_all_kw_array(n_args, n_kw, all_args, MP_ARRAY_SIZE(allowed), allowed, args);

    const char *err = NULL;
    okws_engine_t *eng = okws_engine_create(mp_obj_str_get_str(args[ARG_kmodel].u_obj),
                                            mp_obj_str_get_str(args[ARG_assets].u_obj), &err);
    if (eng == NULL)
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("open_kws: %s"),
                          err ? err : "engine create failed");
    okws_obj_t *self = m_new_obj_with_finaliser(okws_obj_t);
    self->base.type = type;
    self->eng = eng;
    self->kw_ids = mp_obj_new_list(0, NULL);
    self->enroll_err = 0;
    self->enroll_done = false;
    return MP_OBJ_FROM_PTR(self);
}

static mp_obj_t okws_deinit(mp_obj_t self_in)
{
    okws_obj_t *self = MP_OBJ_TO_PTR(self_in);
    if (self->eng != NULL) {
        okws_engine_destroy(self->eng);
        self->eng = NULL;
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(okws_deinit_obj, okws_deinit);

static mp_obj_t dict_get(mp_obj_t d, qstr key, mp_obj_t dflt)
{
    if (!mp_obj_is_type(d, &mp_type_dict))
        mp_raise_TypeError(MP_ERROR_TEXT("enroll record entries must be dicts"));
    mp_map_elem_t *e = mp_map_lookup(mp_obj_dict_get_map(d), MP_OBJ_NEW_QSTR(key),
                                     MP_MAP_LOOKUP);
    return e ? e->value : dflt;
}

typedef struct {
    int units[OKWS_MAX_HYPS_C * OKWS_MAX_UNITS_C];
    int lens[OKWS_MAX_HYPS_C];
    double weights[OKWS_MAX_HYPS_C];
    int n_hyps;
    double threshold;
} kw_arrays_t;

// Hypotheses and threshold of an enroll.json dict.
static void parse_keyword(mp_obj_t rec, kw_arrays_t *k)
{
    if (!mp_obj_is_type(rec, &mp_type_dict))
        mp_raise_TypeError(MP_ERROR_TEXT("keyword must be an enroll dict"));
    mp_obj_t hyps_obj = dict_get(rec, MP_QSTR_hypotheses, MP_OBJ_NULL);
    mp_obj_t th_obj = dict_get(rec, MP_QSTR_threshold, MP_OBJ_NULL);
    if (hyps_obj == MP_OBJ_NULL || th_obj == MP_OBJ_NULL)
        mp_raise_ValueError(MP_ERROR_TEXT("enroll dict needs 'hypotheses' and 'threshold'"));
    size_t n_hyps;
    mp_obj_t *hyps;
    mp_obj_get_array(hyps_obj, &n_hyps, &hyps);
    if (n_hyps == 0 || n_hyps > OKWS_MAX_HYPS_C)
        mp_raise_ValueError(MP_ERROR_TEXT("1..8 hypotheses required"));
    size_t pos = 0;
    for (size_t i = 0; i < n_hyps; i++) {
        mp_obj_t u_obj = dict_get(hyps[i], MP_QSTR_units, MP_OBJ_NULL);
        if (u_obj == MP_OBJ_NULL)
            mp_raise_ValueError(MP_ERROR_TEXT("hypothesis without 'units'"));
        size_t nu;
        mp_obj_t *u;
        mp_obj_get_array(u_obj, &nu, &u);
        if (nu == 0 || nu > OKWS_MAX_UNITS_C)
            mp_raise_ValueError(MP_ERROR_TEXT("bad hypothesis length"));
        for (size_t j = 0; j < nu; j++)
            k->units[pos++] = mp_obj_get_int(u[j]);
        k->lens[i] = (int)nu;
        k->weights[i] = mp_obj_get_float(dict_get(hyps[i], MP_QSTR_weight, mp_obj_new_float(1.0f)));
    }
    k->n_hyps = (int)n_hyps;
    k->threshold = mp_obj_get_float(th_obj);
}

// Registers one enroll.json dict as a keyword; returns its index.
static int add_keyword_rec(okws_obj_t *self, mp_obj_t rec)
{
    if (okws_engine_keyword_count(self->eng) >= OKWS_MAX_KEYWORDS_C)
        mp_raise_ValueError(MP_ERROR_TEXT("too many keywords (max 8)"));
    kw_arrays_t *k = m_new_obj(kw_arrays_t);
    parse_keyword(rec, k);
    int cooldown = mp_obj_get_int(dict_get(rec, MP_QSTR_cooldown_ms, MP_OBJ_NEW_SMALL_INT(1500)));
    int confirm = mp_obj_get_int(dict_get(rec, MP_QSTR_confirm_frames, MP_OBJ_NEW_SMALL_INT(2)));
    // pykws v2 records carry verify_threshold; absent or None disables the
    // second-stage verification (v1 behaviour)
    mp_obj_t vth_obj = dict_get(rec, MP_QSTR_verify_threshold, mp_const_none);
    double vth = vth_obj == mp_const_none ? NAN : mp_obj_get_float(vth_obj);
    int idx = okws_engine_add_keyword(self->eng, k->units, k->lens, k->weights, k->n_hyps,
                                      k->threshold, cooldown, confirm, vth);
    m_del_obj(kw_arrays_t, k);
    if (idx < 0)
        mp_raise_ValueError(MP_ERROR_TEXT("invalid keyword units"));
    char buf[16];
    snprintf(buf, sizeof(buf), "kw_%d", idx);
    mp_obj_list_append(self->kw_ids, dict_get(rec, MP_QSTR_kw_id, mp_obj_new_str(buf, strlen(buf))));
    return idx;
}

// probe(rec, pcm) -> (margin, score, cut): how the (unregistered) keyword rec
// scores on a recording under the current verification rule; score is None if
// no hypothesis can be aligned, cut is None if rec has no verify_threshold.
static mp_obj_t okws_probe(mp_obj_t self_in, mp_obj_t rec, mp_obj_t buf)
{
    okws_obj_t *self = get_engine(self_in);
    kw_arrays_t *k = m_new_obj(kw_arrays_t);
    parse_keyword(rec, k);
    size_t n;
    const int16_t *pcm = pcm_arg(buf, &n);
    mp_obj_t vth_obj = dict_get(rec, MP_QSTR_verify_threshold, mp_const_none);
    double vth = vth_obj == mp_const_none ? NAN : mp_obj_get_float(vth_obj);
    double margin = 0, score = 0, cut = 0;
    int has_score = 0;
    int r = okws_engine_probe(self->eng, k->units, k->lens, k->weights, k->n_hyps, k->threshold,
                              vth, pcm, n, &margin, &score, &has_score, &cut);
    m_del_obj(kw_arrays_t, k);
    if (r != 0)
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("open_kws: probe failed"));
    mp_obj_t t[3] = {mp_obj_new_float((mp_float_t)margin),
                     has_score ? mp_obj_new_float((mp_float_t)score) : mp_const_none,
                     isnan(cut) ? mp_const_none : mp_obj_new_float((mp_float_t)cut)};
    return mp_obj_new_tuple(3, t);
}
static MP_DEFINE_CONST_FUN_OBJ_3(okws_probe_obj, okws_probe);

// add_keyword(rec) -> index; rec is an enroll.json dict.
static mp_obj_t okws_add_keyword(mp_obj_t self_in, mp_obj_t rec)
{
    return MP_OBJ_NEW_SMALL_INT(add_keyword_rec(get_engine(self_in), rec));
}
static MP_DEFINE_CONST_FUN_OBJ_2(okws_add_keyword_obj, okws_add_keyword);

static mp_obj_t okws_clear_keywords(mp_obj_t self_in)
{
    okws_obj_t *self = get_engine(self_in);
    okws_engine_clear_keywords(self->eng);
    self->kw_ids = mp_obj_new_list(0, NULL);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(okws_clear_keywords_obj, okws_clear_keywords);

// set_keywords([rec, ...]): replace all keywords and restart the stream.
static mp_obj_t okws_set_keywords(mp_obj_t self_in, mp_obj_t recs)
{
    okws_obj_t *self = get_engine(self_in);
    size_t n;
    mp_obj_t *items;
    mp_obj_get_array(recs, &n, &items);
    okws_clear_keywords(self_in);
    for (size_t i = 0; i < n; i++)
        add_keyword_rec(self, items[i]);
    okws_engine_reset(self->eng);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(okws_set_keywords_obj, okws_set_keywords);

// set_keyword(rec): single-keyword form of set_keywords(); None clears.
static mp_obj_t okws_set_keyword(mp_obj_t self_in, mp_obj_t rec)
{
    if (rec == mp_const_none) {
        okws_clear_keywords(self_in);
        return mp_const_none;
    }
    mp_obj_t one = mp_obj_new_list(1, &rec);
    return okws_set_keywords(self_in, one);
}
static MP_DEFINE_CONST_FUN_OBJ_2(okws_set_keyword_obj, okws_set_keyword);

static mp_obj_t okws_keywords(mp_obj_t self_in)
{
    okws_obj_t *self = get_engine(self_in);
    size_t n;
    mp_obj_t *ids;
    mp_obj_list_get(self->kw_ids, &n, &ids);
    return mp_obj_new_list(n, ids);
}
static MP_DEFINE_CONST_FUN_OBJ_1(okws_keywords_obj, okws_keywords);

static mp_obj_t okws_has_keyword(mp_obj_t self_in)
{
    return mp_obj_new_bool(okws_engine_has_keyword(get_engine(self_in)->eng));
}
static MP_DEFINE_CONST_FUN_OBJ_1(okws_has_keyword_obj, okws_has_keyword);

// set_sensitivity("sensitive" | "normal" | "conservative" | float bias)
static mp_obj_t okws_set_sensitivity(mp_obj_t self_in, mp_obj_t level)
{
    okws_obj_t *self = get_engine(self_in);
    double bias;
    if (mp_obj_is_str(level)) {
        const char *s = mp_obj_str_get_str(level);
        if (strcmp(s, "sensitive") == 0)
            bias = -0.15;
        else if (strcmp(s, "normal") == 0)
            bias = 0.0;
        else if (strcmp(s, "conservative") == 0)
            bias = 0.15;
        else
            mp_raise_ValueError(MP_ERROR_TEXT("sensitivity: sensitive/normal/conservative"));
    } else {
        bias = mp_obj_get_float(level);
    }
    okws_engine_set_bias(self->eng, bias);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(okws_set_sensitivity_obj, okws_set_sensitivity);

// set_verify(n_hyps=1, alpha=0.0, delta=0.0): second-stage rule for all
// keywords. A trigger passes if
//   max over the first n_hyps hypotheses of the weakest syllable
//   + alpha * (forward score - threshold) > verify_threshold + delta.
// The defaults are the pykws v2 rule. Returns the previous (n_hyps, alpha, delta).
static mp_obj_t okws_set_verify(size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args)
{
    enum { ARG_n_hyps, ARG_alpha, ARG_delta };
    static const mp_arg_t allowed[] = {
        { MP_QSTR_n_hyps, MP_ARG_INT, {.u_int = 1} },
        { MP_QSTR_alpha, MP_ARG_OBJ, {.u_obj = MP_OBJ_NULL} },
        { MP_QSTR_delta, MP_ARG_OBJ, {.u_obj = MP_OBJ_NULL} },
    };
    okws_obj_t *self = get_engine(pos_args[0]);
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed)];
    mp_arg_parse_all(n_args - 1, pos_args + 1, kw_args, MP_ARRAY_SIZE(allowed), allowed, args);
    if (args[ARG_n_hyps].u_int < 1 || args[ARG_n_hyps].u_int > OKWS_MAX_HYPS_C)
        mp_raise_ValueError(MP_ERROR_TEXT("n_hyps must be 1..8"));
    int pn;
    double pa, pd;
    okws_engine_get_verify(self->eng, &pn, &pa, &pd);
    double alpha = args[ARG_alpha].u_obj == MP_OBJ_NULL ? 0.0 : mp_obj_get_float(args[ARG_alpha].u_obj);
    double delta = args[ARG_delta].u_obj == MP_OBJ_NULL ? 0.0 : mp_obj_get_float(args[ARG_delta].u_obj);
    okws_engine_set_verify(self->eng, (int)args[ARG_n_hyps].u_int, alpha, delta);
    mp_obj_t t[3] = {MP_OBJ_NEW_SMALL_INT(pn), mp_obj_new_float((mp_float_t)pa),
                     mp_obj_new_float((mp_float_t)pd)};
    return mp_obj_new_tuple(3, t);
}
static MP_DEFINE_CONST_FUN_OBJ_KW(okws_set_verify_obj, 1, okws_set_verify);

// set_quality(clip_ratio=None, min_snr=None): enrollment recording limits for
// the next enroll_begin() (max share of clipped samples, min SNR in dB); None
// keeps the current value. Returns the new (clip_ratio, min_snr).
static mp_obj_t okws_set_quality(size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args)
{
    enum { ARG_clip_ratio, ARG_min_snr };
    static const mp_arg_t allowed[] = {
        { MP_QSTR_clip_ratio, MP_ARG_OBJ, {.u_obj = mp_const_none} },
        { MP_QSTR_min_snr, MP_ARG_OBJ, {.u_obj = mp_const_none} },
    };
    okws_obj_t *self = get_engine(pos_args[0]);
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed)];
    mp_arg_parse_all(n_args - 1, pos_args + 1, kw_args, MP_ARRAY_SIZE(allowed), allowed, args);
    double clip, snr;
    okws_engine_get_quality(self->eng, &clip, &snr);
    if (args[ARG_clip_ratio].u_obj != mp_const_none)
        clip = mp_obj_get_float(args[ARG_clip_ratio].u_obj);
    if (args[ARG_min_snr].u_obj != mp_const_none)
        snr = mp_obj_get_float(args[ARG_min_snr].u_obj);
    if (clip < 0.0 || clip > 1.0)
        mp_raise_ValueError(MP_ERROR_TEXT("clip_ratio must be in [0, 1]"));
    okws_engine_set_quality(self->eng, clip, snr);
    mp_obj_t t[2] = {mp_obj_new_float((mp_float_t)clip), mp_obj_new_float((mp_float_t)snr)};
    return mp_obj_new_tuple(2, t);
}
static MP_DEFINE_CONST_FUN_OBJ_KW(okws_set_quality_obj, 1, okws_set_quality);

static mp_obj_t okws_set_vad(mp_obj_t self_in, mp_obj_t on)
{
    okws_engine_set_vad(get_engine(self_in)->eng, mp_obj_is_true(on));
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(okws_set_vad_obj, okws_set_vad);

static mp_obj_t okws_reset(mp_obj_t self_in)
{
    okws_engine_reset(get_engine(self_in)->eng);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(okws_reset_obj, okws_reset);

// push(pcm) -> [(kw_id, score, threshold, start_ms, end_ms), ...]
static mp_obj_t okws_push(mp_obj_t self_in, mp_obj_t buf)
{
    okws_obj_t *self = get_engine(self_in);
    size_t n;
    const int16_t *pcm = pcm_arg(buf, &n);
    okws_event_t ev[OKWS_MAX_EVENTS];
    int k = okws_engine_push(self->eng, pcm, n, ev, OKWS_MAX_EVENTS);
    if (k < 0)
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("open_kws: inference failed"));
    return events_list(self, ev, k);
}
static MP_DEFINE_CONST_FUN_OBJ_2(okws_push_obj, okws_push);

static mp_obj_t okws_flush(mp_obj_t self_in)
{
    okws_obj_t *self = get_engine(self_in);
    okws_event_t ev[OKWS_MAX_EVENTS];
    int k = okws_engine_flush(self->eng, ev, OKWS_MAX_EVENTS);
    if (k < 0)
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("open_kws: inference failed"));
    return events_list(self, ev, k);
}
static MP_DEFINE_CONST_FUN_OBJ_1(okws_flush_obj, okws_flush);

static void store_float(mp_obj_t d, qstr k, float v)
{
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(k), mp_obj_new_float(v));
}

static mp_obj_t okws_stats(mp_obj_t self_in)
{
    okws_obj_t *self = get_engine(self_in);
    okws_stats_t s;
    okws_engine_stats(self->eng, &s);
    mp_obj_t d = mp_obj_new_dict(12);
    store_float(d, MP_QSTR_audio_ms, s.audio_ms);
    store_float(d, MP_QSTR_fe_ms, s.fe_ms);
    store_float(d, MP_QSTR_kpu_ms, s.kpu_ms);
    store_float(d, MP_QSTR_dec_ms, s.dec_ms);
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_n_infer), mp_obj_new_int(s.n_infer));
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_n_skip), mp_obj_new_int(s.n_skip));
    store_float(d, MP_QSTR_last_score, s.last_score);
    store_float(d, MP_QSTR_chunk_max, s.chunk_max);
    store_float(d, MP_QSTR_best_score, s.best_score);
    store_float(d, MP_QSTR_level, s.level_rms);
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_speech), mp_obj_new_bool(s.speech));

    size_t n_ids;
    mp_obj_t *ids;
    mp_obj_list_get(self->kw_ids, &n_ids, &ids);
    mp_obj_t kws = mp_obj_new_list(0, NULL);
    int n = okws_engine_keyword_count(self->eng);
    for (int i = 0; i < n; i++) {
        okws_kw_stats_t k;
        okws_engine_keyword_stats(self->eng, i, &k);
        mp_obj_t kd = mp_obj_new_dict(8);
        mp_obj_dict_store(kd, MP_OBJ_NEW_QSTR(MP_QSTR_kw_id),
                          (size_t)i < n_ids ? ids[i] : MP_OBJ_NEW_SMALL_INT(i));
        store_float(kd, MP_QSTR_last_score, k.last_score);
        store_float(kd, MP_QSTR_chunk_max, k.chunk_max);
        store_float(kd, MP_QSTR_best_score, k.best_score);
        store_float(kd, MP_QSTR_threshold, k.threshold);
        mp_obj_dict_store(kd, MP_OBJ_NEW_QSTR(MP_QSTR_verify), mp_obj_new_bool(k.verify));
        store_float(kd, MP_QSTR_last_weak, k.last_weak);
        mp_obj_dict_store(kd, MP_OBJ_NEW_QSTR(MP_QSTR_n_rejected), mp_obj_new_int(k.n_rejected));
        mp_obj_list_append(kws, kd);
    }
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_keywords), kws);
    return d;
}
static MP_DEFINE_CONST_FUN_OBJ_1(okws_stats_obj, okws_stats);

// features(pcm) -> ulab float [40, T]   (debug / alignment)
static mp_obj_t okws_features(mp_obj_t self_in, mp_obj_t buf)
{
    okws_obj_t *self = get_engine(self_in);
    size_t n;
    const int16_t *pcm = pcm_arg(buf, &n);
    int T = okws_features_frames(n);
    if (T <= 0)
        mp_raise_ValueError(MP_ERROR_TEXT("need at least 512 samples"));
    ndarray_obj_t *arr = ndarray_new_dense_ndarray(
        2, ndarray_shape_vector(0, 0, OKWS_N_MELS_PY, T), NDARRAY_FLOAT);
    if (okws_engine_features(self->eng, pcm, n, (float *)arr->array) != T)
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("open_kws: feature extraction failed"));
    return MP_OBJ_FROM_PTR(arr);
}
static MP_DEFINE_CONST_FUN_OBJ_2(okws_features_obj, okws_features);

// logp(pcm) -> ulab float [T', 59]   (debug / alignment)
static mp_obj_t okws_logp(mp_obj_t self_in, mp_obj_t buf)
{
    okws_obj_t *self = get_engine(self_in);
    size_t n;
    const int16_t *pcm = pcm_arg(buf, &n);
    int T = okws_logp_frames(n);
    if (T <= 0)
        mp_raise_ValueError(MP_ERROR_TEXT("need at least 512 samples"));
    float *tmp = m_new(float, (size_t)(T + 8) * OKWS_N_UNITS_PY);
    int got = okws_engine_logp(self->eng, pcm, n, tmp);
    if (got < 0)
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("open_kws: inference failed"));
    ndarray_obj_t *arr = ndarray_new_dense_ndarray(
        2, ndarray_shape_vector(0, 0, got, OKWS_N_UNITS_PY), NDARRAY_FLOAT);
    memcpy(arr->array, tmp, (size_t)got * OKWS_N_UNITS_PY * sizeof(float));
    m_del(float, tmp, (size_t)(T + 8) * OKWS_N_UNITS_PY);
    return MP_OBJ_FROM_PTR(arr);
}
static MP_DEFINE_CONST_FUN_OBJ_2(okws_logp_obj, okws_logp);

// ---------------------------------------------------------------- enrollment

// enroll_begin(use_beam=True)
static mp_obj_t okws_enroll_begin(size_t n_args, const mp_obj_t *args)
{
    okws_obj_t *self = get_engine(args[0]);
    int use_beam = n_args > 1 ? mp_obj_is_true(args[1]) : 1;
    if (okws_engine_enroll_begin(self->eng, use_beam) != 0)
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("open_kws: cannot start enrollment"));
    self->enroll_err = 0;
    self->enroll_done = false;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(okws_enroll_begin_obj, 1, 2, okws_enroll_begin);

// enroll_add(pcm, noise=None) -> (accepted, reason, metrics); noise is the
// ambient rms (e.g. open_kws.level() of silence) used as the SNR reference.
static mp_obj_t okws_enroll_add(size_t n_args, const mp_obj_t *args)
{
    okws_obj_t *self = get_engine(args[0]);
    mp_obj_t buf = args[1];
    double noise = (n_args > 2 && args[2] != mp_const_none) ? mp_obj_get_float(args[2]) : -1.0;
    size_t n;
    const int16_t *pcm = pcm_arg(buf, &n);
    okws_audio_metrics_t m;
    memset(&m, 0, sizeof(m));
    int r = okws_engine_enroll_add(self->eng, pcm, n, &m, noise);
    self->enroll_done = false;
    if (r < 0)
        mp_raise_msg(&mp_type_RuntimeError,
                     MP_ERROR_TEXT("open_kws: enrollment not started or inference failed"));
    const char *reason = okws_audio_reason_str(r);
    mp_obj_t t[3] = {
        mp_obj_new_bool(r == 0),
        mp_obj_new_str(reason, strlen(reason)),
        metrics_dict(&m),
    };
    return mp_obj_new_tuple(3, t);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(okws_enroll_add_obj, 2, 3, okws_enroll_add);

static mp_obj_t okws_enroll_count(mp_obj_t self_in)
{
    return mp_obj_new_int(okws_engine_enroll_count(get_engine(self_in)->eng));
}
static MP_DEFINE_CONST_FUN_OBJ_1(okws_enroll_count_obj, okws_enroll_count);

// enroll_step() -> (done, progress, total); errors surface in enroll_result()
static mp_obj_t okws_enroll_step(mp_obj_t self_in)
{
    okws_obj_t *self = get_engine(self_in);
    int done = 0, progress = 0, total = 1;
    self->enroll_err = okws_engine_enroll_step(self->eng, &done, &progress, &total);
    self->enroll_done = done != 0;
    mp_obj_t t[3] = {mp_obj_new_bool(done), mp_obj_new_int(progress), mp_obj_new_int(total)};
    return mp_obj_new_tuple(3, t);
}
static MP_DEFINE_CONST_FUN_OBJ_1(okws_enroll_step_obj, okws_enroll_step);

// enroll_result(kw_id="kw_0") -> dict in enroll.json format; raises ValueError
static mp_obj_t okws_enroll_result(size_t n_args, const mp_obj_t *args)
{
    okws_obj_t *self = get_engine(args[0]);
    mp_obj_t kw_id = n_args > 1 ? args[1] : MP_OBJ_NEW_QSTR(MP_QSTR_kw_0);
    if (!self->enroll_done)
        mp_raise_ValueError(MP_ERROR_TEXT("enrollment not finished"));
    if (self->enroll_err != 0) {
        const char *msg = okws_enroll_error_str(self->enroll_err);
        mp_raise_msg_varg(&mp_type_ValueError, MP_ERROR_TEXT("%s"), msg);
    }
    okws_enroll_result_t *r = m_new_obj(okws_enroll_result_t);
    if (okws_engine_enroll_result(self->eng, r) != 0 || r->n_hyps == 0)
        mp_raise_ValueError(MP_ERROR_TEXT("enrollment not finished"));

    mp_obj_t hyps = mp_obj_new_list(0, NULL);
    for (int i = 0; i < r->n_hyps; i++) {
        mp_obj_t units = mp_obj_new_list(0, NULL);
        for (int j = 0; j < r->lens[i]; j++)
            mp_obj_list_append(units, MP_OBJ_NEW_SMALL_INT(r->units[i][j]));
        mp_obj_t h = mp_obj_new_dict(2);
        mp_obj_dict_store(h, MP_OBJ_NEW_QSTR(MP_QSTR_units), units);
        mp_obj_dict_store(h, MP_OBJ_NEW_QSTR(MP_QSTR_weight), round_float(r->weights[i], 1e6));
        mp_obj_list_append(hyps, h);
    }
    mp_obj_t pos = mp_obj_new_list(0, NULL);
    for (int i = 0; i < r->n_pos; i++)
        mp_obj_list_append(pos, round_float(r->pos[i], 1e4));
    mp_obj_t calib = mp_obj_new_dict(5);
    mp_obj_dict_store(calib, MP_OBJ_NEW_QSTR(MP_QSTR_gamma), mp_obj_new_float(0.38f));
    mp_obj_dict_store(calib, MP_OBJ_NEW_QSTR(MP_QSTR_pos_scores), pos);
    mp_obj_dict_store(calib, MP_OBJ_NEW_QSTR(MP_QSTR_neg_mean), round_float(r->neg_mean, 1e4));
    mp_obj_dict_store(calib, MP_OBJ_NEW_QSTR(MP_QSTR_margin), round_float(r->margin, 1e4));
    mp_obj_dict_store(calib, MP_OBJ_NEW_QSTR(MP_QSTR_bg), mp_const_none);

    mp_obj_t gate = mp_obj_new_dict(2);
    mp_obj_dict_store(gate, MP_OBJ_NEW_QSTR(MP_QSTR_min_syllables), MP_OBJ_NEW_SMALL_INT(4));
    mp_obj_dict_store(gate, MP_OBJ_NEW_QSTR(MP_QSTR_n_syllables),
                      MP_OBJ_NEW_SMALL_INT(r->n_syllables));
    mp_obj_t audio = mp_obj_new_list(0, NULL);
    for (int i = 0; i < r->n_audio; i++) {
        mp_obj_t m = metrics_dict(&r->audio[i]);
        mp_obj_dict_store(m, MP_OBJ_NEW_QSTR(MP_QSTR_idx), MP_OBJ_NEW_SMALL_INT(i));
        mp_obj_dict_store(m, MP_OBJ_NEW_QSTR(MP_QSTR_ok), mp_const_true);
        mp_obj_list_append(audio, m);
    }
    mp_obj_t quality = mp_obj_new_dict(2);
    mp_obj_dict_store(quality, MP_OBJ_NEW_QSTR(MP_QSTR_gate), gate);
    mp_obj_dict_store(quality, MP_OBJ_NEW_QSTR(MP_QSTR_audio), audio);

    mp_obj_t d = mp_obj_new_dict(8);
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_kw_id), kw_id);
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_n_units), MP_OBJ_NEW_SMALL_INT(OKWS_N_UNITS_PY));
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_hypotheses), hyps);
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_threshold), round_float(r->threshold, 1e4));
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_verify_threshold),
                      mp_obj_new_float((mp_float_t)r->verify_threshold));
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_cooldown_ms), MP_OBJ_NEW_SMALL_INT(1500));
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_confirm_frames), MP_OBJ_NEW_SMALL_INT(2));
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_calib), calib);
    mp_obj_dict_store(d, MP_OBJ_NEW_QSTR(MP_QSTR_quality), quality);
    m_del_obj(okws_enroll_result_t, r);
    return d;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(okws_enroll_result_obj, 1, 2, okws_enroll_result);

// enroll_confusion() -> [(kw_id, margin, score, cut), ...] for every registered
// keyword, measured on this session's clips under the current set_verify() rule:
//   margin: its peak forward score - its threshold (> 0: first stage fires)
//   score:  its best verification score (None: no hypothesis alignable)
//   cut:    verify_threshold + delta; None when the keyword has no second stage
// The keyword would wake on the new word if margin > 0 and (cut is None or
// score > cut).
static mp_obj_t okws_enroll_confusion(mp_obj_t self_in)
{
    okws_obj_t *self = get_engine(self_in);
    okws_confusion_t c[OKWS_MAX_KEYWORDS_C];
    int n = okws_engine_enroll_confusion(self->eng, c, OKWS_MAX_KEYWORDS_C);
    if (n < 0)
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("open_kws: enrollment not started"));
    size_t n_ids;
    mp_obj_t *ids;
    mp_obj_list_get(self->kw_ids, &n_ids, &ids);
    mp_obj_t list = mp_obj_new_list(0, NULL);
    for (int i = 0; i < n; i++) {
        mp_obj_t t[4] = {
            (size_t)i < n_ids ? ids[i] : MP_OBJ_NEW_SMALL_INT(i),
            mp_obj_new_float((mp_float_t)c[i].margin),
            c[i].has_weak ? mp_obj_new_float((mp_float_t)c[i].weak) : mp_const_none,
            c[i].verify ? mp_obj_new_float((mp_float_t)c[i].verify_threshold) : mp_const_none,
        };
        mp_obj_list_append(list, mp_obj_new_tuple(4, t));
    }
    return list;
}
static MP_DEFINE_CONST_FUN_OBJ_1(okws_enroll_confusion_obj, okws_enroll_confusion);

static mp_obj_t okws_enroll_end(mp_obj_t self_in)
{
    okws_engine_enroll_end(get_engine(self_in)->eng);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(okws_enroll_end_obj, okws_enroll_end);

static const mp_rom_map_elem_t okws_locals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&okws_deinit_obj) },
    { MP_ROM_QSTR(MP_QSTR_deinit), MP_ROM_PTR(&okws_deinit_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_keyword), MP_ROM_PTR(&okws_set_keyword_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_keywords), MP_ROM_PTR(&okws_set_keywords_obj) },
    { MP_ROM_QSTR(MP_QSTR_add_keyword), MP_ROM_PTR(&okws_add_keyword_obj) },
    { MP_ROM_QSTR(MP_QSTR_clear_keywords), MP_ROM_PTR(&okws_clear_keywords_obj) },
    { MP_ROM_QSTR(MP_QSTR_keywords), MP_ROM_PTR(&okws_keywords_obj) },
    { MP_ROM_QSTR(MP_QSTR_has_keyword), MP_ROM_PTR(&okws_has_keyword_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_sensitivity), MP_ROM_PTR(&okws_set_sensitivity_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_vad), MP_ROM_PTR(&okws_set_vad_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_verify), MP_ROM_PTR(&okws_set_verify_obj) },
    { MP_ROM_QSTR(MP_QSTR_set_quality), MP_ROM_PTR(&okws_set_quality_obj) },
    { MP_ROM_QSTR(MP_QSTR_reset), MP_ROM_PTR(&okws_reset_obj) },
    { MP_ROM_QSTR(MP_QSTR_push), MP_ROM_PTR(&okws_push_obj) },
    { MP_ROM_QSTR(MP_QSTR_flush), MP_ROM_PTR(&okws_flush_obj) },
    { MP_ROM_QSTR(MP_QSTR_stats), MP_ROM_PTR(&okws_stats_obj) },
    { MP_ROM_QSTR(MP_QSTR_features), MP_ROM_PTR(&okws_features_obj) },
    { MP_ROM_QSTR(MP_QSTR_logp), MP_ROM_PTR(&okws_logp_obj) },
    { MP_ROM_QSTR(MP_QSTR_enroll_begin), MP_ROM_PTR(&okws_enroll_begin_obj) },
    { MP_ROM_QSTR(MP_QSTR_enroll_add), MP_ROM_PTR(&okws_enroll_add_obj) },
    { MP_ROM_QSTR(MP_QSTR_enroll_count), MP_ROM_PTR(&okws_enroll_count_obj) },
    { MP_ROM_QSTR(MP_QSTR_enroll_step), MP_ROM_PTR(&okws_enroll_step_obj) },
    { MP_ROM_QSTR(MP_QSTR_enroll_result), MP_ROM_PTR(&okws_enroll_result_obj) },
    { MP_ROM_QSTR(MP_QSTR_enroll_confusion), MP_ROM_PTR(&okws_enroll_confusion_obj) },
    { MP_ROM_QSTR(MP_QSTR_probe), MP_ROM_PTR(&okws_probe_obj) },
    { MP_ROM_QSTR(MP_QSTR_enroll_end), MP_ROM_PTR(&okws_enroll_end_obj) },
};
static MP_DEFINE_CONST_DICT(okws_locals, okws_locals_table);

static MP_DEFINE_CONST_OBJ_TYPE(okws_engine_type, MP_QSTR_Engine, MP_TYPE_FLAG_NONE,
                                make_new, okws_make_new, locals_dict, &okws_locals);

// ---------------------------------------------------------------- module functions

// trim(pcm) -> (begin, end) sample indices of the spoken part, or None
static mp_obj_t okws_trim_fn(mp_obj_t buf)
{
    size_t n, beg = 0, end = 0;
    const int16_t *pcm = pcm_arg(buf, &n);
    if (okws_trim(pcm, n, &beg, &end) != 0)
        return mp_const_none;
    mp_obj_t t[2] = {mp_obj_new_int_from_uint(beg), mp_obj_new_int_from_uint(end)};
    return mp_obj_new_tuple(2, t);
}
static MP_DEFINE_CONST_FUN_OBJ_1(okws_trim_obj, okws_trim_fn);

// rms(pcm) -> RMS level of int16 PCM normalised to [0, 1], DC offset removed
// (cheap per-chunk level for recording endpointing and level meters)
static mp_obj_t okws_rms_fn(mp_obj_t buf)
{
    size_t n;
    const int16_t *pcm = pcm_arg(buf, &n);
    double s = 0.0, e = 0.0;
    for (size_t i = 0; i < n; i++) {
        s += pcm[i];
        e += (double)pcm[i] * (double)pcm[i];
    }
    double var = n ? e / (double)n - (s / (double)n) * (s / (double)n) : 0.0;   // DC removed
    return mp_obj_new_float((mp_float_t)(sqrt(var > 0.0 ? var : 0.0) / 32768.0));
}
static MP_DEFINE_CONST_FUN_OBJ_1(okws_rms_obj, okws_rms_fn);

// level(pcm) -> (rms, peak) of int16 PCM normalised to [0, 1]; rms has the DC
// offset removed, peak is raw: near 1.0 means the input saturates
static mp_obj_t okws_level_fn(mp_obj_t buf)
{
    size_t n;
    const int16_t *pcm = pcm_arg(buf, &n);
    double s = 0.0, e = 0.0;
    int peak = 0;
    for (size_t i = 0; i < n; i++) {
        int v = pcm[i] < 0 ? -(int)pcm[i] : pcm[i];
        if (v > peak)
            peak = v;
        s += pcm[i];
        e += (double)pcm[i] * (double)pcm[i];
    }
    double var = n ? e / (double)n - (s / (double)n) * (s / (double)n) : 0.0;   // DC removed
    mp_obj_t t[2] = {mp_obj_new_float((mp_float_t)(sqrt(var > 0.0 ? var : 0.0) / 32768.0)),
                     mp_obj_new_float((mp_float_t)(peak / 32768.0))};
    return mp_obj_new_tuple(2, t);
}
static MP_DEFINE_CONST_FUN_OBJ_1(okws_level_obj, okws_level_fn);

// check_audio(pcm) -> (ok, reason, metrics)
static mp_obj_t okws_check_audio_fn(mp_obj_t buf)
{
    size_t n;
    const int16_t *pcm = pcm_arg(buf, &n);
    okws_audio_metrics_t m;
    int r = okws_check_audio(pcm, n, &m);
    const char *reason = okws_audio_reason_str(r);
    mp_obj_t t[3] = {mp_obj_new_bool(r == 0), mp_obj_new_str(reason, strlen(reason)),
                     metrics_dict(&m)};
    return mp_obj_new_tuple(3, t);
}
static MP_DEFINE_CONST_FUN_OBJ_1(okws_check_audio_obj, okws_check_audio_fn);

static const mp_rom_map_elem_t okws_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_open_kws) },
    { MP_ROM_QSTR(MP_QSTR_Engine), MP_ROM_PTR(&okws_engine_type) },
    { MP_ROM_QSTR(MP_QSTR_trim), MP_ROM_PTR(&okws_trim_obj) },
    { MP_ROM_QSTR(MP_QSTR_check_audio), MP_ROM_PTR(&okws_check_audio_obj) },
    { MP_ROM_QSTR(MP_QSTR_rms), MP_ROM_PTR(&okws_rms_obj) },
    { MP_ROM_QSTR(MP_QSTR_level), MP_ROM_PTR(&okws_level_obj) },
    { MP_ROM_QSTR(MP_QSTR_SAMPLE_RATE), MP_ROM_INT(16000) },
    { MP_ROM_QSTR(MP_QSTR_CHUNK), MP_ROM_INT(2560) },
    { MP_ROM_QSTR(MP_QSTR_MAX_KEYWORDS), MP_ROM_INT(OKWS_MAX_KEYWORDS_C) },
};
static MP_DEFINE_CONST_DICT(okws_module_globals, okws_module_globals_table);

const mp_obj_module_t open_kws_module = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&okws_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_open_kws, open_kws_module);
