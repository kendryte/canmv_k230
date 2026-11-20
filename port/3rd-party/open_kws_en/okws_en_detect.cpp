/* Copyright (c) 2026, Canaan Bright Sight Co., Ltd
 * SPDX-License-Identifier: BSD-3-Clause
 */
#include "okws_en_detect.h"

#include <algorithm>
#include <cmath>

#include "okws_en_time.h"

namespace okws_en {

bool EnergyVAD::operator()(const float *pcm, size_t n, double *energy)
{
    double e = 0.0;
    for (size_t i = 0; i < n; i++)
        e += (double)pcm[i] * (double)pcm[i];
    e = (n ? e / (double)n : 0.0) + 1e-12;
    if (energy)
        *energy = e;
    if (!has_noise_) {
        noise_ = e * OKWS_EN_VAD_INIT;
        has_noise_ = true;
    }
    noise_ = std::min(noise_ * OKWS_EN_VAD_RISE, std::max(e, 1e-12));
    bool speech = 10.0 * log10(e / std::max(noise_, 1e-12)) > OKWS_EN_VAD_TH_DB ||
                  e > OKWS_EN_VAD_ABS_RMS * OKWS_EN_VAD_ABS_RMS;
    hang_ = speech ? OKWS_EN_VAD_HANG : std::max(0, hang_ - 1);
    return speech || hang_ > 0;
}

Detector::Detector(const FrontendAssets &assets, Model *model) : fe_(assets), enc_(model)
{
    feats_.reserve(OKWS_EN_N_MELS * OKWS_EN_HOP_FRAMES * 2);
    logp_buf_.reserve((OKWS_EN_VERIFY_BUF + 1) * OKWS_EN_N_UNITS);
    logp_.reserve(OKWS_EN_N_UNITS * OKWS_EN_OUT_HOP * 2);
    reset();
}

static void reset_keyword(Keyword &k)
{
    k.scorer.reset();
    k.hit = 0;
    k.last_fire_ms = -1e9;
    k.best = k.last = k.chunk_max = k.last_weak = OKWS_EN_NEG;
    k.n_rejected = 0;
    k.t0_ms = 0.0;
    k.has_pending = false;
}

void Detector::set_keywords(std::vector<Keyword> kws)
{
    kws_ = std::move(kws);
    reset();
}

void Detector::add_keyword(Keyword kw)
{
    reset_keyword(kw);
    kws_.push_back(std::move(kw));
}

void Detector::reset()
{
    fe_.reset();
    enc_.reset();
    vad_.reset();
    for (auto &k : kws_)
        reset_keyword(k);
    logp_buf_.clear();
    t_frames_ = 0;
    skip_feat_ = 0;
    last_global_fire_ = -1e9;
    st_ = DetectStats();
}

// Second stage (detect.py _verify, generalised by VerifyParams): force-align
// the hypotheses on the buffered posteriors, see verify_score(). No language
// rule here -- the syllable grouping comes from the enrollment record.
bool Detector::verify(Keyword &k, double margin)
{
    if (!k.verify || k.hyp_verify.empty())
        return true;
    int T = buffered_frames();
    if (T < 4)
        return true;
    double v = OKWS_EN_NEG, weak = OKWS_EN_NEG;
    bool ok = verify_score(k.hyp_verify, vp_, logp_buf_.data(), T, margin, v, weak) &&
              v > k.verify_th + vp_.delta;
    k.last_weak = weak;
    if (!ok)
        k.n_rejected++;
    return ok;
}

void Detector::score_frames(const std::vector<float> &logp, std::vector<Event> &events)
{
    size_t T = logp.size() / OKWS_EN_N_UNITS;
    for (size_t t = 0; t < T; t++) {
        const float *lp = &logp[t * OKWS_EN_N_UNITS];
        t_frames_++;
        double ts = t_frames_ * OKWS_EN_FRAME_MS + skip_feat_ * OKWS_EN_FEAT_MS;
        logp_buf_.insert(logp_buf_.end(), lp, lp + OKWS_EN_N_UNITS);
        if (logp_buf_.size() > (size_t)OKWS_EN_VERIFY_BUF * OKWS_EN_N_UNITS)
            logp_buf_.erase(logp_buf_.begin(), logp_buf_.begin() + OKWS_EN_N_UNITS);
        for (size_t i = 0; i < kws_.size(); i++) {
            Keyword &k = kws_[i];
            // Tail check: release or drop the candidate held since tail_w frames.
            if (k.has_pending && t_frames_ - k.pending_frame >= tail_w_) {
                int n = std::min(tail_w_, buffered_frames());
                const float *tail = logp_buf_.data() + (size_t)(buffered_frames() - n) *
                                                           OKWS_EN_N_UNITS;
                if (tail_ok(tail, n, tail_theta_)) {
                    events.push_back(k.pending);
                    k.last_fire_ms = last_global_fire_ = ts;
                }
                k.has_pending = false;
            }
            int start = 0;
            double s = k.scorer.update(lp, &start);
            double th = k.threshold + bias_;
            k.best = std::max(k.best, s);
            k.last = s;
            k.chunk_max = std::max(k.chunk_max, s);
            st_.last_score = i == 0 ? s : std::max(st_.last_score, s);
            st_.chunk_max = std::max(st_.chunk_max, s);
            if (s > th) {
                k.hit++;
                // a vetoed trigger keeps hit counting, so it is retried next frame
                if (k.hit >= k.confirm && ts - k.last_fire_ms > k.cooldown_ms &&
                    ts - last_global_fire_ > k.cooldown_ms && !k.has_pending &&
                    verify(k, s - k.threshold)) {
                    Event ev{(int)i, s, th, k.last_weak, k.t0_ms + start * OKWS_EN_FRAME_MS, ts};
                    k.hit = 0;
                    // Must reset: the free-start score stays high in the pause
                    // after the word, and without a reset it fires again as
                    // soon as the cooldown expires.
                    k.scorer.reset();
                    k.t0_ms = ts;
                    if (k.tail) {
                        k.pending = ev;
                        k.pending_frame = t_frames_;
                        k.has_pending = true;
                    } else {
                        events.push_back(ev);
                        k.last_fire_ms = last_global_fire_ = ts;
                    }
                }
            } else {
                k.hit = 0;
            }
        }
    }
}

bool Detector::push(const float *pcm, size_t n, std::vector<Event> &events)
{
    st_.audio_ms += n * 1000.0 / OKWS_EN_SR;
    st_.chunk_max = OKWS_EN_NEG;
    for (auto &k : kws_)
        k.chunk_max = OKWS_EN_NEG;
    double e = 0.0;
    bool speech = use_vad_ ? vad_(pcm, n, &e) : true;
    if (!use_vad_) {
        for (size_t i = 0; i < n; i++)
            e += (double)pcm[i] * pcm[i];
        e = n ? e / n : 0.0;
    }
    st_.level_rms = sqrt(e);
    st_.speech = speech;

    feats_.clear();
    double t0 = now_ms();
    int k = fe_.push(pcm, n, feats_);
    double t1 = now_ms();
    st_.fe_ms += t1 - t0;
    if (!speech) {
        // Gated chunks still advance the PCM buffer (so a keyword onset is not
        // cut) but their features are dropped, exactly as detect.py does. The
        // dropped frames keep counting towards the clock.
        st_.n_skip++;
        skip_feat_ += k;
        return true;
    }

    logp_.clear();
    double kpu0 = enc_.kpu_ms();
    bool ok = enc_.push_frames(feats_.data(), k, logp_);
    st_.kpu_ms += enc_.kpu_ms() - kpu0;
    if (!ok)
        return false;
    if (!logp_.empty())
        st_.n_infer++;
    double t2 = now_ms();
    score_frames(logp_, events);
    st_.dec_ms += now_ms() - t2;
    return true;
}

bool Detector::flush(std::vector<Event> &events)
{
    logp_.clear();
    if (!enc_.flush(logp_))
        return false;
    score_frames(logp_, events);
    return true;
}

} // namespace okws_en
