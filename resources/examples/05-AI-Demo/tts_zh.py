from libs.PipeLine import ScopedTiming
from libs.AIBase import AIBase
from libs.AI2D import Ai2d
from media.pyaudio import *                     # 音频模块
from media.media import *                       # 软件抽象模块，主要封装媒体数据链路以及媒体缓冲区
import media.wave as wave                       # wav音频处理模块
import nncase_runtime as nn                     # nncase运行模块，封装了kpu（kmodel推理）和ai2d（图片预处理加速）操作
import ulab.numpy as np                         # 类似python numpy操作，但也会有一些接口不同
import aidemo                                   # aidemo模块，封装ai demo相关前处理、后处理等操作
import time                                     # 时间统计
import struct                                   # 字节字符转换模块
import gc                                       # 垃圾回收模块
import os,sys                                   # 操作系统接口模块

# 自定义TTS中文编码器类，继承自AIBase基类
class EncoderApp(AIBase):
    def __init__(self, kmodel_path,dict_path,phase_path,mapfile,debug_mode=0):
        super().__init__(kmodel_path)  # 调用基类的构造函数
        self.kmodel_path = kmodel_path  # 模型文件路径
        self.debug_mode = debug_mode  # 是否开启调试模式
        self.ttszh=aidemo.tts_zh_create(dict_path,phase_path,mapfile)
        self.data=None
        self.data_len=0
        self.durition_sum=0

    # 自定义编码器预处理，返回模型输入tensor列表
    def preprocess(self,text):
        with ScopedTiming("encoder preprocess", self.debug_mode > 0):
            preprocess_data=aidemo.tts_zh_preprocess(self.ttszh,text)
            self.data=preprocess_data[0]
            self.data_len=preprocess_data[1]
            # 创建编码器模型输入并和模型绑定，编码器包含两个输入，一个是文字预处理的序列数据，一个是speaker数据
            # 编码器序列数据
            enc_seq_input_tensor = nn.from_numpy(np.array(self.data))
            # 编码器speaker数据
            enc_speaker_input_tensor=nn.from_numpy(np.array([0.0]))
            return [enc_speaker_input_tensor,enc_seq_input_tensor]

    # 自定义编码器的后处理，results是模型输出ndarray列表,编码器后处理也可以视为解码器的前处理
    def postprocess(self, results):
        with ScopedTiming("encoder postprocess", self.debug_mode > 0):
            enc_output_0_np=results[0]
            enc_output_1_np=results[1]
            # 给编码结果添加持续时间属性，每个音素编码向量按照持续时间重复
            duritions=enc_output_1_np[0][:int(self.data_len[0])]
            self.durition_sum=int(np.sum(duritions))
            # 解码器输入维度为（1,600,256）,不足部分需要padding
            max_value=13
            while self.durition_sum>600:
                for i in range(len(duritions)):
                    if duritions[i]>max_value:
                        duritions[i]=max_value
                max_value=max_value-1
                self.durition_sum=np.sum(duritions)
            dec_input=np.zeros((1,600,256),dtype=np.float)
            m_pad=600-self.durition_sum
            k=0
            for i in range(len(duritions)):
                for j in range(int(duritions[i])):
                    dec_input[0][k]=enc_output_0_np[0][i]
                    k+=1
            return dec_input,self.durition_sum

# 自定义TTS中文解码器类，继承自AIBase基类
class DecoderApp(AIBase):
    def __init__(self, kmodel_path, debug_mode=0):
        super().__init__(kmodel_path)  # 调用基类的构造函数
        self.kmodel_path = kmodel_path  # 模型文件路径
        self.debug_mode = debug_mode  # 是否开启调试模式

    # 自定义解码器预处理，返回模型输入tensor列表
    def preprocess(self,dec_input):
        with ScopedTiming("decoder preprocess", self.debug_mode > 0):
            dec_input_tensor=nn.from_numpy(dec_input)
            return [dec_input_tensor]

    # 自定义解码器后处理，results是模型输出ndarray列表
    def postprocess(self, results):
        with ScopedTiming("decoder postprocess", self.debug_mode > 0):
            return results[0]

# 自定义HifiGan声码器类，继承自AIBase基类
class HifiGanApp(AIBase):
    def __init__(self, kmodel_path, debug_mode=0):
        super().__init__(kmodel_path)  # 调用基类的构造函数
        self.kmodel_path = kmodel_path  # 模型文件路径
        self.debug_mode = debug_mode  # 是否开启调试模式
        self.mel_data=[]
        self.subvector_num=0
        self.hifi_input=None

    # 自定义声码器预处理，返回模型输入tensor列表
    def preprocess(self,dec_output_np,durition_sum):
        with ScopedTiming("hifigan preprocess", self.debug_mode > 0):
            self.subvector_num=durition_sum//100
            remaining=durition_sum%100
            if remaining>0:
                self.subvector_num+=1
            self.hifi_input=np.zeros((1,80,self.subvector_num*100),dtype=np.float)
            for i in range(durition_sum):
                self.hifi_input[:,:,i]=dec_output_np[:,:,i]

    def run(self,dec_output_np,durition_sum):
        self.preprocess(dec_output_np,durition_sum)
        # 依次对每一个子向量进行声码器推理
        for i in range(self.subvector_num):
            hifi_input_tmp=np.zeros((1,80,100),dtype=np.float)
            for j in range(80):
                for k in range(i*100,(i+1)*100):
                    hifi_input_tmp[0][j][k-i*100]=self.hifi_input[0][j][k]
            # 设置模型输入
            hifigan_input_tensor=nn.from_numpy(hifi_input_tmp)
            # 推理
            results=self.inference([hifigan_input_tensor])
            self.postprocess(results)
        return self.mel_data

    # 自定义当前任务的后处理，results是模型输出ndarray列表
    def postprocess(self, results):
        with ScopedTiming("hifigan postprocess", self.debug_mode > 0):
            # 汇总输出数据
            self.mel_data+=results[0][0][0].tolist()

#自定义中文TTS任务类
class TTSZH:
    def __init__(self,encoder_kmodel_path,decoder_kmodel_path,hifigan_kmodel_path,dict_path,phase_path,mapfile,save_wav_file,debug_mode):
        self.save_wav_file=save_wav_file
        self.debug_mode=debug_mode
        self.encoder=EncoderApp(encoder_kmodel_path,dict_path,phase_path,mapfile,debug_mode)
        self.decoder=DecoderApp(decoder_kmodel_path,debug_mode)
        self.hifigan=HifiGanApp(hifigan_kmodel_path,debug_mode)

    def run(self,text):
        encoder_output_0,encoder_output_1=self.encoder.run(text)
        decoder_output_0=self.decoder.run(encoder_output_0)
        hifigan_output=self.hifigan.run(decoder_output_0,encoder_output_1)
        # 将生成的音频数据保存为wav文件
        save_data=hifigan_output[:encoder_output_1*256]
        save_len=len(save_data)
        save_data_np=np.array(save_data.copy(),dtype=np.float)
        save_data_clip=np.clip(save_data_np,-1.0,1.0)
        save_pcm=save_data_clip*32767.0
        save_data_int16=np.array(save_pcm,dtype=np.int16)
        save_data_l=save_data_int16.tobytes()
        wf = wave.open(save_wav_file, 'wb')
        wf.set_channels(1)
        wf.set_sampwidth(2)
        wf.set_framerate(24000)
        wf.write_frames(save_data_l)
        wf.close()
        self.play_audio()

    def play_audio(self):
        with ScopedTiming("play audio", self.debug_mode > 0):
            # 有关音频流的宏变量
            SAMPLE_RATE = 24000         # 采样率24000Hz,即每秒采样24000次
            CHANNELS = 1                # 通道数 1为单声道，2为立体声
            FORMAT = paInt16            # 音频输入输出格式 paInt16
            CHUNK = int(0.3 * 24000)    # 每次读取音频数据的帧数，设置为0.3s的帧数24000*0.3=7200
            # 初始化音频流
            p = PyAudio()
            if ret:
                print("record_audio, buffer_init failed")
            # 用于播放音频
            output_stream = p.open(format=FORMAT,channels=CHANNELS,rate=SAMPLE_RATE,output=True,frames_per_buffer=CHUNK)
            wf = wave.open(self.save_wav_file, "rb")
            wav_data = wf.read_frames(CHUNK)
            while wav_data:
                output_stream.write(wav_data)
                wav_data = wf.read_frames(CHUNK)
            time.sleep(2) # 时间缓冲，用于播放声音
            wf.close()
            output_stream.stop_stream()
            output_stream.close()


    def deinit(self):
        aidemo.tts_zh_destroy(self.encoder.ttszh)
        tts_zh.encoder.deinit()
        tts_zh.decoder.deinit()
        tts_zh.hifigan.deinit()

if __name__ == "__main__":
    os.exitpoint(os.EXITPOINT_ENABLE)
    nn.shrink_memory_pool()
    # 设置模型路径和其他参数
    # 中文tts encoder模型
    encoder_kmodel_path = "/sdcard/examples/kmodel/zh_fastspeech_1_f32.kmodel"
    # 中文tts decoder模型
    decoder_kmodel_path = "/sdcard/examples/kmodel/zh_fastspeech_2.kmodel"
    # 中文tts 声码器模型
    hifigan_kmodel_path="/sdcard/examples/kmodel/hifigan.kmodel"
    # 拼音字典
    dict_path="/sdcard/examples/utils/pinyin.txt"
    # 汉字转拼音字典文件
    phase_path="/sdcard/examples/utils/small_pinyin.txt"
    # 拼音转音素映射文件
    mapfile="/sdcard/examples/utils/phone_map.txt"
    # 输入中文语句
    text="嘉楠科技研发了最新款的芯片"
    # 生成音频存储路径
    save_wav_file = "/sdcard/examples/test.wav"

    # 初始化自定义中文tts实例
    tts_zh = TTSZH(encoder_kmodel_path,decoder_kmodel_path,hifigan_kmodel_path,dict_path,phase_path,mapfile,save_wav_file,debug_mode=0)
    try:
        with ScopedTiming("total",1):
            tts_zh.run(text)
            gc.collect()                        # 垃圾回收
    except Exception as e:
        import sys
        sys.print_exception(e)                  # 打印异常信息
    finally:
        tts_zh.deinit()


