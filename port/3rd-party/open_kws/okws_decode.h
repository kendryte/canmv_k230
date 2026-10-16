/* Copyright (c) 2026, Canaan Bright Sight Co., Ltd
 * SPDX-License-Identifier: BSD-3-Clause
 */
#pragma once

#include <vector>

#include "okws_config.h"

namespace okws {

struct Hypothesis {
    std::vector<int> units;
    double weight;
};

// A scored unit sequence produced by greedy/beam decoding.
struct Candidate {
    std::vector<int> units;
    double logp;
};

double logaddexp(double a, double b);

// greedy: argmax per frame, collapse repeats, drop blanks.
std::vector<int> greedy_units(const float *logp, int T);

// Standard CTC prefix beam search (decode.py beam_units). Ties keep insertion
// order exactly like Python's stable sorted() over an insertion-ordered dict.
std::vector<Candidate> beam_units(const float *logp, int T, int beam = OKWS_BEAM,
                                  int nbest = OKWS_NBEST, float prune = OKWS_BEAM_PRUNE);

// Units with id >= 24 are finals; a syllable ends at a final.
inline bool is_final_unit(int u)
{
    return u >= OKWS_FIRST_FINAL && u < OKWS_N_UNITS;
}

// CTC forced alignment (Viterbi, decode.py ctc_align) of units over logp[T].
// Fills the [start, end] frame span of every unit; false when the clip is too
// short or a unit gets no frame.
bool ctc_align(const float *logp, int T, const std::vector<int> &units,
               std::vector<std::pair<int, int>> &spans);

// Per-syllable confidence (decode.py syllable_scores): mean over the units of
// a syllable of the mean log posterior over the unit's aligned frames.
bool syllable_scores(const float *logp, int T, const std::vector<int> &units,
                     std::vector<double> &scores);

// Lowest syllable score (decode.py weakest_syllable); false if not alignable.
//
// Second-stage check against similar keywords: the length-normalised forward
// score averages the shared syllables in and dilutes a single different one
// ("xiao nan" vs "xiao zhi": forward gap 0.70), the weakest syllable does not
// (gap 9.36). Matching words sit near 0, mismatches at -5 .. -10.
bool weakest_syllable(const float *logp, int T, const std::vector<int> &units, double &weak);

// Second-stage decision (generalised pykws v2 _verify). A candidate passes if
//   max_{j < n_hyps} weakest_syllable(hyp_j) + alpha * margin > verify_th + delta
// where margin = forward score - keyword threshold at the trigger frame.
// Defaults {1, 0, 0} are exactly pykws v2 (main hypothesis only, -3.0).
// Checking several enrollment hypotheses recovers true words whose top decode
// is off in one syllable; alpha trusts a clearly passed first stage more.
struct VerifyParams {
    int n_hyps = 1;
    double alpha = 0.0;
    double delta = 0.0;
};

// Verification score of logp[T] (see VerifyParams); false if no hypothesis
// can be aligned. weak receives the best weakest-syllable value.
bool verify_score(const std::vector<std::vector<int>> &hyps, const VerifyParams &p,
                  const float *logp, int T, double margin, double &score, double &weak);

// Streaming CTC-forward keyword scorer (decode.py KeywordScorer).
//
// Free start: every frame may open a new path with log-prob 0, so the score
// only covers the keyword itself instead of growing with the stream length;
// dividing by the unit count removes the long/short keyword scale gap.
// Score = sum_j w_j * score_j over the weighted hypotheses.
class KeywordScorer {
public:
    KeywordScorer() = default;
    explicit KeywordScorer(const std::vector<Hypothesis> &hyps);
    void reset();
    // lp: one frame of 59 log posteriors. Returns the keyword score;
    // start (optional) receives the start frame of the best path.
    double update(const float *lp, int *start = nullptr);
    double score() const;
    double peak(const float *logp, int T);
    bool empty() const { return rows_.empty(); }

private:
    struct Row {
        std::vector<int> ext;
        std::vector<unsigned char> skip;
        std::vector<double> alpha, v;
        std::vector<int> start, st;
        double norm;
        double w;
    };
    std::vector<Row> rows_;
    int t_ = 0;
};

} // namespace okws
