/* Copyright (c) 2026, Canaan Bright Sight Co., Ltd
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * C interface of the Open-KWS-EN core, used by modopen_kws_en.c. No C++
 * exception crosses this boundary.
 *
 * Mirrors open_kws (Chinese), differing where English does: 42 units,
 * English CMVN, and a syllable grouping that travels with the keyword
 * instead of being derived from the unit ids.
 */
#pragma once

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define OKWS_EN_MAX_HYPS_C 8
#define OKWS_EN_MAX_UNITS_C 64
#define OKWS_EN_MAX_CLIPS_C 5
#define OKWS_EN_MAX_KEYWORDS_C 8
#define OKWS_EN_N_UNITS_C 42

typedef struct okws_en_engine okws_en_engine_t;

typedef struct {
    int kw;
    float score, threshold, weak, start_ms, end_ms;
    int has_weak; /* 0: the keyword has no second stage */
} okws_en_event_t;

typedef struct {
    float audio_ms, fe_ms, kpu_ms, dec_ms;
    int n_infer, n_skip;
    float last_score, chunk_max, best_score, level_rms;
    int speech;
} okws_en_stats_t;

typedef struct {
    float dur, peak, clip_ratio, snr_db;
} okws_en_audio_metrics_t;

typedef struct {
    float last_score, chunk_max, best_score, threshold;
    float last_weak;  /* weakest syllable of the latest verification */
    int n_rejected;   /* triggers vetoed by the verification stage */
    int verify;       /* verification enabled for this keyword */
} okws_en_kw_stats_t;

typedef struct {
    double margin; /* peak forward score on the new clips - threshold */
    double weak;   /* best verification score on the new clips */
    int has_weak;  /* 0: no hypothesis could be aligned on any clip */
    int verify;    /* the registered keyword uses verification */
    double verify_threshold; /* effective cut: keyword verify threshold + delta */
} okws_en_confusion_t;

typedef struct {
    int n_hyps;
    int lens[OKWS_EN_MAX_HYPS_C];
    int units[OKWS_EN_MAX_HYPS_C][OKWS_EN_MAX_UNITS_C];
    double weights[OKWS_EN_MAX_HYPS_C];
    /* syllable grouping per hypothesis; syls[0] becomes verify.syllables */
    int n_syls[OKWS_EN_MAX_HYPS_C];
    int syls[OKWS_EN_MAX_HYPS_C][OKWS_EN_MAX_UNITS_C];
    double threshold, neg_mean, margin, verify_threshold;
    int n_pos;
    double pos[OKWS_EN_MAX_CLIPS_C];
    int n_nuclei, n_main_units; /* length gate values of the main hypothesis */
    int n_audio;
    okws_en_audio_metrics_t audio[OKWS_EN_MAX_CLIPS_C];
} okws_en_enroll_result_t;

/* Engine: kmodel + frontend assets + streaming detector. Returns NULL and
 * sets *err (static string, valid until the next create) on failure.
 * assets_dir must hold window512.npy, mel_fb.npy and the English CMVN pair
 * cmvn_mean_en.npy / cmvn_std_en.npy. */
okws_en_engine_t *okws_en_engine_create(const char *kmodel, const char *assets_dir,
                                        const char **err);
void okws_en_engine_destroy(okws_en_engine_t *e);

/* Enrollment language pack (vowel nuclei + legal onset clusters as unit ids,
 * plus the length gate). Defaults to the compiled-in English table; pass the
 * values of assets/langpack_en.json to keep that asset authoritative.
 * onsets is the concatenation of n_onsets clusters of onset_lens[i] ids.
 * Returns 0, or -1 on an out-of-range unit id (the old table is kept). */
int okws_en_engine_set_langpack(okws_en_engine_t *e, const int *nuclei, int n_nuclei,
                                const int *onsets, const int *onset_lens, int n_onsets,
                                int min_nuclei, int min_units);

/* Keywords (up to OKWS_EN_MAX_KEYWORDS_C). units is the concatenation of all
 * hypotheses of one keyword, lens[i] the unit count of hypothesis i. syls is
 * the concatenation of the syllable groupings, n_syls[i] the syllable count of
 * hypothesis i; pass n_syls = NULL (or n_syls[i] = 0) to syllabify hypothesis i
 * from the language pack. add() returns the keyword index or -1; events report
 * that index. verify_threshold: weakest-syllable threshold (normally -6.0);
 * NAN disables the second stage for this keyword. */
int okws_en_engine_add_keyword(okws_en_engine_t *e, const int *units, const int *lens,
                               const double *weights, int n_hyps, const int *syls,
                               const int *n_syls, double threshold, int cooldown_ms,
                               int confirm_frames, double verify_threshold, int tail_enabled);
void okws_en_engine_clear_keywords(okws_en_engine_t *e);
int okws_en_engine_has_keyword(okws_en_engine_t *e);
int okws_en_engine_keyword_count(okws_en_engine_t *e);
int okws_en_engine_keyword_stats(okws_en_engine_t *e, int idx, okws_en_kw_stats_t *st);
void okws_en_engine_set_bias(okws_en_engine_t *e, double bias);
void okws_en_engine_set_vad(okws_en_engine_t *e, int enable);
/* Tail pause check window and peak threshold, shared by the keywords that
 * enable it; off unless a keyword asks for it. */
void okws_en_engine_set_tail(okws_en_engine_t *e, int w, double theta);
/* Enrollment recording quality limits, used by the next enroll_begin():
 * max share of samples at full scale (default 5e-3) and min SNR in dB (10). */
void okws_en_engine_set_quality(okws_en_engine_t *e, double clip_ratio, double min_snr);
void okws_en_engine_get_quality(okws_en_engine_t *e, double *clip_ratio, double *min_snr);
/* Verification rule for all keywords: passes if
 *   max over the first n_hyps hypotheses of the weakest syllable
 *   + alpha * (forward score - threshold)  >  verify_threshold + delta.
 * Default (1, 0, 0) is the rule the English model was calibrated with. */
void okws_en_engine_set_verify(okws_en_engine_t *e, int n_hyps, double alpha, double delta);
void okws_en_engine_get_verify(okws_en_engine_t *e, int *n_hyps, double *alpha, double *delta);
void okws_en_engine_reset(okws_en_engine_t *e);

/* Streaming detection. Returns the number of events, or -1 on model error. */
int okws_en_engine_push(okws_en_engine_t *e, const int16_t *pcm, size_t n, okws_en_event_t *ev,
                        int max_ev);
int okws_en_engine_flush(okws_en_engine_t *e, okws_en_event_t *ev, int max_ev);
void okws_en_engine_stats(okws_en_engine_t *e, okws_en_stats_t *st);

/* Debug: whole-clip features [40][T] (mel-major like pykws) and streaming
 * log posteriors [T'][42]. *_frames() give the output size for n samples.
 * Return the number of frames written, or -1 on error. */
int okws_en_features_frames(size_t n);
int okws_en_logp_frames(size_t n);
int okws_en_engine_features(okws_en_engine_t *e, const int16_t *pcm, size_t n, float *out);
int okws_en_engine_logp(okws_en_engine_t *e, const int16_t *pcm, size_t n, float *out);

/* Syllabify a unit sequence with the current language pack (the rule used at
 * enrollment time). Writes at most max_out syllable lengths and returns their
 * count, or -1 when the sequence has no vowel nucleus. */
int okws_en_engine_syllabify(okws_en_engine_t *e, const int *units, int n, int *out, int max_out);

/* Enrollment helpers on raw recordings. */
int okws_en_trim(const int16_t *pcm, size_t n, size_t *beg, size_t *end);
int okws_en_check_audio(const int16_t *pcm, size_t n, okws_en_audio_metrics_t *m);

/* One enrollment session per engine. add() returns the audio reason code
 * (0 = accepted) or -1 on model error. step() returns the enroll error code. */
int okws_en_engine_enroll_begin(okws_en_engine_t *e, int use_beam);
/* noise_rms: ambient level (DC removed, full scale = 1) measured before the
 * recording, used as the SNR reference; <= 0 uses the clip's quiet frames. */
int okws_en_engine_enroll_add(okws_en_engine_t *e, const int16_t *pcm, size_t n,
                              okws_en_audio_metrics_t *m, double noise_rms);
int okws_en_engine_enroll_count(okws_en_engine_t *e);
int okws_en_engine_enroll_step(okws_en_engine_t *e, int *done, int *progress, int *total);
int okws_en_engine_enroll_result(okws_en_engine_t *e, okws_en_enroll_result_t *out);
void okws_en_engine_enroll_end(okws_en_engine_t *e);
/* Confusability of the session's clips with every registered keyword. Keyword
 * i would wake on the new word if margin > 0 and (without verification or
 * weak > its verify threshold). Returns the count. */
int okws_en_engine_enroll_confusion(okws_en_engine_t *e, okws_en_confusion_t *out, int max);
/* Reverse confusability: how a candidate keyword (not registered) scores on a
 * recording, e.g. the saved clips of a registered keyword. Fills margin (peak
 * forward score - threshold), weak (verification score under the current
 * rule; *has_weak = 0 if not alignable) and cut (verify_threshold + delta).
 * syls / n_syls follow okws_en_engine_add_keyword. Returns 0, or -1 on bad
 * input or model error. */
int okws_en_engine_probe(okws_en_engine_t *e, const int *units, const int *lens,
                         const double *weights, int n_hyps, const int *syls, const int *n_syls,
                         double threshold, double verify_threshold, const int16_t *pcm, size_t n,
                         double *margin, double *weak, int *has_weak, double *cut);

const char *okws_en_audio_reason_str(int reason);
const char *okws_en_enroll_error_str(int err);

#ifdef __cplusplus
}
#endif
