from model_cleanup import deinit_with_retry
# demo_tts_zh.py - Chinese TTS (text-to-speech) with preset phrase selector

import gc
import struct
import time
import ulab.numpy as np
import nncase_runtime as nn
import aidemo
import media.wave as wave
import config
from app_contract import Application
from libs.AIBase import AIBase
from media.pyaudio import *
from media.media import *

SAVE_WAV = "/data/tts_temp.wav"

KW_ENCODER   = config.KMODEL_DIR + "zh_fastspeech_1_f32.kmodel"
KW_DECODER   = config.KMODEL_DIR + "zh_fastspeech_2.kmodel"
KW_HIFIGAN   = config.KMODEL_DIR + "hifigan.kmodel"
KW_DICT      = config.UTILS_DIR + "pinyin.txt"
KW_PHASE     = config.UTILS_DIR + "small_pinyin.txt"
KW_MAP       = config.UTILS_DIR + "phone_map.txt"


class _EncoderApp(AIBase):
    def __init__(self, kmodel_path, dict_path, phase_path, mapfile):
        try:
            self.ttszh = None
            super().__init__(kmodel_path)
            self.ttszh = aidemo.tts_zh_create(dict_path, phase_path, mapfile)
            self.data = None
            self.data_len = 0
            self.durition_sum = 0
        except BaseException:
            # The caller cannot own this model until construction returns.
            try:
                self.deinit()
            except Exception as error:
                print("model constructor cleanup failed:", error)
            raise

    def preprocess(self, text):
        pre_data = aidemo.tts_zh_preprocess(self.ttszh, text)
        self.data = pre_data[0]
        self.data_len = pre_data[1]
        enc_seq_t = nn.from_numpy(np.array(self.data))
        try:
            enc_spk_t = nn.from_numpy(np.array([0.0]))
        except BaseException:
            try:
                enc_seq_t.release()
            except Exception as error:
                print("TTS input rollback failed:", error)
            raise
        return [enc_spk_t, enc_seq_t]

    def postprocess(self, results):
        enc_out_0 = results[0]
        enc_out_1 = results[1]
        duritions = enc_out_1[0][:int(self.data_len[0])]
        self.durition_sum = int(np.sum(duritions))

        max_val = 13
        while self.durition_sum > 600:
            for i in range(len(duritions)):
                if duritions[i] > max_val:
                    duritions[i] = max_val
            max_val -= 1
            self.durition_sum = int(np.sum(duritions))

        dec_in = np.zeros((1, 600, 256), dtype=np.float)
        k = 0
        for i in range(len(duritions)):
            for j in range(int(duritions[i])):
                dec_in[0][k] = enc_out_0[0][i]
                k += 1
        return dec_in, self.durition_sum

    def destroy(self):
        handle = getattr(self, "ttszh", None)
        if handle is not None:
            aidemo.tts_zh_destroy(handle)
            self.ttszh = None

    def deinit(self):
        error = None
        try:
            self.destroy()
        except Exception as exc:
            error = exc
        try:
            AIBase.deinit(self)
        except Exception as exc:
            if error is None:
                error = exc
        if error is not None:
            raise error


class _DecoderApp(AIBase):
    def __init__(self, kmodel_path):
        try:
            super().__init__(kmodel_path)
        except BaseException:
            # The caller cannot own this model until construction returns.
            try:
                self.deinit()
            except Exception as error:
                print("model constructor cleanup failed:", error)
            raise

    def preprocess(self, dec_input):
        return [nn.from_numpy(dec_input)]

    def postprocess(self, results):
        return results[0]


class _HifiGanApp(AIBase):
    def __init__(self, kmodel_path):
        try:
            super().__init__(kmodel_path)
            self.subvector_num = 0
            self.hifi_input = None
            self.mel_data = []
        except BaseException:
            # The caller cannot own this model until construction returns.
            try:
                self.deinit()
            except Exception as error:
                print("model constructor cleanup failed:", error)
            raise

    def _prep(self, dec_out_np, dur_sum):
        self.subvector_num = dur_sum // 100
        if dur_sum % 100 > 0:
            self.subvector_num += 1
        self.hifi_input = np.zeros((1, 80, self.subvector_num * 100),
                                   dtype=np.float)
        for i in range(dur_sum):
            self.hifi_input[:, :, i] = dec_out_np[:, :, i]

    def generate(self, dec_out_np, dur_sum):
        self.mel_data = []
        self._prep(dec_out_np, dur_sum)
        for i in range(self.subvector_num):
            src = np.zeros((1, 80, 100), dtype=np.float)
            for j in range(80):
                for k in range(i * 100, (i + 1) * 100):
                    src[0][j][k - i * 100] = self.hifi_input[0][j][k]
            t = nn.from_numpy(src)
            try:
                res = self.inference([t])
                self.mel_data += res[0][0][0].tolist()
            finally:
                t.release()
        return self.mel_data


class TTSZHDemo(Application):
    name = "语音合成"
    model_path = KW_ENCODER
    rgb_size = [1280, 720]
    is_audio_only = True
    required_files = [
        KW_ENCODER, KW_DECODER, KW_HIFIGAN,
        KW_DICT, KW_PHASE, KW_MAP,
    ]

    tts_phrases = [
        "你好，今天天气怎么样？",
        "这是一款很好的边缘端芯片",
        "欢迎使用应用中心",
        "人工智能让生活更美好",
        "这是一段中文语音合成测试",
        "今天心情很好",
    ]

    def __init__(self):
        Application.__init__(self)
        self.canvas = None
        self._busy = False
        # Roll back partially-created models on failure: a create() error means
        # runner never calls close(), so the encoder KPU + ttszh C frontend
        # already allocated here must be released before re-raising.
        self.encoder = None
        self.decoder = None
        self.hifigan = None
        try:
            self.encoder = _EncoderApp(KW_ENCODER, KW_DICT, KW_PHASE, KW_MAP)
            self.decoder = _DecoderApp(KW_DECODER)
            self.hifigan = _HifiGanApp(KW_HIFIGAN)
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

    def stop(self):
        super().stop()

    def run(self, input_np=None):
        text = config.tts_text
        if not text or self._busy:
            time.sleep_ms(50)
            return False, ""

        self._busy = True
        config.tts_text = ""
        config.tts_status = "generating"
        completed = False

        try:
            if self.stop_req:
                self._busy = False
                config.tts_status = "ready"
                return False, ""

            dec_in, dur_sum = self.encoder.run(text)
            if self.stop_req:
                self._busy = False
                config.tts_status = "ready"
                return False, ""

            dec_out = self.decoder.run(dec_in)
            if self.stop_req:
                self._busy = False
                config.tts_status = "ready"
                return False, ""

            mel = self.hifigan.generate(dec_out, dur_sum)
            if self.stop_req:
                self._busy = False
                config.tts_status = "ready"
                return False, ""

            clip = np.clip(np.array(mel[:dur_sum * 256],
                                    dtype=np.float), -1.0, 1.0)
            pcm = np.array(clip * 32767.0, dtype=np.int16).tobytes()
            wf = wave.open(SAVE_WAV, 'wb')
            try:
                wf.set_channels(1)
                wf.set_sampwidth(2)
                wf.set_framerate(24000)
                wf.write_frames(pcm)
            finally:
                wf.close()

            if self.stop_req:
                self._busy = False
                config.tts_status = "ready"
                return False, ""

            config.tts_status = "playing"
            self._play_wav()
            completed = True

        except Exception as e:
            import sys as _s
            _s.print_exception(e)
            config.tts_status = "error"
            self._busy = False
            return False, ""
        finally:
            self._clear_synthesis_buffers()
            self._busy = False
            if completed and not self.stop_req:
                config.tts_status = "done"

        gc.collect()
        return True, text

    def _clear_synthesis_buffers(self):
        for model in (self.encoder, self.decoder, self.hifigan):
            if model is None:
                continue
            model.cur_img = None
            model.results.clear()
            for index, tensor in enumerate(model.tensors):
                if tensor is None:
                    continue
                try:
                    tensor.release()
                    model.tensors[index] = None
                except Exception as error:
                    print("TTS tensor release failed:", error)
            if all(tensor is None for tensor in model.tensors):
                model.tensors.clear()
        if self.encoder is not None:
            self.encoder.data = None
        if self.hifigan is not None:
            self.hifigan.hifi_input = None
            self.hifigan.mel_data = []

    def _play_wav(self):
        # These are C-side audio/file resources.  Release them in finally so an
        # error mid-playback cannot leak the output stream, the PyAudio instance
        # or the wave handle (which would accumulate across repeated synthesis).
        p = None
        out = None
        wf = None
        try:
            p = PyAudio()
            SAMPLE_RATE = 24000
            CHANNELS = 1
            FORMAT = paInt16
            CHUNK = int(0.3 * 24000)
            out = p.open(format=FORMAT, channels=CHANNELS,
                         rate=SAMPLE_RATE, output=True,
                         frames_per_buffer=CHUNK)
            wf = wave.open(SAVE_WAV, "rb")
            data = wf.read_frames(CHUNK)
            while data:
                if self.stop_req:
                    break
                out.write(data)
                data = wf.read_frames(CHUNK)
            if not self.stop_req:
                time.sleep(2)
        except Exception as e:
            print("TTS play failed:", e)
        finally:
            if wf is not None:
                try:
                    wf.close()
                except Exception as e:
                    print("TTS wav close failed:", e)
            if out is not None:
                try:
                    out.stop_stream()
                except Exception as e:
                    print("TTS output stream stop failed:", e)
                try:
                    out.close()
                except Exception as e:
                    print("TTS output stream close failed:", e)
            if p is not None:
                try:
                    p.terminate()
                except Exception as e:
                    print("TTS PyAudio terminate failed:", e)

    def draw_result(self, img, result):
        return 1 if result[0] else 0

    def deinit(self):
        try:
            deinit_with_retry(self.encoder)
        except Exception as error:
            print("TTS encoder cleanup failed:", error)
        try:
            deinit_with_retry(self.decoder)
        except Exception as error:
            print("TTS decoder cleanup failed:", error)
        try:
            deinit_with_retry(self.hifigan)
        except Exception as error:
            print("TTS hifigan cleanup failed:", error)
        gc.collect()

    def _release_owned_resources(self):
        self.canvas = None
