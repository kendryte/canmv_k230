# audio input and output example
#
# Note: You will need an SD card to run this example.
#
# Records audio from multiple channels and saves each to separate wav files

import os
from media.media import *   #导入media模块，用于初始化vb buffer
from media.pyaudio import * #导入pyaudio模块，用于采集和播放音频
import media.wave as wave   #导入wav模块，用于保存和加载wav音频文件
from machine import FPIOA

def exit_check():
    try:
        os.exitpoint()
    except KeyboardInterrupt as e:
        print("user stop: ", e)
        return True
    return False


def init_audio_pdm_io():
    """
    初始化PDM音频接口的IO配置（基于庐山派开发板）

    函数功能：配置庐山派开发板上与PDM音频采集相关的GPIO引脚功能，
    映射PDM时钟线和数据线到指定物理引脚，设置引脚为输入/输出模式。
    具体引脚分配如下：
    - 引脚26：PDM时钟线(PDM_CLK)，配置为输出模式
    - 引脚27：PDM数据0线(PDM_IN0)，配置为输入模式
    - 引脚35：PDM数据1线(IIS_D_OUT0_PDM_IN1)，配置为输入模式
    - 引脚36：PDM数据2线(IIS_D_IN1_PDM_IN2)，配置为输入模式
    - 引脚34：PDM数据3线(IIS_D_IN0_PDM_IN3)，配置为输入模式
    """
    fpioa = FPIOA()
    fpioa.set_function(26, FPIOA.PDM_CLK,oe=0x1,ie=0x0)   #pdm clk
    fpioa.set_function(27, FPIOA.PDM_IN0,oe=0x0,ie=0x1)  #pdm data0
    fpioa.set_function(35, FPIOA.IIS_D_OUT0_PDM_IN1,oe=0x0,ie=0x1)  #pdm data1
    fpioa.set_function(36, FPIOA.IIS_D_IN1_PDM_IN2,oe=0x0,ie=0x1)  #pdm data2
    fpioa.set_function(34, FPIOA.IIS_D_IN0_PDM_IN3,oe=0x0,ie=0x1)  #pdm data3

def record_audio_pdm(base_filename, duration, num_channels):
    CHUNK = 44100//25  #设置音频chunk值
    FORMAT = paInt16       #设置采样精度,支持16bit(paInt16)/24bit(paInt24)/32bit(paInt32)
    RATE = 44100           #设置采样率
    pdm_chn_cnt = num_channels // 2

    init_audio_pdm_io()  #初始化pdm音频io口

    try:
        p = PyAudio()

        #创建音频输入流
        stream = p.open(format=FORMAT,
                        channels=num_channels,
                        rate=RATE,
                        input=True,
                        frames_per_buffer=CHUNK,
                        input_device_index=1) #使用PDM设备采集音频


        # 初始化音频帧存储数组，每个元素对应一个通道的帧列表
        channel_frames = [[] for _ in range(pdm_chn_cnt)]

        # 计算总帧数
        total_frames = int(RATE / CHUNK * duration)

        #采集音频数据并存入列表
        print(f"开始录制 {pdm_chn_cnt}组 {num_channels}声道pdm音频，持续 {duration} 秒...")
        for i in range(total_frames):
            for ch in range(pdm_chn_cnt):
                data = stream.read(chn=ch)
                channel_frames[ch].append(data)

            # 每100帧打印一次进度
            if i % 100 == 0:
                progress = (i / total_frames) * 100
                print(f"录制进度: {progress:.1f}%", end='\r')

            if exit_check():
                print("\n用户中断录制")
                break

        # 为每组pdm创建单独的WAV文件
        for ch in range(pdm_chn_cnt):
            # 生成带索引号的文件名，如 base_0.wav, base_1.wav
            filename = f"{base_filename}_ch{ch}.wav"

            # 将列表中的数据保存到wav文件中
            wf = wave.open(filename, 'wb') #创建wav 文件
            wf.set_channels(2)  # 每个文件保存双声道
            wf.set_sampwidth(p.get_sample_size(FORMAT))  #设置wav 采样精度
            wf.set_framerate(RATE)  #设置wav 采样率
            wf.write_frames(b''.join(channel_frames[ch])) #存储对应通道的音频数据
            wf.close() #关闭wav文件
            print(f"已保存声道 {ch*2},{ch*2+1} 到 {filename}")

    except BaseException as e:
            import sys
            sys.print_exception(e)
    finally:
        stream.stop_stream() #停止采集音频数据
        stream.close()#关闭音频输入流
        print("录制完成，资源已释放")


if __name__ == "__main__":
    os.exitpoint(os.EXITPOINT_ENABLE)
    print("pdm sample start")
    # 录制4组共8声道音频，保存为/sdcard/examples/test_ch0.wav 至 test_ch3.wav
    record_audio_pdm('/data/test', 15, 8)

    print("pdm sample done")
