# MP4 Demuxer Example
#
# This script demuxes an MP4 file, extracting video and audio streams.
# Supported video codecs: H.264, H.265
# Supported audio codecs: G.711A, G.711U

from media.media import *
from mpp.mp4_format import *
from mpp.mp4_format_struct import *
from media.pyaudio import *
import media.g711 as g711
from mpp.payload_struct import *
import media.vdecoder as vdecoder
from media.display import *
import uctypes
import time
import _thread
import os
from nonai2d import CSC
from libs.AIBase import AIBase
import ulab.numpy as np
from libs.AI2D import Ai2d
import nncase_runtime as nn
from libs.Utils import *
import os,sys,ujson,gc,math
from media.media import *
import image
import aidemo

csc = None

clock = time.clock()
display_type = Display.LT9611
sub_thread_flag = True
main_thread_flag = True
face_det = None

class FaceDetectionApp(AIBase):
    def __init__(self, kmodel_path, model_input_size, confidence_threshold=0.5, nms_threshold=0.2,top_k=50, rgb888p_size=[224,224], display_size=[1920,1080], debug_mode=0):
        super().__init__(kmodel_path, model_input_size, rgb888p_size, debug_mode)
        self.kmodel_path = kmodel_path  # kmodel path
        self.model_input_size = model_input_size  # model input size
        self.confidence_threshold = confidence_threshold  # confidence threshold
        self.nms_threshold = nms_threshold  # nms threshold
        self.top_k=top_k # topk boxes
        self.rgb888p_size = [ALIGN_UP(rgb888p_size[0], 16), rgb888p_size[1]]
        self.display_size = [ALIGN_UP(display_size[0], 16), display_size[1]]
        self.scale=1.0 # process ratio
        self.debug_mode = debug_mode  # debug mode
        self.ai2d = Ai2d(debug_mode)  # init ai2d for preprocess
        #self.ai2d.set_ai2d_dtype(nn.ai2d_format.RGB_packed, nn.ai2d_format.NCHW_FMT, np.uint8, np.uint8)
        self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT, nn.ai2d_format.NCHW_FMT, np.uint8, np.uint8)

    # preprocess with pad and resize (letterbox)
    def config_preprocess(self, input_image_size=None):
        with ScopedTiming("set preprocess config", self.debug_mode > 0):
            ai2d_input_size = input_image_size if input_image_size else self.rgb888p_size
            top, bottom, left, right, self.scale = letterbox_pad_param(self.rgb888p_size,self.model_input_size)
            self.ai2d.pad([0, 0, 0, 0, top, bottom, left, right], 0, [114, 114, 114])
            self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
            #self.ai2d.build([1,ai2d_input_size[1],ai2d_input_size[0],3],[1,3,self.model_input_size[1],self.model_input_size[0]])
            self.ai2d.build([1,3,ai2d_input_size[1],ai2d_input_size[0]],[1,3,self.model_input_size[1],self.model_input_size[0]])

    # postprocess
    def postprocess(self, results):
        with ScopedTiming("postprocess", self.debug_mode > 0):
            strides=[8,16,32]
            dets_out=aidemo.yunet_postprocess(results,[self.rgb888p_size[1],self.rgb888p_size[0]],[self.model_input_size[1],self.model_input_size[0]],[self.display_size[1],self.display_size[0]],strides,self.confidence_threshold,self.nms_threshold,self.top_k)
            return dets_out

    # 绘制结果
    def draw_result(self,img,dets):
        with ScopedTiming("display_draw",self.debug_mode >0):
            if dets:
                for i in range(len(dets[0])):
                    x, y, w, h = map(lambda x: int(round(x, 0)), dets[0][i])
                    img.draw_rectangle(x,y, w, h, color=(0,255,0),thickness=4)

def demuxer_mp4(filename):
    global csc, display_type, sub_thread_flag, face_det, main_thread_flag
    mp4_cfg = k_mp4_config_s()
    video_info = k_mp4_video_info_s()
    video_track = False
    audio_info = k_mp4_audio_info_s()
    audio_track = False
    mp4_handle = k_u64_ptr()

    mp4_cfg.config_type = K_MP4_CONFIG_DEMUXER
    mp4_cfg.muxer_config.file_name[:] = bytes(filename, 'utf-8')
    mp4_cfg.muxer_config.fmp4_flag = 0

    ret = kd_mp4_create(mp4_handle, mp4_cfg)
    if ret:
        raise OSError("kd_mp4_create failed:",filename)

    file_info = k_mp4_file_info_s()
    kd_mp4_get_file_info(mp4_handle.value, file_info)
    #print("=====file_info: track_num:",file_info.track_num,"duration:",file_info.duration)

    for i in range(file_info.track_num):
        track_info = k_mp4_track_info_s()
        ret = kd_mp4_get_track_by_index(mp4_handle.value, i, track_info)
        if (ret < 0):
            raise ValueError("kd_mp4_get_track_by_index failed")

        if (track_info.track_type == K_MP4_STREAM_VIDEO):
            if (track_info.video_info.codec_id == K_MP4_CODEC_ID_H264 or track_info.video_info.codec_id == K_MP4_CODEC_ID_H265):
                video_track = True
                video_info = track_info.video_info
                print("    codec_id: ", video_info.codec_id)
                print("    track_id: ", video_info.track_id)
                print("    width: ", video_info.width)
                print("    height: ", video_info.height)
            else:
                print("video not support codecid:",track_info.video_info.codec_id)
        elif (track_info.track_type == K_MP4_STREAM_AUDIO):
            if (track_info.audio_info.codec_id == K_MP4_CODEC_ID_G711A or track_info.audio_info.codec_id == K_MP4_CODEC_ID_G711U):
                audio_track = True
                audio_info = track_info.audio_info
                print("    codec_id: ", audio_info.codec_id)
                print("    track_id: ", audio_info.track_id)
                print("    channels: ", audio_info.channels)
                print("    sample_rate: ", audio_info.sample_rate)
                print("    bit_per_sample: ", audio_info.bit_per_sample)
                #audio_info.channels = 2
            else:
                print("audio not support codecid:",track_info.audio_info.codec_id)

    if (video_track == False):
        raise ValueError("video track not found")

    if (track_info.video_info.codec_id == K_MP4_CODEC_ID_H264):
        vdec_payload_type = K_PT_H264
    else:
        vdec_payload_type = K_PT_H265

    vdec = vdecoder.Decoder(vdec_payload_type)

    csc = CSC(2, CSC.PIXEL_FORMAT_RGB_888_PLANAR, buf_num=4)

    # 初始化display
    if (display_type == Display.VIRT):
        Display.init(display_type,width = video_info.width, height = video_info.height, fps=30, to_ide = True)
    else:
        Display.init(display_type,to_ide = True)

    #vb buffer初始化
    MediaManager.init()

    # 创建video decoder
    vdec.create()

    bind_info = vdec.bind_info(width=video_info.width, height=video_info.height,chn=vdec.get_vdec_channel())
    Display.bind_layer(**bind_info, layer = Display.LAYER_VIDEO1)

    vdec_link = MediaManager.link((VIDEO_DECODE_MOD_ID, VDEC_DEV_ID, vdec.get_vdec_channel()), (NONAI_2D_CSC_MOD_ID, 0, 2))
    vdec.start()


    # 记录初始系统时间
    start_system_time = time.ticks_ms()
    # 记录初始视频时间戳
    start_video_timestamp = 0

    _thread.start_new_thread(ai_detect_thread,(video_info.width, video_info.height,))

    try:
        while (main_thread_flag):
            frame_data =  k_mp4_frame_data_s()
            ret = kd_mp4_get_frame(mp4_handle.value, frame_data)
            if (ret < 0):
                raise OSError("get frame data failed")

            if (frame_data.eof):
                sub_thread_flag = False
                main_thread_flag = False
                raise OSError("get frame data failed")

            if (frame_data.codec_id == K_MP4_CODEC_ID_H264 or frame_data.codec_id == K_MP4_CODEC_ID_H265):
                data = uctypes.bytes_at(frame_data.data,frame_data.data_length)

                if(frame_data.data_length != 0):
                    #print("begin to decode")
                    vdec.decode(data)
                    #print("video frame_data.codec_id:",frame_data.codec_id,"data_length:",frame_data.data_length,"timestamp:",frame_data.time_stamp)

                # 计算视频时间戳经历的时长
                video_timestamp_elapsed = frame_data.time_stamp - start_video_timestamp
                # 计算系统时间戳经历的时长
                current_system_time = time.ticks_ms()
                system_time_elapsed = current_system_time - start_system_time

                # 如果系统时间戳经历的时长小于视频时间戳经历的时长，进行延时
                if system_time_elapsed < video_timestamp_elapsed:
                    time.sleep_ms(video_timestamp_elapsed - system_time_elapsed)
                else:
                    time.sleep_ms(1)
    except KeyboardInterrupt as e:
        print("user stop: ", e)
    except BaseException as e:
        print(f"Exception {e}")
    finally:
        sub_thread_flag = False
        main_thread_flag = False
        time.sleep_ms(100)
        Display.deinit()

        kd_mp4_destroy(mp4_handle.value)
        vdec.stop()
        vdec.destroy()
        csc.destroy()

        face_det.deinit()

        time.sleep_ms(200)
        MediaManager.deinit()
        print("release end")

def ai_detect_thread(width, height):
    global csc, sub_thread_flag, face_det
    rgb888p_size = [width, height]
    display_size = [width, height]
    print(rgb888p_size)
    # 设置模型路径和其他参数
    debug_mode = 1
    count = 0
    kmodel_path = "/sdcard/examples/kmodel/yunet_640.kmodel"
    confidence_threshold = 0.6
    nms_threshold = 0.3
    top_k=50
    # init FaceDetectionApp
    face_det = FaceDetectionApp(kmodel_path, model_input_size=[640, 640], confidence_threshold=confidence_threshold, nms_threshold=nms_threshold, top_k=top_k,rgb888p_size=rgb888p_size, display_size=display_size, debug_mode=0)
    face_det.config_preprocess()

    osd_img = image.Image(display_size[0], display_size[1], image.ARGB8888)

    while (sub_thread_flag):
        vf_info = csc.get_frame(timeout_ms=100)
        if vf_info is not None:
            count+=1
            if count % 2 == 0:
                csc.release_frame(vf_info)
            else:
                vf = vf_info.v_frame
                img = vf.to_image()

                img_np_hwc = img.to_numpy_ref()
                shape = img_np_hwc.shape
                img_np_nhwc=img_np_hwc.reshape((1,shape[0],shape[1],shape[2]))
                res = face_det.run(img_np_nhwc)

                csc.release_frame(vf_info)

                osd_img.clear()
                face_det.draw_result(osd_img, res)   # 绘制结果
                Display.show_image(osd_img)

            gc.collect()                    # 垃圾回收

if __name__ == "__main__":
    demuxer_mp4("/data/test.mp4")
