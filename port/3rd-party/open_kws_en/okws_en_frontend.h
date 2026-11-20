/* Copyright (c) 2026, Canaan Bright Sight Co., Ltd
 * SPDX-License-Identifier: BSD-3-Clause
 */
#pragma once

#include <string>
#include <vector>

#include "okws_en_config.h"

namespace okws_en {

// Frontend constants loaded from the four assets/*.npy files. window512.npy and
// mel_fb.npy are byte identical to the Chinese model's; only the CMVN pair is
// English specific -- mixing the two pairs up breaks everything.
struct FrontendAssets {
    std::vector<float> window;      // [512], hann(400) centred and zero padded
    std::vector<float> mel_fb;      // [40][257]
    std::vector<float> mean;        // [40], cmvn_mean_en.npy
    std::vector<float> std_;        // [40], cmvn_std_en.npy
    int mel_lo[OKWS_EN_N_MELS];     // non-zero column range of each mel row
    int mel_hi[OKWS_EN_N_MELS];

    bool load(const std::string &dir, std::string &err);
};

// Stateless log-Mel + CMVN (feat.py LogMelFrontend).
class LogMel {
public:
    explicit LogMel(const FrontendAssets &a);

    static int n_frames(size_t n_samples)
    {
        return n_samples < OKWS_EN_N_FFT ? 0
                                         : (int)((n_samples - OKWS_EN_N_FFT) / OKWS_EN_HOP + 1);
    }

    // pcm: float in [-1,1]. Appends n_frames(n) frames to out, frame-major
    // (out[t*40 + m]).
    void compute(const float *pcm, size_t n, std::vector<float> &out);

private:
    void frame(const float *x, float *feat);

    const FrontendAssets &a_;
    double re_[OKWS_EN_N_FFT];
    double im_[OKWS_EN_N_FFT];
    double cos_[OKWS_EN_N_FFT / 2];
    double sin_[OKWS_EN_N_FFT / 2];
    int rev_[OKWS_EN_N_FFT];
};

// Streaming wrapper keeping the 352-sample overlap (feat.py StreamingFrontend).
class StreamingFrontend {
public:
    explicit StreamingFrontend(const FrontendAssets &a);
    void reset();
    // Appends new frames (frame-major) to out; returns the number of frames.
    int push(const float *pcm, size_t n, std::vector<float> &out);

private:
    LogMel fe_;
    std::vector<float> buf_;
};

} // namespace okws_en
