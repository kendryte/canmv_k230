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
DIV = 100

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

def play_thread_func(stream, wf):
    """播放线程函数"""
    global stop_flag, play_complete, play_thread_done
    try:
        CHUNK = int(wf.get_framerate() / DIV)
        data = wf.read_frames(CHUNK)

        while data and not stop_flag and not exit_check():
            stream.write(data)
            data = wf.read_frames(CHUNK)

        play_complete = True
        print("Playback completed (end of file)")

    except BaseException as e:
        import sys
        sys.print_exception(e)
        play_complete = True
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
    """录制线程函数"""
    global stop_flag, play_complete, record_thread_done
    CHUNK = rate // DIV
    frames = []

    try:
        total_iter = int(rate / CHUNK * 2 * duration)
        for _ in range(total_iter):
            if stop_flag or exit_check() or play_complete:
                break
            data = stream.read(block=False)
            if data:
                frames.append(data)
            else:
                time.sleep(0.01)
                total_iter += 1

    except BaseException as e:
        import sys
        sys.print_exception(e)
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
        else:
            print("No audio recorded")
        # 标记录制线程结束
        record_thread_done = True
        print("Recording thread finished")

def play_and_record(play_filename, record_filename, duration):
    global stop_flag, play_complete, play_thread_done, record_thread_done
    stop_flag = False
    play_complete = False
    play_thread_done = False
    record_thread_done = False

    play_stream = None
    record_stream = None
    wf_play = None

    try:
        # 初始化全局PyAudio
        init_global_pyaudio()

        # 初始化播放资源
        wf_play = wave.open(play_filename, 'rb')
        channels = wf_play.get_channels()
        rate = wf_play.get_framerate()
        play_stream = global_p.open(
            format=global_p.get_format_from_width(wf_play.get_sampwidth()),
            channels=channels,
            rate=rate,
            output=True,
            frames_per_buffer=int(rate/DIV)
        )
        play_stream.volume(vol=85)
        print(f"Play volume: {play_stream.volume()}")

        # 初始化录制资源
        record_stream = global_p.open(
            format=paInt16,
            channels=channels,
            rate=rate,
            input=True,
            frames_per_buffer=rate//DIV
        )
        record_stream.volume(70, LEFT)
        record_stream.volume(85, RIGHT)
        record_stream.enable_audio3a(AUDIO_3A_ENABLE_AEC)
        #record_stream.enable_audio3a(AUDIO_3A_ENABLE_ANS)
        print(f"Record volume: {record_stream.volume()}")

        # 启动线程
        _thread.start_new_thread(play_thread_func, (play_stream, wf_play))
        _thread.start_new_thread(record_thread_func, (record_stream, record_filename, duration, channels, rate))

        # 等待录制时长/用户退出/播放完成
        start_time = time.time()
        while True:
            if (time.time()-start_time >= duration) or exit_check() or play_complete:
                stop_flag = True  # 通知线程停止
                break
            time.sleep(0.1)

        # 等待线程结束
        print("Waiting for threads to exit...")
        timeout = time.time() + 10  # 10秒超时保护
        while not (play_thread_done and record_thread_done):
            if time.time() > timeout:
                print("Warning: Thread wait timeout!")
                break
            time.sleep(0.1)

    except Exception as e:
        print(f"Error: {e}")
        stop_flag = True  # 异常时立即停止线程
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
    PLAY_FILE = '/data/play.wav'
    RECORD_FILE = '/data/record.wav'
    DURATION = 30
    play_and_record(PLAY_FILE, RECORD_FILE, DURATION)
    print("AEC play and record done")
