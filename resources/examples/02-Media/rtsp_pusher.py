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
#   2. on the first HEADER pack: rtsppusher_init() (deferred until the encoder is
#      producing so the pusher's frame queue does not starve the media pipeline on
#      startup); cache the SPS/PPS bytes, do not open yet
#   3. on every I frame: rtsppusher_pushvideoheader() with the latest cached SPS/PPS,
#      then (first time only) rtsppusher_open() -- pushing the header again before
#      each I frame keeps it in sync in case the encoder re-emits SPS/PPS mid-stream;
#      the underlying implementation prefixes this header to every subsequently
#      pushed frame (I and P) until it is updated again
#   4. push I/P frames with rtsppusher_pushvideodata(data, size, key_frame, timestamp)

from media.vencoder import *
from media.sensor import *
from media.media import *
import time, os
import multimedia as mm
from libs.Network import connect_network, load_network_config

NETWORK_CONFIG = load_network_config({
    "network_type": "wifi_sta",
    "wlan_device": "auto",
    "ssid": "TEST",
    "password": "12345678",
    "timeout": 20,
    "host": "192.168.1.100",
    "port": 8554,
    "path": "/live/test",
}, "/sdcard/examples/02-Media/network_config.json")
RTSP_URL = "rtsp://%s:%d/%s" % (
    NETWORK_CONFIG["host"],
    int(NETWORK_CONFIG["port"]),
    NETWORK_CONFIG.get("path", "/live/test").strip("/"),
)
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
        """
        streamData = StreamData()
        frame_count = 0
        last_header = None
        dropped_idr_count = 0
        end = time.ticks_add(time.ticks_ms(), duration * 1000)
        while time.ticks_diff(end, time.ticks_ms()) > 0:
            os.exitpoint()
            # 获取一帧码流 (有限超时, 避免永久阻塞)
            if self.encoder.GetStream(streamData, 2000) != 0:
                continue
            # 推流
            for pack_idx in range(0, streamData.pack_cnt):
                stream_type = streamData.stream_type[pack_idx]
                pack_data = bytes(uctypes.bytearray_at(streamData.data[pack_idx], streamData.data_size[pack_idx]))

                if stream_type == Encoder.STREAM_TYPE_HEADER:
                    last_header = pack_data
                    if not self.pusher_inited:
                        if self.rtsppusher.rtsppusher_init(self.width, self.height, self.url,
                                                           self.fps, self.transport) != 0:
                            raise RuntimeError("RTSP pusher init failed")
                        self.pusher_inited = True
                    continue

                is_idr = (stream_type == Encoder.STREAM_TYPE_I)
                if is_idr:
                    if last_header is None:
                        # 正常启动时序下 HEADER 会先于首个 I 帧到达, 这里只在异常时序下触发
                        dropped_idr_count += 1
                        if dropped_idr_count == 1 or dropped_idr_count % 30 == 0:
                            print("warning: I frame dropped, no SPS/PPS header yet (%d dropped)" % dropped_idr_count)
                        continue
                    # header 紧跟 I 帧一起下发, 保证二者背靠背; pushvideoheader 只是更新
                    # 底层缓存, open 前后调用均安全, 且会被自动前缀到之后每一帧(含P帧)
                    self.rtsppusher.rtsppusher_pushvideoheader(last_header, len(last_header))
                    if not self.pusher_opened:
                        print("opening pusher (rtsp handshake, may take ~5s)...")
                        if self.rtsppusher.rtsppusher_open() != 0:
                            raise RuntimeError("RTSP pusher open failed, check url: %s" % self.url)
                        self.pusher_opened = True
                        print("rtsp pusher opened: %s" % self.url)

                # 仅在有视频数据且 pusher 已开时推流
                if self.pusher_opened:
                    timestamp = streamData.pts[pack_idx]
                    self.rtsppusher.rtsppusher_pushvideodata(pack_data, len(pack_data),
                                                             1 if is_idr else 0, timestamp)
                    frame_count += 1
                    if frame_count % 300 == 0:
                        print("pushed %d frames" % frame_count)
            # 释放一帧码流
            self.encoder.ReleaseStream(streamData)

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
        NETWORK_CONFIG["network_type"],
        ssid=NETWORK_CONFIG.get("ssid"),
        password=NETWORK_CONFIG.get("password"),
        wlan_device=NETWORK_CONFIG.get("wlan_device", "auto"),
        timeout=NETWORK_CONFIG.get("timeout", 20),
        ip_config=NETWORK_CONFIG.get("ip_config"),
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
