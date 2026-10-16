/* Copyright (c) 2026, Canaan Bright Sight Co., Ltd
 * SPDX-License-Identifier: BSD-3-Clause
 */
#include "okws_decode.h"

#include <algorithm>
#include <cmath>
#include <string>
#include <unordered_map>

namespace okws {

double logaddexp(double a, double b)
{
    double m = a > b ? a : b;
    if (m <= OKWS_NEG / 2)
        return OKWS_NEG;
    return m + log1p(exp(-fabs(a - b)));
}

// decode.py _la2 (beam search accumulation).
static double la2(double a, double b)
{
    if (a < b)
        std::swap(a, b);
    if (b <= OKWS_NEG / 2)
        return a;
    return a + log1p(exp(b - a));
}

static int argmax_row(const float *x, int n)
{
    int best = 0;
    for (int i = 1; i < n; i++)
        if (x[i] > x[best])
            best = i;
    return best;
}

std::vector<int> greedy_units(const float *logp, int T)
{
    std::vector<int> out;
    int prev = -1;
    for (int t = 0; t < T; t++) {
        int u = argmax_row(logp + (size_t)t * OKWS_N_UNITS, OKWS_N_UNITS);
        if (u != prev && u != OKWS_BLANK)
            out.push_back(u);
        prev = u;
    }
    return out;
}

namespace {

struct Beam {
    std::string prefix; // one byte per unit id (< 59)
    double pb, pnb;
};

// Insertion-ordered map, mirroring the Python dict used by beam_units.
struct BeamSet {
    std::vector<Beam> items;
    std::unordered_map<std::string, size_t> index;

    void add(const std::string &pref, double pb, double pnb)
    {
        auto it = index.find(pref);
        if (it == index.end()) {
            index.emplace(pref, items.size());
            items.push_back({pref, pb, pnb});
        } else {
            Beam &o = items[it->second];
            o.pb = la2(o.pb, pb);
            o.pnb = la2(o.pnb, pnb);
        }
    }
};

} // namespace

std::vector<Candidate> beam_units(const float *logp, int T, int beam, int nbest, float prune)
{
    std::vector<Beam> beams{{std::string(), 0.0, OKWS_NEG}};
    std::vector<int> top;
    for (int t = 0; t < T; t++) {
        const float *lp = logp + (size_t)t * OKWS_N_UNITS;
        float mx = lp[argmax_row(lp, OKWS_N_UNITS)];
        float th = mx + prune;
        top.clear();
        for (int c = 0; c < OKWS_N_UNITS; c++)
            if (lp[c] >= th)
                top.push_back(c);

        BeamSet nxt;
        for (const Beam &b : beams) {
            double ptot = la2(b.pb, b.pnb);
            for (int c : top) {
                double p = (double)lp[c];
                if (c == OKWS_BLANK) {
                    nxt.add(b.prefix, ptot + p, OKWS_NEG);
                } else if (!b.prefix.empty() && c == (unsigned char)b.prefix.back()) {
                    nxt.add(b.prefix, OKWS_NEG, b.pnb + p);
                    nxt.add(b.prefix + (char)c, OKWS_NEG, b.pb + p);
                } else {
                    nxt.add(b.prefix + (char)c, OKWS_NEG, ptot + p);
                }
            }
        }
        std::stable_sort(nxt.items.begin(), nxt.items.end(), [](const Beam &x, const Beam &y) {
            return la2(x.pb, x.pnb) > la2(y.pb, y.pnb);
        });
        if ((int)nxt.items.size() > beam)
            nxt.items.resize(beam);
        beams.swap(nxt.items);
    }

    std::vector<Candidate> ranked;
    for (const Beam &b : beams)
        ranked.push_back({std::vector<int>(b.prefix.begin(), b.prefix.end()), la2(b.pb, b.pnb)});
    std::stable_sort(ranked.begin(), ranked.end(),
                     [](const Candidate &x, const Candidate &y) { return x.logp > y.logp; });
    if ((int)ranked.size() > nbest)
        ranked.resize(nbest);
    std::vector<Candidate> out;
    for (auto &c : ranked)
        if (!c.units.empty())
            out.push_back(c);
    return out;
}

bool ctc_align(const float *logp, int T, const std::vector<int> &units,
               std::vector<std::pair<int, int>> &spans)
{
    std::vector<int> ext{OKWS_BLANK};
    for (int u : units) {
        ext.push_back(u);
        ext.push_back(OKWS_BLANK);
    }
    const int S = (int)ext.size();
    if (T < S / 2 + 1)
        return false;
    std::vector<unsigned char> skip(S, 0);
    for (int s = 2; s < S; s++)
        if (ext[s] != OKWS_BLANK && ext[s] != ext[s - 2])
            skip[s] = 1;

    std::vector<double> prev(S, OKWS_NEG), cur(S);
    std::vector<unsigned char> bp((size_t)T * S, 0);
    prev[0] = logp[ext[0]];
    if (S > 1)
        prev[1] = logp[ext[1]];
    for (int t = 1; t < T; t++) {
        const float *lp = logp + (size_t)t * OKWS_N_UNITS;
        for (int s = 0; s < S; s++) {
            double a = prev[s];
            double b = s >= 1 ? prev[s - 1] : OKWS_NEG;
            double c = (s >= 2 && skip[s]) ? prev[s - 2] : OKWS_NEG;
            int src = 0; // numpy argmax: first maximum wins
            double best = a;
            if (b > best) {
                src = 1;
                best = b;
            }
            if (c > best) {
                src = 2;
                best = c;
            }
            cur[s] = best + (double)lp[ext[s]];
            bp[(size_t)t * S + s] = (unsigned char)src;
        }
        prev.swap(cur);
    }
    int s = (S == 1 || prev[S - 1] >= prev[S - 2]) ? S - 1 : S - 2;
    std::vector<int> path(T);
    for (int t = T - 1; t >= 0; t--) {
        path[t] = s;
        s -= bp[(size_t)t * S + s];
    }
    spans.clear();
    for (size_t k = 0; k < units.size(); k++) {
        int st = 2 * (int)k + 1, first = -1, last = -1;
        for (int t = 0; t < T; t++) {
            if (path[t] == st) {
                if (first < 0)
                    first = t;
                last = t;
            }
        }
        if (first < 0)
            return false;
        spans.push_back({first, last});
    }
    return true;
}

bool syllable_scores(const float *logp, int T, const std::vector<int> &units,
                     std::vector<double> &scores)
{
    std::vector<std::pair<int, int>> spans;
    if (!ctc_align(logp, T, units, spans))
        return false;
    scores.clear();
    double sum = 0.0;
    int n = 0;
    for (size_t k = 0; k < units.size(); k++) {
        int u = units[k];
        double conf = 0.0;
        for (int t = spans[k].first; t <= spans[k].second; t++)
            conf += (double)logp[(size_t)t * OKWS_N_UNITS + u];
        sum += conf / (spans[k].second - spans[k].first + 1);
        n++;
        bool end = is_final_unit(u) || k + 1 == units.size();
        if (end) {
            scores.push_back(sum / n);
            sum = 0.0;
            n = 0;
        }
    }
    return !scores.empty();
}

bool weakest_syllable(const float *logp, int T, const std::vector<int> &units, double &weak)
{
    std::vector<double> sc;
    if (!syllable_scores(logp, T, units, sc))
        return false;
    weak = *std::min_element(sc.begin(), sc.end());
    return true;
}

bool verify_score(const std::vector<std::vector<int>> &hyps, const VerifyParams &p,
                  const float *logp, int T, double margin, double &score, double &weak)
{
    bool any = false;
    weak = OKWS_NEG;
    int n = std::min<int>((int)hyps.size(), std::max(p.n_hyps, 1));
    for (int j = 0; j < n; j++) {
        double w;
        if (weakest_syllable(logp, T, hyps[j], w) && (!any || w > weak)) {
            weak = w;
            any = true;
        }
    }
    score = any ? weak + p.alpha * margin : OKWS_NEG;
    return any;
}

KeywordScorer::KeywordScorer(const std::vector<Hypothesis> &hyps)
{
    double wsum = 0.0;
    for (const auto &h : hyps)
        wsum += h.weight;
    wsum = std::max(wsum, 1e-9);
    for (const auto &h : hyps) {
        Row r;
        r.ext.push_back(OKWS_BLANK);
        for (int u : h.units) {
            r.ext.push_back(u);
            r.ext.push_back(OKWS_BLANK);
        }
        size_t S = r.ext.size();
        r.skip.assign(S, 0);
        for (size_t s = 2; s < S; s++)
            if (r.ext[s] != OKWS_BLANK && r.ext[s] != r.ext[s - 2])
                r.skip[s] = 1; // may skip one blank between different units
        r.alpha.resize(S);
        r.v.resize(S);
        r.start.resize(S);
        r.st.resize(S);
        r.norm = (double)std::max<size_t>(h.units.size(), 1);
        r.w = h.weight / wsum;
        rows_.push_back(std::move(r));
    }
    reset();
}

void KeywordScorer::reset()
{
    for (auto &r : rows_) {
        std::fill(r.alpha.begin(), r.alpha.end(), OKWS_NEG);
        std::fill(r.start.begin(), r.start.end(), 0);
    }
    t_ = 0;
}

double KeywordScorer::update(const float *lp, int *start)
{
    for (auto &r : rows_) {
        size_t S = r.ext.size();
        for (size_t s = 0; s < S; s++) {
            double a = r.alpha[s];
            double b = s >= 1 ? r.alpha[s - 1] : OKWS_NEG;
            double c = (s >= 2 && r.skip[s]) ? r.alpha[s - 2] : OKWS_NEG;
            // numpy argmax over (a, b, c): first maximum wins
            int src = 0;
            double best = a;
            if (b > best) {
                src = 1;
                best = b;
            }
            if (c > best)
                src = 2;
            r.v[s] = logaddexp(logaddexp(a, b), c);
            if (src == 0)
                r.st[s] = r.start[s];
            else if (src == 1)
                r.st[s] = s >= 1 ? r.start[s - 1] : t_;
            else
                r.st[s] = s >= 2 ? r.start[s - 2] : t_;
        }
        for (size_t col = 0; col < 2 && col < S; col++) {
            if (r.v[col] < 0.0) {
                r.st[col] = t_;
                r.v[col] = 0.0;
            } else {
                r.v[col] = logaddexp(r.v[col], 0.0);
            }
        }
        for (size_t s = 0; s < S; s++)
            r.alpha[s] = r.v[s] + (double)lp[r.ext[s]];
        r.start.swap(r.st);
    }
    t_++;
    if (start)
        *start = rows_.empty() ? 0 : rows_[0].start[rows_[0].ext.size() - 1];
    return score();
}

double KeywordScorer::score() const
{
    double sc = 0.0;
    for (const auto &r : rows_) {
        size_t last = r.ext.size() - 1;
        double end1 = r.alpha[last];
        double end2 = last >= 1 ? r.alpha[last - 1] : OKWS_NEG;
        sc += r.w * (logaddexp(end1, end2) / r.norm);
    }
    return sc;
}

double KeywordScorer::peak(const float *logp, int T)
{
    reset();
    double best = OKWS_NEG;
    for (int t = 0; t < T; t++)
        best = std::max(best, update(logp + (size_t)t * OKWS_N_UNITS));
    return best;
}

} // namespace okws
