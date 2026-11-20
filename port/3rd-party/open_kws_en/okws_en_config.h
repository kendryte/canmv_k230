/* Copyright (c) 2026, Canaan Bright Sight Co., Ltd
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * Open-KWS-EN constants. Every value mirrors the English model's reference
 * implementation and porting specification and must stay identical: they were
 * calibrated together with the kmodel, so changing one here silently breaks
 * the thresholds. Differences against the Chinese open_kws are marked "EN:".
 */
#pragma once

/* frontend (feat.py) -- identical to the Chinese model, the two share
 * window512.npy and mel_fb.npy byte for byte; only the CMVN files differ */
#define OKWS_EN_SR 16000
#define OKWS_EN_N_FFT 512
#define OKWS_EN_HOP 160
#define OKWS_EN_OVERLAP (OKWS_EN_N_FFT - OKWS_EN_HOP) /* 352 */
#define OKWS_EN_N_BINS (OKWS_EN_N_FFT / 2 + 1)        /* 257 */
#define OKWS_EN_N_MELS 40
#define OKWS_EN_LOG_EPS 1e-6f

/* sliding-window encoder (encoder.py) */
#define OKWS_EN_T_WIN 96
#define OKWS_EN_HOP_FRAMES 16
#define OKWS_EN_OUT_HOP (OKWS_EN_HOP_FRAMES / 4)
#define OKWS_EN_T_OUT (OKWS_EN_T_WIN / 4)
#define OKWS_EN_GUARD 2
#define OKWS_EN_N_UNITS 42 /* EN: 42 ARPAbet units, not the 59 Chinese ones */
#define OKWS_EN_BLANK 0
#define OKWS_EN_FIRST_PHONE 3 /* ids 0..2 are <blank> <sil> <unk> */

/* streaming detector (detect.py) */
#define OKWS_EN_CHUNK (OKWS_EN_HOP * OKWS_EN_HOP_FRAMES) /* 2560 samples = 160 ms */
#define OKWS_EN_FRAME_MS (OKWS_EN_HOP * 4 * 1000.0 / OKWS_EN_SR)
#define OKWS_EN_FEAT_MS (OKWS_EN_HOP * 1000.0 / OKWS_EN_SR) /* 10 ms per feature frame */
#define OKWS_EN_NEG (-1e30)
#define OKWS_EN_VAD_TH_DB 8.0
#define OKWS_EN_VAD_HANG 6
#define OKWS_EN_VAD_ABS_RMS 0.02
#define OKWS_EN_VAD_RISE 1.002
#define OKWS_EN_VAD_INIT 0.05
#define OKWS_EN_CONFIRM 2
#define OKWS_EN_COOLDOWN_MS 1500

/* enrollment (enroll.py DEFAULT_CFG) */
#define OKWS_EN_BEAM 20
#define OKWS_EN_NBEST 5
#define OKWS_EN_BEAM_PRUNE (-9.0f)
#define OKWS_EN_MAX_HYPS 8
#define OKWS_EN_GAMMA 0.38
#define OKWS_EN_MIN_DUR 0.5  /* EN: 0.5 s, a fast 3-syllable phrase is shorter than 0.6 s */
#define OKWS_EN_MAX_DUR 2.5
#define OKWS_EN_MIN_SNR 10.0
#define OKWS_EN_CLIP_RATIO 5e-3 /* EN: K230 recordings clip 0.35% on average */
#define OKWS_EN_MAX_ENROLL 5
#define OKWS_EN_MAX_UNITS 64
#define OKWS_EN_MAX_KEYWORDS 8
/* EN: length gate on the main hypothesis (langpack_en.json "gate"), replacing
 * the Chinese "at least 4 finals" rule. "Hey Kendryte" = 3 nuclei, 9 units. */
#define OKWS_EN_MIN_NUCLEI 3
#define OKWS_EN_MIN_UNITS 6

/* two-stage verification: weakest syllable of the main hypothesis, force
 * aligned on the last VERIFY_BUF output frames. Syllable grouping comes from
 * the enrollment record (verify.syllables), so detection has no language rule. */
#define OKWS_EN_VERIFY_TH (-6.0) /* EN: -6.0, NOT the Chinese -3.0. Measured: */
                                 /* true wake-ups reach -4.33 at worst, so -3.0 rejects ~5% of them */
#define OKWS_EN_VERIFY_BUF 50    /* EN: 50 output frames = 2.0 s */

/* tail pause check, disabled by default: real usage is
 * "<wake word>, <command>" with no pause, where enabling it causes false rejects */
#define OKWS_EN_TAIL_W 4
#define OKWS_EN_TAIL_THETA 0.5

/* board-side endpoint trimming of fixed-length enrollment recordings */
#define OKWS_EN_TRIM_FRAME 160
#define OKWS_EN_TRIM_NOISE_Q 0.10
#define OKWS_EN_TRIM_RATIO_DB 9.0
#define OKWS_EN_TRIM_ABS_RMS 0.005
#define OKWS_EN_TRIM_PAD 3200 /* 200 ms */
