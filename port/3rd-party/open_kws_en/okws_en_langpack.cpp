/* Copyright (c) 2026, Canaan Bright Sight Co., Ltd
 * SPDX-License-Identifier: BSD-3-Clause
 */
#include "okws_en_langpack.h"

#include <algorithm>
#include <cstring>

namespace okws_en {

namespace {

/* Default English tables, the unit ids of assets/langpack_en.json v1.0 under
 * assets/units_en.txt (sha1 ae006c197917). Symbols are in the comments; the
 * application can override both with LangPack::set() straight from the asset. */

const int kNuclei[] = {
    3,  /* AA */ 4,  /* AE */ 5,  /* AH */ 6,  /* AO */ 7,  /* AW */
    8,  /* AY */ 13, /* EH */ 14, /* ER */ 15, /* EY */ 19, /* IH */
    20, /* IY */ 27, /* OW */ 28, /* OY */ 35, /* UH */ 36, /* UW */
};

/* 71 legal onsets, "" first. Terminated by -1 within each row; a row of only
 * -1 is the empty onset. */
const signed char kOnsets[][4] = {
    {-1, -1, -1, -1},  /* (empty) */
    {9, -1},  /* B */     {10, -1}, /* CH */    {11, -1}, /* D */
    {12, -1}, /* DH */    {16, -1}, /* F */     {17, -1}, /* G */
    {18, -1}, /* HH */    {21, -1}, /* JH */    {22, -1}, /* K */
    {23, -1}, /* L */     {24, -1}, /* M */     {25, -1}, /* N */
    {29, -1}, /* P */     {30, -1}, /* R */     {31, -1}, /* S */
    {32, -1}, /* SH */    {33, -1}, /* T */     {34, -1}, /* TH */
    {37, -1}, /* V */     {38, -1}, /* W */     {39, -1}, /* Y */
    {40, -1}, /* Z */     {41, -1}, /* ZH */
    {29, 30, -1}, /* P R */   {29, 23, -1}, /* P L */   {9, 30, -1},  /* B R */
    {9, 23, -1},  /* B L */   {33, 30, -1}, /* T R */   {11, 30, -1}, /* D R */
    {22, 30, -1}, /* K R */   {22, 23, -1}, /* K L */   {17, 30, -1}, /* G R */
    {17, 23, -1}, /* G L */   {16, 30, -1}, /* F R */   {16, 23, -1}, /* F L */
    {34, 30, -1}, /* TH R */  {32, 30, -1}, /* SH R */  {31, 29, -1}, /* S P */
    {31, 33, -1}, /* S T */   {31, 22, -1}, /* S K */   {31, 24, -1}, /* S M */
    {31, 25, -1}, /* S N */   {31, 23, -1}, /* S L */   {31, 38, -1}, /* S W */
    {33, 38, -1}, /* T W */   {11, 38, -1}, /* D W */   {22, 38, -1}, /* K W */
    {17, 38, -1}, /* G W */   {34, 38, -1}, /* TH W */  {29, 39, -1}, /* P Y */
    {9, 39, -1},  /* B Y */   {16, 39, -1}, /* F Y */   {24, 39, -1}, /* M Y */
    {22, 39, -1}, /* K Y */   {18, 39, -1}, /* HH Y */  {37, 39, -1}, /* V Y */
    {33, 39, -1}, /* T Y */   {11, 39, -1}, /* D Y */   {25, 39, -1}, /* N Y */
    {32, 23, -1}, /* SH L */  {32, 24, -1}, /* SH M */  {32, 25, -1}, /* SH N */
    {32, 38, -1}, /* SH W */
    {31, 29, 30, -1}, /* S P R */ {31, 29, 23, -1}, /* S P L */
    {31, 33, 30, -1}, /* S T R */ {31, 22, 30, -1}, /* S K R */
    {31, 22, 38, -1}, /* S K W */ {31, 29, 39, -1}, /* S P Y */
    {31, 22, 39, -1}, /* S K Y */
};

} // namespace

LangPack::LangPack()
{
    memset(nucleus_, 0, sizeof(nucleus_));
    for (int u : kNuclei)
        nucleus_[u] = true;
    max_onset_ = 0;
    for (const signed char *row : kOnsets) {
        std::vector<int> o;
        for (int i = 0; i < 4 && row[i] >= 0; i++)
            o.push_back(row[i]);
        max_onset_ = std::max(max_onset_, (int)o.size());
        onsets_.push_back(std::move(o));
    }
    min_nuclei_ = OKWS_EN_MIN_NUCLEI;
    min_units_ = OKWS_EN_MIN_UNITS;
}

bool LangPack::set(const std::vector<int> &nuclei, const std::vector<std::vector<int>> &onsets,
                   int min_nuclei, int min_units)
{
    for (int u : nuclei)
        if (u < 0 || u >= OKWS_EN_N_UNITS)
            return false;
    for (const auto &o : onsets)
        for (int u : o)
            if (u < 0 || u >= OKWS_EN_N_UNITS)
                return false;
    memset(nucleus_, 0, sizeof(nucleus_));
    for (int u : nuclei)
        nucleus_[u] = true;
    onsets_.assign(1, std::vector<int>()); // the empty onset is always legal
    max_onset_ = 0;
    for (const auto &o : onsets) {
        if (o.empty())
            continue;
        onsets_.push_back(o);
        max_onset_ = std::max(max_onset_, (int)o.size());
    }
    min_nuclei_ = min_nuclei > 0 ? min_nuclei : 1;
    min_units_ = min_units > 0 ? min_units : 1;
    return true;
}

int LangPack::count_nuclei(const std::vector<int> &units) const
{
    int n = 0;
    for (int u : units)
        if (is_nucleus(u))
            n++;
    return n;
}

bool LangPack::is_onset(const int *u, int n) const
{
    for (const auto &o : onsets_)
        if ((int)o.size() == n && std::equal(o.begin(), o.end(), u))
            return true;
    return false;
}

bool LangPack::syllabify(const std::vector<int> &units, std::vector<int> &lens) const
{
    std::vector<int> V;
    for (size_t k = 0; k < units.size(); k++)
        if (is_nucleus(units[k]))
            V.push_back((int)k);
    if (V.empty())
        return false;

    // bounds[k] = first unit of syllable k; consonants before the first nucleus
    // go to syllable 0 and those after the last nucleus to the last syllable.
    std::vector<int> bounds{0};
    for (size_t j = 1; j < V.size(); j++) {
        const int c0 = V[j - 1] + 1, len = V[j] - c0; // the consonant cluster
        // Longest suffix first; the empty suffix always matches, so m <= len.
        int m = len;
        for (int cand = std::max(0, len - max_onset_); cand <= len; cand++) {
            if (is_onset(&units[c0 + cand], len - cand)) {
                m = cand;
                break;
            }
        }
        bounds.push_back(c0 + m);
    }
    bounds.push_back((int)units.size());

    lens.clear();
    for (size_t k = 0; k + 1 < bounds.size(); k++)
        lens.push_back(bounds[k + 1] - bounds[k]);
    return true;
}

} // namespace okws_en
