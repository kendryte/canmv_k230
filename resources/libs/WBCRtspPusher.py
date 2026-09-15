import time
import os
import multimedia as mm
import _thread

from mpp import *
from media.vencoder import *
from _media import Display


class RtspPusher:
    def __init__(self,
                 url,
                 video_type=mm.multi_media_type.media_h264,
                 width=1280,
                 height=720,
                 bit_rate=512,
                 gop_len=30,
                 fps=30,
                 transport="tcp"):
        self.url = url
        self.video_type = video_type
        self.width = ALIGN_UP(width, 16)
        self.height = height
        self.bit_rate = bit_rate
        self.gop_len = gop_len
        self.fps = fps
        self.transport = transport

        self.rtsppusher = mm.rtsp_pusher()
        self.encoder = Encoder()

        self.start_stream = False
        self.pusher_inited = False
        self.pusher_opened = False

        if bit_rate < 100 or bit_rate > 20000:
            raise ValueError(
                "bit_rate must be between 100 and 20000 Kbit/s"
            )

        if transport not in ("tcp", "udp"):
            raise ValueError(
                "transport must be 'tcp' or 'udp'"
            )

        # rtsp_pusher 底层当前固定使用 H264
        if video_type == mm.multi_media_type.media_h264:
            self.payload_type = Encoder.PAYLOAD_TYPE_H264
            self.profile = Encoder.H264_PROFILE_MAIN
        else:
            raise ValueError(
                "rtsp_pusher only supports media_h264"
            )

    def start(self):
        if self.start_stream:
            return

        encoder_created = False

        try:
            self.encoder.SetOutBufs(16, self.width, self.height)
            chnAttr = ChnAttrStr(
                self.payload_type,
                self.profile,
                self.width,
                self.height,
                bit_rate=self.bit_rate,
                gopLen=self.gop_len
            )
            self.encoder.Create(chnAttr)
            encoder_created = True
            self.encoder.Start()
        except:
            if encoder_created:
                try:
                    self.encoder.Destroy()
                except:
                    pass
            raise
        self.start_stream = True

    def stop(self):
        if not self.start_stream:
            self._stop_pusher()
            return

        self.start_stream = False
        try:
            self.encoder.Stop()
            self.encoder.Destroy()
        except:
            pass
        self._stop_pusher()

    def _stop_pusher(self):
        if self.pusher_opened:
            try:
                self.rtsppusher.rtsppusher_close()
            except:
                pass
            self.pusher_opened = False

        if self.pusher_inited:
            try:
                self.rtsppusher.rtsppusher_deinit()
            except:
                pass

            self.pusher_inited = False

    def send_video_frame(self, frame_info):
        if not self.start_stream:
            print("RTSP pusher is not started.")
            return -1

        ret = self.encoder.SendFrame(frame_info, timeout=-1)
        if ret != 0:
            print("[ENC] SendFrame fail:", ret)
            return -1

        streamData = StreamData()
        ret = self.encoder.GetStream(streamData, timeout=-1)
        if ret != 0:
            print("[ENC] GetStream fail:", ret)
            return -1

        try:
            for pack_idx in range(0, streamData.pack_cnt):
                stream_type = (streamData.stream_type[pack_idx])
                data_size = (streamData.data_size[pack_idx])
                data_addr = (streamData.data[pack_idx])
                if data_addr == 0 or data_size <= 0:
                    continue

                if (stream_type == Encoder.STREAM_TYPE_HEADER):
                    header_data = bytes(uctypes.bytearray_at(data_addr,data_size))
                    self.last_header = header_data

                    ret = (self.rtsppusher.rtsppusher_pushvideoheader(self.last_header,len(self.last_header)))
                    if ret != 0:
                        print("rtsppusher_pushvideoheader failed")
                    continue

                is_idr = (stream_type == Encoder.STREAM_TYPE_I)
                if is_idr:
                    if not hasattr(self, "last_header") or self.last_header is None:
                        print("warning: I frame received before SPS/PPS")
                        continue

                    if not self.pusher_inited:
                        ret = (self.rtsppusher.rtsppusher_init(self.width, self.height, self.url, self.fps, self.transport))
                        if ret != 0:
                            print("RTSP pusher init failed")
                            return -1

                        self.pusher_inited = True


                    if not self.pusher_opened:
                        ret = self.rtsppusher.rtsppusher_open()
                        if ret != 0:
                            print("RTSP pusher open failed:", self.url)
                            return -1
                        self.pusher_opened = True
                        print("RTSP pusher opened:", self.url)

                if not self.pusher_opened:
                    continue

                timestamp = (streamData.pts[pack_idx])
                data = bytes(uctypes.bytearray_at(data_addr,data_size))
                ret = (self.rtsppusher.rtsppusher_pushvideodata(data, len(data), 1 if is_idr else 0, timestamp))
                if ret != 0:
                    print("rtsppusher_pushvideodata failed:", ret)
                    return -1
        finally:
            self.encoder.ReleaseStream(streamData)
        return 0


class WBCRtspPusher:
    _running = False
    _runthread_over = True
    rtsp_pusher = None

    @classmethod
    def configure(cls,
                  rtsp_url,
                  video_type=mm.multi_media_type.media_h264,
                  bit_rate=512,
                  gop_len=30,
                  fps=30,
                  transport="tcp"):

        if not Display.inited():
            raise RuntimeError("start wbc before Display.init()")
        width = Display.width()
        height = Display.height()
        cls.rtsp_pusher = RtspPusher(
            url=rtsp_url,
            video_type=video_type,
            width=width,
            height=height,
            bit_rate=bit_rate,
            gop_len=gop_len,
            fps=fps,
            transport=transport
        )

    @classmethod
    def _wbc_rtsp_pusher(cls):
        try:
            while cls._running:
                os.exitpoint()
                vf = Display.writeback_dump(100)
                if vf:
                    try:
                        cls.rtsp_pusher.send_video_frame(vf)
                    except Exception as e:
                        print("send WBC frame failed:", e)
                time.sleep(0.01)
        finally:
            print("_wbc_rtsp_pusher thread over")
            cls._runthread_over = True

    @classmethod
    def start(cls):
        if cls._running:
            return
        if cls.rtsp_pusher is None:
            raise RuntimeError("please call WBCRtspPusher.configure() first")
        if not Display.writeback(True):
            raise RuntimeError("start wbc failed")

        try:
            cls.rtsp_pusher.start()
            cls._running = True
            cls._runthread_over = False
            _thread.start_new_thread(cls._wbc_rtsp_pusher, ())
        except:
            cls._running = False
            cls._runthread_over = True
            try:
                cls.rtsp_pusher.stop()
            except:
                pass
            Display.writeback(False)
            raise

    @classmethod
    def stop(cls):
        if not cls._running:
            return
        cls._running = False
        while not cls._runthread_over:
            time.sleep(0.1)

        if not Display.writeback(False):
            print("stop wbc failed")

        if cls.rtsp_pusher is not None:
            cls.rtsp_pusher.stop()

        print("WBC RTSP Pusher stopped")
