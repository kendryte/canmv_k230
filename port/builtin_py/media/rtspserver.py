from media.vencoder import *
from media.sensor import *
from media.media import *
import time, os
import _thread
import multimedia as mm
from time import *

class RtspServer:
    def __init__(self,session_name="test",port=8554,video_type = mm.multi_media_type.media_h264,enable_audio=False):
        self.session_name = session_name
        self.video_type = video_type
        self.enable_audio = enable_audio
        self.port = port
        self.rtspserver = mm.rtsp_server()
        self.venc_chn = VENC_CHN_ID_0
        self.start_stream = False
        self.runthread_over = False

    def start(self):
        self._init_stream()
        self.rtspserver.rtspserver_init(self.port)
        self.rtspserver.rtspserver_createsession(self.session_name,self.video_type,self.enable_audio)
        self.rtspserver.rtspserver_start()
        self._start_stream()

        self.start_stream = True
        _thread.start_new_thread(self._do_rtsp_stream,())


    def stop(self):
        self.start_stream = False
        while not self.runthread_over:
            sleep(0.1)
        self.runthread_over = False

        self._stop_stream()
        self.rtspserver.rtspserver_stop()
        #self.rtspserver.rtspserver_destroysession(self.session_name)
        self.rtspserver.rtspserver_deinit()

    def get_rtsp_url(self):
        return self.rtspserver.rtspserver_getrtspurl(self.session_name)

    def _init_stream(self):
        width = 1280
        height = 720
        width = ALIGN_UP(width, 16)
        self.sensor = Sensor()
        self.sensor.reset()
        self.sensor.set_framesize(width = width, height = height, alignment=12)
        self.sensor.set_pixformat(Sensor.YUV420SP)
        self.encoder = Encoder()
        self.encoder.SetOutBufs(self.venc_chn, 15, width, height)
        self.link = MediaManager.link(self.sensor.bind_info()['src'], (VIDEO_ENCODE_MOD_ID, VENC_DEV_ID, self.venc_chn))
        chnAttr = ChnAttrStr(self.encoder.PAYLOAD_TYPE_H264, self.encoder.H264_PROFILE_MAIN, width, height,bit_rate=1024)
        self.encoder.Create(self.venc_chn, chnAttr)

    def _start_stream(self):
        self.encoder.Start(self.venc_chn)
        self.sensor.run()

    def _stop_stream(self):
        self.sensor.stop()
        del self.link
        self.encoder.Stop(self.venc_chn)
        self.encoder.Destroy(self.venc_chn)

    def _do_rtsp_stream(self):
        try:
            streamData = StreamData()
            while self.start_stream:
                os.exitpoint()
                self.encoder.GetStream(self.venc_chn, streamData) # 获取一帧码流

                for pack_idx in range(0, streamData.pack_cnt):
                    stream_data = bytes(uctypes.bytearray_at(streamData.data[pack_idx], streamData.data_size[pack_idx]))
                    self.rtspserver.rtspserver_sendvideodata(self.session_name,stream_data, streamData.data_size[pack_idx],1000)
                    #print("stream size: ", streamData.data_size[pack_idx], "stream type: ", streamData.stream_type[pack_idx])

                self.encoder.ReleaseStream(self.venc_chn, streamData) # 释放一帧码流

        except KeyboardInterrupt as e:
            print("user stop: ", e)
        except BaseException as e:
            sys.print_exception(e)

        self.runthread_over = True
        print("_do_rtsp_stream over")
