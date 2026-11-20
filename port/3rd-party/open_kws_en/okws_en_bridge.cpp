/* Copyright (c) 2026, Canaan Bright Sight Co., Ltd
 * SPDX-License-Identifier: BSD-3-Clause
 */
#include "okws_en_bridge.h"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <memory>
#include <string>

#include "okws_en_detect.h"
#include "okws_en_enroll.h"
#include "okws_en_langpack.h"

using namespace okws_en;

struct okws_en_engine {
    FrontendAssets assets;
    LangPack langpack;
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

int copy_events(okws_en_engine *e, okws_en_event_t *ev, int max_ev)
{
    int n = 0;
    for (const Event &x : e->events) {
        if (n >= max_ev)
            break;
        ev[n].kw = x.kw;
        ev[n].score = (float)x.score;
        ev[n].threshold = (float)x.threshold;
        ev[n].weak = (float)x.weak;
        ev[n].has_weak = x.weak > OKWS_EN_NEG / 2;
        ev[n].start_ms = (float)x.start_ms;
        ev[n].end_ms = (float)x.end_ms;
        n++;
    }
    return n;
}

void copy_metrics(const AudioMetrics &a, okws_en_audio_metrics_t *m)
{
    m->dur = (float)a.dur;
    m->peak = (float)a.peak;
    m->clip_ratio = (float)a.clip_ratio;
    m->snr_db = (float)a.snr_db;
}

// Unpacks the flat (units, lens, weights, syls, n_syls) form of one keyword.
// Missing or empty syllable groupings are filled in from the language pack, so
// an enrollment record without verify.syllables still works.
bool build_hyps(const okws_en_engine *e, const int *units, const int *lens, const double *weights,
                int n_hyps, const int *syls, const int *n_syls, std::vector<Hypothesis> &out,
                std::vector<VerifyHyp> &vout)
{
    if (n_hyps <= 0 || n_hyps > OKWS_EN_MAX_HYPS_C)
        return false;
    const int *p = units;
    const int *s = syls;
    for (int i = 0; i < n_hyps; i++) {
        if (lens[i] <= 0 || lens[i] > OKWS_EN_MAX_UNITS)
            return false;
        for (int j = 0; j < lens[i]; j++)
            if (p[j] < 0 || p[j] >= OKWS_EN_N_UNITS)
                return false;
        std::vector<int> u(p, p + lens[i]);
        VerifyHyp vh;
        const int ns = (syls && n_syls) ? n_syls[i] : 0;
        if (ns > 0) {
            int sum = 0;
            for (int j = 0; j < ns; j++) {
                if (s[j] <= 0)
                    return false;
                sum += s[j];
            }
            if (sum != lens[i])
                return false; // a grouping must cover the hypothesis exactly
            vh.syls.assign(s, s + ns);
        } else if (!e->langpack.syllabify(u, vh.syls)) {
            vh.syls.assign(1, lens[i]); // no vowel nucleus: treat as one syllable
        }
        if (s)
            s += ns;
        vh.units = u;
        vout.push_back(std::move(vh));
        out.push_back({std::move(u), weights[i]});
        p += lens[i];
    }
    return true;
}

} // namespace

extern "C" okws_en_engine_t *okws_en_engine_create(const char *kmodel, const char *assets_dir,
                                                   const char **err)
{
    try {
        std::unique_ptr<Model> model = create_kmodel(kmodel, g_err);
        if (!model) {
            *err = g_err.c_str();
            return nullptr;
        }
        std::unique_ptr<okws_en_engine> e(new okws_en_engine());
        if (!e->assets.load(assets_dir, g_err)) {
            *err = g_err.c_str();
            return nullptr;
        }
        e->model = std::move(model);
        e->det.reset(new Detector(e->assets, e->model.get()));
        e->scratch.reserve(OKWS_EN_CHUNK * 2);
        e->events.reserve(8);
        return e.release();
    } catch (...) {
        g_err = "out of memory";
        *err = g_err.c_str();
        return nullptr;
    }
}

extern "C" {

void okws_en_engine_destroy(okws_en_engine_t *e)
{
    delete e; // enroller and detector go before the model (member order)
    shrink_model_pool();
}

int okws_en_engine_set_langpack(okws_en_engine_t *e, const int *nuclei, int n_nuclei,
                                const int *onsets, const int *onset_lens, int n_onsets,
                                int min_nuclei, int min_units)
{
    try {
        std::vector<int> nuc(nuclei, nuclei + (n_nuclei > 0 ? n_nuclei : 0));
        std::vector<std::vector<int>> ons;
        const int *p = onsets;
        for (int i = 0; i < n_onsets; i++) {
            int n = onset_lens[i];
            if (n < 0)
                return -1;
            ons.push_back(std::vector<int>(p, p + n));
            p += n;
        }
        return e->langpack.set(nuc, ons, min_nuclei, min_units) ? 0 : -1;
    } catch (...) {
        return -1;
    }
}

int okws_en_engine_add_keyword(okws_en_engine_t *e, const int *units, const int *lens,
                               const double *weights, int n_hyps, const int *syls,
                               const int *n_syls, double threshold, int cooldown_ms,
                               int confirm_frames, double verify_threshold, int tail_enabled)
{
    try {
        if ((int)e->det->keywords().size() >= OKWS_EN_MAX_KEYWORDS)
            return -1;
        std::vector<Hypothesis> hyps;
        std::vector<VerifyHyp> vhyps;
        if (!build_hyps(e, units, lens, weights, n_hyps, syls, n_syls, hyps, vhyps))
            return -1;
        Keyword k;
        k.id = "kw_" + std::to_string(e->det->keywords().size());
        k.scorer = KeywordScorer(hyps);
        k.threshold = threshold;
        k.cooldown_ms = cooldown_ms;
        k.confirm = confirm_frames;
        k.verify = !std::isnan(verify_threshold);
        if (k.verify)
            k.verify_th = verify_threshold;
        k.hyp_verify = std::move(vhyps);
        k.tail = tail_enabled != 0;
        e->det->add_keyword(std::move(k));
        return (int)e->det->keywords().size() - 1;
    } catch (...) {
        return -1;
    }
}

void okws_en_engine_clear_keywords(okws_en_engine_t *e)
{
    e->det->clear_keywords();
}

int okws_en_engine_keyword_count(okws_en_engine_t *e)
{
    return (int)e->det->keywords().size();
}

int okws_en_engine_keyword_stats(okws_en_engine_t *e, int idx, okws_en_kw_stats_t *st)
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

int okws_en_engine_has_keyword(okws_en_engine_t *e)
{
    return !e->det->keywords().empty();
}

void okws_en_engine_set_bias(okws_en_engine_t *e, double bias)
{
    e->det->set_bias(bias);
}

void okws_en_engine_set_verify(okws_en_engine_t *e, int n_hyps, double alpha, double delta)
{
    VerifyParams p;
    p.n_hyps = n_hyps < 1 ? 1 : n_hyps;
    p.alpha = alpha;
    p.delta = delta;
    e->det->set_verify_params(p);
}

void okws_en_engine_get_verify(okws_en_engine_t *e, int *n_hyps, double *alpha, double *delta)
{
    const VerifyParams &p = e->det->verify_params();
    *n_hyps = p.n_hyps;
    *alpha = p.alpha;
    *delta = p.delta;
}

void okws_en_engine_set_tail(okws_en_engine_t *e, int w, double theta)
{
    e->det->set_tail(w, theta);
}

void okws_en_engine_set_quality(okws_en_engine_t *e, double clip_ratio, double min_snr)
{
    e->quality.clip_ratio = clip_ratio;
    e->quality.min_snr = min_snr;
}

void okws_en_engine_get_quality(okws_en_engine_t *e, double *clip_ratio, double *min_snr)
{
    *clip_ratio = e->quality.clip_ratio;
    *min_snr = e->quality.min_snr;
}

void okws_en_engine_set_vad(okws_en_engine_t *e, int enable)
{
    e->det->set_vad(enable != 0);
}

void okws_en_engine_reset(okws_en_engine_t *e)
{
    e->det->reset();
}

int okws_en_engine_push(okws_en_engine_t *e, const int16_t *pcm, size_t n, okws_en_event_t *ev,
                        int max_ev)
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

int okws_en_engine_flush(okws_en_engine_t *e, okws_en_event_t *ev, int max_ev)
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

void okws_en_engine_stats(okws_en_engine_t *e, okws_en_stats_t *st)
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
    st->best_score =
        e->det->keywords().empty() ? (float)OKWS_EN_NEG : (float)e->det->keywords()[0].best;
    st->level_rms = (float)s.level_rms;
    st->speech = s.speech;
}

int okws_en_features_frames(size_t n)
{
    return LogMel::n_frames(n);
}

int okws_en_logp_frames(size_t n)
{
    int T = LogMel::n_frames(n);
    return ((T + 1) / 2 + 1) / 2;
}

int okws_en_engine_features(okws_en_engine_t *e, const int16_t *pcm, size_t n, float *out)
{
    try {
        std::vector<float> x, f;
        to_float(pcm, n, x);
        LogMel fe(e->assets);
        fe.compute(x.data(), n, f);
        int T = (int)(f.size() / OKWS_EN_N_MELS);
        for (int t = 0; t < T; t++)
            for (int m = 0; m < OKWS_EN_N_MELS; m++)
                out[(size_t)m * T + t] = f[(size_t)t * OKWS_EN_N_MELS + m];
        return T;
    } catch (...) {
        return -1;
    }
}

int okws_en_engine_logp(okws_en_engine_t *e, const int16_t *pcm, size_t n, float *out)
{
    try {
        std::vector<float> x, lp;
        to_float(pcm, n, x);
        LogMel fe(e->assets);
        Encoder enc(e->model.get());
        if (!enc.encode_offline(fe, x.data(), n, lp))
            return -1;
        memcpy(out, lp.data(), lp.size() * sizeof(float));
        return (int)(lp.size() / OKWS_EN_N_UNITS);
    } catch (...) {
        return -1;
    }
}

int okws_en_engine_syllabify(okws_en_engine_t *e, const int *units, int n, int *out, int max_out)
{
    try {
        if (n <= 0)
            return -1;
        for (int i = 0; i < n; i++)
            if (units[i] < 0 || units[i] >= OKWS_EN_N_UNITS)
                return -1;
        std::vector<int> lens;
        if (!e->langpack.syllabify(std::vector<int>(units, units + n), lens))
            return -1;
        int k = (int)lens.size() < max_out ? (int)lens.size() : max_out;
        for (int i = 0; i < k; i++)
            out[i] = lens[i];
        return (int)lens.size();
    } catch (...) {
        return -1;
    }
}

int okws_en_trim(const int16_t *pcm, size_t n, size_t *beg, size_t *end)
{
    try {
        std::vector<float> x;
        to_float(pcm, n, x);
        return trim_speech(x.data(), n, *beg, *end) ? 0 : -1;
    } catch (...) {
        return -1;
    }
}

int okws_en_check_audio(const int16_t *pcm, size_t n, okws_en_audio_metrics_t *m)
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

int okws_en_engine_enroll_begin(okws_en_engine_t *e, int use_beam)
{
    try {
        e->enroller.reset(
            new Enroller(e->assets, e->model.get(), e->langpack, use_beam != 0, e->quality));
        return 0;
    } catch (...) {
        return -1;
    }
}

int okws_en_engine_enroll_add(okws_en_engine_t *e, const int16_t *pcm, size_t n,
                              okws_en_audio_metrics_t *m, double noise_rms)
{
    if (!e->enroller || e->enroller->count() >= OKWS_EN_MAX_CLIPS_C)
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

int okws_en_engine_enroll_count(okws_en_engine_t *e)
{
    return e->enroller ? e->enroller->count() : 0;
}

int okws_en_engine_enroll_step(okws_en_engine_t *e, int *done, int *progress, int *total)
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

int okws_en_engine_enroll_result(okws_en_engine_t *e, okws_en_enroll_result_t *out)
{
    if (!e->enroller)
        return -1;
    const EnrollResult &r = e->enroller->result();
    memset(out, 0, sizeof(*out));
    out->n_hyps = (int)std::min<size_t>(r.hyps.size(), OKWS_EN_MAX_HYPS_C);
    for (int i = 0; i < out->n_hyps; i++) {
        const auto &u = r.hyps[i].units;
        out->lens[i] = (int)std::min<size_t>(u.size(), OKWS_EN_MAX_UNITS_C);
        for (int j = 0; j < out->lens[i]; j++)
            out->units[i][j] = u[j];
        out->weights[i] = r.hyps[i].weight;
        if ((size_t)i < r.hyp_syls.size()) {
            const auto &s = r.hyp_syls[i];
            out->n_syls[i] = (int)std::min<size_t>(s.size(), OKWS_EN_MAX_UNITS_C);
            for (int j = 0; j < out->n_syls[i]; j++)
                out->syls[i][j] = s[j];
        }
    }
    out->threshold = r.threshold;
    out->verify_threshold = r.verify_threshold;
    out->neg_mean = r.neg_mean;
    out->margin = r.margin;
    out->n_pos = (int)std::min<size_t>(r.pos.size(), OKWS_EN_MAX_CLIPS_C);
    for (int i = 0; i < out->n_pos; i++)
        out->pos[i] = r.pos[i];
    out->n_nuclei = r.n_nuclei;
    out->n_main_units = r.n_units;
    out->n_audio = (int)std::min<size_t>(r.audio.size(), OKWS_EN_MAX_CLIPS_C);
    for (int i = 0; i < out->n_audio; i++)
        copy_metrics(r.audio[i], &out->audio[i]);
    return 0;
}

void okws_en_engine_enroll_end(okws_en_engine_t *e)
{
    e->enroller.reset();
}

int okws_en_engine_enroll_confusion(okws_en_engine_t *e, okws_en_confusion_t *out, int max)
{
    if (!e->enroller)
        return -1;
    try {
        const auto &kws = e->det->keywords();
        int n = 0;
        for (const auto &k : kws) {
            if (n >= max)
                break;
            okws_en_confusion_t &c = out[n++];
            bool has = false;
            e->enroller->confusion_over_clips(k.scorer, k.threshold, k.hyp_verify,
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

int okws_en_engine_probe(okws_en_engine_t *e, const int *units, const int *lens,
                         const double *weights, int n_hyps, const int *syls, const int *n_syls,
                         double threshold, double verify_threshold, const int16_t *pcm, size_t n,
                         double *margin, double *weak, int *has_weak, double *cut)
{
    try {
        std::vector<Hypothesis> hyps;
        std::vector<VerifyHyp> vhyps;
        if (!build_hyps(e, units, lens, weights, n_hyps, syls, n_syls, hyps, vhyps))
            return -1;
        std::vector<float> x, lp;
        to_float(pcm, n, x);
        LogMel fe(e->assets);
        Encoder enc(e->model.get());
        if (!enc.encode_offline(fe, x.data(), n, lp))
            return -1;
        int T = (int)(lp.size() / OKWS_EN_N_UNITS);
        KeywordScorer sc(hyps);
        *margin = sc.peak(lp.data(), T) - threshold;
        const VerifyParams &vp = e->det->verify_params();
        double w;
        *has_weak = verify_score(vhyps, vp, lp.data(), T, *margin, *weak, w);
        *cut = verify_threshold + vp.delta; // NAN when the candidate has no verification
        return 0;
    } catch (...) {
        return -1;
    }
}

const char *okws_en_audio_reason_str(int reason)
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

const char *okws_en_enroll_error_str(int err)
{
    switch (err) {
    case ENROLL_OK: return "ok";
    case ENROLL_TOO_FEW: return "need at least 2 recordings";
    case ENROLL_NO_HYP: return "no phoneme sequence decoded";
    case ENROLL_TOO_SHORT: return "wake word too short";
    case ENROLL_INCONSISTENT: return "recordings inconsistent";
    default: return "model error";
    }
}

} // extern "C"
