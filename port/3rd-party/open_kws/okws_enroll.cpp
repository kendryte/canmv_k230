/* Copyright (c) 2026, Canaan Bright Sight Co., Ltd
 * SPDX-License-Identifier: BSD-3-Clause
 */
#include "okws_enroll.h"

#include <algorithm>
#include <cmath>
#include <map>

namespace okws {

namespace {

double round_n(double x, int nd)
{
    double p = pow(10.0, nd);
    return std::round(x * p) / p;
}

bool is_initial(int u)
{
    return u >= 3 && u <= 23; // units.txt: b .. zh
}

} // namespace

double quantile(std::vector<double> v, double q)
{
    if (v.empty())
        return 0.0;
    std::sort(v.begin(), v.end());
    double pos = q * (double)(v.size() - 1);
    size_t lo = (size_t)floor(pos);
    size_t hi = std::min(lo + 1, v.size() - 1);
    return v[lo] + (v[hi] - v[lo]) * (pos - (double)lo);
}

static double mean_of(const float *pcm, size_t n)
{
    double s = 0.0;
    for (size_t i = 0; i < n; i++)
        s += pcm[i];
    return n ? s / (double)n : 0.0;
}

AudioReason check_audio(const float *pcm, size_t n, AudioMetrics &m, const QualityParams &q,
                        double noise_rms)
{
    m = AudioMetrics();
    m.dur = (double)n / OKWS_SR;
    size_t clipped = 0;
    for (size_t i = 0; i < n; i++) {
        double a = fabs((double)pcm[i]);
        m.peak = std::max(m.peak, a);
        if (a >= 0.999)
            clipped++;
    }
    m.clip_ratio = n ? (double)clipped / n : 1.0;
    if (n > 1600) {
        // SNR = loud speech frames (85th percentile energy) against the noise.
        // A DC offset of the ADC is removed first, otherwise it counts as noise.
        // The noise reference is the ambient level measured before recording
        // when given; else the quiet frames (15th percentile) of the clip
        // itself, as in enroll.py, which mistakes speech for noise when the
        // clip is mostly speech.
        const int frame = 400, hop = 160;
        const double dc = mean_of(pcm, n);
        size_t nf = n >= (size_t)frame ? (n - frame) / hop + 1 : 1;
        std::vector<double> e(nf);
        for (size_t f = 0; f < nf; f++) {
            double s = 0.0;
            for (int i = 0; i < frame; i++) {
                double x = pcm[f * hop + i] - dc;
                s += x * x;
            }
            e[f] = s / frame + 1e-12;
        }
        double ref = noise_rms > 0.0 ? noise_rms * noise_rms : quantile(e, 0.15);
        m.snr_db = 10.0 * log10(quantile(e, 0.85) / std::max(ref, 1e-12));
    }
    if (m.dur < OKWS_MIN_DUR)
        return AUDIO_TOO_SHORT;
    if (m.dur > OKWS_MAX_DUR)
        return AUDIO_TOO_LONG;
    if (m.peak < 0.01)
        return AUDIO_TOO_QUIET;
    if (m.clip_ratio > q.clip_ratio)
        return AUDIO_CLIPPED;
    if (m.snr_db < q.min_snr)
        return AUDIO_NOISY;
    return AUDIO_OK;
}

bool trim_speech(const float *pcm, size_t n, size_t &beg, size_t &end)
{
    const size_t F = OKWS_TRIM_FRAME;
    size_t nf = n / F;
    if (nf == 0)
        return false;
    const double dc = mean_of(pcm, n);    // ADC DC offset is not signal energy
    std::vector<double> e(nf);
    for (size_t f = 0; f < nf; f++) {
        double s = 0.0;
        for (size_t i = 0; i < F; i++) {
            double x = pcm[f * F + i] - dc;
            s += x * x;
        }
        e[f] = s / F;
    }
    double noise = quantile(e, OKWS_TRIM_NOISE_Q);
    double th = std::max(noise * pow(10.0, OKWS_TRIM_RATIO_DB / 10.0),
                         OKWS_TRIM_ABS_RMS * OKWS_TRIM_ABS_RMS);
    long first = -1, last = -1;
    for (size_t f = 0; f < nf; f++) {
        if (e[f] > th) {
            if (first < 0)
                first = (long)f;
            last = (long)f;
        }
    }
    if (first < 0)
        return false;

    long N = (long)n;
    long b = std::max(0L, first * (long)F - OKWS_TRIM_PAD);
    long en = std::min(N, (last + 1) * (long)F + OKWS_TRIM_PAD);
    const long max_len = (long)(OKWS_MAX_DUR * OKWS_SR);
    const long min_len = (long)(OKWS_MIN_DUR * OKWS_SR);
    if (en - b > max_len) {
        // Too long: centre a max-length window on the speech energy centroid.
        double se = 0.0, sc = 0.0;
        for (long f = first; f <= last; f++) {
            se += e[f];
            sc += e[f] * (double)f;
        }
        long centre = (long)((sc / se + 0.5) * (double)F);
        b = std::min(std::max(0L, centre - max_len / 2), N - max_len);
        en = b + max_len;
    } else if (en - b < min_len) {
        long need = min_len - (en - b);
        b -= need / 2;
        en += need - need / 2;
        if (b < 0) {
            en -= b;
            b = 0;
        }
        if (en > N) {
            b -= en - N;
            en = N;
        }
        b = std::max(0L, b);
    }
    beg = (size_t)b;
    end = (size_t)en;
    return true;
}

std::vector<std::vector<float>> shuffled_negatives(const std::vector<float> &pcm)
{
    const size_t overlap = 160;
    std::vector<std::vector<float>> negs;
    size_t L = pcm.size() / 3;
    if (L <= overlap)
        return negs;
    int perm[3] = {0, 1, 2};
    while (std::next_permutation(perm, perm + 3)) { // lexicographic, identity skipped
        std::vector<float> seg;
        seg.reserve(3 * L);
        for (int k = 0; k < 3; k++) {
            const float *p = &pcm[perm[k] * L];
            for (size_t i = 0; i < L; i++) {
                float x = p[i];
                if (k > 0 && i < overlap)
                    x *= (float)((double)i / (double)(overlap - 1)); // np.linspace(0, 1, 160)
                seg.push_back(x);
            }
        }
        negs.push_back(std::move(seg));
    }
    return negs;
}

std::vector<Hypothesis> merge_hyps(const std::vector<Candidate> &pool, int max_hyps)
{
    // Insertion-ordered dedupe keeping the best score (Python dict semantics).
    std::vector<Candidate> best;
    std::map<std::vector<int>, size_t> index;
    for (const auto &c : pool) {
        auto it = index.find(c.units);
        if (it == index.end()) {
            index.emplace(c.units, best.size());
            best.push_back(c);
        } else if (c.logp > best[it->second].logp) {
            best[it->second].logp = c.logp;
        }
    }
    std::stable_sort(best.begin(), best.end(),
                     [](const Candidate &a, const Candidate &b) { return a.logp > b.logp; });
    if ((int)best.size() > max_hyps)
        best.resize(max_hyps);
    std::vector<Hypothesis> hyps;
    double sum = 0.0;
    for (const auto &c : best) {
        double w = 1.0 / std::max(fabs(c.logp), 1e-6);
        hyps.push_back({c.units, w});
        sum += w;
    }
    for (auto &h : hyps)
        h.weight = round_n(h.weight / sum, 6);
    return hyps;
}

int count_syllables(const std::vector<Hypothesis> &hyps)
{
    int best = 0;
    for (const auto &h : hyps) {
        int n = 0;
        for (int u : h.units)
            if (!is_initial(u))
                n++;
        best = std::max(best, n);
    }
    return best;
}

Enroller::Enroller(const FrontendAssets &assets, Model *model, bool use_beam,
                   const QualityParams &q)
    : fe_(assets), enc_(model), use_beam_(use_beam), q_(q)
{
}

bool Enroller::logp_of(const std::vector<float> &pcm, std::vector<float> &logp, int &T)
{
    if (!enc_.encode_offline(fe_, pcm.data(), pcm.size(), logp))
        return false;
    T = (int)(logp.size() / OKWS_N_UNITS);
    return true;
}

std::vector<Candidate> Enroller::decode(const std::vector<float> &logp, int T)
{
    if (use_beam_)
        return beam_units(logp.data(), T);
    std::vector<Candidate> out;
    std::vector<int> u = greedy_units(logp.data(), T);
    if (!u.empty()) {
        double mean_max = 0.0;
        for (int t = 0; t < T; t++) {
            const float *lp = &logp[(size_t)t * OKWS_N_UNITS];
            mean_max += *std::max_element(lp, lp + OKWS_N_UNITS);
        }
        out.push_back({u, mean_max / T * (double)u.size()});
    }
    return out;
}

double Enroller::peak_over_clips(KeywordScorer scorer) const
{
    double best = OKWS_NEG;
    for (const auto &c : clips_)
        best = std::max(best, scorer.peak(c.logp.data(), c.T));
    return best;
}

void Enroller::confusion_over_clips(KeywordScorer scorer, double threshold,
                                    const std::vector<std::vector<int>> &hyps,
                                    const VerifyParams &p, double &margin, double &score,
                                    bool &has_score) const
{
    margin = score = OKWS_NEG;
    has_score = false;
    for (const auto &c : clips_) {
        double m = scorer.peak(c.logp.data(), c.T) - threshold;
        margin = std::max(margin, m);
        double v, w;
        if (verify_score(hyps, p, c.logp.data(), c.T, m, v, w)) {
            score = has_score ? std::max(score, v) : v;
            has_score = true;
        }
    }
}

AudioReason Enroller::add(const float *pcm, size_t n, AudioMetrics &m, bool &model_ok,
                          double noise_rms)
{
    model_ok = true;
    AudioReason r = check_audio(pcm, n, m, q_, noise_rms);
    if (r != AUDIO_OK)
        return r;
    Clip c;
    c.pcm.assign(pcm, pcm + n);
    c.m = m;
    if (!logp_of(c.pcm, c.logp, c.T)) {
        model_ok = false;
        return AUDIO_OK;
    }
    c.cands = decode(c.logp, c.T);
    clips_.push_back(std::move(c));
    stage_ = 0;
    return AUDIO_OK;
}

void Enroller::step(bool &done, int &progress, int &total, EnrollError &err)
{
    int n = (int)clips_.size();
    // work units: 1 (merge/gate) + per clip: 1 positive + its negatives
    total = 1 + n * 6;
    done = false;
    err = ENROLL_OK;

    if (stage_ == 0) {
        if (n < 2) {
            err = ENROLL_TOO_FEW;
            done = true;
            return;
        }
        std::vector<Candidate> pool;
        for (const auto &c : clips_)
            pool.insert(pool.end(), c.cands.begin(), c.cands.end());
        res_ = EnrollResult();
        res_.hyps = merge_hyps(pool, OKWS_MAX_HYPS);
        for (const auto &c : clips_)
            res_.audio.push_back(c.m);
        if (res_.hyps.empty()) {
            err = ENROLL_NO_HYP;
            done = true;
            return;
        }
        res_.n_syllables = count_syllables(res_.hyps);
        if (res_.n_syllables < OKWS_MIN_SYL) {
            err = ENROLL_TOO_SHORT;
            done = true;
            return;
        }
        scorer_ = KeywordScorer(res_.hyps);
        neg_.clear();
        clip_ = 0;
        neg_idx_ = -1; // -1: positive score of clip_ still pending
        stage_ = 1;
        progress = 1;
        return;
    }

    if (stage_ == 1) {
        if (clip_ < n) {
            if (neg_idx_ < 0) {
                // leave-one-out positive: hypotheses from the other clips only
                std::vector<Candidate> others;
                for (int j = 0; j < n; j++)
                    if (j != clip_)
                        others.insert(others.end(), clips_[j].cands.begin(), clips_[j].cands.end());
                std::vector<Hypothesis> loo = merge_hyps(others, OKWS_MAX_HYPS);
                double pos = OKWS_NEG;
                if (!loo.empty()) {
                    KeywordScorer s(loo);
                    pos = s.peak(clips_[clip_].logp.data(), clips_[clip_].T);
                }
                res_.pos.push_back(pos);
                negs_ = shuffled_negatives(clips_[clip_].pcm);
                neg_idx_ = 0;
            } else if (neg_idx_ < (int)negs_.size()) {
                std::vector<float> lp;
                int T = 0;
                if (!logp_of(negs_[neg_idx_], lp, T)) {
                    err = ENROLL_MODEL;
                    done = true;
                    return;
                }
                neg_.push_back(scorer_.peak(lp.data(), T));
                neg_idx_++;
            }
            if (neg_idx_ >= (int)negs_.size()) {
                clip_++;
                neg_idx_ = -1;
                negs_.clear();
            }
            progress = 1 + clip_ * 6 + (neg_idx_ < 0 ? 0 : 1 + neg_idx_);
            return;
        }

        double pos_mean = 0.0, pos_min = res_.pos[0];
        for (double p : res_.pos) {
            pos_mean += p;
            pos_min = std::min(pos_min, p);
        }
        pos_mean /= res_.pos.size();
        if (neg_.empty())
            neg_.push_back(pos_min - 5.0);
        double neg_mean = 0.0;
        for (double v : neg_)
            neg_mean += v;
        neg_mean /= neg_.size();
        double th = OKWS_GAMMA * pos_mean + (1.0 - OKWS_GAMMA) * neg_mean;
        res_.margin = pos_min - th;
        res_.neg_mean = neg_mean;
        res_.threshold = th;
        stage_ = 2;
        progress = total;
        done = true;
        if (res_.margin <= 0)
            err = ENROLL_INCONSISTENT;
        return;
    }

    progress = total;
    done = true;
}

} // namespace okws
