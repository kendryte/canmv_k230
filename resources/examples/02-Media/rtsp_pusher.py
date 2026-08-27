# Description: This example demonstrates how to push encoded video to a remote RTSP server.
#
# Note: You will need an SD card to run this example.
#
# Unlike rtsp_server.py (which hosts the stream), the rtsp_pusher connects as a
# client to an external RTSP server URL and pushes H.264 video to it.
#
# Reference C++ sample: src/rtsmart/examples/mpp/sample_rtsppusher/main.cpp
#
# H.264 video at 512 Kbit/s is the default. Audio is not supported by the pusher.
#
# Flow (mirrors the C++ sample, which drives pushing from the encoder thread via
# OnVEncData; Python has no encoder callback, so we poll GetStream in the main
# thread instead of spawning a worker thread -- this avoids thread-creation
# failures on memory-constrained devices):
#   1. start the encoder so it begins producing SPS/PPS (K_VENC_HEADER)
#   2. on the first HEADER frame: rtsppusher_init() -> rtsppusher_pushvideoheader()
#      -> rtsppusher_open()  (init is deferred until the encoder is producing so
#       the pusher's frame queue does not starve the media pipeline on startup;
#       the pusher must be opened AFTER SPS/PPS is available; every pushed frame
#       is prefixed with this header by the underlying implementation)
#   3. push I/P frames with rtsppusher_pushvideodata(data, size, key_frame, timestamp)

from media.vencoder import *
from media.sensor import *
from media.media import *
import time, os
import multimedia as mm
from libs.Network import connect_network

# Select "default", "lan", "wifi_sta", or "wifi_ap".
NETWORK_TYPE = "wifi_sta"
WLAN_DEVICE = "auto"  # "auto", "usb", "sdio", or "spi"
NETWORK_TIMEOUT = 15
WIFI_SSID = "Test"
WIFI_PASSWORD = "12345678"
# URL of the remote RTSP server that will receive the pushed stream.
# Replace the host with the address of your RTSP server (e.g. EasyDarwin/mediamtx/ZLMediaKit).
RTSP_URL = "rtsp://192.168.1.100:8554/live"
# NOTE: the rtsp_pusher middleware hardcodes AV_CODEC_ID_H264 (see
# RtspPusherImpl.cpp), so it can only push H.264. H.265 is not supported.
VIDEO_TYPE = mm.multi_media_type.media_h264
VIDEO_WIDTH = 1280
VIDEO_HEIGHT = 720
VIDEO_BIT_RATE = 512  # Kbit/s
VIDEO_GOP = 30
VIDEO_FPS = 25
TRANSPORT = "tcp"  # "tcp" or "udp"


class RtspPusher:
    def __init__(self, url=RTSP_URL,
                 video_type=mm.multi_media_type.media_h264,
                 width=1280, height=720, bit_rate=512, gop_len=30,
                 fps=25, transport="tcp"):
        self.url = url                # 远端rtsp server url
        self.video_type = video_type  # 视频类型 (pusher底层仅支持H.264)
        self.width = ALIGN_UP(width, 16)
        self.height = height
        self.bit_rate = bit_rate
        self.gop_len = gop_len
        self.fps = fps
        self.transport = transport
        self.rtsppusher = mm.rtsp_pusher()  # 实例化rtsp pusher
        self.pusher_opened = False   # pusher是否已open(收到首个SPS/PPS后才init+open)
        self.pusher_inited = False   # pusher是否已init
        self.started = False         # 编码是否已启动

        if bit_rate < 100 or bit_rate > 20000:
            raise ValueError("bit_rate must be between 100 and 20000 Kbit/s")
        if transport not in ("tcp", "udp"):
            raise ValueError("transport must be 'tcp' or 'udp'")
        # pusher中间件硬编码 AV_CODEC_ID_H264, 不支持H.265
        if video_type != mm.multi_media_type.media_h264:
            raise ValueError("rtsp_pusher only supports media_h264 (middleware hardcodes H.264)")
        self.payload_type = Encoder.PAYLOAD_TYPE_H264
        self.profile = Encoder.H264_PROFILE_HIGH  # 与 C++ sample (VENC_PROFILE_H264_HIGH) 一致

    def start(self):
        # 仅初始化并启动编码器; pusher init 推迟到收到首个SPS/PPS后(run里),
        # 避免 pusher 64MB 队列分配在编码器启动前压垮 media pipeline
        try:
            self._init_stream()
            self._start_stream()
            self.started = True
        except:
            if hasattr(self, 'encoder'):
                try:
                    self._stop_stream()
                except:
                    pass
            raise

    def run(self, duration=60):
        """在主线程中轮询编码器并推流 duration 秒。

        不创建工作线程: rtsppusher_open() 内部会阻塞做 RTSP 握手 (最长约 5s),
        放在主线程不会影响其他线程; 同时避免在内存吃紧时 _thread.start_new_thread
        以 EAGAIN 失败。

        SPS/PPS 的获取不依赖 stream_type==HEADER: 直接按 H.264 Annex-B 解析 NAL
        (SPS=7/PPS=8 抽出做 header, IDR=5 作关键帧)。这样无论编码器把 SPS/PPS 作
        为独立 pack 还是塞进 IDR 帧, 都能正确开流。
        """
        streamData = StreamData()
        frame_count = 0
        end = time.ticks_add(time.ticks_ms(), duration * 1000)
        while time.ticks_diff(end, time.ticks_ms()) > 0:
            os.exitpoint()
            # 获取一帧码流 (有限超时, 避免永久阻塞)
            if self.encoder.GetStream(streamData, 2000) != 0:
                continue
            # 推流
            for pack_idx in range(0, streamData.pack_cnt):
                stream_data = bytes(uctypes.bytearray_at(streamData.data[pack_idx], streamData.data_size[pack_idx]))
                # 解析 H.264 NAL: 分离 SPS/PPS 与视频数据
                header_data, video_data, is_idr = self._parse_h264_nals(stream_data)
                # 有 SPS/PPS: 先 init pusher (仅一次, 推迟到此处避免内存影响),
                # 再 push header, 再 open pusher
                if header_data and not self.pusher_opened:
                    print("opening pusher (rtsp handshake, may take ~5s)...")
                    if self.rtsppusher.rtsppusher_init(self.width, self.height, self.url,
                                                       self.fps, self.transport) != 0:
                        raise RuntimeError("RTSP pusher init failed")
                    self.pusher_inited = True
                    self.rtsppusher.rtsppusher_pushvideoheader(header_data, len(header_data))
                    if self.rtsppusher.rtsppusher_open() != 0:
                        raise RuntimeError("RTSP pusher open failed, check url: %s" % self.url)
                    self.pusher_opened = True
                    print("rtsp pusher opened: %s" % self.url)
                # 仅在有视频数据且 pusher 已开时推流
                if video_data and self.pusher_opened:
                    timestamp = time.ticks_us()
                    self.rtsppusher.rtsppusher_pushvideodata(video_data, len(video_data),
                                                             1 if is_idr else 0, timestamp)
                    frame_count += 1
                    if frame_count % 300 == 0:
                        print("pushed %d frames" % frame_count)
            # 释放一帧码流
            self.encoder.ReleaseStream(streamData)

    @staticmethod
    def _parse_h264_nals(data):
        """解析 H.264 Annex-B 码流, 分离 SPS/PPS 与视频 NAL。

        返回 (header_bytes, video_bytes, is_idr)。
        header_bytes: SPS/PPS NAL (含 start code), 供 pushvideoheader。
        video_bytes:  视频帧 NAL (含 start code), 供 pushvideodata。
        is_idr:       视频部分是否包含 IDR (NAL type 5)。
        """
        header = bytearray()
        video = bytearray()
        is_idr = False
        sc = b'\x00\x00\x00\x01'
        pos = data.find(sc)
        nal_starts = []
        while pos != -1:
            nal_starts.append(pos)
            pos = data.find(sc, pos + 4)
        # 兼容 3 字节 start code (00 00 01): 4字节start code已覆盖大部分情况
        if not nal_starts:
            sc3 = b'\x00\x00\x01'
            pos = data.find(sc3)
            while pos != -1:
                nal_starts.append(pos)
                pos = data.find(sc3, pos + 3)
        i = 0
        while i < len(nal_starts):
            start = nal_starts[i]
            # NAL header byte 在 start code 之后 (跳过 00 00 00 01 或 00 00 01)
            sc_len = 4 if data[start:start+4] == sc else 3
            hdr_off = start + sc_len
            if hdr_off >= len(data):
                break
            nal_type = data[hdr_off] & 0x1f
            end = nal_starts[i+1] if i+1 < len(nal_starts) else len(data)
            nal = data[start:end]
            if nal_type == 7 or nal_type == 8:  # SPS / PPS
                header += nal
            else:
                video += nal
                if nal_type == 5:  # IDR
                    is_idr = True
            i += 1
        return (bytes(header), bytes(video), is_idr)

    def stop(self):
        if not self.started:
            return
        self.started = False
        # 停止编码
        self._stop_stream()
        # 关闭pusher连接并去初始化 (pusher可能未init, 需判断)
        if self.pusher_opened:
            self.rtsppusher.rtsppusher_close()
            self.pusher_opened = False
        if self.pusher_inited:
            self.rtsppusher.rtsppusher_deinit()
            self.pusher_inited = False

    def _init_stream(self):
        # 初始化sensor
        self.sensor = Sensor()
        self.sensor.reset()
        self.sensor.set_framesize(width=self.width, height=self.height, alignment=12)
        self.sensor.set_pixformat(Sensor.YUV420SP)
        # 实例化video encoder
        self.encoder = Encoder()
        self.encoder.SetOutBufs(8, self.width, self.height)
        # 创建编码器 (不传 src/dst_frame_rate, 用默认30, 避免与sensor实际帧率不匹配导致不出帧)
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
        # 解除绑定camera和venc
        self.link.destroy()
        # 停止编码
        self.encoder.Stop()
        self.encoder.Destroy()


if __name__ == "__main__":
    os.exitpoint(os.EXITPOINT_ENABLE)
    # Connect the selected network interface before opening the RTSP socket.
    nic, network_ip = connect_network(
        NETWORK_TYPE,
        ssid=WIFI_SSID,
        password=WIFI_PASSWORD,
        wlan_device=WLAN_DEVICE,
        timeout=NETWORK_TIMEOUT,
    )
    # 创建rtsp pusher对象
    rtsppusher = RtspPusher(url=RTSP_URL,
                            video_type=VIDEO_TYPE,
                            width=VIDEO_WIDTH,
                            height=VIDEO_HEIGHT,
                            bit_rate=VIDEO_BIT_RATE,
                            gop_len=VIDEO_GOP,
                            fps=VIDEO_FPS,
                            transport=TRANSPORT)
    # 启动编码器 (pusher将在收到首个SPS/PPS时才init+open)
    rtsppusher.start()
    # 打印推流信息
    print("RTSP pusher started: %s (H264, %dx%d, %d Kbit/s, %s)" %
          (RTSP_URL, VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_BIT_RATE, TRANSPORT))
    # 主线程推流60s
    try:
        rtsppusher.run(60)
    finally:
        # 停止rtsp pusher
        rtsppusher.stop()
    print("done")
