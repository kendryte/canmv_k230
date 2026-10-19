"""Board audio policy shared by voice applications (xiaozhi etc.).

Same table-driven pattern as DisplayConfig: a known-board policy table,
apps query it and fall back to their current behaviour when the board
is not listed. Boards not in the table keep byte-identical behaviour.

Loudness chain notes (see also examples/02-Media/
audio_dmic_record_playback.py, the reference implementation):
  capture: PDM int32 frames are scaled to s16 by a fixed right shift
    (pdm_shift); realtime apps cannot use offline peak normalization.
  playback: BTL bridge amps (HP_OUTL/HP_OUTR across the speaker) need
    differential stereo (L=+s, R=-s); in-phase mono cancels to silence.
"""

import os
from array import array
from machine import FPIOA, Pin
from media.pyaudio import *


# board_type -> policy. Boards without an entry keep the app default.
# Only boards verified on real hardware may be added here.
_POLICIES = {
    # RockBase: onboard LMD4737T261 PDM mic on PDM_IN1 (right lane),
    # NS4150B BTL mono amp on HP_OUTL/HP_OUTR, PA CTRL on GPIO71
    # (hardware pull-up, no software toggle needed).
    "k230_canmv_rockbase": {
        "input": {"clk_pin": 26, "data_pin": 28, "group": 1, "lane": "R"},
        "output": {"btl_diff": True, "pa_pin": None},
        "pdm_shift": 12,
    },
}


def get_audio_policy(board_type=None):
    """Return the audio policy dict for a board, or None for default path.

    Args:
        board_type (str or None): os.uname()[-1] board identifier; None
            queries the running firmware.
    """
    if board_type is None:
        board_type = os.uname()[-1]
    return _POLICIES.get(board_type)


def _pdm_to_s16(data, shift):
    """Convert interleaved PDM int32 stereo to s16 mono (left lane).

    Uses array() with a bytes initializer and bytes(memoryview(...));
    this firmware has neither array.frombytes/tobytes nor
    memoryview.cast(), but both forms here are supported.
    """
    src = array("i", bytes(data))
    dst = array("h", bytearray(len(src) * 2))
    for i in range(len(src)):
        s = src[i] >> shift
        if s > 32767:
            s = 32767
        elif s < -32768:
            s = -32768
        dst[i] = s
    return bytes(memoryview(dst))


def _identity(data):
    return data


def open_input(pa, policy, rate, frames_per_buffer):
    """Open the capture stream described by policy.

    Returns:
        (stream, transform): transform converts one raw read() frame to
            s16 mono bytes ready for opus encoding.
    """
    inp = policy["input"]
    fpioa = FPIOA()
    fpioa.set_function(inp["clk_pin"], FPIOA.PDM_CLK, oe=0x1, ie=0x0)
    fpioa.set_function(inp["data_pin"], FPIOA.PDM_IN1, oe=0x0, ie=0x1)

    last_error = None
    for channels in (8, 2):
        try:
            stream = pa.open(format=paInt32, channels=channels, rate=rate,
                             input=True, input_device_index=1,
                             frames_per_buffer=frames_per_buffer)
            break
        except BaseException as e:
            last_error = e
    else:
        raise last_error

    group = inp["group"]
    shift = policy.get("pdm_shift", 12)
    lane_off = 4 if inp.get("lane", "R") == "R" else 0

    def transform(data):
        # keep one lane of each int32 stereo frame (L at 0, R at 4)
        src = memoryview(bytes(data))
        half = bytearray(len(src) // 2)
        mv = memoryview(half)
        j = 0
        for i in range(0, len(src) - 7, 8):
            mv[j] = src[i + lane_off]
            mv[j + 1] = src[i + lane_off + 1]
            mv[j + 2] = src[i + lane_off + 2]
            mv[j + 3] = src[i + lane_off + 3]
            j += 4
        return _pdm_to_s16(bytes(half), shift)

    return stream, transform, group


def open_output(pa, policy, rate, channels, frames_per_buffer):
    """Open the playback stream described by policy.

    Returns:
        (stream, transform): transform converts mono s16 PCM to the
            interleaved form the stream expects (differential stereo
            for BTL amps).
    """
    out = policy["output"]
    btl = out.get("btl_diff", False)
    pa_pin = None
    if out.get("pa_pin") is not None:
        fpioa = FPIOA()
        fpioa.set_function(out["pa_pin"], getattr(FPIOA, "GPIO%d" % out["pa_pin"]))
        pa_pin = Pin(out["pa_pin"], Pin.OUT, pull=Pin.PULL_NONE, drive=7)
        pa_pin.value(1)

    stream = pa.open(format=paInt16, channels=2 if btl else channels,
                     rate=rate, output=True,
                     frames_per_buffer=frames_per_buffer)

    if not btl:
        return stream, _identity, pa_pin

    def transform(data):
        src = array("h", bytes(data))
        # array initializer counts BYTES: 2 output samples per input
        # sample = len(src)*4 bytes, otherwise indices run out of range.
        dst = array("h", bytearray(len(src) * 4))
        for i in range(len(src)):
            s = src[i]
            dst[2 * i] = s
            dst[2 * i + 1] = -s if s != -32768 else 32767
        return bytes(memoryview(dst))

    return stream, transform, pa_pin


def close_pa(pa_pin):
    if pa_pin:
        pa_pin.value(0)
