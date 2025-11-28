# aec_playrec.py
# 多线程播放和录制音频（流初始化移至线程外）

import os
import _thread
from media.media import *
from media.pyaudio import *
import media.wave as wave
import time

# 全局PyAudio实例
global_p = None
# 线程停止标志
stop_flag = False
# 播放完成标志
play_complete = False

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
    """播放线程函数（接收外部创建的流和文件对象）"""
    global stop_flag, play_complete
    try:
        CHUNK = int(wf.get_framerate() / 25)

        data = wf.read_frames(CHUNK)
        while data and not stop_flag and not exit_check():
            stream.write(data)
            data = wf.read_frames(CHUNK)

        # 播放完成，设置标志
        play_complete = True
        print("Playback completed (end of file)")

    except BaseException as e:
        import sys
        sys.print_exception(e)
        play_complete = True  # 异常时也标记为播放完成
    finally:
        if stream:
            stream.stop_stream()
            stream.close()
        if wf:
            wf.close()
        print("Playback thread finished")

def record_thread_func(stream, filename, duration, channels, rate):
    """录制线程函数（接收外部创建的流）"""
    global stop_flag, play_complete
    CHUNK = rate // 25
    frames = []

    try:
        total_iter = int(rate / CHUNK * 2 * duration)
        for _ in range(total_iter):
            # 如果停止标志、退出信号或播放完成，都终止录制
            if stop_flag or exit_check() or play_complete:
                break
            data = stream.read(block=False)
            if data:
                frames.append(data)
            else:
                time.sleep(0.01)
                total_iter += 1  # 如果没有数据则多尝试一次

    except BaseException as e:
        import sys
        sys.print_exception(e)
    finally:
        if stream:
            stream.stop_stream()
            stream.close()

        # 保存录制数据
        if frames:
            try:
                print("Saving file ...")
                wf = wave.open(filename, 'wb')
                wf.set_channels(channels)  # 与录制通道保持一致
                wf.set_sampwidth(global_p.get_sample_size(paInt16))
                wf.set_framerate(rate)
                wf.write_frames(b''.join(frames))
                wf.close()
                print(f"Recorded audio saved to {filename} (duration: {len(frames)*CHUNK/rate:.2f}s)")
            except Exception as e:
                print(f"Failed to save recording file: {e}")
        else:
            print("No audio data recorded")
        print("Recording thread finished")

def play_and_record(play_filename, record_filename, duration):
    global stop_flag, play_complete
    stop_flag = False  # 重置停止标志
    play_complete = False  # 重置播放完成标志
    play_stream = None
    record_stream = None
    wf_play = None

    try:
        # 初始化全局PyAudio
        init_global_pyaudio()

        # 主线程中初始化播放相关资源
        wf_play = wave.open(play_filename, 'rb')
        CHUNK_PLAY = int(wf_play.get_framerate() / 25)
        channels = wf_play.get_channels()
        rate = wf_play.get_framerate()
        play_stream = global_p.open(
            format=global_p.get_format_from_width(wf_play.get_sampwidth()),
            channels=channels,
            rate=rate,
            output=True,
            frames_per_buffer=CHUNK_PLAY
        )
        play_stream.volume(vol=85)
        print(f"Playback output volume: {play_stream.volume()}")

        print("wf play params:", wf_play.get_channels(), wf_play.get_sampwidth(), wf_play.get_framerate())

        # 主线程中初始化录制相关资源
        CHUNK_RECORD = wf_play.get_framerate() // 25
        record_stream = global_p.open(
            format=paInt16,
            channels=channels,
            rate=rate,
            input=True,
            frames_per_buffer=CHUNK_RECORD
        )

        record_stream.volume(70, LEFT)
        record_stream.volume(85, RIGHT)
        print(f"Recording input volume: {record_stream.volume()}")
        record_stream.enable_audio3a(AUDIO_3A_ENABLE_ANS | AUDIO_3A_ENABLE_AEC)

        # 创建并启动线程（传递已初始化的流）
        _thread.start_new_thread(play_thread_func, (play_stream, wf_play))
        _thread.start_new_thread(record_thread_func, (record_stream, record_filename, duration, channels, rate))

        # 主线程等待：直到录制时长结束、用户退出、或播放完成
        start_time = time.time()
        while True:
            # 检查退出条件
            if (time.time() - start_time >= duration or
                exit_check() or
                play_complete):
                break
            time.sleep(0.1)

        # 设置停止标志
        stop_flag = True
        # 等待线程结束
        time.sleep(1)  # 缩短等待时间，因为播放已完成

    except Exception as e:
        print(f"Operation failed: {e}")
        stop_flag = True
        play_complete = True
    finally:
        # 确保资源释放（防止线程异常时未释放）
        if play_stream:
            try:
                play_stream.stop_stream()
                play_stream.close()
            except:
                pass
        if record_stream:
            try:
                record_stream.stop_stream()
                record_stream.close()
            except:
                pass
        if wf_play:
            try:
                wf_play.close()
            except:
                pass
        # 终止全局PyAudio
        terminate_global_pyaudio()
        print("Operation completed")

if __name__ == "__main__":
    os.exitpoint(os.EXITPOINT_ENABLE)
    print("AEC play and record start")
    PLAY_FILE = '/data/play_8k_1.wav'    # 请替换为实际播放文件路径
    RECORD_FILE = '/data/record_8k_1.wav'  # 录制文件保存路径
    DURATION = 15  # 录制时长（秒）
    play_and_record(PLAY_FILE, RECORD_FILE, DURATION)
    print("AEC play and record done")