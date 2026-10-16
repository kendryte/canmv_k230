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

enum AudioReason {
    AUDIO_OK = 0,
    AUDIO_TOO_SHORT,
    AUDIO_TOO_LONG,
    AUDIO_TOO_QUIET,
    AUDIO_CLIPPED,
    AUDIO_NOISY,
    AUDIO_NO_SPEECH,
};

struct AudioMetrics {
    double dur = 0, peak = 0, clip_ratio = 0, snr_db = 0;
};

// Recording quality limits (enroll.py check_audio defaults).
struct QualityParams {
    double clip_ratio = OKWS_CLIP_RATIO; // max share of samples at full scale
    double min_snr = OKWS_MIN_SNR;       // dB
};

// Quality check (enroll.py check_audio, with DC removal). noise_rms > 0 is the
// ambient level measured before recording and is used as the SNR reference.
AudioReason check_audio(const float *pcm, size_t n, AudioMetrics &m,
                        const QualityParams &q = QualityParams(), double noise_rms = -1.0);

// Board-side endpoint trimming of a fixed-length recording to the spoken
// part (+200 ms padding), clamped to [min_dur, max_dur]. Returns false when
// no speech frame is found.
bool trim_speech(const float *pcm, size_t n, size_t &beg, size_t &end);

// numpy.quantile (linear interpolation) on a copy of v.
double quantile(std::vector<double> v, double q);

enum EnrollError {
    ENROLL_OK = 0,
    ENROLL_TOO_FEW,     // fewer than 2 recordings
    ENROLL_NO_HYP,      // no unit sequence decoded
    ENROLL_TOO_SHORT,   // fewer than min_syllables syllables
    ENROLL_INCONSISTENT,// calibrated threshold above the worst positive
    ENROLL_MODEL,       // model failure
};

struct EnrollResult {
    std::vector<Hypothesis> hyps; // weights rounded to 6 decimals
    double threshold = 0;
    double verify_threshold = OKWS_VERIFY_TH;
    std::vector<double> pos;
    double neg_mean = 0, margin = 0;
    int n_syllables = 0;
    std::vector<AudioMetrics> audio;
};

// On-device enrollment (enroll.py Enroller without the text/background
// channels). add() decodes each recording; step() runs the threshold
// calibration in small units so the UI can refresh between them.
class Enroller {
public:
    Enroller(const FrontendAssets &assets, Model *model, bool use_beam = true,
             const QualityParams &q = QualityParams());

    // Quality-checks and decodes one recording. Returns AUDIO_OK or the
    // rejection reason (the recording is then discarded).
    AudioReason add(const float *pcm, size_t n, AudioMetrics &m, bool &model_ok,
                    double noise_rms = -1.0);
    int count() const { return (int)clips_.size(); }

    // Runs one unit of work. Sets done when finished; err != ENROLL_OK aborts.
    void step(bool &done, int &progress, int &total, EnrollError &err);
    const EnrollResult &result() const { return res_; }

    // Highest score a registered keyword reaches on the accepted clips of
    // this session: > its threshold means the new word would wake it too.
    double peak_over_clips(KeywordScorer scorer) const;
    // Worst case of a registered keyword on the accepted clips: its peak
    // forward margin and its best verification score (clip by clip, with the
    // clip's own margin). has_score is false if no clip can be aligned.
    void confusion_over_clips(KeywordScorer scorer, double threshold,
                              const std::vector<std::vector<int>> &hyps, const VerifyParams &p,
                              double &margin, double &score, bool &has_score) const;

private:
    struct Clip {
        std::vector<float> pcm;
        std::vector<float> logp;
        int T;
        std::vector<Candidate> cands;
        AudioMetrics m;
    };
    std::vector<Candidate> decode(const std::vector<float> &logp, int T);
    bool logp_of(const std::vector<float> &pcm, std::vector<float> &logp, int &T);

    LogMel fe_;
    Encoder enc_;
    bool use_beam_;
    QualityParams q_;
    std::vector<Clip> clips_;
    std::vector<std::vector<float>> negs_; // negatives of the current clip
    KeywordScorer scorer_;
    std::vector<double> neg_;
    int stage_ = 0, clip_ = 0, neg_idx_ = 0;
    EnrollResult res_;
};

// enroll.py _merge (without the text channel).
std::vector<Hypothesis> merge_hyps(const std::vector<Candidate> &pool, int max_hyps);

// Syllable count = number of finals (units that are not initials).
int count_syllables(const std::vector<Hypothesis> &hyps);

// Query-specific negatives: split into 3 parts and re-order (5 non-identity
// permutations), fading in each non-leading part over 160 samples.
std::vector<std::vector<float>> shuffled_negatives(const std::vector<float> &pcm);

} // namespace okws
