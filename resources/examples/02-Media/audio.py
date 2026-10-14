# audio input and output example
#
# Note: You will need an SD card to run this example.
#
# You can play wav files or capture audio to save as wav

import os
from media.media import *   #导入media模块，用于初始化vb buffer
from media.pyaudio import * #导入pyaudio模块，用于采集和播放音频
import media.wave as wave   #导入wav模块，用于保存和加载wav音频文件

def exit_check():
    try:
        os.exitpoint()
    except KeyboardInterrupt as e:
        print("user stop: ", e)
        return True
    return False

def _safe_cleanup(name, callback):
    try:
        callback()
    except Exception as e:
        print("{} cleanup failed: {}".format(name, e))

def _close_stream(stream):
    if stream is None:
        return
    _safe_cleanup("audio stream stop", stream.stop_stream)
    _safe_cleanup("audio stream close", stream.close)

def _close_wave(wf):
    if wf is not None:
        _safe_cleanup("wave file close", wf.close)

def _terminate_audio(p):
    if p is not None:
        _safe_cleanup("PyAudio terminate", p.terminate)

def record_audio(filename, duration):
    CHUNK = 44100//25  #设置音频chunk值
    FORMAT = paInt16       #设置采样精度,支持16bit(paInt16)/24bit(paInt24)/32bit(paInt32)
    CHANNELS = 2           #设置声道数,支持单声道(1)/立体声(2)
    RATE = 44100           #设置采样率

    p = None
    stream = None
    wf = None
    try:
        p = PyAudio()

        #创建音频输入流
        stream = p.open(format=FORMAT,
                        channels=CHANNELS,
                        rate=RATE,
                        input=True,
                        frames_per_buffer=CHUNK)

        stream.volume(70, LEFT)
        stream.volume(85, RIGHT)
        print("volume :",stream.volume())

        #启用音频3A功能：自动噪声抑制(ANS)
        stream.enable_audio3a(AUDIO_3A_ENABLE_ANS)

        frames = []
        #采集音频数据并存入列表
        for i in range(0, int(RATE / CHUNK * duration)):
            data = stream.read()
            frames.append(data)
            if exit_check():
                break
        #将列表中的数据保存到wav文件中
        wf = wave.open(filename, 'wb') #创建wav 文件
        wf.set_channels(CHANNELS) #设置wav 声道数
        wf.set_sampwidth(p.get_sample_size(FORMAT))  #设置wav 采样精度
        wf.set_framerate(RATE)  #设置wav 采样率
        wf.write_frames(b''.join(frames)) #存储wav音频数据
    except KeyboardInterrupt as e:
        print("user stop: ", e)
    except BaseException as e:
        import sys
        sys.print_exception(e)
        raise
    finally:
        _close_wave(wf)
        _close_stream(stream)
        _terminate_audio(p)

def play_audio(filename):
    wf = None
    p = None
    stream = None
    try:
        wf = wave.open(filename, 'rb')#打开wav文件
        CHUNK = int(wf.get_framerate()/25)#设置音频chunk值

        p = PyAudio()

        #创建音频输出流，设置的音频参数均为wave中获取到的参数
        stream = p.open(format=p.get_format_from_width(wf.get_sampwidth()),
                    channels=wf.get_channels(),
                    rate=wf.get_framerate(),
                    output=True,frames_per_buffer=CHUNK)

        #设置音频输出流的音量
        stream.volume(vol=85)

        data = wf.read_frames(CHUNK)#从wav文件中读取数一帧数据

        while data:
            stream.write(data)  #将帧数据写入到音频输出流中
            data = wf.read_frames(CHUNK) #从wav文件中读取数一帧数据
            if exit_check():
                break
    except KeyboardInterrupt as e:
        print("user stop: ", e)
    except BaseException as e:
        import sys
        sys.print_exception(e)
        raise
    finally:
        _close_stream(stream)
        _close_wave(wf)
        _terminate_audio(p)


def loop_audio(duration):
    CHUNK = 44100//25#设置音频chunck
    FORMAT = paInt16 #设置音频采样精度,支持16bit(paInt16)/24bit(paInt24)/32bit(paInt32)
    CHANNELS = 2 #设置音频声道数，支持单声道(1)/立体声(2)
    RATE = 44100 #设置音频采样率

    p = None
    input_stream = None
    output_stream = None
    try:
        p = PyAudio()

        #创建音频输入流
        input_stream = p.open(format=FORMAT,
                        channels=CHANNELS,
                        rate=RATE,
                        input=True,
                        frames_per_buffer=CHUNK)

        #设置音频输入流的音量
        input_stream.volume(70, LEFT)
        input_stream.volume(85, RIGHT)
        print("input volume :",input_stream.volume())

        #启用音频3A功能：自动噪声抑制(ANS)
        input_stream.enable_audio3a(AUDIO_3A_ENABLE_ANS)

        #创建音频输出流
        output_stream = p.open(format=FORMAT,
                        channels=CHANNELS,
                        rate=RATE,
                        output=True,frames_per_buffer=CHUNK)

        #设置音频输出流的音量
        output_stream.volume(vol=85)

        #从音频输入流中获取数据写入到音频输出流中
        for i in range(0, int(RATE / CHUNK * duration)):
            output_stream.write(input_stream.read())
            if exit_check():
                break
    except KeyboardInterrupt as e:
        print("user stop: ", e)
    except BaseException as e:
        import sys
        sys.print_exception(e)
        raise
    finally:
        _close_stream(input_stream)
        _close_stream(output_stream)
        _terminate_audio(p)


def audio_recorder(filename, duration):
    CHUNK = 44100//25      #设置音频chunk值
    FORMAT = paInt16       #设置采样精度,支持16bit(paInt16)/24bit(paInt24)/32bit(paInt32)
    CHANNELS = 1           #设置声道数,支持单声道(1)/立体声(2)
    RATE = 44100           #设置采样率

    p = None
    input_stream = None
    output_stream = None
    wf = None
    try:
        p = PyAudio()
        #创建音频输入流
        input_stream = p.open(format=FORMAT,
                        channels=CHANNELS,
                        rate=RATE,
                        input=True,
                        frames_per_buffer=CHUNK)

        input_stream.volume(70, LEFT)
        input_stream.volume(85, RIGHT)
        print("input volume :",input_stream.volume())

        #启用音频3A功能：自动噪声抑制(ANS)
        input_stream.enable_audio3a(AUDIO_3A_ENABLE_ANS)
        print("enable audio 3a:ans")

        print("start record...")
        frames = []
        #采集音频数据并存入列表
        for i in range(0, int(RATE / CHUNK * duration)):
            data = input_stream.read()
            frames.append(data)
            if exit_check():
                break
        print("stop record...")
        #将列表中的数据保存到wav文件中
        wf = wave.open(filename, 'wb') #创建wav 文件
        wf.set_channels(CHANNELS) #设置wav 声道数
        wf.set_sampwidth(p.get_sample_size(FORMAT))  #设置wav 采样精度
        wf.set_framerate(RATE)  #设置wav 采样率
        wf.write_frames(b''.join(frames)) #存储wav音频数据
        _close_wave(wf)
        wf = None
        _close_stream(input_stream)
        input_stream = None

        wf = wave.open(filename, 'rb')#打开wav文件
        CHUNK = int(wf.get_framerate()/25)#设置音频chunk值

        #创建音频输出流，设置的音频参数均为wave中获取到的参数
        output_stream = p.open(format=p.get_format_from_width(wf.get_sampwidth()),
                    channels=wf.get_channels(),
                    rate=wf.get_framerate(),
                    output=True,frames_per_buffer=CHUNK)

        #设置音频输出流的音量
        output_stream.volume(vol=85)
        print("output volume :",output_stream.volume())

        print("start play...")
        data = wf.read_frames(CHUNK)#从wav文件中读取数一帧数据

        while data:
            output_stream.write(data)  #将帧数据写入到音频输出流中
            data = wf.read_frames(CHUNK) #从wav文件中读取数一帧数据
            if exit_check():
                break
        print("stop play...")
    except KeyboardInterrupt as e:
        print("user stop: ", e)
    except BaseException as e:
        import sys
        sys.print_exception(e)
        raise
    finally:
        _close_stream(input_stream)
        _close_stream(output_stream)
        _close_wave(wf)
        _terminate_audio(p)


if __name__ == "__main__":
    os.exitpoint(os.EXITPOINT_ENABLE)
    print("audio sample start")
    #record_audio('/data/test.wav', 15)  #录制wav文件
    # play_audio('/data/test.wav') #播放wav文件
    # loop_audio(15) #采集音频并输出
    audio_recorder('/data/test.wav', 15) #录制15秒音频并播放
    print("audio sample done")
