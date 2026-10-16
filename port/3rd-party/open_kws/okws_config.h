/* Copyright (c) 2026, Canaan Bright Sight Co., Ltd
 * SPDX-License-Identifier: BSD-3-Clause
 *
 * Open-KWS constants. Every value mirrors kws_deploy_package/pykws
 * (feat.py / encoder.py / detect.py / enroll.py) and must stay identical.
 */
#pragma once

/* frontend (feat.py) */
#define OKWS_SR 16000
#define OKWS_N_FFT 512
#define OKWS_HOP 160
#define OKWS_OVERLAP (OKWS_N_FFT - OKWS_HOP) /* 352 */
#define OKWS_N_BINS (OKWS_N_FFT / 2 + 1)     /* 257 */
#define OKWS_N_MELS 40
#define OKWS_LOG_EPS 1e-6f

/* sliding-window encoder (encoder.py) */
#define OKWS_T_WIN 96
#define OKWS_HOP_FRAMES 16
#define OKWS_OUT_HOP (OKWS_HOP_FRAMES / 4)
#define OKWS_T_OUT (OKWS_T_WIN / 4)
#define OKWS_GUARD 2
#define OKWS_N_UNITS 59
#define OKWS_BLANK 0

/* streaming detector (detect.py) */
#define OKWS_CHUNK (OKWS_HOP * OKWS_HOP_FRAMES) /* 2560 samples = 160 ms */
#define OKWS_FRAME_MS (OKWS_HOP * 4 * 1000.0 / OKWS_SR)
#define OKWS_NEG (-1e30)
#define OKWS_VAD_TH_DB 8.0
#define OKWS_VAD_HANG 6
#define OKWS_VAD_ABS_RMS 0.02
#define OKWS_VAD_RISE 1.002
#define OKWS_VAD_INIT 0.05
#define OKWS_CONFIRM 2
#define OKWS_COOLDOWN_MS 1500

/* enrollment (enroll.py cfg) */
#define OKWS_BEAM 20
#define OKWS_NBEST 5
#define OKWS_BEAM_PRUNE (-9.0f)
#define OKWS_MAX_HYPS 8
#define OKWS_GAMMA 0.38
#define OKWS_MIN_SYL 4
#define OKWS_MIN_DUR 0.6
#define OKWS_MAX_DUR 2.5
#define OKWS_MIN_SNR 10.0
#define OKWS_CLIP_RATIO 1e-3
#define OKWS_MAX_ENROLL 5
#define OKWS_MAX_UNITS 64
#define OKWS_MAX_KEYWORDS 8

/* two-stage verification (pykws v2 detect.py / enroll.py): weakest syllable of
 * the main hypothesis, force-aligned on the last VERIFY_BUF output frames */
#define OKWS_VERIFY_TH (-3.0)
#define OKWS_VERIFY_BUF 40
#define OKWS_FIRST_FINAL 24 /* units.txt: ids >= 24 are finals (a .. vn) */

/* board-side endpoint trimming of fixed-length enrollment recordings */
#define OKWS_TRIM_FRAME 160
#define OKWS_TRIM_NOISE_Q 0.10
#define OKWS_TRIM_RATIO_DB 9.0
#define OKWS_TRIM_ABS_RMS 0.005
#define OKWS_TRIM_PAD 3200 /* 200 ms */
