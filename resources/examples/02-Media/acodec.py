# g711/opus encode/decode example
#
# Note: You will need an SD card to run this example.
#
# You can collect raw data and encode it into g711/opus or decode it into raw data output.

import os
from mpp.payload_struct import * #导入payload模块，用于获取音视频编解码类型
from media.media import * #导入media模块，用于初始化vb buffer
from media.pyaudio import * #导入pyaudio模块，用于采集和播放音频
import media.g711 as g711 #导入g711模块，用于g711编解码
import media.opus as opus #导入opus模块，用于opus编解码

def exit_check():
    try:
        os.exitpoint()
    except KeyboardInterrupt as e:
        import sys
        sys.print_exception(e)
        return True
    return False

def encode_audio(filename, duration):
    CHUNK = int(44100/25) #设置音频chunk值
    FORMAT = paInt16 #设置采样精度
    CHANNELS = 2 #设置声道数
    RATE = 44100 #设置采样率

    try:
        p = PyAudio()
        enc = g711.Encoder(K_PT_G711A,CHUNK) #创建g711编码器对象

        enc.create() #创建编码器
        #创建音频输入流
        stream = p.open(format=FORMAT,
                        channels=CHANNELS,
                        rate=RATE,
                        input=True,
                        frames_per_buffer=CHUNK)

        frames = []
        #采集音频数据编码并存入列表
        for i in range(0, int(RATE / CHUNK * duration)):
            frame_data = stream.read() #从音频输入流中读取音频数据
            data = enc.encode(frame_data) #编码音频数据为g711
            frames.append(data)  #将g711编码数据保存到列表中
            if exit_check():
                break
        #将g711编码数据存入文件中
        with open(filename,mode='w') as wf:
            wf.write(b''.join(frames))
        stream.stop_stream() #停止音频输入流
        stream.close() #关闭音频输入流
        enc.destroy() #销毁g711音频编码器
    except BaseException as e:
        import sys
        sys.print_exception(e)
    finally:
        pass

def decode_audio(filename):
    FORMAT = paInt16 #设置音频chunk值
    CHANNELS = 2 #设置声道数
    RATE = 44100 #设置采样率
    CHUNK = int(RATE/25) #设置音频chunk值

    try:
        wf = open(filename,mode='rb') #打开g711文件
        p = PyAudio()
        dec = g711.Decoder(K_PT_G711A,CHUNK) #创建g711解码器对象

        dec.create() #创建解码器

        #创建音频输出流
        stream = p.open(format=FORMAT,
                    channels=CHANNELS,
                    rate=RATE,
                    output=True,
                    frames_per_buffer=CHUNK)

        stream_len = CHUNK*CHANNELS*2//2  #设置每次读取的g711数据流长度
        stream_data = wf.read(stream_len) #从g711文件中读取数据

        #解码g711文件并播放
        while stream_data:
            frame_data = dec.decode(stream_data) #解码g711文件
            stream.write(frame_data) #播放raw数据
            stream_data = wf.read(stream_len) #从g711文件中读取数据
            if exit_check():
                break
        stream.stop_stream() #停止音频输入流
        stream.close() #关闭音频输入流
        dec.destroy() #销毁解码器
        wf.close() #关闭g711文件

    except BaseException as e:
        import sys
        sys.print_exception(e)
    finally:
        pass

def loop_codec(duration):
    CHUNK = int(44100/25) #设置音频chunk值
    FORMAT = paInt16 #设置采样精度
    CHANNELS = 2 #设置声道数
    RATE = 44100 #设置采样率

    try:
        p = PyAudio()
        dec = g711.Decoder(K_PT_G711A,CHUNK) #创建g711解码器对象
        enc = g711.Encoder(K_PT_G711A,CHUNK) #创建g711编码器对象

        dec.create() #创建g711解码器
        enc.create() #创建g711编码器

        #创建音频输入流
        input_stream = p.open(format=FORMAT,
                        channels=CHANNELS,
                        rate=RATE,
                        input=True,
                        frames_per_buffer=CHUNK)

        #创建音频输出流
        output_stream = p.open(format=FORMAT,
                        channels=CHANNELS,
                        rate=RATE,
                        output=True,
                        frames_per_buffer=CHUNK)

        #从音频输入流中获取数据->编码->解码->写入到音频输出流中
        for i in range(0, int(RATE / CHUNK * duration)):
            frame_data = input_stream.read() #从音频输入流中获取raw音频数据
            stream_data = enc.encode(frame_data) #编码音频数据为g711
            frame_data = dec.decode(stream_data) #解码g711数据为raw数据
            output_stream.write(frame_data) #播放raw数据
            if exit_check():
                break
        input_stream.stop_stream() #停止音频输入流
        output_stream.stop_stream() #停止音频输出流
        input_stream.close() #关闭音频输入流
        output_stream.close() #关闭音频输出流
        dec.destroy() #销毁g711解码器
        enc.destroy() #销毁g711编码器
    except BaseException as e:
        import sys
        sys.print_exception(e)
    finally:
        pass

def loop_codec_opus(duration):
    CHUNK = int(8000/25) #设置音频chunk值
    FORMAT = paInt16 #设置采样精度
    CHANNELS = 1 #设置声道数
    RATE = 8000 #设置采样率

    try:
        p = PyAudio()
        dec = opus.Decoder(channels = CHANNELS,sample_rate = RATE,frames_per_buffer = CHUNK) #创建opus解码器对象
        enc = opus.Encoder(channels = CHANNELS,sample_rate = RATE,bitrate = 16000,frames_per_buffer = CHUNK) #创建opus编码器对象

        dec.create() #创建opus解码器
        enc.create() #创建opus编码器

        #创建音频输入流
        input_stream = p.open(format=FORMAT,
                        channels=CHANNELS,
                        rate=RATE,
                        input=True,
                        frames_per_buffer=CHUNK)

        #创建音频输出流
        output_stream = p.open(format=FORMAT,
                        channels=CHANNELS,
                        rate=RATE,
                        output=True,
                        frames_per_buffer=CHUNK)

        #从音频输入流中获取数据->编码->解码->写入到音频输出流中
        for i in range(0, int(RATE / CHUNK * duration)):
            frame_data = input_stream.read() #从音频输入流中获取raw音频数据
            stream_data = enc.encode(frame_data) #编码音频数据为opus
            frame_data = dec.decode(stream_data) #解码opus数据为raw数据
            output_stream.write(frame_data) #播放raw数据
            if exit_check():
                break
        input_stream.stop_stream() #停止音频输入流
        output_stream.stop_stream() #停止音频输出流
        input_stream.close() #关闭音频输入流
        output_stream.close() #关闭音频输出流
        dec.destroy() #销毁opus解码器
        enc.destroy() #销毁opus编码器
    except BaseException as e:
        import sys
        sys.print_exception(e)
    finally:
        pass

def loop_codec_opus_bind(duration):
    CHUNK = int(8000/25) #设置音频chunk值
    FORMAT = paInt16 #设置采样精度
    CHANNELS = 1 #设置声道数
    RATE = 8000 #设置采样率

    try:
        p = PyAudio()
        dec = opus.Decoder(channels = CHANNELS,sample_rate = RATE,frames_per_buffer = CHUNK) #创建opus解码器对象
        enc = opus.Encoder(channels = CHANNELS,sample_rate = RATE,bitrate = 16000,frames_per_buffer = CHUNK) #创建opus编码器对象

        dec.create() #创建opus解码器
        enc.create() #创建opus编码器

        #绑定音频采集和编码器
        link_ai_aenc = MediaManager.link((AUDIO_IN_MOD_ID, 0, 0), (AUDIO_ENCODE_MOD_ID, 0, 0))
        #绑定音频解码器和输出
        link_adec_ao = MediaManager.link((AUDIO_DECODE_MOD_ID, 0, 0), (AUDIO_OUT_MOD_ID, 0, 0))

        #创建音频输入流
        input_stream = p.open(format=FORMAT,
                        channels=CHANNELS,
                        rate=RATE,
                        input=True,
                        frames_per_buffer=CHUNK)

        #创建音频输出流
        output_stream = p.open(format=FORMAT,
                        channels=CHANNELS,
                        rate=RATE,
                        output=True,
                        frames_per_buffer=CHUNK)

        #从编码器获取编码数据，并发送给解码器
        for i in range(0, int(RATE / CHUNK * duration)):
            stream_data = enc.get_stream() #获取编码音频数据
            dec.send_stream(stream_data) #将编码数据发送到解码器
            if exit_check():
                break
        input_stream.stop_stream() #停止音频输入流
        output_stream.stop_stream() #停止音频输出流
        input_stream.close() #关闭音频输入流
        output_stream.close() #关闭音频输出流
        dec.destroy() #销毁opus解码器
        enc.destroy() #销毁opus编码器
        del link_ai_aenc
        del link_adec_ao
    except BaseException as e:
        import sys
        sys.print_exception(e)
    finally:
        pass

if __name__ == "__main__":
    os.exitpoint(os.EXITPOINT_ENABLE)
    print("audio codec sample start")
    #encode_audio('/data/test.g711a', 15) #采集并编码g711文件
    #decode_audio('/data/test.g711a') #解码g711文件并输出
    #loop_codec_opus(15) #采集音频数据->编码opus->解码opus->播放音频
    #loop_codec_opus_bind(15) #采集音频数据->编码opus->解码opus->播放音频(pipeline 绑定模式)
    loop_codec(15) #采集音频数据->编码g711->解码g711->播放音频
    print("audio codec sample done")
