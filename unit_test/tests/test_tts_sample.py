"""TTS sample lifecycle and numerical checks; hardware APIs are simulated."""
import ast
from contextlib import contextmanager, redirect_stdout
import io
from pathlib import Path
from types import SimpleNamespace
import unittest

import numpy as numpy

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "resources/examples/05-AI-Demo/tts_zh.py"
APP_SAMPLE = ROOT / "resources/examples/28-APP_CENTER/demo_tts_zh.py"


def definitions(path, namespace):
    nodes = [node for node in ast.parse(path.read_text()).body
             if isinstance(node, (ast.ClassDef, ast.FunctionDef))]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


class ArrayAPI:
    float = numpy.float32
    def __getattr__(self, name):
        return getattr(numpy, name)


class SampleTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.tensors = []
        self.fail_model = None
        self.fail_tensor = None
        self.owner = object()
        test = self

        class Tensor:
            def __init__(self, data):
                self.data = numpy.array(data, copy=True)
                self.released = False
            def release(self):
                test.assertFalse(self.released)
                self.released = True

        class Kpu:
            def __init__(self):
                self.path = None
                self.released = False
            def load_kmodel(self, path):
                self.path = path
                test.events.append(("load", path))
                if path == test.fail_model:
                    raise RuntimeError("load " + path)
            def release(self):
                test.assertFalse(self.released)
                self.released = True
                test.events.append(("release", self.path))

        def from_numpy(data):
            if len(self.tensors) == self.fail_tensor:
                raise MemoryError("tensor allocation")
            tensor = Tensor(data)
            self.tensors.append(tensor)
            return tensor

        @contextmanager
        def timing(label, enabled):
            if enabled:
                self.events.append(("begin", label))
            try:
                yield
            finally:
                if enabled:
                    self.events.append(("end", label))

        def destroy(handle):
            self.assertIs(handle, self.owner)
            self.events.append(("destroy", "frontend"))

        self.env = dict(
            np=ArrayAPI(), ScopedTiming=timing,
            nn=SimpleNamespace(kpu=Kpu, from_numpy=from_numpy,
                               shrink_memory_pool=lambda: self.events.append(("shrink",))),
            aidemo=SimpleNamespace(tts_zh_create=lambda *args: self.owner,
                                   tts_zh_destroy=destroy,
                                   tts_zh_preprocess=lambda *args: [[1.0] * 50, [4.0]]),
            time=SimpleNamespace(sleep_ms=lambda ms: None, sleep=lambda value: None),
            gc=SimpleNamespace(collect=lambda: None),
            os=SimpleNamespace(EXITPOINT_ENABLE=1, exitpoint=lambda flag: None),
            paInt16=0)
        definitions(ROOT / "resources/libs/AIBase.py", self.env)
        definitions(ROOT / "resources/libs/TTSInput.py", self.env)
        definitions(SAMPLE, self.env)

    def encoder(self):
        return self.env["EncoderApp"]("encoder", "dict", "phrases", "map")

    def tts(self):
        return self.env["TTSZH"]("encoder", "decoder", "hifigan", "dict", "phrases", "map", "/data/instance.wav")

    def app_environment(self):
        env = dict(self.env, Application=object,
                   config=SimpleNamespace(tts_text="", tts_status=""))
        env.update({name: name for name in
                    ("KW_ENCODER", "KW_DECODER", "KW_HIFIGAN", "KW_DICT", "KW_PHASE", "KW_MAP")})
        return definitions(APP_SAMPLE, env)

    def test_both_examples_reject_unusable_input_before_tensor_creation(self):
        app_env = self.app_environment()
        app_encoder = app_env["_EncoderApp"]("encoder", "dict", "phrases", "map")
        for encoder in (self.encoder(), app_encoder):
            with self.subTest(encoder=type(encoder).__name__):
                calls = []
                def preprocess(frontend, text):
                    calls.append(text)
                    return [[1.0] * 50, [4.0]]
                self.env["aidemo"].tts_zh_preprocess = preprocess
                for text in ("ABCDEFG", "abc", "", " \t\r\n"):
                    with self.assertRaises(self.env["TTSInputError"]):
                        encoder.preprocess(text)
                self.assertEqual(calls, [])
                for data in ([[], []], [[1.0] * 100, [50, 1]],
                             [[1.0] * 50, [0]], [[1.0] * 50, [51]]):
                    self.env["aidemo"].tts_zh_preprocess = lambda *args: data
                    with self.assertRaises(self.env["TTSInputError"]):
                        encoder.preprocess("你好")
                self.assertEqual(self.tensors, [])
                encoder.deinit()

    def test_both_examples_preserve_native_error_categories(self):
        app_encoder = self.app_environment()["_EncoderApp"]("encoder", "dict", "phrases", "map")
        for encoder in (self.encoder(), app_encoder):
            for failure in (ValueError("no usable phonemes"), MemoryError("allocation"),
                            RuntimeError("native preprocessing")):
                with self.subTest(encoder=type(encoder).__name__, error=type(failure).__name__):
                    def preprocess(*args):
                        raise failure
                    self.env["aidemo"].tts_zh_preprocess = preprocess
                    expected = self.env["TTSInputError"] if isinstance(failure, ValueError) else type(failure)
                    with self.assertRaises(expected) as caught:
                        encoder.preprocess("。")
                    self.assertEqual(str(caught.exception), str(failure))
                    if not isinstance(failure, ValueError):
                        self.assertIs(caught.exception, failure)
                    self.assertEqual(self.tensors, [])
            encoder.deinit()

    def test_app_input_errors_report_once_and_leave_app_ready_for_another_request(self):
        env = self.app_environment()
        cls = env["TTSZHDemo"]
        app = cls.__new__(cls)
        app._busy = False
        app.stop_req = False
        app.encoder = env["_EncoderApp"]("encoder", "dict", "phrases", "map")
        app.decoder = None
        app.hifigan = None
        for text, data in (("ABCDEFG", None), ("你好", [[1.0] * 100, [50, 1]])):
            env["config"].tts_text = text
            self.env["aidemo"].tts_zh_preprocess = lambda *args: data
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(app.run(), (False, ""))
            self.assertEqual(output.getvalue().count("TTS input error:"), 1)
            self.assertNotIn("Traceback", output.getvalue())
            self.assertEqual(env["config"].tts_status, "error")
            self.assertEqual(env["config"].tts_text, "")
            self.assertFalse(app._busy)
            self.assertIsNone(app.encoder.data)
            self.assertEqual(self.tensors, [])
        app.encoder.deinit()

    def test_reject_empty_and_english_before_initialization(self):
        cases = [(text, "Please enter text") for text in ("", " \t\r\n")]
        cases += [(text, "Enter Chinese text; English letters are ignored")
                  for text in ("ABCDEFG", "abcdefg", "ABC def")]
        for text, message in cases:
            with self.subTest(text=text), redirect_stdout(io.StringIO()) as output:
                self.env["main"](text)
            self.assertEqual(output.getvalue(), "TTS input error: " + message + "\n")
        self.assertFalse(any(event[0] in ("load", "shrink", "destroy") for event in self.events))

    def test_fast_validation_preserves_native_normalization_inputs(self):
        for text in ("你好", "你好ABC", "123", "2026-10-28", "/", "~", "。"):
            self.env["validate_text"](text)

    def test_frontend_constructor_failure_releases_encoder(self):
        failure = MemoryError("frontend allocation")
        def create(*args):
            raise failure
        self.env["aidemo"].tts_zh_create = create
        with self.assertRaises(MemoryError) as caught:
            self.encoder()
        self.assertIs(caught.exception, failure)
        self.assertEqual(self.events.count(("release", "encoder")), 1)

    def test_partial_model_construction_cleans_every_acquired_resource(self):
        for failed in ("decoder", "hifigan"):
            self.events.clear()
            self.fail_model = failed
            with self.assertRaisesRegex(RuntimeError, "load " + failed):
                self.tts()
            for model in ("encoder", "decoder") + (("hifigan",) if failed == "hifigan" else ()):
                self.assertEqual(self.events.count(("release", model)), 1)
            self.assertEqual(self.events.count(("destroy", "frontend")), 1)

    def test_deinit_uses_instance_and_is_repeatable(self):
        tts = self.tts()
        tts.deinit()
        events = self.events.copy()
        tts.deinit()
        self.assertEqual(events, self.events)
        self.assertTrue(all(getattr(tts, name) is None for name in ("encoder", "decoder", "hifigan")))
        for text in ("你好", "ABCDEFG", ""):
            with self.assertRaisesRegex(RuntimeError, "deinitialized"):
                tts.run(text)

    def test_cleanup_continues_and_retains_failed_resource_for_retry(self):
        tts = self.tts()
        original = tts.decoder.deinit
        def fail():
            raise RuntimeError("decoder cleanup")
        tts.decoder.deinit = fail
        with self.assertRaisesRegex(RuntimeError, "decoder cleanup"):
            tts.deinit()
        self.assertIsNone(tts.encoder)
        self.assertIsNone(tts.hifigan)
        self.assertIsNotNone(tts.decoder)
        tts.decoder.deinit = original
        tts.deinit()
        self.assertIsNone(tts.decoder)

    def test_reject_empty_and_multi_chunk_data_before_tensor_creation(self):
        encoder = self.encoder()
        for data in ([[], []], [[1.0] * 100, [50, 1]], [[1.0] * 50, [0]]):
            self.env["aidemo"].tts_zh_preprocess = lambda *args: data
            with self.assertRaises(self.env["TTSInputError"]):
                encoder.preprocess("你好")
            self.assertEqual(self.tensors, [])
        encoder.deinit()

    def test_failed_speaker_allocation_releases_sequence(self):
        encoder = self.encoder()
        self.fail_tensor = 1
        with self.assertRaisesRegex(MemoryError, "tensor allocation"):
            encoder.preprocess("你好")
        self.assertTrue(self.tensors[0].released)
        encoder.deinit()

    def test_duration_count_matches_expanded_frames_and_is_bounded(self):
        encoder = self.encoder()
        encoder.data_len = [3]
        features = numpy.ones((1, 50, 256), dtype=numpy.float32)
        output, duration = encoder.postprocess([features, numpy.array([[1.9, 2.8, 0.5]])])
        self.assertIsInstance(duration, int)
        self.assertEqual(duration, 3)
        numpy.testing.assert_array_equal(output[0, :3], 1)
        numpy.testing.assert_array_equal(output[0, 3:], 0)
        encoder.data_len = [50]
        output, duration = encoder.postprocess([features, numpy.full((1, 50), 100.0)])
        self.assertEqual(duration, 600)
        numpy.testing.assert_array_equal(output, 1)
        with self.assertRaisesRegex(RuntimeError, "no audio frames"):
            encoder.postprocess([features, numpy.zeros((1, 50))])
        encoder.deinit()

    def test_vocoder_padding_and_repeated_calls_do_not_accumulate_audio(self):
        model = self.env["HifiGanApp"]("hifigan")
        chunks = []
        def inference(tensors):
            self.assertFalse(tensors[0].released)
            chunks.append(tensors[0].data.copy())
            return [numpy.full((1, 1, 25600), len(chunks), dtype=numpy.float32)]
        model.inference = inference
        source = numpy.arange(80 * 600, dtype=numpy.float32).reshape(1, 80, 600)
        first = model.run(source, 101)
        self.assertEqual(len(first), 51200)
        numpy.testing.assert_array_equal(chunks[0], source[:, :, :100])
        numpy.testing.assert_array_equal(chunks[1][:, :, :1], source[:, :, 100:101])
        numpy.testing.assert_array_equal(chunks[1][:, :, 1:], 0)
        second = model.run(source, 1)
        self.assertEqual(len(second), 25600)
        self.assertEqual(second[0], 3)
        self.assertEqual(len(first), 51200)
        self.assertIsNot(first, second)
        self.assertIs(model.tensors[0], self.tensors[-1])
        model.deinit()

    def test_wav_uses_instance_path_and_closes_on_write_failure(self):
        tts = self.tts()
        tts.encoder.run = lambda text: (None, 1)
        tts.decoder.run = lambda data: None
        tts.hifigan.run = lambda *args: [0.0] * 256
        events = []
        def fail_write(data):
            raise OSError("wav write")
        output = SimpleNamespace(set_channels=lambda *args: None, set_sampwidth=lambda *args: None,
                                 set_framerate=lambda *args: None, write_frames=fail_write,
                                 close=lambda: events.append("close"))
        def open_file(path, mode):
            events.append((path, mode))
            return output
        self.env["wave"] = SimpleNamespace(open=open_file)
        with self.assertRaisesRegex(OSError, "wav write"):
            tts.run("你好")
        self.assertEqual(events, [("/data/instance.wav", "wb"), "close"])
        tts.deinit()

    def test_playback_failure_closes_all_resources_and_preserves_error(self):
        tts = self.tts()
        events = []
        def write(data):
            raise OSError("audio write")
        def close_wave():
            events.append("wave")
            raise RuntimeError("wave cleanup")
        source = SimpleNamespace(read_frames=lambda n: b"pcm", close=close_wave)
        stream = SimpleNamespace(write=write, close=lambda: events.append("stream"))
        audio = SimpleNamespace(open=lambda **kwargs: stream, terminate=lambda: events.append("audio"))
        self.env["wave"] = SimpleNamespace(open=lambda *args: source)
        self.env["PyAudio"] = lambda: audio
        with redirect_stdout(io.StringIO()), self.assertRaisesRegex(OSError, "audio write"):
            tts.play_audio()
        self.assertEqual(events, ["wave", "stream", "audio"])
        tts.deinit()

    def test_main_timings_cover_initialization_run_and_cleanup(self):
        self.env["TTSZH"] = lambda *args, **kwargs: SimpleNamespace(run=lambda text: None, deinit=lambda: None)
        self.env["main"]("你好")
        self.assertEqual([event for event in self.events if event[0] in ("begin", "end")], [
            ("begin", "total"), ("begin", "initialize"), ("end", "initialize"),
            ("begin", "synthesize and play"), ("end", "synthesize and play"),
            ("begin", "cleanup"), ("end", "cleanup"), ("end", "total")])

    def test_main_native_input_error_is_reported_once_and_cleans_up(self):
        def run(text):
            raise self.env["TTSInputError"]("no usable phonemes")
        self.env["TTSZH"] = lambda *args, **kwargs: SimpleNamespace(
            run=run, deinit=lambda: self.events.append(("cleanup",)))
        with redirect_stdout(io.StringIO()) as output:
            self.env["main"]("。")
        self.assertEqual(output.getvalue(), "TTS input error: no usable phonemes\n")
        self.assertEqual(self.events.count(("cleanup",)), 1)

    def test_main_keeps_unexpected_error_when_cleanup_also_fails(self):
        failure = RuntimeError("inference failed")
        def run(text):
            raise failure
        def cleanup():
            raise OSError("cleanup failed")
        self.env["TTSZH"] = lambda *args, **kwargs: SimpleNamespace(run=run, deinit=cleanup)
        with redirect_stdout(io.StringIO()) as output, self.assertRaises(RuntimeError) as caught:
            self.env["main"]("你好")
        self.assertIs(caught.exception, failure)
        self.assertNotIn("inference failed", output.getvalue())
        self.assertEqual(self.events[-1], ("end", "total"))


if __name__ == "__main__":
    unittest.main()
