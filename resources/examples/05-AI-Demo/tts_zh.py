from libs.Utils import ScopedTiming
from libs.AIBase import AIBase
from libs.TTSInput import TTSInputError, validate_text, preprocess_text
from media.pyaudio import PyAudio, paInt16
import media.wave as wave
import nncase_runtime as nn
import ulab.numpy as np
import aidemo
import time
import gc
import os


def _cleanup(actions, suppress_errors=False):
    """Attempt every cleanup; preserve an error already being handled."""
    first_error = None
    for action in actions:
        try:
            action()
        except Exception as error:
            if suppress_errors:
                print("TTS cleanup failed:", error)
            elif first_error is None:
                first_error = error
    if first_error is not None:
        raise first_error


class EncoderApp(AIBase):
    def __init__(self, kmodel_path, dict_path, phase_path, mapfile, debug_mode=0):
        self.ttszh = None
        self.data = None
        self.data_len = []
        self.durition_sum = 0
        try:
            with ScopedTiming("load encoder model", debug_mode > 0):
                super().__init__(kmodel_path, debug_mode=debug_mode)
            with ScopedTiming("initialize TTS dictionaries", debug_mode > 0):
                self.ttszh = aidemo.tts_zh_create(dict_path, phase_path, mapfile)
        except BaseException:
            _cleanup([self.deinit], suppress_errors=True)
            raise

    def preprocess(self, text):
        with ScopedTiming("encoder preprocess", self.debug_mode > 0):
            self.data, self.data_len = preprocess_text(self.ttszh, text)
            sequence = nn.from_numpy(np.array(self.data, dtype=np.float))
            try:
                speaker = nn.from_numpy(np.array([0.0], dtype=np.float))
                return [speaker, sequence]
            except BaseException:
                _cleanup([sequence.release], suppress_errors=True)
                raise

    def postprocess(self, results):
        with ScopedTiming("encoder postprocess", self.debug_mode > 0):
            # Sum the same integer durations used to repeat encoder vectors.
            durations = [int(value) for value in results[1][0][:int(self.data_len[0])]]
            if any(value < 0 for value in durations):
                raise RuntimeError("Encoder returned a negative duration")
            self.durition_sum = sum(durations)
            max_duration = 13
            while self.durition_sum > 600:
                durations = [min(value, max_duration) for value in durations]
                self.durition_sum = sum(durations)
                max_duration -= 1
            if self.durition_sum <= 0:
                raise RuntimeError("Encoder returned no audio frames")
            decoder_input = np.zeros((1, 600, 256), dtype=np.float)
            frame = 0
            for index, duration in enumerate(durations):
                for _ in range(duration):
                    decoder_input[0][frame] = results[0][0][index]
                    frame += 1
            return decoder_input, self.durition_sum

    def _destroy_frontend(self):
        if self.ttszh is not None:
            aidemo.tts_zh_destroy(self.ttszh)
            self.ttszh = None

    def deinit(self):
        self.data = None
        self.data_len = []
        _cleanup([self._destroy_frontend, lambda: AIBase.deinit(self)])


class DecoderApp(AIBase):
    def __init__(self, kmodel_path, debug_mode=0):
        with ScopedTiming("load decoder model", debug_mode > 0):
            super().__init__(kmodel_path, debug_mode=debug_mode)

    def preprocess(self, decoder_input):
        with ScopedTiming("decoder preprocess", self.debug_mode > 0):
            return [nn.from_numpy(decoder_input)]

    def postprocess(self, results):
        return results[0]


class HifiGanApp(AIBase):
    def __init__(self, kmodel_path, debug_mode=0):
        self.mel_data = []
        with ScopedTiming("load hifigan model", debug_mode > 0):
            super().__init__(kmodel_path, debug_mode=debug_mode)

    def preprocess(self, chunk):
        return [nn.from_numpy(chunk)]

    def run(self, decoder_output, duration):
        self.mel_data = []
        # Copy one 100-frame block at a time. Avoid a second full padded mel
        # buffer and the Python loop over every individual element.
        for start in range(0, duration, 100):
            count = min(100, duration - start)
            chunk = np.zeros((1, 80, 100), dtype=np.float)
            chunk[:, :, :count] = decoder_output[:, :, start:start + count]
            # AIBase retains the input tensor until replacement or model cleanup.
            AIBase.run(self, chunk)
        return self.mel_data

    def postprocess(self, results):
        self.mel_data.extend(results[0][0][0].tolist())

    def deinit(self):
        self.mel_data = []
        AIBase.deinit(self)


class TTSZH:
    """Reuse one instance for multiple requests, then call deinit() once."""
    def __init__(self, encoder_kmodel_path, decoder_kmodel_path, hifigan_kmodel_path,
                 dict_path, phase_path, mapfile, save_wav_file, debug_mode=0):
        self.save_wav_file = save_wav_file
        self.debug_mode = debug_mode
        self.encoder = None
        self.decoder = None
        self.hifigan = None
        try:
            self.encoder = EncoderApp(encoder_kmodel_path, dict_path, phase_path, mapfile, debug_mode)
            self.decoder = DecoderApp(decoder_kmodel_path, debug_mode)
            self.hifigan = HifiGanApp(hifigan_kmodel_path, debug_mode)
        except BaseException:
            _cleanup([self.deinit], suppress_errors=True)
            raise

    def run(self, text):
        if self.encoder is None or self.decoder is None or self.hifigan is None:
            raise RuntimeError("TTS instance has been deinitialized")
        with ScopedTiming("synthesis", self.debug_mode > 0):
            decoder_input, duration = self.encoder.run(text)
            decoder_output = self.decoder.run(decoder_input)
            audio = self.hifigan.run(decoder_output, duration)
            samples = np.array(audio[:duration * 256], dtype=np.float)
            pcm = np.array(np.clip(samples, -1.0, 1.0) * 32767.0, dtype=np.int16).tobytes()
        if self.debug_mode > 0:
            print("generated audio duration: %.2f s" % (len(pcm) / (24000 * 2)))
        with ScopedTiming("save wav", self.debug_mode > 0):
            output = wave.open(self.save_wav_file, "wb")
            completed = False
            try:
                output.set_channels(1)
                output.set_sampwidth(2)
                output.set_framerate(24000)
                output.write_frames(pcm)
                completed = True
            finally:
                _cleanup([output.close], suppress_errors=not completed)
        self.play_audio()

    def play_audio(self):
        with ScopedTiming("play audio", self.debug_mode > 0):
            audio = None
            stream = None
            source = None
            completed = False
            try:
                audio = PyAudio()
                stream = audio.open(format=paInt16, channels=1, rate=24000,
                                    output=True, frames_per_buffer=7200)
                source = wave.open(self.save_wav_file, "rb")
                data = source.read_frames(7200)
                while data:
                    stream.write(data)
                    data = source.read_frames(7200)
                time.sleep(2)  # Allow the device to finish queued audio.
                completed = True
            finally:
                actions = []
                if source is not None:
                    actions.append(source.close)
                if stream is not None:
                    actions.append(stream.close)
                if audio is not None:
                    actions.append(audio.terminate)
                _cleanup(actions, suppress_errors=not completed)

    def deinit(self):
        first_error = None
        for name in ("hifigan", "decoder", "encoder"):
            model = getattr(self, name)
            if model is None:
                continue
            try:
                model.deinit()
            except Exception as error:
                if first_error is None:
                    first_error = error
            else:
                setattr(self, name, None)
        if first_error is not None:
            raise first_error


def main(text="", debug_mode=0):
    encoder_kmodel_path = "/sdcard/examples/kmodel/zh_fastspeech_1_f32.kmodel"
    decoder_kmodel_path = "/sdcard/examples/kmodel/zh_fastspeech_2.kmodel"
    hifigan_kmodel_path = "/sdcard/examples/kmodel/hifigan.kmodel"
    dict_path = "/sdcard/examples/utils/pinyin.txt"
    phase_path = "/sdcard/examples/utils/small_pinyin.txt"
    mapfile = "/sdcard/examples/utils/phone_map.txt"
    save_wav_file = "/data/tts.wav"

    tts_zh = None
    failed = False
    # Include initialization and cleanup in the total, even on an error.
    with ScopedTiming("total", 1):
        try:
            validate_text(text)
            os.exitpoint(os.EXITPOINT_ENABLE)
            with ScopedTiming("initialize", 1):
                with ScopedTiming("shrink memory pool", debug_mode > 0):
                    nn.shrink_memory_pool()
                tts_zh = TTSZH(encoder_kmodel_path, decoder_kmodel_path, hifigan_kmodel_path,
                               dict_path, phase_path, mapfile, save_wav_file, debug_mode=debug_mode)
            with ScopedTiming("synthesize and play", 1):
                tts_zh.run(text)
                gc.collect()
        except TTSInputError as error:
            print("TTS input error:", error)
        except BaseException:
            # Unexpected failures retain their original traceback, printed by the VM.
            failed = True
            raise
        finally:
            if tts_zh is not None:
                with ScopedTiming("cleanup", 1):
                    _cleanup([tts_zh.deinit], suppress_errors=failed)


if __name__ == "__main__":
    main("嘉楠科技研发了最新款的芯片")
