"""Record configured-duration WAV files from an IDE virtual-display button.

Open the IDE preview and click Record. Files are written to /data/audio_data
with an automatically increasing name.
"""

import gc
import os
import sys
import time
import uctypes

import image
import lvgl as lv
import media.wave as wave
from machine import TOUCH
from media.display import Display
from media.pyaudio import (
    PyAudio, paInt16, paInt24, paInt32, AUDIO_3A_ENABLE_ANS)


DISPLAY_WIDTH = 800
DISPLAY_HEIGHT = 480
UI_LAYER = Display.LAYER_OSD0

AUDIO_PATH = "/data/audio_data/"
AUDIO_PREFIX = "audio_"
AUDIO_SUFFIX = ".wav"
RECORD_SECONDS = 15
SAMPLE_RATE = 16000
AUDIO_FORMAT = paInt16
CHANNELS = 1
CHUNKS_PER_SECOND = 25
CHUNK = SAMPLE_RATE // CHUNKS_PER_SECOND
TOTAL_CHUNKS = RECORD_SECONDS * CHUNKS_PER_SECOND


def audio_config_text():
    """Build the displayed audio description from the recording settings."""
    if SAMPLE_RATE % 1000 == 0:
        rate_text = "%d kHz" % (SAMPLE_RATE // 1000)
    else:
        rate_text = "%.1f kHz" % (SAMPLE_RATE / 1000.0)
    sample_bits = {paInt16: 16, paInt24: 24, paInt32: 32}.get(
        AUDIO_FORMAT, 0)
    if CHANNELS == 1:
        channel_text = "mono"
    elif CHANNELS == 2:
        channel_text = "stereo"
    else:
        channel_text = "%d channels" % CHANNELS
    duration_text = "%d second%s" % (
        RECORD_SECONDS, "" if RECORD_SECONDS == 1 else "s")
    return "%s | %d-bit %s | %s" % (
        rate_text, sample_bits, channel_text, duration_text)


def record_button_text():
    return "Record %d s" % RECORD_SECONDS


def prepare_directory():
    """Create the output directory and return the next unused file index."""
    current = ""
    for part in AUDIO_PATH.strip("/").split("/"):
        current += "/" + part
        try:
            os.mkdir(current)
        except OSError as error:
            if error.args[0] != 17:
                raise
            if not os.stat(current)[0] & 0x4000:
                raise

    next_index = 1
    for name in os.listdir(AUDIO_PATH):
        if name.startswith(AUDIO_PREFIX) and name.endswith(AUDIO_SUFFIX):
            number = name[len(AUDIO_PREFIX):-len(AUDIO_SUFFIX)]
            if number.isdigit():
                next_index = max(next_index, int(number) + 1)
    return next_index


class AudioRecordApp:
    """Own the virtual display, IDE touch input and current audio recording."""

    def __init__(self):
        self.display_ready = False
        self.lv_ready = False
        self.buffers = []
        self.touch = None
        self.indev = None

        self.button = None
        self.button_label = None
        self.status = None
        self.file_label = None
        self.progress = None

        self.pending = False
        self.recording = False
        self.file_index = 1
        self.file_path = None
        self.chunk_count = 0
        self.pyaudio = None
        self.stream = None
        self.wav_file = None

    def flush(self, driver, area, color):
        """Present the completed LVGL buffer on the virtual display."""
        try:
            if driver.flush_is_last():
                address = uctypes.addressof(color.__dereference__())
                frame = self.buffers[0]
                if address != frame.virtaddr():
                    frame = self.buffers[1]
                Display.show_image(frame, layer=UI_LAYER)
        finally:
            driver.flush_ready()

    def read_touch(self, driver, data):
        """Forward IDE preview mouse input to LVGL."""
        points = self.touch.read(1)
        data.state = lv.INDEV_STATE.RELEASED
        if points:
            point = points[0]
            data.point.x = point.x
            data.point.y = point.y
            if point.event in (TOUCH.EVENT_DOWN, TOUCH.EVENT_MOVE):
                data.state = lv.INDEV_STATE.PRESSED

    def request_record(self, event):
        """Queue recording work outside the LVGL event callback."""
        if not self.pending and not self.recording:
            self.pending = True
            self.button.add_state(lv.STATE.DISABLED)
            self.button_label.set_text("Preparing...")
            self.status.set_text("Opening audio input")

    def setup_ui(self):
        screen = lv.scr_act()
        screen.set_style_bg_color(lv.color_hex(0x171A1F), 0)
        screen.clear_flag(lv.obj.FLAG.SCROLLABLE)

        title = lv.label(screen)
        title.set_text("Audio Recorder")
        title.set_style_text_color(lv.color_hex(0xF5F7FA), 0)
        title.align(lv.ALIGN.TOP_MID, 0, 42)

        subtitle = lv.label(screen)
        subtitle.set_text(audio_config_text())
        subtitle.set_style_text_color(lv.color_hex(0x9DA7B3), 0)
        subtitle.align(lv.ALIGN.TOP_MID, 0, 82)

        panel = lv.obj(screen)
        panel.set_size(620, 230)
        panel.align(lv.ALIGN.CENTER, 0, 0)
        panel.set_style_radius(8, 0)
        panel.set_style_border_width(1, 0)
        panel.set_style_border_color(lv.color_hex(0x39414C), 0)
        panel.set_style_bg_color(lv.color_hex(0x22272E), 0)
        panel.clear_flag(lv.obj.FLAG.SCROLLABLE)

        self.status = lv.label(panel)
        self.status.set_width(560)
        self.status.set_long_mode(lv.label.LONG.DOT)
        self.status.set_style_text_color(lv.color_hex(0xFFFFFF), 0)
        self.status.align(lv.ALIGN.TOP_LEFT, 20, 18)
        self.status.set_text("Ready")

        self.file_label = lv.label(panel)
        self.file_label.set_width(560)
        self.file_label.set_long_mode(lv.label.LONG.DOT)
        self.file_label.set_style_text_color(lv.color_hex(0x9DA7B3), 0)
        self.file_label.align(lv.ALIGN.TOP_LEFT, 20, 54)
        self.file_label.set_text(AUDIO_PATH)

        self.progress = lv.bar(panel)
        self.progress.set_size(560, 18)
        self.progress.align(lv.ALIGN.TOP_MID, 0, 100)
        self.progress.set_range(0, 100)
        self.progress.set_value(0, lv.ANIM.OFF)

        self.button = lv.btn(panel)
        self.button.set_size(220, 54)
        self.button.align(lv.ALIGN.BOTTOM_MID, 0, -6)
        self.button.set_style_radius(8, 0)
        self.button.set_style_bg_color(lv.color_hex(0xD4473A), 0)
        self.button.add_event(self.request_record, lv.EVENT.CLICKED, None)

        self.button_label = lv.label(self.button)
        self.button_label.set_text(record_button_text())
        self.button_label.center()

    def setup(self):
        """Initialize the output directory, virtual display, LVGL and IDE touch."""
        self.file_index = prepare_directory()

        Display.init(Display.VIRT, width=DISPLAY_WIDTH, height=DISPLAY_HEIGHT,
                     fps=60, to_ide=True)
        self.display_ready = True

        lv.init()
        self.lv_ready = True
        driver = lv.disp_create(DISPLAY_WIDTH, DISPLAY_HEIGHT)
        for _ in range(2):
            frame = image.Image(DISPLAY_WIDTH, DISPLAY_HEIGHT, image.BGRA8888)
            frame.clear()
            self.buffers.append(frame)
        driver.set_color_format(lv.COLOR_FORMAT.ARGB8888)
        driver.set_draw_buffers(
            self.buffers[0].bytearray(), self.buffers[1].bytearray(),
            self.buffers[0].size(), lv.DISP_RENDER_MODE.FULL)
        driver.set_flush_cb(self.flush)

        self.touch = TOUCH(
            TOUCH.DEV_IDE, range_x=DISPLAY_WIDTH, range_y=DISPLAY_HEIGHT)
        self.indev = lv.indev_create()
        self.indev.set_type(lv.INDEV_TYPE.POINTER)
        self.indev.set_read_cb(self.read_touch)
        self.setup_ui()

    def next_file_path(self):
        name = AUDIO_PREFIX + ("%04d" % self.file_index) + AUDIO_SUFFIX
        return AUDIO_PATH + name

    def start_record(self):
        """Open a fresh audio stream and WAV file for one recording."""
        self.pending = False
        self.file_path = self.next_file_path()
        self.chunk_count = 0
        self.progress.set_value(0, lv.ANIM.OFF)
        self.file_label.set_text(self.file_path)

        try:
            self.pyaudio = PyAudio()
            self.stream = self.pyaudio.open(
                format=AUDIO_FORMAT, channels=CHANNELS, rate=SAMPLE_RATE,
                input=True, frames_per_buffer=CHUNK)
            self.stream.enable_audio3a(AUDIO_3A_ENABLE_ANS)
            self.wav_file = wave.open(self.file_path, "wb")
            self.wav_file.set_channels(CHANNELS)
            self.wav_file.set_sampwidth(
                self.pyaudio.get_sample_size(AUDIO_FORMAT))
            self.wav_file.set_framerate(SAMPLE_RATE)
            self.wav_file.set_frames(SAMPLE_RATE * RECORD_SECONDS)
            self.recording = True
            self.button_label.set_text("Recording...")
            self.status.set_text(
                "Recording | %d.0 s remaining" % RECORD_SECONDS)
            print("Recording:", self.file_path)
        except BaseException:
            self.finish_record(False)
            raise

    def record_step(self):
        """Capture and write one audio chunk, then refresh progress."""
        data = self.stream.read()
        if not data:
            raise RuntimeError("audio input returned no data")

        self.wav_file.write_frames_raw(data)
        self.chunk_count += 1
        progress = self.chunk_count * 100 // TOTAL_CHUNKS
        remaining_tenths = (
            (TOTAL_CHUNKS - self.chunk_count) * 10 // CHUNKS_PER_SECOND)
        self.progress.set_value(progress, lv.ANIM.OFF)
        self.status.set_text(
            "Recording | %d.%d s remaining" %
            (remaining_tenths // 10, remaining_tenths % 10))

        if self.chunk_count >= TOTAL_CHUNKS:
            self.finish_record(True)

    def close_audio(self):
        """Stop the current stream and terminate its PyAudio owner."""
        cleanup_error = None
        if self.stream is not None:
            try:
                self.stream.stop_stream()
            except Exception as error:
                cleanup_error = error
            try:
                self.stream.close()
            except Exception as error:
                if cleanup_error is None:
                    cleanup_error = error
        if self.pyaudio is not None:
            try:
                self.pyaudio.terminate()
            except Exception as error:
                if cleanup_error is None:
                    cleanup_error = error
        if cleanup_error is None:
            self.stream = None
            self.pyaudio = None
        else:
            raise cleanup_error

    def finish_record(self, completed):
        """Close one recording and discard incomplete output files."""
        audio_error = None
        wave_error = None
        try:
            self.close_audio()
        except Exception as error:
            audio_error = error

        if self.wav_file is not None:
            try:
                self.wav_file.close()
            except Exception as error:
                wave_error = error
            self.wav_file = None

        self.recording = False
        saved_path = self.file_path
        if completed and audio_error is None and wave_error is None:
            self.file_index += 1
            self.progress.set_value(100, lv.ANIM.OFF)
            self.status.set_text("Saved")
            self.button_label.set_text("Record another")
            self.button.clear_state(lv.STATE.DISABLED)
            print("Saved:", saved_path)
        else:
            if saved_path is not None:
                try:
                    os.remove(saved_path)
                except OSError:
                    pass
            self.progress.set_value(0, lv.ANIM.OFF)
            self.status.set_text("Recording cancelled")
            self.button_label.set_text(record_button_text())
            self.button.clear_state(lv.STATE.DISABLED)

        self.file_path = None
        gc.collect()
        if audio_error is not None:
            raise audio_error
        if wave_error is not None:
            raise wave_error

    def run(self):
        """Process UI events and advance recording one chunk at a time."""
        while True:
            os.exitpoint()
            delay = lv.task_handler()
            if self.pending:
                self.start_record()
            if self.recording:
                self.record_step()
            else:
                if delay is None or delay < 5:
                    delay = 5
                time.sleep_ms(delay)

    def close(self):
        """Release audio, touch, LVGL and display resources in order."""
        if self.recording or self.stream is not None or self.wav_file is not None:
            try:
                self.finish_record(False)
            except Exception as error:
                sys.print_exception(error)

        actions = []
        if self.indev is not None:
            actions.append(self.indev.delete)
        if self.touch is not None:
            actions.append(self.touch.deinit)
        if self.lv_ready:
            actions.append(lv.deinit)
        if self.display_ready:
            actions.append(Display.deinit)

        for release in actions:
            try:
                release()
            except Exception as error:
                sys.print_exception(error)


def main():
    app = AudioRecordApp()
    os.exitpoint(os.EXITPOINT_ENABLE)
    try:
        app.setup()
        print("Open the IDE preview and click %s." % record_button_text())
        app.run()
    except KeyboardInterrupt:
        print("Audio recorder stopped")
    except BaseException as error:
        sys.print_exception(error)
    finally:
        os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
        app.close()
        app = None
        gc.collect()
        time.sleep_ms(100)


if __name__ == "__main__":
    main()
