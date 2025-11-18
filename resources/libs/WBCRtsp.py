import time
import os
import multimedia as mm
from mpp import *
from media.vencoder import *
import _thread

class VOWBCFrameGrabber:
    def __init__(self):
        pass

    @classmethod
    def configure(cls, wbc_width,wbc_height):
        cls.wbc_width = wbc_width
        cls.wbc_height = wbc_height

    @classmethod
    def start(cls):
        """启用WBC功能"""
        vo_wbc_attr = k_vo_wbc_attr()
        vo_wbc_attr.blk_cnt = 3

        vo_wbc_attr.dump_size.width = cls.wbc_width
        vo_wbc_attr.dump_size.height = cls.wbc_height

        print(f"VO_WBC initialized, width: {cls.wbc_width}, height: {cls.wbc_height}")

        ret = kd_mpi_vo_set_wbc_attr(vo_wbc_attr)
        if ret != 0:
            raise OSError("set wbc attr failed.")

        ret = kd_mpi_vo_enable_wbc()
        if ret != 0:
            raise OSError("enable wbc failed.")

    @classmethod
    def stop(cls):
        """禁用WBC功能"""
        ret = kd_mpi_vo_disable_wbc()
        if ret != 0:
            raise OSError("disable wbc failed.")

    @classmethod
    def capture_frame(cls, frame):
        """捕获一帧屏幕数据"""
        return kd_mpi_wbc_dump_frame(frame, -1)

    @classmethod
    def free_frame(cls, frame):
        """释放捕获的帧数据"""
        ret = kd_mpi_wbc_dump_release(frame)
        if ret != 0:
            raise OSError("dump release wbc frame failed.")

    @classmethod
    def get_resolution(cls):
        """获取当前配置的分辨率"""
        return cls.wbc_width, cls.wbc_height

class RtspServer:
    def __init__(self,session_name="test",port=8554,video_type = mm.multi_media_type.media_h264,enable_audio=False,width=1280,height=720):
        self.session_name = session_name
        self.video_type = video_type
        self.enable_audio = enable_audio
        self.port = port
        self.rtspserver = mm.rtsp_server()
        self.venc_chn = VENC_CHN_ID_0
        self.start_stream = False
        self.width=ALIGN_UP(width, 16)
        self.height=height
        self.encoder = Encoder()
        self.encoder.SetOutBufs(self.venc_chn, 16, self.width, self.height)

    def start(self):
        if (self.start_stream == True):
            return
        chnAttr = ChnAttrStr(self.encoder.PAYLOAD_TYPE_H264, self.encoder.H264_PROFILE_MAIN, self.width, self.height,bit_rate=2048)
        self.encoder.Create(self.venc_chn, chnAttr)
        self.rtspserver.rtspserver_init(self.port)
        self.rtspserver.rtspserver_createsession(self.session_name,self.video_type,self.enable_audio)
        self.rtspserver.rtspserver_start()
        self.encoder.Start(self.venc_chn)
        self.start_stream = True

    def stop(self):
        if (self.start_stream == False):
            return
        # 等待推流线程退出
        self.start_stream = False
        # 清空编码器缓存
        while True:
            streamData = StreamData()
            ret= self.encoder.GetStream(self.venc_chn, streamData,timeout = 0) # 获取一帧码流
            if ret != 0:
                break
            self.encoder.ReleaseStream(self.venc_chn, streamData) # 释放一帧码流

        # 停止销毁编码器
        self.encoder.Stop(self.venc_chn)
        self.encoder.Destroy(self.venc_chn)
        #停止销毁rtsp 服务器
        self.rtspserver.rtspserver_stop()
        self.rtspserver.rtspserver_deinit()

    def get_rtsp_url(self):
        return self.rtspserver.rtspserver_getrtspurl(self.session_name)

    def send_video_frame(self,frame_info):
        if not self.start_stream:
            print("RTSP server is not started.")
            return -1

        # print("frame_info width:%d,height:%d,pyaddr:0x%x_0x%x" % (frame_info.v_frame.width, frame_info.v_frame.height, frame_info.v_frame.phys_addr[0], frame_info.v_frame.phys_addr[1]))
        #encode frame
        ret = self.encoder.SendFrame(self.venc_chn,frame_info,timeout=-1)
        if ret != 0:
            return -1

        streamData = StreamData()
        ret= self.encoder.GetStream(self.venc_chn, streamData,timeout = -1) # 获取码流
        if ret != 0:
            return -1

        for pack_idx in range(0, streamData.pack_cnt):
            self.rtspserver.rtspserver_sendvideodata_byphyaddr(self.session_name,streamData.phy_addr[pack_idx], streamData.data_size[pack_idx],1000)

        self.encoder.ReleaseStream(self.venc_chn, streamData) # 释放一帧码流
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
        frame_info = k_video_frame_info()  # 初始化帧信息对象
        cls._running = True  # 启动线程时打开开关

        while cls._running:  # 用类属性控制循环
            os.exitpoint()
            # 获取WBC帧数据（捕获帧）
            ret = VOWBCFrameGrabber.capture_frame(frame_info)
            if ret == 0:
                if frame_info.v_frame.width != VOWBCFrameGrabber.wbc_width or frame_info.v_frame.height != VOWBCFrameGrabber.wbc_height :
                    print("@@@@@@@@@@@@ invalid wbc frame")
                    continue
                # 发送帧到RTSP服务器
                cls.rtspserver.send_video_frame(frame_info)
                # 释放帧资源
                VOWBCFrameGrabber.free_frame(frame_info)

            time.sleep(0.01)

        print("_wbc_rtsp thread over")
        cls._runthread_over = True

    @classmethod
    def configure(cls, wbc_width,wbc_height):
        """配置WBC和RTSP服务器参数"""
        VOWBCFrameGrabber.configure(wbc_width,wbc_height)
        # 获取分辨率
        width, height = VOWBCFrameGrabber.get_resolution()
        # 初始化RTSP服务器
        cls.rtspserver = RtspServer(
            session_name="test",
            port=8554,
            video_type=mm.multi_media_type.media_h264,
            enable_audio=False,
            width=width,
            height=height
        )

    @classmethod
    def start(cls):
        """启动WBC、RTSP服务器和推流线程"""
        if not cls._running:  # 避免重复启动线程
            VOWBCFrameGrabber.start()
            cls.rtspserver.start()
            print("RTSP server started:", cls.rtspserver.get_rtsp_url())
            # 启动线程：调用类的内部方法（需用cls引用）
            _thread.start_new_thread(cls._wbc_rtsp, ())  # 注意参数是元组，即使无参数也要加逗号

    @classmethod
    def stop(cls):
        """停止线程、RTSP服务器和WBC功能"""
        cls._running = False  # 关闭线程循环
        while not cls._runthread_over:
            time.sleep(0.1)
        # time.sleep(0.1)  # 等待线程退出
        VOWBCFrameGrabber.stop()  # 停止WBC功能
        cls.rtspserver.stop()  # 停止RTSP服务器
        print("WBC RTSP stopped")