/* Copyright (c) 2026, Canaan Bright Sight Co., Ltd
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * C interface of the Open-KWS core, used by modopen_kws.c. No C++ exception
 * crosses this boundary.
 */
#pragma once

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define OKWS_MAX_HYPS_C 8
#define OKWS_MAX_UNITS_C 64
#define OKWS_MAX_CLIPS_C 5
#define OKWS_MAX_KEYWORDS_C 8

typedef struct okws_engine okws_engine_t;

typedef struct {
    int kw;
    float score, threshold, start_ms, end_ms;
} okws_event_t;

typedef struct {
    float audio_ms, fe_ms, kpu_ms, dec_ms;
    int n_infer, n_skip;
    float last_score, chunk_max, best_score, level_rms;
    int speech;
} okws_stats_t;

typedef struct {
    float dur, peak, clip_ratio, snr_db;
} okws_audio_metrics_t;

typedef struct {
    float last_score, chunk_max, best_score, threshold;
    float last_weak;  /* weakest syllable of the latest verification */
    int n_rejected;   /* triggers vetoed by the verification stage */
    int verify;       /* verification enabled for this keyword */
} okws_kw_stats_t;

typedef struct {
    double margin; /* peak forward score on the new clips - threshold */
    double weak;   /* best verification score on the new clips (see okws_engine_set_verify) */
    int has_weak;  /* 0: no hypothesis could be aligned on any clip */
    int verify;    /* the registered keyword uses verification */
    double verify_threshold; /* effective cut: keyword verify threshold + delta */
} okws_confusion_t;

typedef struct {
    int n_hyps;
    int lens[OKWS_MAX_HYPS_C];
    int units[OKWS_MAX_HYPS_C][OKWS_MAX_UNITS_C];
    double weights[OKWS_MAX_HYPS_C];
    double threshold, neg_mean, margin, verify_threshold;
    int n_pos;
    double pos[OKWS_MAX_CLIPS_C];
    int n_syllables;
    int n_audio;
    okws_audio_metrics_t audio[OKWS_MAX_CLIPS_C];
} okws_enroll_result_t;

/* Engine: kmodel + frontend assets + streaming detector. Returns NULL and
 * sets *err (static string, valid until the next create) on failure. */
okws_engine_t *okws_engine_create(const char *kmodel, const char *assets_dir, const char **err);
void okws_engine_destroy(okws_engine_t *e);

/* Keywords (up to OKWS_MAX_KEYWORDS_C). units is the concatenation of all
 * hypotheses of one keyword. add() returns the keyword index or -1; events
 * report that index. set_keyword() = clear + add (n_hyps = 0 only clears).
 * verify_threshold: weakest-syllable verification threshold (pykws v2,
 * normally -3.0); NAN disables the second stage for this keyword. */
int okws_engine_add_keyword(okws_engine_t *e, const int *units, const int *lens,
                            const double *weights, int n_hyps, double threshold,
                            int cooldown_ms, int confirm_frames, double verify_threshold);
int okws_engine_set_keyword(okws_engine_t *e, const int *units, const int *lens,
                            const double *weights, int n_hyps, double threshold,
                            int cooldown_ms, int confirm_frames, double verify_threshold);
void okws_engine_clear_keywords(okws_engine_t *e);
int okws_engine_has_keyword(okws_engine_t *e);
int okws_engine_keyword_count(okws_engine_t *e);
int okws_engine_keyword_stats(okws_engine_t *e, int idx, okws_kw_stats_t *st);
void okws_engine_set_bias(okws_engine_t *e, double bias);
void okws_engine_set_vad(okws_engine_t *e, int enable);
/* Enrollment recording quality limits, used by the next enroll_begin():
 * max share of samples at full scale (default 1e-3) and min SNR in dB (10). */
void okws_engine_set_quality(okws_engine_t *e, double clip_ratio, double min_snr);
void okws_engine_get_quality(okws_engine_t *e, double *clip_ratio, double *min_snr);
/* Verification rule for all keywords: passes if
 *   max over the first n_hyps hypotheses of the weakest syllable
 *   + alpha * (forward score - threshold)  >  verify_threshold + delta.
 * Default (1, 0, 0) is pykws v2. */
void okws_engine_set_verify(okws_engine_t *e, int n_hyps, double alpha, double delta);
void okws_engine_get_verify(okws_engine_t *e, int *n_hyps, double *alpha, double *delta);
void okws_engine_reset(okws_engine_t *e);

/* Streaming detection. Returns the number of events, or -1 on model error. */
int okws_engine_push(okws_engine_t *e, const int16_t *pcm, size_t n, okws_event_t *ev, int max_ev);
int okws_engine_flush(okws_engine_t *e, okws_event_t *ev, int max_ev);
void okws_engine_stats(okws_engine_t *e, okws_stats_t *st);

/* Debug: whole-clip features [40][T] (mel-major like pykws) and streaming
 * log posteriors [T'][59]. *_frames() give the output size for n samples.
 * Return the number of frames written, or -1 on error. */
int okws_features_frames(size_t n);
int okws_logp_frames(size_t n);
int okws_engine_features(okws_engine_t *e, const int16_t *pcm, size_t n, float *out);
int okws_engine_logp(okws_engine_t *e, const int16_t *pcm, size_t n, float *out);

/* Enrollment helpers on raw recordings. */
int okws_trim(const int16_t *pcm, size_t n, size_t *beg, size_t *end);
int okws_check_audio(const int16_t *pcm, size_t n, okws_audio_metrics_t *m);

/* One enrollment session per engine. add() returns the audio reason code
 * (0 = accepted) or -1 on model error. step() returns the enroll error code. */
int okws_engine_enroll_begin(okws_engine_t *e, int use_beam);
/* noise_rms: ambient level (DC removed, full scale = 1) measured before the
 * recording, used as the SNR reference; <= 0 uses the clip's quiet frames. */
int okws_engine_enroll_add(okws_engine_t *e, const int16_t *pcm, size_t n, okws_audio_metrics_t *m,
                           double noise_rms);
int okws_engine_enroll_count(okws_engine_t *e);
int okws_engine_enroll_step(okws_engine_t *e, int *done, int *progress, int *total);
int okws_engine_enroll_result(okws_engine_t *e, okws_enroll_result_t *out);
void okws_engine_enroll_end(okws_engine_t *e);
/* Confusability of the session's clips with every registered keyword. Keyword
 * i would wake on the new word if margin > 0 and (without verification or
 * weak > its verify threshold). Returns the count. */
int okws_engine_enroll_confusion(okws_engine_t *e, okws_confusion_t *out, int max);
/* Reverse confusability: how a candidate keyword (not registered) scores on a
 * recording, e.g. the saved clips of a registered keyword. Fills margin (peak
 * forward score - threshold), weak (verification score under the current
 * rule; *has_weak = 0 if not alignable) and cut (verify_threshold + delta).
 * Returns 0, or -1 on bad input/model error. */
int okws_engine_probe(okws_engine_t *e, const int *units, const int *lens, const double *weights,
                      int n_hyps, double threshold, double verify_threshold, const int16_t *pcm,
                      size_t n, double *margin, double *weak, int *has_weak, double *cut);

const char *okws_audio_reason_str(int reason);
const char *okws_enroll_error_str(int err);

#ifdef __cplusplus
}
#endif
