/* Copyright (c) 2026, Canaan Bright Sight Co., Ltd
 * SPDX-License-Identifier: BSD-3-Clause
 */
#pragma once

#include <utility>
#include <vector>

#include "okws_en_config.h"

namespace okws_en {

struct Hypothesis {
    std::vector<int> units;
    double weight;
};

// A hypothesis plus its syllable grouping: syls[i] is how many units belong to
// syllable i and the sum is units.size(). The grouping is produced once at
// enrollment time by LangPack::syllabify (or read from the enrollment record's
// verify.syllables), so detection stays language independent -- this is the one
// real difference from the Chinese decoder, which derives syllable ends from
// "unit id >= 24 is a final".
struct VerifyHyp {
    std::vector<int> units;
    std::vector<int> syls;
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
std::vector<Candidate> beam_units(const float *logp, int T, int beam = OKWS_EN_BEAM,
                                  int nbest = OKWS_EN_NBEST, float prune = OKWS_EN_BEAM_PRUNE);

// CTC forced alignment (Viterbi, decode.py ctc_align) of units over logp[T].
// Fills the [start, end] frame span of every unit; false when the clip is too
// short or a unit gets no frame.
bool ctc_align(const float *logp, int T, const std::vector<int> &units,
               std::vector<std::pair<int, int>> &spans);

// Per-syllable confidence (decode.py syllable_scores_by_lens): mean over the
// units of a syllable of the mean log posterior over the unit's aligned frames.
bool syllable_scores_by_lens(const float *logp, int T, const VerifyHyp &h,
                             std::vector<double> &scores);

// Lowest syllable score (decode.py weakest_syllable); false if not alignable.
//
// Second-stage check against similar keywords: the length-normalised forward
// score averages the shared syllables in and dilutes a single different one,
// the weakest syllable does not. Matching words sit near 0, mismatches lower.
bool weakest_syllable(const float *logp, int T, const VerifyHyp &h, double &weak);

// Second-stage decision. A candidate passes if
//   max_{j < n_hyps} weakest_syllable(hyp_j) + alpha * margin > verify_th + delta
// where margin = forward score - keyword threshold at the trigger frame.
// Defaults {1, 0, 0} are exactly the calibrated English rule (main hypothesis
// only, threshold -6.0). Checking several enrollment
// hypotheses recovers true words whose top decode is off in one syllable;
// alpha trusts a clearly passed first stage more.
struct VerifyParams {
    int n_hyps = 1;
    double alpha = 0.0;
    double delta = 0.0;
};

// Verification score of logp[T] (see VerifyParams); false if no hypothesis
// can be aligned. weak receives the best weakest-syllable value.
bool verify_score(const std::vector<VerifyHyp> &hyps, const VerifyParams &p, const float *logp,
                  int T, double margin, double &score, double &weak);

// Tail pause check (detect.py _tail_ok): no new phoneme
// peak in the W frames after a candidate. Disabled by default.
bool tail_ok(const float *logp, int T, double theta);

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
    // lp: one frame of 42 log posteriors. Returns the keyword score;
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

} // namespace okws_en
