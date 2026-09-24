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

# 自定义关键词唤醒类，继承自AIBase基类
class KWSApp(AIBase):
    def __init__(self, kmodel_path, threshold, debug_mode=0):
        super().__init__(kmodel_path)  # 调用基类的构造函数
        self.kmodel_path = kmodel_path  # 模型文件路径
        self.threshold=threshold
        self.debug_mode = debug_mode  # 是否开启调试模式
        self.cache_np = np.zeros((1, 256, 105), dtype=np.float)

    # 自定义预处理，返回模型输入tensor列表
    def preprocess(self,pcm_data):
        pcm_data_list=[]
        # 获取音频流数据
        for i in range(0, len(pcm_data), 2):
            # 每两个字节组织成一个有符号整数，然后将其转换为浮点数，即为一次采样的数据，加入到当前一帧（0.3s）的数据列表中
            int_pcm_data = struct.unpack("<h", pcm_data[i:i+2])[0]
            float_pcm_data = float(int_pcm_data)
            pcm_data_list.append(float_pcm_data)
        # 将pcm数据处理为模型输入的特征向量
        mp_feats = aidemo.kws_preprocess(fp, pcm_data_list)[0]
        mp_feats_np = np.array(mp_feats).reshape((1, 30, 40))
        audio_input_tensor = nn.from_numpy(mp_feats_np)
        cache_input_tensor = nn.from_numpy(self.cache_np)
        return [audio_input_tensor,cache_input_tensor]

    # 自定义当前任务的后处理，results是模型输出array列表
    def postprocess(self, results):
        with ScopedTiming("postprocess", self.debug_mode > 0):
            logits_np = results[0]
            self.cache_np= results[1]
            max_logits = np.max(logits_np, axis=1)[0]
            max_p = np.max(max_logits)
            idx = np.argmax(max_logits)
            # 如果分数大于阈值，且idx==1(即包含唤醒词)，播放回复音频
            if max_p > self.threshold and idx == 1:
                return 1
            else:
                return 0


def close_audio_stream(stream,name):
    if stream is None:
        return
    try:
        stream.stop_stream()
    except Exception as error:
        print(name,"stop failed:",error)
    try:
        stream.close()
    except Exception as error:
        print(name,"close failed:",error)


if __name__ == "__main__":
    os.exitpoint(os.EXITPOINT_ENABLE)
    nn.shrink_memory_pool()
    # 设置模型路径和其他参数
    kmodel_path = "/sdcard/examples/kmodel/kws.kmodel"
    # 其它参数
    THRESH = 0.5
    SAMPLE_RATE = 16000
    CHANNELS = 1
    FORMAT = paInt16
    CHUNK = int(0.3 * 16000)
    reply_wav_file = "/sdcard/examples/utils/wozai.wav"

    fp=None
    p=None
    input_stream=None
    output_stream=None
    kws=None
    wf=None
    try:
        # 音频预处理、音频设备和模型都纳入同一个生命周期。
        fp=aidemo.kws_fp_create()
        p=PyAudio()
        input_stream=p.open(format=FORMAT,channels=CHANNELS,rate=SAMPLE_RATE,input=True,frames_per_buffer=CHUNK)
        input_stream.volume(vol=100)
        output_stream=p.open(format=FORMAT,channels=CHANNELS,rate=SAMPLE_RATE,output=True,frames_per_buffer=CHUNK)
        kws=KWSApp(kmodel_path,threshold=THRESH,debug_mode=0)

        while True:
            os.exitpoint()
            with ScopedTiming("total",1):
                pcm_data=input_stream.read()
                res=kws.run(pcm_data)
                if res:
                    print("====Detected XiaonanXiaonan!====")
                    wf=wave.open(reply_wav_file,"rb")
                    try:
                        wav_data=wf.read_frames(CHUNK)
                        while wav_data:
                            output_stream.write(wav_data)
                            wav_data=wf.read_frames(CHUNK)
                        time.sleep(1)
                    finally:
                        wf.close()
                        wf=None
                else:
                    print("Deactivated!")
                gc.collect()
    except KeyboardInterrupt:
        print("Keyword spotting stopped")
    except Exception as error:
        sys.print_exception(error)
    finally:
        os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
        if wf is not None:
            try:
                wf.close()
            except Exception as error:
                print("wave close failed:",error)
            wf=None

        # 先停采集和播放，再终止 PyAudio，最后释放算法和 KPU。
        close_audio_stream(input_stream,"audio input")
        input_stream=None
        close_audio_stream(output_stream,"audio output")
        output_stream=None
        if p is not None:
            try:
                p.terminate()
            except Exception as error:
                print("PyAudio terminate failed:",error)
            p=None
        if fp is not None:
            try:
                aidemo.kws_fp_destroy(fp)
            except Exception as error:
                print("KWS preprocess destroy failed:",error)
            fp=None
        if kws is not None:
            try:
                kws.deinit()
            except Exception as error:
                print("KWS model deinit failed:",error)
            kws=None
        gc.collect()
        nn.shrink_memory_pool()
        gc.collect()
        time.sleep_ms(100)


