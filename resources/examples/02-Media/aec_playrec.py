# aec_playrec.py
# 多线程播放和录制音频

import os
import _thread
from media.media import *
from media.pyaudio import *
import media.wave as wave
import time

# 全局PyAudio实例
global_p = None
stop_flag = False        # 线程停止信号
play_complete = False    # 播放完成标志
play_thread_done = False # 播放线程是否结束
record_thread_done = False # 录制线程是否结束
play_thread_error = None
record_thread_error = None
DIV = 50

def exit_check():
    try:
        os.exitpoint()
    except KeyboardInterrupt as e:
        print("User stopped: ", e)
        return True
    return False

def init_global_pyaudio():
    """初始化全局PyAudio实例"""
    global global_p
    if global_p is None:
        global_p = PyAudio()

def terminate_global_pyaudio():
    """终止全局PyAudio实例"""
    global global_p
    if global_p is not None:
        global_p.terminate()
        global_p = None

def get_wav_duration(wf):
    """从WAV文件元数据计算播放时长（秒）"""
    nframes = wf.get_frames()
    framerate = wf.get_framerate()
    if framerate > 0:
        return nframes / framerate
    return 0

def play_thread_func(stream, wf):
    """播放线程函数"""
    global stop_flag, play_complete, play_thread_done, play_thread_error
    try:
        CHUNK = int(wf.get_framerate() / DIV)
        data = wf.read_frames(CHUNK)

        while data and not stop_flag and not exit_check():
            stream.write(data)
            data = wf.read_frames(CHUNK)

        play_complete = True
        print("Playback completed (end of file)")

    except BaseException as e:
        play_thread_error = e
        play_complete = True
        stop_flag = True
    finally:
        # 释放资源
        if stream:
            try: stream.stop_stream(); stream.close()
            except: pass
        if wf:
            try: wf.close()
            except: pass
        # 标记播放线程结束
        play_thread_done = True
        print("Playback thread finished")

def record_thread_func(stream, filename, duration, channels, rate):
    """录制线程函数 - 基于时间驱动，精确控制录制时长"""
    global stop_flag, record_thread_done, record_thread_error
    CHUNK = rate // DIV
    frames = []

    try:
        start_time = time.time()
        while (time.time() - start_time) < duration:
            if stop_flag or exit_check():
                break
            data = stream.read(block=False)
            if data:
                frames.append(data)
            else:
                time.sleep(0.01)

    except BaseException as e:
        record_thread_error = e
        stop_flag = True
    finally:
        # 释放资源
        if stream:
            try: stream.stop_stream(); stream.close()
            except: pass
        # 保存录制文件
        if frames:
            try:
                print("Saving file ...")
                wf = wave.open(filename, 'wb')
                wf.set_channels(channels)
                wf.set_sampwidth(global_p.get_sample_size(paInt16))
                wf.set_framerate(rate)
                wf.write_frames(b''.join(frames))
                wf.close()
                print(f"Recorded to {filename} (duration: {len(frames)*CHUNK/rate:.2f}s)")
            except Exception as e:
                print(f"Save failed: {e}")
                if record_thread_error is None:
                    record_thread_error = e
                stop_flag = True
        else:
            print("No audio recorded")
        # 标记录制线程结束
        record_thread_done = True
        print("Recording thread finished")

def play_and_record(play_filename, record_filename, duration):
    global stop_flag, play_complete, play_thread_done, record_thread_done
    global play_thread_error, record_thread_error
    stop_flag = False
    play_complete = False
    play_thread_done = False
    record_thread_done = False
    play_thread_error = None
    record_thread_error = None

    play_stream = None
    record_stream = None
    wf_play = None

    try:
        init_global_pyaudio()

        wf_play = wave.open(play_filename, 'rb')
        channels = wf_play.get_channels()
        rate = wf_play.get_framerate()
        wav_duration = get_wav_duration(wf_play)
        actual_duration = max(duration, wav_duration)
        print(f"WAV duration: {wav_duration:.2f}s, record duration: {actual_duration:.2f}s")

        play_stream = global_p.open(
            format=global_p.get_format_from_width(wf_play.get_sampwidth()),
            channels=channels,
            rate=rate,
            output=True,
            frames_per_buffer=int(rate/DIV)
        )
        play_stream.volume(vol=85)
        print(f"Play volume: {play_stream.volume()}")

        record_stream = global_p.open(
            format=paInt16,
            channels=channels,
            rate=rate,
            input=True,
            frames_per_buffer=rate//DIV
        )
        record_stream.volume(70, LEFT)
        record_stream.volume(85, RIGHT)
        record_stream.enable_audio3a(AUDIO_3A_ENABLE_AEC | AUDIO_3A_ENABLE_AGC | AUDIO_3A_ENABLE_ANS)
        print(f"Record volume: {record_stream.volume()}")

        _thread.start_new_thread(play_thread_func, (play_stream, wf_play))
        _thread.start_new_thread(record_thread_func, (record_stream, record_filename, actual_duration, channels, rate))

        start_time = time.time()
        while True:
            if stop_flag or (time.time() - start_time >= actual_duration) or exit_check():
                stop_flag = True
                break
            time.sleep(0.1)

        print("Waiting for threads to exit...")
        timeout = time.time() + 10
        thread_wait_timed_out = False
        while not (play_thread_done and record_thread_done):
            if time.time() > timeout:
                stop_flag = True
                thread_wait_timed_out = True
                break
            time.sleep(0.1)

        if thread_wait_timed_out:
            raise RuntimeError("audio thread wait timeout")
        if play_thread_error is not None:
            raise play_thread_error
        if record_thread_error is not None:
            raise record_thread_error

    except Exception as e:
        print(f"Error: {e}")
        stop_flag = True  # 异常时立即停止线程
        raise
    finally:
        if play_stream:
            try: play_stream.stop_stream(); play_stream.close()
            except: pass
        if record_stream:
            try: record_stream.stop_stream(); record_stream.close()
            except: pass
        if wf_play:
            try: wf_play.close()
            except: pass
        # 终止PyAudio
        terminate_global_pyaudio()
        print("All resources released")

if __name__ == "__main__":
    os.exitpoint(os.EXITPOINT_ENABLE)
    print("AEC play and record start")
    PLAY_FILE = '/data/test.wav' # Created by audio.py.
    RECORD_FILE = '/data/record.wav'
    DURATION = 30
    play_and_record(PLAY_FILE, RECORD_FILE, DURATION)
    print("AEC play and record done")
