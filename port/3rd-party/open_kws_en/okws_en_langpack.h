/* Copyright (c) 2026, Canaan Bright Sight Co., Ltd
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * Enrollment-time language pack (pykws/syllabify.py, assets/langpack_en.json).
 *
 * Only enrollment needs language rules: the length gate and the syllable
 * segmentation of the main hypothesis, which is written into the enrollment
 * record as verify.syllables. Detection reads those lengths and therefore
 * contains no language rule at all.
 */
#pragma once

#include <vector>

#include "okws_en_config.h"

namespace okws_en {

// Vowel nuclei and legal onset clusters, as unit ids. Defaults to the English
// table compiled in from assets/langpack_en.json v1.0; set() replaces it, so
// the asset stays the single source of truth for an application that ships it.
class LangPack {
public:
    LangPack(); // English defaults

    // nuclei: unit ids. onsets: clusters as id sequences (the empty cluster is
    // always legal and is added when missing). Returns false on a bad id, in
    // which case the previous table is kept.
    bool set(const std::vector<int> &nuclei, const std::vector<std::vector<int>> &onsets,
             int min_nuclei, int min_units);

    bool is_nucleus(int u) const { return u >= 0 && u < OKWS_EN_N_UNITS && nucleus_[u]; }
    int count_nuclei(const std::vector<int> &units) const;

    // Syllable boundaries by the maximum onset principle: of the consonant
    // cluster between two nuclei, the longest suffix that is a legal onset
    // starts the next syllable and the rest closes the previous one. Fills the
    // unit count of each syllable (summing to units.size()); false when the
    // sequence has no nucleus at all.
    bool syllabify(const std::vector<int> &units, std::vector<int> &lens) const;

    int min_nuclei() const { return min_nuclei_; }
    int min_units() const { return min_units_; }

private:
    bool is_onset(const int *u, int n) const;

    bool nucleus_[OKWS_EN_N_UNITS];
    std::vector<std::vector<int>> onsets_; // includes the empty cluster
    int max_onset_;                        // longest legal onset, bounds the suffix search
    int min_nuclei_;
    int min_units_;
};

} // namespace okws_en
