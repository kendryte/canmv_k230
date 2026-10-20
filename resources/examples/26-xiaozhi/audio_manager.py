"""
音频管理模块 - 基于K230 CanMV Audio API
处理音频采集、播放和编解码
"""

import time
import _thread
import media
from media.media import *
from media.pyaudio import *
import media.opus as opus

try:
    from libs.AudioConfig import get_audio_policy, open_input, open_output, close_pa
except ImportError:
    get_audio_policy = None

class AudioManager:
    """音频管理器 - 基于K230 CanMV Audio API"""
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = AudioManager()
        return cls._instance
    
    def __init__(self):
        self.recording = False
        self.playing = False
        self.play_thread_running = False
        self.record_callback = None
        self.play_callback = None
        self.record_thread = None
        self.play_thread = None
        
        # 音频参数 - 符合小智语音助手要求
        self.sample_rate = 16000
        self.channels = 1
        self.sample_width = 2  # 16-bit
        self.chunk_size = 960  # 60ms at 16kHz
        self.pcm_frame_bytes = self.chunk_size * self.channels * self.sample_width

        # TTS 播放队列（仅入队，不在 WS 线程里 decode/write）
        self.play_queue = []
        self.play_lock = _thread.allocate_lock()
        self.play_started = False
        self.PLAY_PREBUFFER = 6      # ~360ms 启动缓冲
        self.PLAY_QUEUE_MAX = 50
        self._underrun_since = None
        
        # 音频设备句柄
        self.audio_input = None
        self.audio_output = None
        self.audio_buffer = None
        self.dec_dev = None
        self.enc_dev = None
        self.p = None
        self.audio_init = False
        self.in_transform = None
        self.out_transform = None
        self.in_group = 0
        self.pa_pin = None
        # 音频配置
        self.audio_config = {
            'sample_rate': self.sample_rate,
            'channel_count': self.channels,
            'bit_width': self.sample_width * 8,  # 16-bit
            'period_size': self.chunk_size,
            'period_count': 4
        }
        self._init_audio_device()

    def _init_audio_device(self):
        """初始化音频设备"""
        try:
            if self.audio_init:
                return True

            self.p = PyAudio()

            self.dec_dev = opus.Decoder(channels = self.channels, sample_rate = self.sample_rate, frames_per_buffer = self.chunk_size)
            self.enc_dev = opus.Encoder(channels = self.channels,sample_rate = self.sample_rate, bitrate = self.sample_rate,frames_per_buffer = self.chunk_size)

            self.dec_dev.create()
            self.enc_dev.create()

            policy = get_audio_policy() if get_audio_policy else None
            if policy:
                self.audio_input, self.in_transform, self.in_group = open_input(
                    self.p, policy, self.sample_rate, self.chunk_size)
                self.audio_output, self.out_transform, self.pa_pin = open_output(
                    self.p, policy, self.sample_rate, self.channels, self.chunk_size)
                print("音频设备初始化成功 (board policy)")
            else:
                self.in_transform = None
                self.out_transform = None
                self.audio_input = self.p.open(
                    format=paInt16,
                    channels=self.channels,
                    rate=self.sample_rate,
                    input=True,
                    frames_per_buffer=self.chunk_size
                )

                self.audio_output = self.p.open(
                    format=paInt16,
                    channels=self.channels,
                    rate=self.sample_rate,
                    output=True,
                    frames_per_buffer=self.chunk_size
                )
                print("音频设备初始化成功")

            self.audio_init = True
            return True

        except Exception as e:
            print("音频设备初始化异常: %s" % e)
            self.audio_init = False
            return False

    def getVolume(self):
        if not self.audio_output:
            return (0, 0)
        return self.audio_output.volume()
    
    def setVolume(self, volume):
        if not self.audio_output:
            return -1
        return self.audio_output.volume(volume)
             
    def _deinit_audio_device(self):
        """释放音频设备"""
        if not self.audio_init:
            return

        # 先停播/录线程，再关设备，避免 decode/write 踩已销毁句柄
        self.recording = False
        self.playing = False
        self.play_thread_running = False
        with self.play_lock:
            self.play_queue = []
            self.play_started = False
            self._underrun_since = None
        time.sleep(0.08)

        self.audio_init = False
        if self.audio_input:
            try:
                self.audio_input.stop_stream()
                self.audio_input.close()
            except:
                pass
            self.audio_input = None

        if self.audio_output:
            try:
                self.audio_output.stop_stream()
                self.audio_output.close()
            except:
                pass
            self.audio_output = None

        try:
            self.enc_dev.destroy()
        except:
            pass
        try:
            self.dec_dev.destroy()
        except:
            pass
        try:
            close_pa(self.pa_pin)
        except Exception:
            pass
        self.pa_pin = None
            
    def start_recording(self, callback):
        """开始录音"""
        if self.recording:
            print("已经在录音中")
            return -1
            
        if not self._init_audio_device():
            print("音频设备初始化失败，无法开始录音")
            return -1
            
        self.record_callback = callback
        self.recording = True
        
        # 启动录音线程
        self.record_thread = _thread.start_new_thread(self._record_thread, ())
        
        print("开始录音 - 采样率: %dHz, 通道: %d, 位宽: %d-bit" % 
              (self.sample_rate, self.channels, self.sample_width * 8))
        return 0
        
    def stop_recording(self):
        """停止录音"""
        if not self.recording:
            return -1
            
        self.recording = False

        print("停止录音")
        return 0

    def release_audio(self):
        self._deinit_audio_device()
          
    def get_recorde_status(self):
        return self.recording 
       
    def start_playing(self, callback):
        """开始播放"""
        if self.playing:
            print("已经在播放中")
            return -1
            
        if not self._init_audio_device():
            print("音频设备初始化失败，无法开始播放")
            return -1
            
        self.play_callback = callback
        self.playing = True
        
        # 启动播放线程
        self.play_thread = _thread.start_new_thread(self._play_thread, ())
        
        print("开始播放 - 采样率: %dHz, 通道: %d, 位宽: %d-bit" % 
              (self.sample_rate, self.channels, self.sample_width * 8))
        return 0
        
    def stop_playing(self):
        """停止播放"""
        with self.play_lock:
            self.play_queue = []
            self.play_started = False
            self._underrun_since = None
        self.playing = False
        # 不清 play_thread_running：线程可复用；真正释放在 _deinit_audio_device
        print("停止播放")
        return 0
        
    def play_audio_data(self, audio_data):
        """播放音频数据"""
        if not self.audio_output:
            return -1
        # AO write 要求长度精确匹配一帧
        need = self.pcm_frame_bytes
        if self.out_transform:
            audio_data = self.out_transform(audio_data)
            need = need * 2
        n = len(audio_data)
        if n > need:
            audio_data = audio_data[:need]
        elif n < need:
            audio_data = audio_data + bytes(need - n)
        ret = self.audio_output.write(audio_data)
        if ret is not None and ret < 0:
            print("音频播放失败: %d" % ret)
            return -1
        return 0
            
    def _record_thread(self):
        """录音线程"""
        print("录音线程启动")
        
        try:
            while self.recording:
                if self.in_group:
                    audio_data = self.audio_input.read(chn=self.in_group)
                else:
                    audio_data = self.audio_input.read()

                if audio_data and len(audio_data) > 0:
                    if self.in_transform:
                        audio_data = self.in_transform(audio_data)
                    opus_data = self.enc_dev.encode(audio_data)
                    
                    if self.record_callback and opus_data:
                        self.record_callback(opus_data, len(opus_data))
                        
                time.sleep(0.001)
                
        except Exception as e:
            print("录音线程异常: %s" % e)
            
        finally:
            print("录音线程结束")
            
    def _ensure_play_thread(self):
        if self.play_thread_running:
            return
        self.play_thread_running = True
        self.play_thread = _thread.start_new_thread(self._play_thread, ())

    def _play_thread(self):
        """播放线程：出队 -> decode -> write"""
        print("播放线程启动")
        try:
            while self.play_thread_running:
                opus_pkt = None
                with self.play_lock:
                    if not self.play_started:
                        if len(self.play_queue) >= self.PLAY_PREBUFFER:
                            self.play_started = True
                            self._underrun_since = None
                    if self.play_started and self.play_queue:
                        opus_pkt = self.play_queue.pop(0)
                        self._underrun_since = None
                    elif self.play_started and not self.play_queue:
                        # underrun：不立刻要求重新攒满预缓冲，避免句中反复卡顿
                        now = time.time()
                        if self._underrun_since is None:
                            self._underrun_since = now
                        elif now - self._underrun_since > 0.4:
                            # 超时无新包，认为本轮播完
                            self.play_started = False
                            self._underrun_since = None

                if opus_pkt is None:
                    self.playing = False
                    time.sleep(0.002)
                    continue

                self.playing = True
                try:
                    if not self.audio_init or not self.audio_output:
                        break
                    pcm_data = self.dec_dev.decode(opus_pkt)
                    if pcm_data:
                        self.play_audio_data(pcm_data)
                except Exception as e:
                    print("播放解码异常: %s" % e)
        except Exception as e:
            print("播放线程异常: %s" % e)
        finally:
            self.play_thread_running = False
            self.playing = False
            print("播放线程结束")
            
    def play_opus_stream(self, opus_data, size):
        """入队 Opus（非阻塞），由播放线程消费"""
        try:
            if not self._init_audio_device():
                print("音频设备初始化失败，无法开始播放")
                return -1

            self._ensure_play_thread()
            pkt = bytes(opus_data[:size])
            with self.play_lock:
                if len(self.play_queue) >= self.PLAY_QUEUE_MAX:
                    # 丢最旧，保住实时性
                    self.play_queue.pop(0)
                self.play_queue.append(pkt)
            return 0
        except Exception as e:
            print("播放Opus流失败: %s" % e)
            return -1
            
    def get_audio_config(self):
        """获取音频配置"""
        return self.audio_config.copy()
        
    def set_audio_config(self, sample_rate=None, channels=None, chunk_size=None):
        """设置音频配置"""
        if sample_rate:
            self.sample_rate = sample_rate
            self.audio_config['sample_rate'] = sample_rate
            
        if channels:
            self.channels = channels
            self.audio_config['channel_count'] = channels
            
        if chunk_size:
            self.chunk_size = chunk_size
            self.audio_config['period_size'] = chunk_size
            
        print("音频配置已更新: %s" % self.audio_config)

# 音频工具函数
class AudioUtils:
    """音频工具类"""
    
    @staticmethod
    def pcm_to_wav(pcm_data, sample_rate=16000, channels=1, sample_width=2):
        """将PCM数据转换为WAV格式"""
        try:
            import struct
            
            # WAV文件头
            wav_header = bytearray()
            
            # RIFF头
            wav_header.extend(b'RIFF')
            file_size = len(pcm_data) + 36  # 数据大小 + 头部大小
            wav_header.extend(struct.pack('<I', file_size))
            wav_header.extend(b'WAVE')
            
            # fmt块
            wav_header.extend(b'fmt ')
            wav_header.extend(struct.pack('<I', 16))  # fmt块大小
            wav_header.extend(struct.pack('<H', 1))   # PCM格式
            wav_header.extend(struct.pack('<H', channels))
            wav_header.extend(struct.pack('<I', sample_rate))
            byte_rate = sample_rate * channels * sample_width
            wav_header.extend(struct.pack('<I', byte_rate))
            block_align = channels * sample_width
            wav_header.extend(struct.pack('<H', block_align))
            wav_header.extend(struct.pack('<H', sample_width * 8))  # 位深度
            
            # data块
            wav_header.extend(b'data')
            wav_header.extend(struct.pack('<I', len(pcm_data)))
            
            return bytes(wav_header) + pcm_data
            
        except Exception as e:
            print("PCM转WAV失败: %s" % e)
            return pcm_data
            
    @staticmethod
    def validate_audio_data(audio_data, expected_size=None):
        """验证音频数据"""
        if not audio_data or len(audio_data) == 0:
            return False
            
        if expected_size and len(audio_data) != expected_size:
            return False
            
        return True
        
    @staticmethod
    def calculate_audio_duration(audio_data, sample_rate=16000, channels=1, sample_width=2):
        """计算音频时长（秒）"""
        if not audio_data:
            return 0
            
        sample_count = len(audio_data) // (channels * sample_width)
        return sample_count / sample_rate

# 音频测试函数
def test_audio_manager():
    """测试音频管理器"""
    print("=== 音频管理器测试 ===")
    
    audio_mgr = AudioManager()
    
    # 测试录音
    def record_callback(data, size):
        print("收到录音数据: %d 字节" % size)
        
    ret = audio_mgr.start_recording(record_callback)
    if ret == 0:
        print("录音测试开始，等待3秒...")
        time.sleep(3)
        audio_mgr.stop_recording()
        print("录音测试结束")
    else:
        print("录音测试失败")
        
    # 测试播放
    def play_callback(data, size):
        print("收到播放数据: %d 字节" % size)
        
    ret = audio_mgr.start_playing(play_callback)
    if ret == 0:
        print("播放测试开始，等待2秒...")
        time.sleep(2)
        
        # 生成测试音频数据
        import struct
        test_audio = bytearray()
        for i in range(16000):  # 1秒的音频
            sample = int(32767 * 0.5)  # 50%幅度的正弦波
            test_audio.extend(struct.pack('<h', sample))
            
        audio_mgr.play_audio_data(bytes(test_audio))
        time.sleep(1)
        audio_mgr.stop_playing()
        print("播放测试结束")
    else:
        print("播放测试失败")
        
    print("=== 音频管理器测试完成 ===")
