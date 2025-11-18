from media.vencoder import *
from media.sensor import *
from media.media import *
from mpp.mp4_format import *
from mpp.mp4_format_struct import *
from mpp.aenc import *
from media.pyaudio import *
import media.g711 as g711
from mpp.payload_struct import *
import uctypes
import time


class MuxerCfgStr:
    def __init__(self):
        self.file_name = 0
        self.video_payload_type = 0
        self.pic_width = 0
        self.pic_height = 0
        self.audio_payload_type = 0
        self.video_start_timestamp = 0
        self.fmp4_flag = 0

class Mp4CfgStr:
    def __init__(self, type):
        self.type = type
        self.muxerCfg = MuxerCfgStr()

    def SetMuxerCfg(self, fileName, videoPayloadType, picWidth, picHeight, audioPayloadType, fmp4Flag = 0):
        self.muxerCfg.file_name = fileName
        self.muxerCfg.video_payload_type = videoPayloadType
        self.muxerCfg.pic_width = picWidth
        self.muxerCfg.pic_height = picHeight
        self.muxerCfg.audio_payload_type = audioPayloadType
        self.muxerCfg.fmp4_flag = fmp4Flag

    def SetDemuxerCfg(self, fileName):
        pass


class Mp4Container:
    MP4_CONFIG_TYPE_MUXER = K_MP4_CONFIG_MUXER
    MP4_CONFIG_TYPE_DEMUXER = K_MP4_CONFIG_DEMUXER

    MP4_STREAM_TYPE_VIDEO = K_MP4_STREAM_VIDEO
    MP4_STREAM_TYPE_AUDIO = K_MP4_STREAM_AUDIO

    MP4_CODEC_ID_H264 = K_MP4_CODEC_ID_H264
    MP4_CODEC_ID_H265 = K_MP4_CODEC_ID_H265
    MP4_CODEC_ID_G711A = K_MP4_CODEC_ID_G711A
    MP4_CODEC_ID_G711U = K_MP4_CODEC_ID_G711U

    def __init__(self,sensor_csi_id = -1):
        if sensor_csi_id in [0, 1, 2]:
            self.sensor = Sensor(id=sensor_csi_id)
        else:
            self.sensor = Sensor()

        self.sensor.reset()
        self.venc = Encoder()
        self.stream_data = StreamData()
        self.mp4_handle = 0
        self.mp4_video_track_handle = 0
        self.mp4_audio_track_handle = 0
        self.video_payload_type = 0
        self.audio_payload_type = 0
        self.get_idr = 0
        self.save_idr = 0
        self.idr_size = 0
        self.idr_pts = 0
        self.count = 0
        self.audio_timestamp = 0

    def Create(self, mp4Cfg):
        if mp4Cfg.type == K_MP4_CONFIG_MUXER:
            # set chn0 output size
            self.sensor.set_framesize(width = mp4Cfg.muxerCfg.pic_width, height = mp4Cfg.muxerCfg.pic_height, alignment=12)
            # set chn0 output format
            self.sensor.set_pixformat(Sensor.YUV420SP)

            self.venc.SetOutBufs(VENC_CHN_ID_0, 15, mp4Cfg.muxerCfg.pic_width, mp4Cfg.muxerCfg.pic_height)
            # audio init
            FORMAT = paInt16
            CHANNELS = 1
            RATE = 8000
            CHUNK = RATE//25
            self.pyaudio = PyAudio()
            self.pyaudio.initialize(CHUNK)

            if mp4Cfg.muxerCfg.audio_payload_type == self.MP4_CODEC_ID_G711U:
                self.aenc = g711.Encoder(K_PT_G711U,CHUNK)
            elif mp4Cfg.muxerCfg.audio_payload_type == self.MP4_CODEC_ID_G711A:
                self.aenc = g711.Encoder(K_PT_G711A,CHUNK)

            # 绑定camera和venc
            self.link = MediaManager.link(self.sensor.bind_info()['src'], (VIDEO_ENCODE_MOD_ID, VENC_DEV_ID, VENC_CHN_ID_0))

            self.video_payload_type = mp4Cfg.muxerCfg.video_payload_type
            self.audio_payload_type = mp4Cfg.muxerCfg.audio_payload_type

            profile = self.venc.H265_PROFILE_MAIN
            payload_type = self.venc.PAYLOAD_TYPE_H265
            if mp4Cfg.muxerCfg.video_payload_type == self.MP4_CODEC_ID_H265:
                profile = self.venc.H265_PROFILE_MAIN
                payload_type = self.venc.PAYLOAD_TYPE_H265
            elif mp4Cfg.muxerCfg.video_payload_type == self.MP4_CODEC_ID_H264:
                profile = self.venc.H264_PROFILE_MAIN
                payload_type = self.venc.PAYLOAD_TYPE_H264

            width = ALIGN_UP(mp4Cfg.muxerCfg.pic_width, 16)
            chnAttr = ChnAttrStr(payload_type, profile, width, mp4Cfg.muxerCfg.pic_height)
            self.save_idr = bytearray(width * mp4Cfg.muxerCfg.pic_height * 3 // 4)
            self.venc.Create(VENC_CHN_ID_0, chnAttr)

            self.aenc.create()
            self.audio_stream = self.pyaudio.open(format=FORMAT,
                            channels=CHANNELS,
                            rate=RATE,
                            input=True,
                            frames_per_buffer=CHUNK)

            mp4_cfg = k_mp4_config_s()
            mp4_cfg.config_type = mp4Cfg.type

            mp4_cfg.muxer_config.file_name[:] = bytes(mp4Cfg.muxerCfg.file_name, 'utf-8')
            mp4_cfg.muxer_config.fmp4_flag = mp4Cfg.muxerCfg.fmp4_flag

            handle = k_u64_ptr()
            ret = kd_mp4_create(handle, mp4_cfg)
            if ret:
                raise OSError("Mp4Container, kd_mp4_create failed.")

            self.mp4_handle = handle.value
            video_track_info = k_mp4_track_info_s()
            video_track_info.track_type = K_MP4_STREAM_VIDEO
            video_track_info.time_scale = 1000
            video_track_info.video_info.width = mp4Cfg.muxerCfg.pic_width
            video_track_info.video_info.height = mp4Cfg.muxerCfg.pic_height
            video_track_info.video_info.codec_id = mp4Cfg.muxerCfg.video_payload_type
            video_track_handle = k_u64_ptr()
            ret = kd_mp4_create_track(self.mp4_handle, video_track_handle, video_track_info)
            if ret:
                raise OSError("Mp4Container, kd_mp4_create_track failed.")

            self.mp4_video_track_handle = video_track_handle.value

            audio_track_info = k_mp4_track_info_s()
            audio_track_info.track_type = K_MP4_STREAM_AUDIO
            audio_track_info.time_scale = 1000
            audio_track_info.audio_info.channels = CHANNELS
            if mp4Cfg.muxerCfg.audio_payload_type == self.MP4_CODEC_ID_G711U:
                audio_track_info.audio_info.codec_id = K_MP4_CODEC_ID_G711U
            elif mp4Cfg.muxerCfg.audio_payload_type == self.MP4_CODEC_ID_G711A:
                audio_track_info.audio_info.codec_id = K_MP4_CODEC_ID_G711A
            audio_track_info.audio_info.sample_rate = RATE
            audio_track_info.audio_info.bit_per_sample = 16
            audio_track_handle = k_u64_ptr()
            ret = kd_mp4_create_track(self.mp4_handle, audio_track_handle, audio_track_info)
            if ret:
                raise OSError("Mp4Container, kd_mp4_create_track failed.")
            self.mp4_audio_track_handle = audio_track_handle.value

    def Start(self):
        self.venc.Start(VENC_CHN_ID_0)
        self.sensor.run()

    def Process(self):
        frame_data = k_mp4_frame_data_s()
        self.venc.GetStream(VENC_CHN_ID_0, self.stream_data)

        for pack_idx in range(0, self.stream_data.pack_cnt):
            if self.get_idr == 0:
                self.save_idr[self.idr_size:self.idr_size+self.stream_data.data_size[pack_idx]] = uctypes.bytearray_at(self.stream_data.data[pack_idx], self.stream_data.data_size[pack_idx])
                self.idr_size += self.stream_data.data_size[pack_idx]
                self.idr_pts = self.stream_data.pts[pack_idx]
            elif self.get_idr == 1:
                frame_data.codec_id = self.video_payload_type
                frame_data.data = self.stream_data.data[pack_idx]
                frame_data.data_length = self.stream_data.data_size[pack_idx]
                frame_data.time_stamp = self.stream_data.pts[pack_idx]

        if self.get_idr == 0:
            self.count += 1
            if self.count == 2:
                frame_data.codec_id = self.video_payload_type
                frame_data.data = uctypes.addressof(self.save_idr)
                frame_data.data_length = self.idr_size
                frame_data.time_stamp = self.idr_pts
                self.get_idr = 1
                self.video_start_timestamp = frame_data.time_stamp
            else:
                self.venc.ReleaseStream(VENC_CHN_ID_0, self.stream_data)
                return

        frame_data.time_stamp = frame_data.time_stamp - self.video_start_timestamp
        #print("video timestamp:",frame_data.time_stamp)
        ret = kd_mp4_write_frame(self.mp4_handle, self.mp4_video_track_handle, frame_data)
        if ret:
            raise OSError("Mp4Container, kd_mp4_write_frame failed.")

        self.venc.ReleaseStream(VENC_CHN_ID_0, self.stream_data)

        audio_data = self.audio_stream.read(block=False)
        if (audio_data):
            enc_data = self.aenc.encode(audio_data)
            frame_data.codec_id = self.audio_payload_type
            frame_data.data = uctypes.addressof(enc_data)
            frame_data.data_length = len(enc_data)
            frame_data.time_stamp = self.audio_timestamp
            self.audio_timestamp += 40*1000
            #print("audio timestamp:",frame_data.time_stamp)
            ret = kd_mp4_write_frame(self.mp4_handle, self.mp4_audio_track_handle, frame_data)
            if ret:
                raise OSError("Mp4Container, write audio stream failed.")

    def Stop(self):
        # 停止camera
        self.sensor.stop()

        # 销毁camera和venc的绑定
        del self.link
        self.venc.Stop(VENC_CHN_ID_0)
        self.audio_stream.stop_stream()
        self.audio_stream.close()
        self.pyaudio.terminate()
        self.aenc.destroy()

    def Destroy(self):
        ret = kd_mp4_destroy_tracks(self.mp4_handle)
        if ret:
            raise OSError("Mp4Container, kd_mp4_destroy_tracks failed.")

        ret = kd_mp4_destroy(self.mp4_handle)
        if ret:
            raise OSError("Mp4Container, kd_mp4_destroy failed.")

        self.venc.Destroy(VENC_CHN_ID_0)
