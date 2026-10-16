/* Copyright (c) 2026, Canaan Bright Sight Co., Ltd
 * SPDX-License-Identifier: BSD-3-Clause
 */
#pragma once

#include <string>
#include <vector>

#include "okws_decode.h"
#include "okws_encoder.h"
#include "okws_frontend.h"

namespace okws {

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

struct Keyword {
    std::string id;
    KeywordScorer scorer;
    double threshold = 0.0;
    int cooldown_ms = OKWS_COOLDOWN_MS;
    int confirm = OKWS_CONFIRM;
    int hit = 0;
    double last_fire_ms = -1e9;
    double best = OKWS_NEG;
    double last = OKWS_NEG;      // score of the latest frame
    double chunk_max = OKWS_NEG; // best score within the latest push()
    // two-stage verification (pykws v2): off when the enroll record has no
    // verify_threshold; hyp_units = hypotheses in enroll order (0 = main)
    bool verify = false;
    double verify_th = OKWS_VERIFY_TH;
    std::vector<std::vector<int>> hyp_units;
    double last_weak = OKWS_NEG; // weakest syllable of the latest verification
    int n_rejected = 0;          // triggers vetoed by the verification
};

struct Event {
    int kw;
    double score, threshold, start_ms, end_ms;
};

struct DetectStats {
    double audio_ms = 0, fe_ms = 0, kpu_ms = 0, dec_ms = 0;
    int n_infer = 0, n_skip = 0;
    // last_score / chunk_max: maximum over all keywords
    double last_score = OKWS_NEG, chunk_max = OKWS_NEG, level_rms = 0;
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
    void reset();

    // Feed a PCM chunk (2560 samples recommended). Appends fired events.
    bool push(const float *pcm, size_t n, std::vector<Event> &events);
    // End-of-stream flush (file tests; detect.py run_wave tail).
    bool flush(std::vector<Event> &events);

    const DetectStats &stats() const { return st_; }

private:
    void score_frames(const std::vector<float> &logp, std::vector<Event> &events);

    StreamingFrontend fe_;
    Encoder enc_;
    EnergyVAD vad_;
    std::vector<Keyword> kws_;
    double bias_ = 0.0;
    bool use_vad_ = true;
    long t_frames_ = 0;
    DetectStats st_;
    std::vector<float> feats_, logp_;
    std::vector<float> logp_buf_; // last OKWS_VERIFY_BUF output frames [n][59]
    VerifyParams vp_;
    bool verify(Keyword &k, double score);
};

} // namespace okws
