/* Copyright (c) 2026, Canaan Bright Sight Co., Ltd
 * SPDX-License-Identifier: BSD-3-Clause
 */
#include "okws_bridge.h"

#include <cmath>
#include <cstring>
#include <memory>
#include <string>

#include "okws_detect.h"
#include "okws_enroll.h"

using namespace okws;

struct okws_engine {
    FrontendAssets assets;
    std::unique_ptr<Model> model;
    std::unique_ptr<Detector> det;
    std::unique_ptr<Enroller> enroller;
    QualityParams quality;
    std::vector<float> scratch;
    std::vector<Event> events;
};

namespace {

std::string g_err;

void to_float(const int16_t *pcm, size_t n, std::vector<float> &out)
{
    out.resize(n);
    for (size_t i = 0; i < n; i++)
        out[i] = (float)pcm[i] / 32768.0f;
}

int copy_events(okws_engine *e, okws_event_t *ev, int max_ev)
{
    int n = 0;
    for (const Event &x : e->events) {
        if (n >= max_ev)
            break;
        ev[n++] = {x.kw, (float)x.score, (float)x.threshold, (float)x.start_ms, (float)x.end_ms};
    }
    return n;
}

void copy_metrics(const AudioMetrics &a, okws_audio_metrics_t *m)
{
    m->dur = (float)a.dur;
    m->peak = (float)a.peak;
    m->clip_ratio = (float)a.clip_ratio;
    m->snr_db = (float)a.snr_db;
}

} // namespace

static okws_engine_t *engine_create_with_model(std::unique_ptr<Model> model,
                                               const char *assets_dir, const char **err)
{
    try {
        std::unique_ptr<okws_engine> e(new okws_engine());
        if (!e->assets.load(assets_dir, g_err)) {
            *err = g_err.c_str();
            return nullptr;
        }
        e->model = std::move(model);
        e->det.reset(new Detector(e->assets, e->model.get()));
        e->scratch.reserve(OKWS_CHUNK * 2);
        e->events.reserve(8);
        return e.release();
    } catch (...) {
        g_err = "out of memory";
        *err = g_err.c_str();
        return nullptr;
    }
}

extern "C" okws_engine_t *okws_engine_create(const char *kmodel, const char *assets_dir,
                                             const char **err)
{
    try {
        std::unique_ptr<Model> model = create_kmodel(kmodel, g_err);
        if (!model) {
            *err = g_err.c_str();
            return nullptr;
        }
        return engine_create_with_model(std::move(model), assets_dir, err);
    } catch (...) {
        g_err = "out of memory";
        *err = g_err.c_str();
        return nullptr;
    }
}

extern "C" {

void okws_engine_destroy(okws_engine_t *e)
{
    delete e; // enroller and detector go before the model (member order)
    shrink_model_pool();
}

int okws_engine_add_keyword(okws_engine_t *e, const int *units, const int *lens,
                            const double *weights, int n_hyps, double threshold,
                            int cooldown_ms, int confirm_frames, double verify_threshold)
{
    try {
        if (n_hyps <= 0 || n_hyps > OKWS_MAX_HYPS_C ||
            (int)e->det->keywords().size() >= OKWS_MAX_KEYWORDS)
            return -1;
        std::vector<Hypothesis> hyps;
        const int *p = units;
        for (int i = 0; i < n_hyps; i++) {
            if (lens[i] <= 0 || lens[i] > OKWS_MAX_UNITS)
                return -1;
            for (int j = 0; j < lens[i]; j++)
                if (p[j] < 0 || p[j] >= OKWS_N_UNITS)
                    return -1;
            hyps.push_back({std::vector<int>(p, p + lens[i]), weights[i]});
            p += lens[i];
        }
        Keyword k;
        k.id = "kw_" + std::to_string(e->det->keywords().size());
        k.scorer = KeywordScorer(hyps);
        k.threshold = threshold;
        k.cooldown_ms = cooldown_ms;
        k.confirm = confirm_frames;
        k.verify = !std::isnan(verify_threshold);
        if (k.verify)
            k.verify_th = verify_threshold;
        for (const auto &h : hyps)
            k.hyp_units.push_back(h.units);
        e->det->add_keyword(std::move(k));
        return (int)e->det->keywords().size() - 1;
    } catch (...) {
        return -1;
    }
}

int okws_engine_set_keyword(okws_engine_t *e, const int *units, const int *lens,
                            const double *weights, int n_hyps, double threshold,
                            int cooldown_ms, int confirm_frames, double verify_threshold)
{
    e->det->clear_keywords();
    if (n_hyps == 0)
        return 0;
    int r = okws_engine_add_keyword(e, units, lens, weights, n_hyps, threshold, cooldown_ms,
                                    confirm_frames, verify_threshold);
    e->det->reset();
    return r < 0 ? -1 : 0;
}

void okws_engine_clear_keywords(okws_engine_t *e)
{
    e->det->clear_keywords();
}

int okws_engine_keyword_count(okws_engine_t *e)
{
    return (int)e->det->keywords().size();
}

int okws_engine_keyword_stats(okws_engine_t *e, int idx, okws_kw_stats_t *st)
{
    const auto &kws = e->det->keywords();
    if (idx < 0 || idx >= (int)kws.size())
        return -1;
    st->last_score = (float)kws[idx].last;
    st->chunk_max = (float)kws[idx].chunk_max;
    st->best_score = (float)kws[idx].best;
    st->threshold = (float)kws[idx].threshold;
    st->last_weak = (float)kws[idx].last_weak;
    st->n_rejected = kws[idx].n_rejected;
    st->verify = kws[idx].verify;
    return 0;
}

int okws_engine_has_keyword(okws_engine_t *e)
{
    return !e->det->keywords().empty();
}

void okws_engine_set_bias(okws_engine_t *e, double bias)
{
    e->det->set_bias(bias);
}

void okws_engine_set_verify(okws_engine_t *e, int n_hyps, double alpha, double delta)
{
    VerifyParams p;
    p.n_hyps = n_hyps < 1 ? 1 : n_hyps;
    p.alpha = alpha;
    p.delta = delta;
    e->det->set_verify_params(p);
}

void okws_engine_get_verify(okws_engine_t *e, int *n_hyps, double *alpha, double *delta)
{
    const VerifyParams &p = e->det->verify_params();
    *n_hyps = p.n_hyps;
    *alpha = p.alpha;
    *delta = p.delta;
}

void okws_engine_set_quality(okws_engine_t *e, double clip_ratio, double min_snr)
{
    e->quality.clip_ratio = clip_ratio;
    e->quality.min_snr = min_snr;
}

void okws_engine_get_quality(okws_engine_t *e, double *clip_ratio, double *min_snr)
{
    *clip_ratio = e->quality.clip_ratio;
    *min_snr = e->quality.min_snr;
}

void okws_engine_set_vad(okws_engine_t *e, int enable)
{
    e->det->set_vad(enable != 0);
}

void okws_engine_reset(okws_engine_t *e)
{
    e->det->reset();
}

int okws_engine_push(okws_engine_t *e, const int16_t *pcm, size_t n, okws_event_t *ev, int max_ev)
{
    try {
        to_float(pcm, n, e->scratch);
        e->events.clear();
        if (!e->det->push(e->scratch.data(), n, e->events))
            return -1;
        return copy_events(e, ev, max_ev);
    } catch (...) {
        return -1;
    }
}

int okws_engine_flush(okws_engine_t *e, okws_event_t *ev, int max_ev)
{
    try {
        e->events.clear();
        if (!e->det->flush(e->events))
            return -1;
        return copy_events(e, ev, max_ev);
    } catch (...) {
        return -1;
    }
}

void okws_engine_stats(okws_engine_t *e, okws_stats_t *st)
{
    const DetectStats &s = e->det->stats();
    st->audio_ms = (float)s.audio_ms;
    st->fe_ms = (float)s.fe_ms;
    st->kpu_ms = (float)s.kpu_ms;
    st->dec_ms = (float)s.dec_ms;
    st->n_infer = s.n_infer;
    st->n_skip = s.n_skip;
    st->last_score = (float)s.last_score;
    st->chunk_max = (float)s.chunk_max;
    st->best_score = e->det->keywords().empty() ? (float)OKWS_NEG : (float)e->det->keywords()[0].best;
    st->level_rms = (float)s.level_rms;
    st->speech = s.speech;
}

int okws_features_frames(size_t n)
{
    return LogMel::n_frames(n);
}

int okws_logp_frames(size_t n)
{
    int T = LogMel::n_frames(n);
    return ((T + 1) / 2 + 1) / 2;
}

int okws_engine_features(okws_engine_t *e, const int16_t *pcm, size_t n, float *out)
{
    try {
        std::vector<float> x, f;
        to_float(pcm, n, x);
        LogMel fe(e->assets);
        fe.compute(x.data(), n, f);
        int T = (int)(f.size() / OKWS_N_MELS);
        for (int t = 0; t < T; t++)
            for (int m = 0; m < OKWS_N_MELS; m++)
                out[(size_t)m * T + t] = f[(size_t)t * OKWS_N_MELS + m];
        return T;
    } catch (...) {
        return -1;
    }
}

int okws_engine_logp(okws_engine_t *e, const int16_t *pcm, size_t n, float *out)
{
    try {
        std::vector<float> x, lp;
        to_float(pcm, n, x);
        LogMel fe(e->assets);
        Encoder enc(e->model.get());
        if (!enc.encode_offline(fe, x.data(), n, lp))
            return -1;
        memcpy(out, lp.data(), lp.size() * sizeof(float));
        return (int)(lp.size() / OKWS_N_UNITS);
    } catch (...) {
        return -1;
    }
}

int okws_trim(const int16_t *pcm, size_t n, size_t *beg, size_t *end)
{
    try {
        std::vector<float> x;
        to_float(pcm, n, x);
        return trim_speech(x.data(), n, *beg, *end) ? 0 : -1;
    } catch (...) {
        return -1;
    }
}

int okws_check_audio(const int16_t *pcm, size_t n, okws_audio_metrics_t *m)
{
    try {
        std::vector<float> x;
        to_float(pcm, n, x);
        AudioMetrics a;
        int r = check_audio(x.data(), n, a);
        copy_metrics(a, m);
        return r;
    } catch (...) {
        return -1;
    }
}

int okws_engine_enroll_begin(okws_engine_t *e, int use_beam)
{
    try {
        e->enroller.reset(new Enroller(e->assets, e->model.get(), use_beam != 0, e->quality));
        return 0;
    } catch (...) {
        return -1;
    }
}

int okws_engine_enroll_add(okws_engine_t *e, const int16_t *pcm, size_t n, okws_audio_metrics_t *m,
                           double noise_rms)
{
    if (!e->enroller || e->enroller->count() >= OKWS_MAX_CLIPS_C)
        return -1;
    try {
        std::vector<float> x;
        to_float(pcm, n, x);
        AudioMetrics a;
        bool model_ok = true;
        int r = e->enroller->add(x.data(), n, a, model_ok, noise_rms);
        copy_metrics(a, m);
        return model_ok ? r : -1;
    } catch (...) {
        return -1;
    }
}

int okws_engine_enroll_count(okws_engine_t *e)
{
    return e->enroller ? e->enroller->count() : 0;
}

int okws_engine_enroll_step(okws_engine_t *e, int *done, int *progress, int *total)
{
    if (!e->enroller)
        return ENROLL_TOO_FEW;
    try {
        bool d = false;
        EnrollError err = ENROLL_OK;
        e->enroller->step(d, *progress, *total, err);
        *done = d;
        return err;
    } catch (...) {
        *done = 1;
        return ENROLL_MODEL;
    }
}

int okws_engine_enroll_result(okws_engine_t *e, okws_enroll_result_t *out)
{
    if (!e->enroller)
        return -1;
    const EnrollResult &r = e->enroller->result();
    memset(out, 0, sizeof(*out));
    out->n_hyps = (int)std::min<size_t>(r.hyps.size(), OKWS_MAX_HYPS_C);
    for (int i = 0; i < out->n_hyps; i++) {
        const auto &u = r.hyps[i].units;
        out->lens[i] = (int)std::min<size_t>(u.size(), OKWS_MAX_UNITS_C);
        for (int j = 0; j < out->lens[i]; j++)
            out->units[i][j] = u[j];
        out->weights[i] = r.hyps[i].weight;
    }
    out->threshold = r.threshold;
    out->verify_threshold = r.verify_threshold;
    out->neg_mean = r.neg_mean;
    out->margin = r.margin;
    out->n_pos = (int)std::min<size_t>(r.pos.size(), OKWS_MAX_CLIPS_C);
    for (int i = 0; i < out->n_pos; i++)
        out->pos[i] = r.pos[i];
    out->n_syllables = r.n_syllables;
    out->n_audio = (int)std::min<size_t>(r.audio.size(), OKWS_MAX_CLIPS_C);
    for (int i = 0; i < out->n_audio; i++)
        copy_metrics(r.audio[i], &out->audio[i]);
    return 0;
}

void okws_engine_enroll_end(okws_engine_t *e)
{
    e->enroller.reset();
}

int okws_engine_enroll_confusion(okws_engine_t *e, okws_confusion_t *out, int max)
{
    if (!e->enroller)
        return -1;
    try {
        const auto &kws = e->det->keywords();
        int n = 0;
        for (const auto &k : kws) {
            if (n >= max)
                break;
            okws_confusion_t &c = out[n++];
            bool has = false;
            e->enroller->confusion_over_clips(k.scorer, k.threshold, k.hyp_units,
                                              e->det->verify_params(), c.margin, c.weak, has);
            c.has_weak = has;
            c.verify = k.verify;
            c.verify_threshold = k.verify_th + e->det->verify_params().delta;
        }
        return n;
    } catch (...) {
        return -1;
    }
}

int okws_engine_probe(okws_engine_t *e, const int *units, const int *lens, const double *weights,
                      int n_hyps, double threshold, double verify_threshold, const int16_t *pcm,
                      size_t n, double *margin, double *weak, int *has_weak, double *cut)
{
    try {
        if (n_hyps <= 0 || n_hyps > OKWS_MAX_HYPS_C)
            return -1;
        std::vector<Hypothesis> hyps;
        const int *p = units;
        for (int i = 0; i < n_hyps; i++) {
            if (lens[i] <= 0 || lens[i] > OKWS_MAX_UNITS)
                return -1;
            for (int j = 0; j < lens[i]; j++)
                if (p[j] < 0 || p[j] >= OKWS_N_UNITS)
                    return -1;
            hyps.push_back({std::vector<int>(p, p + lens[i]), weights[i]});
            p += lens[i];
        }
        std::vector<float> x, lp;
        to_float(pcm, n, x);
        LogMel fe(e->assets);
        Encoder enc(e->model.get());
        if (!enc.encode_offline(fe, x.data(), n, lp))
            return -1;
        int T = (int)(lp.size() / OKWS_N_UNITS);
        KeywordScorer sc(hyps);
        *margin = sc.peak(lp.data(), T) - threshold;
        std::vector<std::vector<int>> hu;
        for (const auto &h : hyps)
            hu.push_back(h.units);
        const VerifyParams &vp = e->det->verify_params();
        double w;
        *has_weak = verify_score(hu, vp, lp.data(), T, *margin, *weak, w);
        *cut = verify_threshold + vp.delta; // NAN when the candidate has no verification
        return 0;
    } catch (...) {
        return -1;
    }
}

const char *okws_audio_reason_str(int reason)
{
    switch (reason) {
    case AUDIO_OK: return "ok";
    case AUDIO_TOO_SHORT: return "too short";
    case AUDIO_TOO_LONG: return "too long";
    case AUDIO_TOO_QUIET: return "too quiet";
    case AUDIO_CLIPPED: return "clipped";
    case AUDIO_NOISY: return "too noisy";
    case AUDIO_NO_SPEECH: return "no speech";
    default: return "model error";
    }
}

const char *okws_enroll_error_str(int err)
{
    switch (err) {
    case ENROLL_OK: return "ok";
    case ENROLL_TOO_FEW: return "need at least 2 recordings";
    case ENROLL_NO_HYP: return "no unit sequence decoded";
    case ENROLL_TOO_SHORT: return "keyword too short";
    case ENROLL_INCONSISTENT: return "recordings inconsistent";
    default: return "model error";
    }
}

} // extern "C"
