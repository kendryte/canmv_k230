import time
import os
import multimedia as mm
from mpp import *
from media.vencoder import *
import _thread

from _media import Display

class RtspServer:
    def __init__(self, session_name="test", port=8554,
                 video_type=mm.multi_media_type.media_h265, enable_audio=False,
                 width=1280, height=720, bit_rate=512, gop_len=30):
        self.session_name = session_name
        self.video_type = video_type
        self.enable_audio = enable_audio
        self.port = port
        self.rtspserver = mm.rtsp_server()
        self.start_stream = False
        self.width=ALIGN_UP(width, 16)
        self.height=height
        self.bit_rate=bit_rate
        self.gop_len=gop_len
        self.encoder = Encoder()

        if bit_rate < 100 or bit_rate > 20000:
            raise ValueError("bit_rate must be between 100 and 20000 Kbit/s")
        if video_type == mm.multi_media_type.media_h265:
            self.payload_type = Encoder.PAYLOAD_TYPE_H265
            self.profile = Encoder.H265_PROFILE_MAIN
        elif video_type == mm.multi_media_type.media_h264:
            self.payload_type = Encoder.PAYLOAD_TYPE_H264
            self.profile = Encoder.H264_PROFILE_MAIN
        else:
            raise ValueError("video_type must be media_h265 or media_h264")

    def start(self):
        if (self.start_stream == True):
            return
        encoder_created = False
        server_initialized = False
        try:
            self.encoder.SetOutBufs(16, self.width, self.height)
            chnAttr = ChnAttrStr(self.payload_type, self.profile,
                                 self.width, self.height,
                                 bit_rate=self.bit_rate, gopLen=self.gop_len)
            self.encoder.Create(chnAttr)
            encoder_created = True

            if self.rtspserver.rtspserver_init(self.port) != 0:
                raise RuntimeError("RTSP server failed to bind port %d" % self.port)
            server_initialized = True
            if self.rtspserver.rtspserver_createsession(self.session_name,self.video_type,self.enable_audio) != 0:
                raise RuntimeError("RTSP session creation failed")

            self.rtspserver.rtspserver_start()
            self.encoder.Start()
        except:
            if server_initialized:
                self.rtspserver.rtspserver_deinit()
            if encoder_created:
                self.encoder.Destroy()
            raise
        self.start_stream = True

    def stop(self):
        if (self.start_stream == False):
            return
        # 等待推流线程退出
        self.start_stream = False
        # 清空编码器缓存
        while True:
            streamData = StreamData()
            ret= self.encoder.GetStream(streamData, timeout = 0) # 获取一帧码流
            if ret != 0:
                break
            self.encoder.ReleaseStream(streamData) # 释放一帧码流

        # 停止销毁编码器
        self.encoder.Stop()
        self.encoder.Destroy()
        #停止销毁rtsp 服务器
        self.rtspserver.rtspserver_stop()
        self.rtspserver.rtspserver_deinit()

    def get_rtsp_url(self, host=None):
        if host is not None:
            return "rtsp://%s:%d/%s" % (host, self.port, self.session_name)
        return self.rtspserver.rtspserver_getrtspurl(self.session_name)

    def send_video_frame(self,frame_info):
        if not self.start_stream:
            print("RTSP server is not started.")
            return -1

        # print("frame_info width:%d,height:%d,pyaddr:0x%x_0x%x" % (frame_info.v_frame.width, frame_info.v_frame.height, frame_info.v_frame.phys_addr[0], frame_info.v_frame.phys_addr[1]))
        #encode frame
        ret = self.encoder.SendFrame(frame_info, timeout=-1)
        if ret != 0:
            return -1

        streamData = StreamData()
        ret= self.encoder.GetStream(streamData, timeout = -1) # 获取码流
        if ret != 0:
            return -1

        for pack_idx in range(0, streamData.pack_cnt):
            self.rtspserver.rtspserver_sendvideodata_byphyaddr(self.session_name,streamData.phy_addr[pack_idx], streamData.data_size[pack_idx],1000)

        self.encoder.ReleaseStream(streamData) # 释放一帧码流
        return 0

class WBCRtsp:
    # 类属性：用于控制线程循环的开关
    _running = False
    _runthread_over = False

    def __init__(self):
        pass

    @classmethod
    def _wbc_rtsp(cls):
        """内部线程函数：循环获取WBC帧并发送到RTSP服务器"""
        while cls._running:  # 用类属性控制循环
            os.exitpoint()

            vf = Display.writeback_dump(100)
            if vf:
                cls.rtspserver.send_video_frame(vf)

            time.sleep(0.01)

        print("_wbc_rtsp thread over")
        cls._runthread_over = True

    @classmethod
    def configure(cls, wbc_width, wbc_height,
                  video_type=mm.multi_media_type.media_h265,
                  bit_rate=512, gop_len=30, enable_audio=False,
                  session_name="test", port=8554):
        if not Display.inited():
            raise RuntimeError("start wbc before Display.init()")

        width = Display.width()
        height = Display.height()

        # 初始化RTSP服务器
        cls.rtspserver = RtspServer(
            session_name=session_name,
            port=port,
            video_type=video_type,
            enable_audio=enable_audio,
            width=width,
            height=height,
            bit_rate=bit_rate,
            gop_len=gop_len
        )

    @classmethod
    def start(cls, network_ip=None):
        """启动WBC、RTSP服务器和推流线程"""
        if not cls._running:  # 避免重复启动线程
            if not Display.writeback(True):
                raise RuntimeError("start wbc failed")

            try:
                cls.rtspserver.start()
                print("RTSP server started:", cls.rtspserver.get_rtsp_url(network_ip))
                cls._running = True
                cls._runthread_over = False
                # 启动线程：调用类的内部方法（需用cls引用）
                _thread.start_new_thread(cls._wbc_rtsp, ())  # 注意参数是元组，即使无参数也要加逗号
            except:
                cls._running = False
                cls.rtspserver.stop()
                Display.writeback(False)
                raise

    @classmethod
    def stop(cls):
        """停止线程、RTSP服务器和WBC功能"""
        cls._running = False  # 关闭线程循环

        while not cls._runthread_over:
            time.sleep(0.1)

        if not Display.writeback(False):
            print("stop wbc failed")
            
        cls.rtspserver.stop()  # 停止RTSP服务器
        print("WBC RTSP stopped")
