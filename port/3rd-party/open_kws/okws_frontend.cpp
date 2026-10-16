/* Copyright (c) 2026, Canaan Bright Sight Co., Ltd
 * SPDX-License-Identifier: BSD-3-Clause
 */
#include "okws_frontend.h"

#include <cmath>
#include <cstring>

#include "okws_npy.h"

namespace okws {

bool FrontendAssets::load(const std::string &dir, std::string &err)
{
    std::string d = dir;
    if (!d.empty() && d.back() != '/')
        d += '/';
    if (!load_npy_f32(d + "window512.npy", {OKWS_N_FFT}, window, err) ||
        !load_npy_f32(d + "mel_fb.npy", {OKWS_N_MELS, OKWS_N_BINS}, mel_fb, err) ||
        !load_npy_f32(d + "cmvn_mean.npy", {OKWS_N_MELS}, mean, err) ||
        !load_npy_f32(d + "cmvn_std.npy", {OKWS_N_MELS}, std_, err))
        return false;
    // Zero weights contribute exactly 0 to the dot product, so restricting
    // each row to its non-zero span keeps the result identical.
    for (int m = 0; m < OKWS_N_MELS; m++) {
        const float *row = &mel_fb[m * OKWS_N_BINS];
        int lo = 0, hi = OKWS_N_BINS;
        while (lo < hi && row[lo] == 0.0f)
            lo++;
        while (hi > lo && row[hi - 1] == 0.0f)
            hi--;
        mel_lo[m] = lo;
        mel_hi[m] = hi;
    }
    return true;
}

LogMel::LogMel(const FrontendAssets &a) : a_(a)
{
    for (int k = 0; k < OKWS_N_FFT / 2; k++) {
        cos_[k] = cos(-2.0 * M_PI * k / OKWS_N_FFT);
        sin_[k] = sin(-2.0 * M_PI * k / OKWS_N_FFT);
    }
    int bits = 0;
    while ((1 << bits) < OKWS_N_FFT)
        bits++;
    for (int i = 0; i < OKWS_N_FFT; i++) {
        int r = 0;
        for (int b = 0; b < bits; b++)
            if (i & (1 << b))
                r |= 1 << (bits - 1 - b);
        rev_[i] = r;
    }
}

void LogMel::frame(const float *x, float *feat)
{
    // numpy multiplies in float32, then rfft runs in float64.
    for (int i = 0; i < OKWS_N_FFT; i++) {
        re_[rev_[i]] = (double)(x[i] * a_.window[i]);
        im_[rev_[i]] = 0.0;
    }
    for (int len = 2; len <= OKWS_N_FFT; len <<= 1) {
        int half = len >> 1, step = OKWS_N_FFT / len;
        for (int s = 0; s < OKWS_N_FFT; s += len) {
            for (int k = 0; k < half; k++) {
                double wr = cos_[k * step], wi = sin_[k * step];
                int p = s + k, q = p + half;
                double tr = re_[q] * wr - im_[q] * wi;
                double ti = re_[q] * wi + im_[q] * wr;
                re_[q] = re_[p] - tr;
                im_[q] = im_[p] - ti;
                re_[p] += tr;
                im_[p] += ti;
            }
        }
    }
    float power[OKWS_N_BINS];
    for (int k = 0; k < OKWS_N_BINS; k++)
        power[k] = (float)(re_[k] * re_[k] + im_[k] * im_[k]);
    for (int m = 0; m < OKWS_N_MELS; m++) {
        const float *row = &a_.mel_fb[m * OKWS_N_BINS];
        double acc = 0.0;
        for (int k = a_.mel_lo[m]; k < a_.mel_hi[m]; k++)
            acc += (double)row[k] * (double)power[k];
        float lg = logf((float)acc + OKWS_LOG_EPS);
        feat[m] = (lg - a_.mean[m]) / a_.std_[m];
    }
}

void LogMel::compute(const float *pcm, size_t n, std::vector<float> &out)
{
    int k = n_frames(n);
    size_t base = out.size();
    out.resize(base + (size_t)k * OKWS_N_MELS);
    for (int t = 0; t < k; t++)
        frame(pcm + (size_t)t * OKWS_HOP, &out[base + (size_t)t * OKWS_N_MELS]);
}

StreamingFrontend::StreamingFrontend(const FrontendAssets &a) : fe_(a)
{
    buf_.reserve(OKWS_N_FFT + 2 * OKWS_CHUNK);
}

void StreamingFrontend::reset()
{
    buf_.clear();
}

int StreamingFrontend::push(const float *pcm, size_t n, std::vector<float> &out)
{
    buf_.insert(buf_.end(), pcm, pcm + n);
    int k = LogMel::n_frames(buf_.size());
    if (k <= 0)
        return 0;
    fe_.compute(buf_.data(), OKWS_N_FFT + (size_t)(k - 1) * OKWS_HOP, out);
    buf_.erase(buf_.begin(), buf_.begin() + (size_t)k * OKWS_HOP);
    return k;
}

} // namespace okws
