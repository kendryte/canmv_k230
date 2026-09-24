from model_cleanup import deinit_with_retry
# demo_keyword_spotting.py - Keyword spotting (audio-only, no camera)

import gc
import struct
import time
import ulab.numpy as np
import nncase_runtime as nn
import aidemo
import config
from app_contract import Application
from libs.AIBase import AIBase
from media.pyaudio import *
from media.media import *

KW_KMODEL   = config.KMODEL_DIR + "kws.kmodel"
KW_THRESH   = 0.5
SAMPLE_RATE = 16000
CHANNELS    = 1
CHUNK       = int(0.3 * SAMPLE_RATE)   # 4800 samples per frame
FORMAT      = paInt16

# waveform display constants
WAVE_N_BARS = 60                         # number of bars across the viewport
WAVE_COLOR_IDLE  = (255, 48, 209, 88)    # green  (ARGB)
WAVE_COLOR_DETECT = (255, 10, 132, 255)  # blue highlight when detected
WAVE_BG          = (255, 20, 20, 20)     # dark background


class _KWSModel(AIBase):
    def __init__(self, kmodel_path, threshold):
        try:
            super().__init__(kmodel_path)
            self.threshold = threshold
            self.cache_np = np.zeros((1, 256, 105), dtype=np.float)
        except BaseException:
            # The caller cannot own this model until construction returns.
            try:
                self.deinit()
            except Exception as error:
                print("model constructor cleanup failed:", error)
            raise

    def preprocess(self, pcm_data):
        pcm_list = []
        for i in range(0, len(pcm_data), 2):
            val = struct.unpack("<h", pcm_data[i:i + 2])[0]
            pcm_list.append(float(val))
        mp_feats = aidemo.kws_preprocess(self._fp, pcm_list)[0]
        mp_np = np.array(mp_feats).reshape((1, 30, 40))
        return [nn.from_numpy(mp_np), nn.from_numpy(self.cache_np)]

    def postprocess(self, results):
        logits_np = results[0]
        self.cache_np = results[1]
        max_logits = np.max(logits_np, axis=1)[0]
        max_p = np.max(max_logits)
        idx = np.argmax(max_logits)
        if max_p > self.threshold and idx == 1:
            return True, float(max_p)
        return False, float(max_p)

    def set_fp(self, fp_handle):
        self._fp = fp_handle


class KeywordSpottingDemo(Application):
    name = "关键词唤醒"
    model_path = KW_KMODEL
    rgb_size = [1280, 720]
    is_audio_only = True
    required_files = [KW_KMODEL]

    def __init__(self):
        Application.__init__(self)
        self.canvas = None
        self.detected = False
        self.p = None
        self.input_stream = None
        self._wave_buf = [0] * (WAVE_N_BARS * 4)

        # Roll back on failure: a create() error means runner never calls
        # close(), so the KWS model KPU and the kws feature-pipeline C handle
        # already allocated here must be released before re-raising.
        self.kws = None
        self._fp = None
        try:
            self.kws = _KWSModel(KW_KMODEL, KW_THRESH)
            self._fp = aidemo.kws_fp_create()
            self.kws.set_fp(self._fp)
        except Exception:
            self.deinit()
            raise

    def open(self):
        if self._opened or self.stop_req:
            return
        self.canvas = self.display.create_canvas()
        if self.stop_req:
            return
        self.start()
        self._opened = True

    def run_once(self):
        self.canvas.clear()
        result = self.run()
        count = self.draw_result(self.canvas, result)
        self.display.show(self.canvas)
        return count if count else 0

    def start(self):
        super().start()
        self.p = PyAudio()
        self.input_stream = self.p.open(
            format=FORMAT, channels=CHANNELS, rate=SAMPLE_RATE,
            input=True, frames_per_buffer=CHUNK)
        self.input_stream.volume(vol=100)

    def stop(self):
        super().stop()
        if self.input_stream:
            try:
                self.input_stream.stop_stream()
            except Exception as error:
                print("KWS stream stop failed:", error)
            try:
                self.input_stream.close()
            except Exception:
                pass
            self.input_stream = None
        if self.p:
            try:
                self.p.terminate()
            except Exception:
                pass
            self.p = None

    def run(self, input_np=None):
        pcm_data = self.input_stream.read()
        ok, conf = self.kws.run(pcm_data)

        # down-sample PCM to a small set of amplitudes for the waveform
        samples = len(pcm_data) // 2
        step = max(1, samples // WAVE_N_BARS)
        new_amps = []
        for i in range(0, samples - step, step):
            peak = 0
            for j in range(step):
                idx = (i + j) * 2
                if idx + 1 >= len(pcm_data):
                    break
                val = abs(struct.unpack("<h", pcm_data[idx:idx + 2])[0])
                if val > peak:
                    peak = val
            new_amps.append(peak)

        self._wave_buf = self._wave_buf[len(new_amps):] + new_amps
        return ok, conf, self._wave_buf[-WAVE_N_BARS:]

    def draw_result(self, img, result):
        detected, conf, amps = result
        count = len(amps) if amps else 0
        if not count:
            return 0

        # background
        cw, ch = img.width(), img.height()
        bg_color = (255, 40, 80, 40) if detected else WAVE_BG
        img.draw_rectangle(0, 0, cw, ch, color=bg_color, fill=True)

        # normalize and draw bars
        peak = max(amps) if max(amps) > 0 else 1.0
        bar_w = max(6, cw // count - 2)
        total_w = count * (bar_w + 2)
        offset_x = max(0, (cw - total_w) // 2)

        for i, amp in enumerate(amps):
            h = int(round(amp / peak * ch * 0.9))
            if h < 2:
                h = 2
            x = offset_x + i * (bar_w + 2)
            y = (ch - h) // 2
            color = WAVE_COLOR_DETECT if detected else WAVE_COLOR_IDLE
            img.draw_rectangle(x, y, bar_w, h, color=color, fill=True)

        # detection indicator
        if detected:
            img.draw_string_advanced(16, 28, 32, "Wake!", color=(255, 10, 132, 255))

        return 1 if detected else 0

    def deinit(self):
        # Destroy the feature-pipeline C handle here (not in stop()): keep all
        # resource release in deinit, and guard with None so close()'s single
        # stop()+deinit() sequence destroys it exactly once.
        if self._fp is not None:
            try:
                aidemo.kws_fp_destroy(self._fp)
            except Exception as e:
                print("KWS fp destroy failed:", e)
            self._fp = None
        if self.kws is not None:
            try:
                deinit_with_retry(self.kws)
            except Exception as error:
                print("KWS model cleanup failed:", error)
        gc.collect()

    def _release_owned_resources(self):
        self.canvas = None
