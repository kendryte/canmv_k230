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


ogg_muxer = k_u64_ptr()
def exit_check():
    try:
        os.exitpoint()
    except KeyboardInterrupt as e:
        import sys
        sys.print_exception(e)
        return True
    return False


def record_audio_to_opus_ogg(filename, duration):
    """Record audio for `duration` seconds and save it as an Opus-encoded Ogg file."""

    global ogg_muxer
    CHUNK = int(8000/25) #设置音频chunk值
    FORMAT = paInt16 #设置采样精度
    CHANNELS = 1 #设置声道数
    RATE = 8000 #设置采样率

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
            frame_params.frame_samples = 8000//25

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

if __name__ == "__main__":
    os.exitpoint(os.EXITPOINT_ENABLE)

    muxer_params = kd_ogg_muxer_params()
    muxer_params.sample_rate = 8000
    muxer_params.channels = 1
    muxer_params.serial_no = 0
    muxer_params.filename[:] = bytes("/data/test.ogg", 'utf-8')

    
    kd_ogg_muxer_init(ogg_muxer, muxer_params)

    print("ogg sample start")
    record_audio_to_opus_ogg("/data/test.ogg",15)
    print("ogg sample done")


