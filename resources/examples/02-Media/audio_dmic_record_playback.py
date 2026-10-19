# DMIC (digital PDM microphone) record & playback example.
#
# Records from an onboard PDM digital microphone, saves a normalized 16-bit
# WAV to the SD card, then plays the WAV back through the codec output —
# exercising the full audio in/out path in one run.
#
# Default capture wiring matches boards with an onboard PDM mic:
#   PDM_CLK -> GPIO26 (output), PDM data -> GPIO28 (PDM_IN1, input)
#   Mic L/R pin tied HIGH -> data appears on the right lane of channel group 1.
#
# Note: You will need an SD card to run this example.

import os, time, sys
from media.media import *
from media.pyaudio import *
import media.wave as wave
from machine import FPIOA, Pin

# =====================================================================
# Board / audio configuration — every knob is here, with what it does,
# how to tune it, and what changing it affects.
#
# Playback loudness chain (in order):
#   WAV (already normalized to ~98% full-scale by convert_to_s16)
#     -> PLAYBACK_GAIN (software multiply, clips if >1!)
#     -> BTL_DIFF      (differential drive = +6 dB at the speaker)
#     -> PLAYBACK_VOLUME (codec output analog gain, -43..+7 dB)
#     -> PA (fixed hardware gain, not software adjustable)
# Capture sensitivity chain:
#   PDM mic (digital path, NOT the analog ADC)
#     -> MAX_AUTO_GAIN normalization decides recorded loudness.
#     -> INPUT_VOLUME only affects the ANALOG codec ADC path, so it has
#        no effect on a PDM/DMIC capture. Kept for analog-mic boards.
# =====================================================================

# --- Capture wiring (modify to match your board) ---
# PDM bit clock output pin and data input pin, remapped via FPIOA.
# Wrong pins -> stream opens but captures silence/noise. Check your
# board schematic for the DMIC's CLK/DATA nets.
PDM_CLK_PIN    = 26
PDM_DATA_PIN   = 28
# PDM groups: group 0/1/2/3 map to PDM_IN0..PDM_IN3. Set to the group
# your mic's DATA pin is routed to (GPIO28 = PDM_IN1 -> group 1).
CAPTURE_GROUP  = 1       # which PDM channel group carries the mic
# Each PDM group carries 2 lanes (L/R); the mic's L/R select pin picks
# one. Tied HIGH -> right lane (True); tied LOW/floating -> left (False).
# Wrong lane -> recording is silence or only noise floor.
USE_RIGHT_LANE = True    # mic L/R pin tied HIGH -> right lane

# --- Playback wiring ---
# Boards wiring the codec HP_OUTL/HP_OUTR differentially to a BTL mono
# amplifier need the right channel inverted (L=+s, R=-s), otherwise
# in-phase content cancels and the amp outputs silence. Such boards also
# have a PA enable pin. Example: RockBase (NS4150B) -> PA_PIN=71, BTL_DIFF=True
# PA enable GPIO, driven high before playback and low after.
# None = board enables the amp in hardware (pull-up) or has no PA.
# Wrong value -> playback is silent (amp stays off) or pops at start/stop.
PA_PIN         = None    # amplifier enable pin, None = no PA to toggle
# True = software builds differential stereo (L=+s, R=-s) for BTL bridge
# amps: doubles voltage swing = +6 dB louder, but only if the amp really
# is wired BTL (HP_OUTL/HP_OUTR across the speaker).
# False = both channels in phase, for single-ended amp or stereo speakers.
# Wrong value on a BTL board -> near-total silence (signal cancels).
BTL_DIFF       = True    # True = invert right channel for BTL bridge amps
# Codec output volume: 0..100 maps to -43..+7 dB analog gain at
# HP_OUTL/HP_OUTR (0.5 dB per step, 100 = hardware maximum).
# Raise this first for more loudness — it never distorts the samples.
# Lower it if the amp output is harsh/clipping at speaker level.
# NOTE: the codec's own analog noise floor rises with this setting, so
# a hissier output means lowering it (90 -> +2 dB is a good balance;
# 100 -> +7 dB adds ~5 dB more hiss). Loudness lost here can be won
# back by raising MAX_AUTO_GAIN instead (digital, but also lifts the
# mic noise floor — trade off by ear).
PLAYBACK_VOLUME = 90
# Software multiply applied to samples before writing to the codec.
# The WAV is already normalized to ~98% full-scale, so keep this at 1.0:
# any value > ~1.02 pushes peaks past s16 and hard-clips (audible
# crackling at loud passages). Use PLAYBACK_VOLUME for loudness instead.
# Only raise above 1.0 if you lowered MAX_AUTO_GAIN well below 28.
PLAYBACK_GAIN  = 1.0

# --- Capture params ---
# Recording length in seconds; also sets the WAV size
# (SAMPLE_RATE * RECORD_SECONDS * 2 bytes).
RECORD_SECONDS = 10
# Where the mono s16 WAV is written; must be on the SD card.
OUTPUT_FILE    = "/sdcard/dmic_record.wav"
# PDM decimation sample rate in Hz (16000/48000 typical).
# Changing it changes capture bandwidth and WAV size; playback follows
# the rate stored in the WAV, so record and play stay consistent.
SAMPLE_RATE    = 16000
# Analog codec ADC input gain, 0..100 maps to -20..+30 dB.
# NOTE: only affects the ANALOG mic path (onboard codec ADC). A PDM/DMIC
# capture bypasses the ADC entirely, so this has no effect on DMIC
# sensitivity — loudness there is set by MAX_AUTO_GAIN below.
INPUT_VOLUME   = 35
# Number of first stream reads discarded after opening the PDM stream;
# they often contain zeros or PDM startup pops. Increase if the WAV
# starts with a click, decrease if the first words get cut off.
WARMUP_READS   = 4       # drop the first reads after enabling PDM
# Ceiling of the peak-normalization gain applied when converting the
# raw 32-bit PDM capture to s16 (peak is pushed to 98% of full-scale).
# Higher -> quiet sounds recorded louder, but noise floor is amplified
# too. Lower -> quieter recording, less hiss. The actual gain used is
# printed as auto_gain=... in the [rec] log; if it always hits this cap
# the mic signal is very weak — raise the cap or check wiring/lane.
MAX_AUTO_GAIN  = 28.0    # cap of the normalize-to-s16 gain
# Noise gate: after normalization, samples whose |amplitude| stays below
# this percent of s16 full-scale for a few consecutive samples are driven
# to silence; they pass through unchanged once speech/sound exceeds it.
# Removes the hiss (DMIC + gain noise floor) in quiet stretches.
# 0 = disabled. Raise (3-6) for more aggressive gating; lower (1) if the
# gate clips soft word endings. Hiss DURING loud speech cannot be gated.
NOISE_GATE_PCT = 2       # gate threshold, percent of s16 full-scale
# How many consecutive below-threshold samples must occur before the gate
# closes (at 16 kHz, 800 ~= 50 ms). Longer -> fewer clicks but slower to
# mute after a sound; shorter -> snappier gating, risk of cutting tails.
GATE_HOLD_SAMPLES = 800


def exit_check():
    try:
        os.exitpoint()
    except KeyboardInterrupt:
        return True
    return False


def print_exc(e):
    try:
        sys.print_exception(e)
    except AttributeError:
        print(e)


def init_pdm_io():
    fpioa = FPIOA()
    fpioa.set_function(PDM_CLK_PIN, FPIOA.PDM_CLK, oe=0x1, ie=0x0)
    fpioa.set_function(PDM_DATA_PIN, FPIOA.PDM_IN1, oe=0x0, ie=0x1)
    print("[io] PDM_CLK=GPIO%d PDM_DATA=GPIO%d(PDM_IN1)" % (PDM_CLK_PIN, PDM_DATA_PIN))


def enable_pa():
    if PA_PIN is None:
        return None
    fpioa = FPIOA()
    fpioa.set_function(PA_PIN, getattr(FPIOA, "GPIO%d" % PA_PIN))
    pin = Pin(PA_PIN, Pin.OUT, pull=Pin.PULL_NONE, drive=7)
    pin.value(1)
    print("[play] PA enable GPIO%d -> high" % PA_PIN)
    return pin


def disable_pa(pin):
    if pin:
        pin.value(0)
        print("[play] PA enable GPIO%d -> low" % PA_PIN)


def open_dmic(p):
    # 8 channels = 4 PDM groups, 2 channels = 1 group; fall back if unsupported.
    last_error = None
    for channels in (8, 2):
        try:
            stream = p.open(format=paInt32, channels=channels, rate=SAMPLE_RATE,
                            input=True, input_device_index=1,  # device 1 = PDM
                            frames_per_buffer=max(256, SAMPLE_RATE // 25))
            print("[rec] stream opened: rate=%dHz channels=%d (%d PDM group(s))" %
                  (SAMPLE_RATE, channels, channels // 2))
            return stream, max(1, channels // 2)
        except BaseException as e:
            print("[rec] open with channels=%d failed, retrying..." % channels)
            last_error = e
    raise last_error or RuntimeError("PDM open failed")


def select_lane(data, sample_width):
    # Each PDM group frame interleaves L/R lanes; keep the lane the mic drives.
    if not USE_RIGHT_LANE:
        return data
    frame_bytes = sample_width * 2
    out = bytearray(len(data) // 2)
    src, dst = memoryview(data), memoryview(out)
    j = 0
    for i in range(0, len(data) - (frame_bytes - 1), frame_bytes):
        for k in range(sample_width):
            dst[j + k] = src[i + sample_width + k]
        j += sample_width
    return out[:j]


def convert_to_s16(data, sample_width):
    # PDM capture is 32-bit with low amplitude; normalize peak to ~98% of s16.
    src = memoryview(data)
    sign_bit = 1 << (sample_width * 8 - 1)
    full_scale = 1 << (sample_width * 8)
    base_div = 1 << max(0, (sample_width - 2) * 8)

    peak_abs = 0
    for i in range(0, len(data) - (sample_width - 1), sample_width):
        sample = 0
        for k in range(sample_width):
            sample |= src[i + k] << (8 * k)
        if sample & sign_bit:
            sample -= full_scale
        if abs(sample) > peak_abs:
            peak_abs = abs(sample)

    src_max_abs = (1 << (sample_width * 8 - 1)) - 1
    peak_pct = peak_abs * 100 // src_max_abs
    auto_gain = 1.0
    if peak_abs:
        auto_gain = min(MAX_AUTO_GAIN, (32767 * 0.98) * base_div / peak_abs)

    scale = auto_gain / base_div
    gate_level = 32767 * NOISE_GATE_PCT / 100 if NOISE_GATE_PCT else 0
    out = bytearray((len(data) // sample_width) * 2)
    dst = memoryview(out)
    j = 0
    below_run = 0
    for i in range(0, len(data) - (sample_width - 1), sample_width):
        sample = 0
        for k in range(sample_width):
            sample |= src[i + k] << (8 * k)
        if sample & sign_bit:
            sample -= full_scale
        sample = int(sample * scale)
        sample = max(-32768, min(32767, sample))
        if gate_level:
            # Gate the noise floor: after GATE_HOLD_SAMPLES consecutive
            # samples under the threshold, output silence until a sample
            # crosses it again (hold avoids chopping word onsets/endings).
            if abs(sample) < gate_level:
                below_run += 1
                if below_run > GATE_HOLD_SAMPLES:
                    sample = 0
            else:
                below_run = 0
        dst[j] = sample & 0xFF
        dst[j + 1] = (sample >> 8) & 0xFF
        j += 2
    return out, auto_gain, peak_pct


def to_dual_channel(data, src_channels, sample_width, gain, invert_right):
    # The codec output stage runs in stereo; mono content is duplicated to
    # both lanes. invert_right=True produces differential stereo (L=+s,
    # R=-s) for BTL bridge amps; False keeps both lanes in phase.
    if sample_width != 2:
        return data

    def s16(lo, hi):
        value = lo | (hi << 8)
        return value - 65536 if value >= 32768 else value

    def pack(sample):
        sample = int(sample * gain)
        sample = max(-32768, min(32767, sample))
        return sample & 0xFF, (sample >> 8) & 0xFF

    out = bytearray()
    i = 0
    n = len(data)
    if src_channels == 1:
        while i + 1 < n:
            sample = s16(data[i], data[i + 1])
            i += 2
            lo, hi = pack(sample)
            r_lo, r_hi = pack(-sample if invert_right else sample)
            out += bytes((lo, hi, r_lo, r_hi))
    else:
        if not invert_right:
            return data
        while i + 3 < n:
            sample_l = s16(data[i], data[i + 1])
            sample_r = s16(data[i + 2], data[i + 3])
            i += 4
            lo, hi = pack(sample_l)
            r_lo, r_hi = pack(-sample_r)
            out += bytes((lo, hi, r_lo, r_hi))
    return bytes(out)


def record():
    p, stream = None, None
    try:
        print("\n[1] === Record %ds from DMIC ===" % RECORD_SECONDS)
        init_pdm_io()
        p = PyAudio()
        stream, group_count = open_dmic(p)
        group = CAPTURE_GROUP if CAPTURE_GROUP < group_count else 0
        sample_width = p.get_sample_size(paInt32)
        target_bytes = SAMPLE_RATE * RECORD_SECONDS * sample_width

        try:
            stream.volume(vol=INPUT_VOLUME)
            print("[rec] input volume=%s" % (stream.volume(),))
        except Exception:
            print("[rec] input volume control unavailable")

        print("[rec] capture group=%d/%d lane=%s width=%dbit" %
              (group, group_count, "R" if USE_RIGHT_LANE else "LR", sample_width * 8))

        capture = bytearray()
        reads = 0
        last_pct = -1
        while len(capture) < target_bytes:
            data = stream.read(chn=group)
            if not data:
                continue
            reads += 1
            if reads == 1:
                print("[rec] first packet: %d bytes" % len(data))
            if reads <= WARMUP_READS:
                continue
            capture.extend(select_lane(data, sample_width))
            pct = len(capture) * 100 // target_bytes
            if pct // 10 != last_pct // 10:
                last_pct = pct
                print("[rec] progress %d%%" % pct)
            if exit_check():
                print("[rec] cancelled by user")
                return None

        out, gain, peak_pct = convert_to_s16(bytes(capture[:target_bytes]), sample_width)
        print("[rec] captured %d bytes, raw peak=%d%% full-scale, auto_gain=%.2f" %
              (len(capture), peak_pct, gain))

        wf = wave.open(OUTPUT_FILE, 'wb')
        wf.set_channels(1)
        wf.set_sampwidth(2)
        wf.set_framerate(SAMPLE_RATE)
        wf.write_frames(out)
        wf.close()
        print("[rec] saved %s (%d bytes PCM, 16kHz mono s16)" % (OUTPUT_FILE, len(out)))
        return OUTPUT_FILE
    except BaseException as e:
        print_exc(e)
        return None
    finally:
        if stream:
            stream.stop_stream()
            stream.close()
        if p:
            p.terminate()


def play(filename):
    wf, p, stream, pa_pin = None, None, None, None
    try:
        print("\n[2] === Play back %s ===" % filename)
        wf = wave.open(filename, 'rb')
        sample_width = wf.get_sampwidth()
        rate = wf.get_framerate()
        wav_channels = wf.get_channels()
        chunk = max(256, rate // 25)
        # The codec AO path expects a stereo stream; mono WAV content is
        # expanded to dual channel in software (see to_dual_channel).
        out_channels = 2
        print("[play] wav: %dHz ch=%d width=%dbit -> output ch=%d btl_diff=%s gain=%.1f vol=%d" %
              (rate, wav_channels, sample_width * 8, out_channels, BTL_DIFF,
               PLAYBACK_GAIN, PLAYBACK_VOLUME))

        pa_pin = enable_pa()
        p = PyAudio()
        stream = p.open(format=p.get_format_from_width(sample_width),
                        channels=out_channels, rate=rate, output=True,
                        frames_per_buffer=chunk)
        stream.volume(vol=PLAYBACK_VOLUME)

        total = 0
        data = wf.read_frames(chunk)
        while data:
            data = to_dual_channel(data, wav_channels, sample_width, PLAYBACK_GAIN, BTL_DIFF)
            stream.write(data)
            total += len(data)
            if total % (rate * 2 * out_channels) < chunk:
                print("[play] played ~%ds" % (total // (rate * 2 * out_channels)))
            data = wf.read_frames(chunk)
            if exit_check():
                print("[play] cancelled by user")
                break
        print("[play] done, %d bytes written" % total)
    except BaseException as e:
        print_exc(e)
    finally:
        if stream:
            stream.stop_stream()
            stream.close()
        if p:
            p.terminate()
        if wf:
            wf.close()
        disable_pa(pa_pin)


def main():
    print("=== DMIC record & playback test ===")
    os.exitpoint(os.EXITPOINT_ENABLE)
    path = record()
    if path:
        time.sleep_ms(500)
        play(path)
        print("\n=== Test complete ===")
    else:
        print("\n=== Record failed, playback skipped ===")
    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    time.sleep_ms(100)


if __name__ == "__main__":
    main()
