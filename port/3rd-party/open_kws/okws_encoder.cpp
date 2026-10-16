/* Copyright (c) 2026, Canaan Bright Sight Co., Ltd
 * SPDX-License-Identifier: BSD-3-Clause
 */
#include "okws_encoder.h"

#include <cmath>
#include <cstring>

#include "okws_time.h"

namespace okws {

// numpy float32 sum order for short rows (pairwise_sum with 8 accumulators).
static float np_sum_f32(const float *a, int n)
{
    if (n < 8) {
        float r = 0.0f;
        for (int i = 0; i < n; i++)
            r += a[i];
        return r;
    }
    float r[8];
    for (int j = 0; j < 8; j++)
        r[j] = a[j];
    int i = 8;
    for (; i < n - n % 8; i += 8)
        for (int j = 0; j < 8; j++)
            r[j] += a[i + j];
    float res = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]));
    for (; i < n; i++)
        res += a[i];
    return res;
}

// float32 log-softmax exactly like pykws (numpy float32). This matters: a
// saturated frame must give lp == 0.0f like the reference, because the
// free-start rule in the CTC scorer is discontinuous at v == 0 and the
// enrollment thresholds were calibrated with that behaviour.
void log_softmax_row(const float *x, float *out, int n)
{
    float m = x[0];
    for (int i = 1; i < n; i++)
        if (x[i] > m)
            m = x[i];
    float e[OKWS_N_UNITS];
    for (int i = 0; i < n; i++)
        e[i] = expf(x[i] - m);
    float ls = logf(np_sum_f32(e, n));
    for (int i = 0; i < n; i++)
        out[i] = (x[i] - m) - ls;
}

Encoder::Encoder(Model *model) : model_(model)
{
    pending_.reserve(OKWS_N_MELS * OKWS_HOP_FRAMES * 4);
    reset();
}

void Encoder::reset()
{
    memset(ring_, 0, sizeof(ring_));
    pending_.clear();
    i_win_ = 0;
    kpu_ms_ = 0.0;
}

bool Encoder::run_window(std::vector<float> &logp)
{
    // Shift the ring left by one hop and append the next 16 pending frames.
    for (int m = 0; m < OKWS_N_MELS; m++) {
        float *row = &ring_[m * OKWS_T_WIN];
        memmove(row, row + OKWS_HOP_FRAMES, (OKWS_T_WIN - OKWS_HOP_FRAMES) * sizeof(float));
        for (int t = 0; t < OKWS_HOP_FRAMES; t++)
            row[OKWS_T_WIN - OKWS_HOP_FRAMES + t] = pending_[t * OKWS_N_MELS + m];
    }
    pending_.erase(pending_.begin(), pending_.begin() + OKWS_HOP_FRAMES * OKWS_N_MELS);

    double t0 = now_ms();
    bool ok = model_->run(ring_, logits_);
    kpu_ms_ += now_ms() - t0;
    if (!ok)
        return false;

    int s = OKWS_T_OUT - OKWS_GUARD - OKWS_OUT_HOP; // 18
    int p0 = i_win_ == 0 ? s + OKWS_GUARD : s;
    for (int p = p0; p < s + OKWS_OUT_HOP; p++) {
        size_t base = logp.size();
        logp.resize(base + OKWS_N_UNITS);
        log_softmax_row(&logits_[p * OKWS_N_UNITS], &logp[base], OKWS_N_UNITS);
    }
    i_win_++;
    return true;
}

bool Encoder::push_frames(const float *feats, int k, std::vector<float> &logp)
{
    if (k > 0)
        pending_.insert(pending_.end(), feats, feats + (size_t)k * OKWS_N_MELS);
    while (pending_.size() >= (size_t)OKWS_HOP_FRAMES * OKWS_N_MELS)
        if (!run_window(logp))
            return false;
    return true;
}

bool Encoder::flush(std::vector<float> &logp)
{
    if (!pending_.empty()) {
        pending_.resize((size_t)OKWS_HOP_FRAMES * OKWS_N_MELS, 0.0f);
        if (!push_frames(nullptr, 0, logp))
            return false;
    }
    float zeros[OKWS_HOP_FRAMES * OKWS_N_MELS] = {0};
    return push_frames(zeros, OKWS_HOP_FRAMES, logp);
}

bool Encoder::encode_offline(LogMel &fe, const float *pcm, size_t n, std::vector<float> &logp)
{
    std::vector<float> feats;
    fe.compute(pcm, n, feats);
    int T = (int)(feats.size() / OKWS_N_MELS);
    reset();
    logp.clear();
    if (!push_frames(feats.data(), T, logp) || !flush(logp))
        return false;
    size_t keep = (size_t)(((T + 1) / 2 + 1) / 2);
    if (logp.size() > keep * OKWS_N_UNITS)
        logp.resize(keep * OKWS_N_UNITS);
    return true;
}

} // namespace okws
