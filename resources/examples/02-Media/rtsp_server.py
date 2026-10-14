# Description: This example demonstrates how to stream encoded video using the RTSP server.
#
# Note: You will need an SD card to run this example.
#
# H.265 video at 512 Kbit/s is the default. Audio is disabled.

from media.vencoder import *
from media.sensor import *
from media.media import *
import time, os
import _thread
import multimedia as mm
from libs.Network import connect_network, load_network_config

NETWORK_CONFIG = load_network_config({
    "network_type": "wifi_sta",
    "wlan_device": "auto",
    "ssid": "TEST",
    "password": "12345678",
    "timeout": 20,
    "port": 8554,
    "path": "/test",
}, "/sdcard/examples/02-Media/network_config.json")
VIDEO_TYPE = mm.multi_media_type.media_h265
ENABLE_AUDIO = False
VIDEO_WIDTH = 1280
VIDEO_HEIGHT = 720
VIDEO_BIT_RATE = 512  # Kbit/s
VIDEO_GOP = 30

class RtspServer:
    def __init__(self, session_name="test", port=8554,
                 video_type=mm.multi_media_type.media_h265, enable_audio=False,
                 width=1280, height=720, bit_rate=512, gop_len=30):
        self.session_name = session_name # session name
        self.video_type = video_type  # 视频类型264/265
        self.enable_audio = enable_audio # 是否启用音频
        self.port = port   #rtsp 端口号
        self.width = ALIGN_UP(width, 16)
        self.height = height
        self.bit_rate = bit_rate
        self.gop_len = gop_len
        self.rtspserver = mm.rtsp_server() # 实例化rtsp server
        self.start_stream = False #是否启动推流线程
        self.runthread_over = False #推流线程是否结束

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
        if self.rtspserver.rtspserver_init(self.port) != 0:
            raise RuntimeError("RTSP server failed to bind port %d" % self.port)

        try:
            # 创建session
            if self.rtspserver.rtspserver_createsession(self.session_name,self.video_type,self.enable_audio) != 0:
                raise RuntimeError("RTSP session creation failed")
            # 初始化推流
            self._init_stream()
            # 启动rtsp server
            self.rtspserver.rtspserver_start()
            self._start_stream()
        except:
            self.rtspserver.rtspserver_deinit()
            raise

        # 启动推流线程
        self.start_stream = True
        _thread.start_new_thread(self._do_rtsp_stream,())


    def stop(self):
        if (self.start_stream == False):
            return
        # 等待推流线程退出
        self.start_stream = False
        while not self.runthread_over:
            time.sleep(0.1)
        self.runthread_over = False

        # 停止推流
        self._stop_stream()
        self.rtspserver.rtspserver_stop()
        #self.rtspserver.rtspserver_destroysession(self.session_name)
        self.rtspserver.rtspserver_deinit()

    def get_rtsp_url(self, host=None):
        if host is not None:
            return "rtsp://%s:%d/%s" % (host, self.port, self.session_name)
        return self.rtspserver.rtspserver_getrtspurl(self.session_name)

    def _init_stream(self):
        # 初始化sensor
        self.sensor = Sensor()
        self.sensor.reset()
        self.sensor.set_framesize(width=self.width, height=self.height, alignment=12)
        self.sensor.set_pixformat(Sensor.YUV420SP)
        # 实例化video encoder
        self.encoder = Encoder()
        self.encoder.SetOutBufs(8, self.width, self.height)
        # 创建编码器
        chnAttr = ChnAttrStr(self.payload_type, self.profile,
                             self.width, self.height,
                             bit_rate=self.bit_rate, gopLen=self.gop_len)
        self.encoder.Create(chnAttr)
        # 绑定camera和venc
        self.link = MediaManager.link(self.sensor.bind_info()['src'], (VIDEO_ENCODE_MOD_ID, VENC_DEV_ID, self.encoder.chn))

    def _start_stream(self):
        # 开始编码
        self.encoder.Start()
        # 启动camera
        self.sensor.run()

    def _stop_stream(self):
        # 停止camera
        self.sensor.stop()
        # 接绑定camera和venc
        self.link.destroy()
        # 停止编码
        self.encoder.Stop()
        self.encoder.Destroy()

    def _do_rtsp_stream(self):
        try:
            streamData = StreamData()
            while self.start_stream:
                os.exitpoint()
                # 获取一帧码流
                self.encoder.GetStream(streamData)
                # 推流
                for pack_idx in range(0, streamData.pack_cnt):
                    stream_data = bytes(uctypes.bytearray_at(streamData.data[pack_idx], streamData.data_size[pack_idx]))
                    self.rtspserver.rtspserver_sendvideodata(self.session_name,stream_data, streamData.data_size[pack_idx],1000)
                    #print("stream size: ", streamData.data_size[pack_idx], "stream type: ", streamData.stream_type[pack_idx])
                # 释放一帧码流
                self.encoder.ReleaseStream(streamData)

        except KeyboardInterrupt as e:
            print("user stop: ", e)
        except BaseException as e:
            import sys
            sys.print_exception(e)
            raise
        finally:
            self.runthread_over = True
            # 停止rtsp server
            self.stop()

        self.runthread_over = True

if __name__ == "__main__":
    os.exitpoint(os.EXITPOINT_ENABLE)
    # Connect the selected network interface before opening the RTSP socket.
    nic, network_ip = connect_network(
        NETWORK_CONFIG["network_type"],
        ssid=NETWORK_CONFIG.get("ssid"),
        password=NETWORK_CONFIG.get("password"),
        wlan_device=NETWORK_CONFIG.get("wlan_device", "auto"),
        timeout=NETWORK_CONFIG.get("timeout", 20),
        ip_config=NETWORK_CONFIG.get("ip_config"),
    )
    # 创建rtsp server对象
    rtspserver = RtspServer(session_name=NETWORK_CONFIG.get("path", "/test").strip("/"),
                            port=int(NETWORK_CONFIG["port"]),
                            video_type=VIDEO_TYPE,
                            enable_audio=ENABLE_AUDIO,
                            width=VIDEO_WIDTH,
                            height=VIDEO_HEIGHT,
                            bit_rate=VIDEO_BIT_RATE,
                            gop_len=VIDEO_GOP)
    # 启动rtsp server
    rtspserver.start()
    # 打印rtsp url
    codec_name = "H265" if VIDEO_TYPE == mm.multi_media_type.media_h265 else "H264"
    audio_state = "enabled" if ENABLE_AUDIO else "disabled"
    print("RTSP server started: %s (%s, %d Kbit/s, audio %s)" %
          (rtspserver.get_rtsp_url(network_ip), codec_name,
           VIDEO_BIT_RATE, audio_state))
    try:
        # 推流60s
        time.sleep(60)
    except KeyboardInterrupt as e:
        print("user stop: ", e)
    finally:
        # 停止rtsp server
        rtspserver.stop()
    print("done")
