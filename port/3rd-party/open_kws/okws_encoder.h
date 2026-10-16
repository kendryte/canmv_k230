/* Copyright (c) 2026, Canaan Bright Sight Co., Ltd
 * SPDX-License-Identifier: BSD-3-Clause
 */
#pragma once

#include <vector>

#include "okws_config.h"
#include "okws_frontend.h"
#include "okws_model.h"

namespace okws {

// Sliding-window streaming encoder (encoder.py _StreamingEncoderBase).
//
//   window [1,1,40,96], hop 16 input frames, 4x downsampling, guard 2.
//   Window i covers input frames [16i-80, 16i+16); in-window output p maps to
//   stream output o = 4i-20+p. Steady state keeps p in [18,22); the first
//   window drops its first 2 frames (o=-2,-1 lie before the stream), otherwise
//   the whole stream shifts by 800 ms and its tail is cut.
class Encoder {
public:
    explicit Encoder(Model *model);
    void reset();

    // feats: k frames, frame-major [k][40]. Appends new log posteriors to
    // logp (frame-major [m][59], m a multiple of 4 except the first window).
    // Returns false if the model fails.
    bool push_frames(const float *feats, int k, std::vector<float> &logp);

    // Pad the pending hop and push one all-zero hop to release the last
    // guard frames (encoder.flush()). Without it a keyword at the very end
    // of a short clip never reaches its peak score.
    bool flush(std::vector<float> &logp);

    // Whole clip -> [T/4][59] log posteriors through the streaming path.
    bool encode_offline(LogMel &fe, const float *pcm, size_t n, std::vector<float> &logp);

    double kpu_ms() const { return kpu_ms_; }

private:
    bool run_window(std::vector<float> &logp);

    Model *model_;
    float ring_[OKWS_N_MELS * OKWS_T_WIN];
    float logits_[OKWS_T_OUT * OKWS_N_UNITS];
    std::vector<float> pending_; // frame-major [n][40]
    int i_win_;
    double kpu_ms_;
};

void log_softmax_row(const float *x, float *out, int n);

} // namespace okws
