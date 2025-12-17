import os
from mpp.payload_struct import * #导入payload模块，用于获取音视频编解码类型
from media.media import * #导入media模块，用于初始化vb buffer
from media.pyaudio import * #导入pyaudio模块，用于采集和播放音频
import media.opus as opus #导入opus模块，用于opus编解码
from mpp.libogg import *
from mpp.libogg_struct import *
import uctypes
import time
import os

def exit_check():
    try:
        os.exitpoint()
    except KeyboardInterrupt as e:
        import sys
        sys.print_exception(e)
        return True
    return False


def record_audio_to_ogg_file(filename, duration,sample_rate = 8000,channels = 1):
    """Record audio for `duration` seconds and save it as an Opus-encoded Ogg file."""

    ogg_muxer = k_u64_ptr()
    muxer_params = kd_ogg_muxer_params()
    muxer_params.sample_rate = sample_rate
    muxer_params.channels = channels
    muxer_params.serial_no = 0
    muxer_params.filename[:] = bytes("/data/test.ogg", 'utf-8')
    kd_ogg_muxer_init(ogg_muxer, muxer_params)

    CHUNK = int(sample_rate/25) #设置音频chunk值
    FORMAT = paInt16 #设置采样精度
    CHANNELS = channels #设置声道数
    RATE = sample_rate #设置采样率

    try:
        p = PyAudio()
        enc = opus.Encoder(channels = CHANNELS,sample_rate = RATE,bitrate = 16000,frames_per_buffer = CHUNK) #创建opus编码器对象

        enc.create() #创建opus编码器

        #创建音频输入流
        input_stream = p.open(format=FORMAT,
                        channels=CHANNELS,
                        rate=RATE,
                        input=True,
                        frames_per_buffer=CHUNK)

        #从音频输入流中获取数据->编码->封装成ogg
        for i in range(0, int(RATE / CHUNK * duration)):
            frame_data = input_stream.read() #从音频输入流中获取raw音频数据
            stream_data = enc.encode(frame_data) #编码音频数据为opus

            opus_buf = bytearray(stream_data)
            frame_params = kd_ogg_frame_params()
            frame_params.data = uctypes.addressof(opus_buf)
            frame_params.len = len(stream_data)
            frame_params.frame_samples = CHUNK

            kd_ogg_write_frame(ogg_muxer.value,frame_params)

            if exit_check():
                break
        input_stream.stop_stream() #停止音频输入流
        input_stream.close() #关闭音频输入流
        enc.destroy() #销毁opus编码器
        kd_ogg_muxer_destroy(ogg_muxer.value)
    except BaseException as e:
        import sys
        sys.print_exception(e)
    finally:
        pass


def record_audio_to_ogg_stream_file(duration,sample_rate = 8000,channels = 1):
    """Record audio for `duration` seconds and save it as an Opus-encoded Ogg file."""

    ogg_muxer = k_u64_ptr()
    muxer_params = kd_ogg_muxer_params()
    muxer_params.sample_rate = sample_rate
    muxer_params.channels = channels
    muxer_params.serial_no = 0
    kd_ogg_muxer_init(ogg_muxer, muxer_params)

    CHUNK = int(sample_rate/25) #设置音频chunk值
    FORMAT = paInt16 #设置采样精度
    CHANNELS = channels #设置声道数
    RATE = sample_rate #设置采样率

    data_ogg = bytearray(1000)  # 存储muxer后的OGG页数据
    data_ogg_size = uctypes.struct(uctypes.addressof(bytearray(4)), {"value": 0 | uctypes.UINT32})
    data_ogg_size.value = 0
    ogg_file = None

    try:
        ogg_file = open("/data/test.ogg", "wb")  # 二进制写入模式
        p = PyAudio()
        enc = opus.Encoder(channels = CHANNELS,sample_rate = RATE,bitrate = 16000,frames_per_buffer = CHUNK) #创建opus编码器对象

        enc.create() #创建opus编码器

        #创建音频输入流
        input_stream = p.open(format=FORMAT,
                        channels=CHANNELS,
                        rate=RATE,
                        input=True,
                        frames_per_buffer=CHUNK)

        #从音频输入流中获取数据->编码->封装成ogg
        for i in range(0, int(RATE / CHUNK * duration)):
            frame_data = input_stream.read() #从音频输入流中获取raw音频数据
            stream_data = enc.encode(frame_data) #编码音频数据为opus

            opus_buf = bytearray(stream_data)
            frame_params = kd_ogg_frame_params_ex()
            frame_params.data = uctypes.addressof(opus_buf)
            frame_params.len = len(stream_data)
            frame_params.frame_samples = CHUNK
            frame_params.out_page = uctypes.addressof(data_ogg)
            frame_params.out_page_size = uctypes.addressof(data_ogg_size)

            kd_ogg_write_frame_ex(ogg_muxer.value,frame_params)

            # 读取OGG页数据
            if (data_ogg_size.value > 0):
                print("Got OGG page of size:", data_ogg_size.value)
                ogg_file.write(data_ogg[:data_ogg_size.value])
                ogg_file.flush()  # 立即刷入文件
                data_ogg_size.value = 0

            if exit_check():
                break
        input_stream.stop_stream() #停止音频输入流
        input_stream.close() #关闭音频输入流
        enc.destroy() #销毁opus编码器
        kd_ogg_muxer_destroy(ogg_muxer.value)
    except BaseException as e:
        import sys
        sys.print_exception(e)
    finally:
        if ogg_file:
            ogg_file.close()

def loop_ogg_bind(duration):
    """Loop audio through ogg muxer and demuxer using media manager bindings:ai -> aenc opus -> muxer ogg -> demuxer ogg -> opus -> adec -> ao."""
    RATE = 8000 #设置采样率
    CHUNK = int(RATE/25) #设置音频chunk值
    FORMAT = paInt16 #设置采样精度
    CHANNELS = 1 #设置声道数

    data_ogg = bytearray(1000)  # 存储muxer后的OGG页数据
    data_ogg_size = uctypes.struct(uctypes.addressof(bytearray(4)), {"value": 0 | uctypes.UINT32})
    data_ogg_size.value = 0

    data_opus = bytearray(1000)  # 存储demuxer后的Opus帧数据
    data_opus_size = uctypes.struct(uctypes.addressof(bytearray(4)), {"value": 0 | uctypes.UINT32})
    data_opus_size.value = 0

    #init ogg muxer
    ogg_muxer = k_u64_ptr()
    muxer_params = kd_ogg_muxer_params()
    muxer_params.sample_rate = RATE
    muxer_params.channels = CHANNELS
    muxer_params.serial_no = 0
    kd_ogg_muxer_init(ogg_muxer, muxer_params)

    #init ogg demuxer
    ogg_demuxer = k_u64_ptr()
    demuxer_params = kd_ogg_demuxer_params()
    kd_ogg_demuxer_init(ogg_demuxer, demuxer_params)
    audio_stream = k_audio_stream()

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

        #ai -> aenc opus -> muxer ogg -> demuxer ogg -> opus -> adec -> ao
        for i in range(0, int(RATE / CHUNK * duration)):
            stream_data = enc.get_stream() #获取opus 编码音频数据
            #封装成ogg
            opus_buf = bytearray(stream_data)
            frame_params = kd_ogg_frame_params_ex()
            frame_params.data = uctypes.addressof(opus_buf)
            frame_params.len = len(stream_data)
            frame_params.frame_samples = CHUNK
            frame_params.out_page = uctypes.addressof(data_ogg)
            frame_params.out_page_size = uctypes.addressof(data_ogg_size)
            kd_ogg_write_frame_ex(ogg_muxer.value,frame_params)
            #读取ogg页数据，送给demuxer
            if (data_ogg_size.value > 0):
                #print("Got OGG page of size:", data_ogg_size.value)
                page_parames = kd_ogg_page_params_ex()
                page_parames.page_data = uctypes.addressof(data_ogg)
                page_parames.page_size = data_ogg_size.value
                page_parames.out_frame = uctypes.addressof(data_opus)
                page_parames.out_frame_size = uctypes.addressof(data_opus_size)
                kd_ogg_demuxer_feed_page_ex(ogg_demuxer.value,page_parames)
                #读取opus帧数据，送给adec
                if (data_opus_size.value > 0):
                    #print("Got Opus frame of size:", data_opus_size.value)
                    audio_stream.stream = uctypes.addressof(data_opus)
                    audio_stream.len = data_opus_size.value
                    dec.send_stream(stream_data)
                    data_opus_size.value = 0
                data_ogg_size.value = 0

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

    print("ogg sample start")
    #record_audio_to_ogg_file("/data/test.ogg",15)
    #record_audio_to_ogg_stream_file(15)
    loop_ogg_bind(15)
    print("ogg sample done")


