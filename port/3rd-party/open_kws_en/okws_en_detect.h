/* Copyright (c) 2026, Canaan Bright Sight Co., Ltd
 * SPDX-License-Identifier: BSD-3-Clause
 */
#pragma once

#include <string>
#include <vector>

#include "okws_en_decode.h"
#include "okws_en_encoder.h"
#include "okws_en_frontend.h"

namespace okws_en {

// Energy VAD (detect.py EnergyVAD). The noise floor tracks the minimum:
// initialising it from the first chunk and updating only on non-speech would
// gate the whole stream when it starts with speech.
class EnergyVAD {
public:
    void reset()
    {
        has_noise_ = false;
        hang_ = 0;
    }
    bool operator()(const float *pcm, size_t n, double *energy);

private:
    bool has_noise_ = false;
    double noise_ = 0.0;
    int hang_ = 0;
};

struct Event {
    int kw;
    double score, threshold, weak, start_ms, end_ms;
};

struct Keyword {
    std::string id;
    KeywordScorer scorer;
    double threshold = 0.0;
    int cooldown_ms = OKWS_EN_COOLDOWN_MS;
    int confirm = OKWS_EN_CONFIRM;
    int hit = 0;
    double last_fire_ms = -1e9;
    double best = OKWS_EN_NEG;
    double last = OKWS_EN_NEG;      // score of the latest frame
    double chunk_max = OKWS_EN_NEG; // best score within the latest push()
    // Scorer frame 0 corresponds to this audio time; the scorer is reset on
    // every trigger, so start_ms = t0_ms + start * FRAME_MS (detect.py).
    double t0_ms = 0.0;
    // Second stage: off when the enrollment record carries no verify threshold.
    // hyp_verify holds the units and the syllable grouping of each hypothesis
    // in enrollment order (0 = main).
    bool verify = false;
    double verify_th = OKWS_EN_VERIFY_TH;
    std::vector<VerifyHyp> hyp_verify;
    double last_weak = OKWS_EN_NEG; // weakest syllable of the latest verification
    int n_rejected = 0;             // triggers vetoed by the verification
    // Tail pause check, off by default: a candidate
    // waits tail_w frames and is dropped if a new phoneme peaks meanwhile.
    bool tail = false;
    bool has_pending = false;
    long pending_frame = 0;
    Event pending{};
};

struct DetectStats {
    double audio_ms = 0, fe_ms = 0, kpu_ms = 0, dec_ms = 0;
    int n_infer = 0, n_skip = 0;
    // last_score / chunk_max: maximum over all keywords
    double last_score = OKWS_EN_NEG, chunk_max = OKWS_EN_NEG, level_rms = 0;
    bool speech = false;
};

// Streaming detector (detect.py StreamingDetector): all keywords share one
// forward pass, the marginal cost of a keyword is its CTC scorer only.
class Detector {
public:
    Detector(const FrontendAssets &assets, Model *model);

    void set_keywords(std::vector<Keyword> kws);
    // Adding or clearing keywords keeps the audio/encoder stream running.
    void add_keyword(Keyword kw);
    void clear_keywords() { kws_.clear(); }
    const std::vector<Keyword> &keywords() const { return kws_; }
    void set_bias(double bias) { bias_ = bias; }
    void set_vad(bool on) { use_vad_ = on; }
    void set_verify_params(const VerifyParams &p) { vp_ = p; }
    const VerifyParams &verify_params() const { return vp_; }
    void set_tail(int w, double theta)
    {
        tail_w_ = w > 0 ? w : 1;
        tail_theta_ = theta;
    }
    void reset();

    // Feed a PCM chunk (2560 samples recommended). Appends fired events.
    bool push(const float *pcm, size_t n, std::vector<Event> &events);
    // End-of-stream flush (file tests; detect.py run_wave tail).
    bool flush(std::vector<Event> &events);

    const DetectStats &stats() const { return st_; }

private:
    void score_frames(const std::vector<float> &logp, std::vector<Event> &events);
    bool verify(Keyword &k, double margin);
    int buffered_frames() const { return (int)(logp_buf_.size() / OKWS_EN_N_UNITS); }

    StreamingFrontend fe_;
    Encoder enc_;
    EnergyVAD vad_;
    std::vector<Keyword> kws_;
    double bias_ = 0.0;
    bool use_vad_ = true;
    long t_frames_ = 0;
    // Feature frames dropped by the VAD. They must still count towards the
    // clock (10 ms each), otherwise timestamps and the cooldown drift further
    // apart the longer the stream stays silent; the Chinese reference
    // implementation has this defect.
    long skip_feat_ = 0;
    double last_global_fire_ = -1e9; // cooldown shared by all keywords
    int tail_w_ = OKWS_EN_TAIL_W;
    double tail_theta_ = OKWS_EN_TAIL_THETA;
    DetectStats st_;
    std::vector<float> feats_, logp_;
    std::vector<float> logp_buf_; // last OKWS_EN_VERIFY_BUF output frames [n][42]
    VerifyParams vp_;
};

} // namespace okws_en
