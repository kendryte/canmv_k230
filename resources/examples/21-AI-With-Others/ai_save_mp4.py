"""
Script: ai_save_mp4.py
脚本名称：ai_save_mp4.py

Description:
    This script performs real-time object detection using a YOLOv8 model with a camera sensor input.
    It captures frames in parallel for AI inference and MP4 recording, performs preprocessing with Ai2d,
    runs inference via NNCase, overlays detection results, and saves the video when specific conditions are met.

    The script supports YUV and RGB format handling, integrates with a hardware encoder for H.264/H.265 video,
    and uses MP4 muxing APIs to generate standard MP4 files on detection events.

脚本说明：
    本脚本基于 YOLOv8 模型，通过摄像头采集图像实现实时目标检测。
    使用 Ai2d 进行预处理，通过 NNCase 进行推理，在检测到特定目标（如苹果）时，自动保存编码后的视频为 MP4 文件。

    脚本支持 YUV 和 RGB 图像格式处理，集成硬件编码器进行 H.264/H.265 编码，
    并通过 MP4 封装模块生成标准 MP4 视频文件。

Author: Canaan Developer
作者：Canaan 开发者
"""


from libs.PipeLine import PipeLine
from libs.AIBase import AIBase
from libs.AI2D import Ai2d
from libs.Utils import *
from media.vencoder import *
from media.sensor import *
from media.media import *
from media.display import *
from mpp.mp4_format import *
from mpp.mp4_format_struct import *
import nncase_runtime as nn
import time, os
import aidemo
import gc
import uctypes

# 自定义YOLOv8检测类
class ObjectDetectionApp(AIBase):
    def __init__(self,kmodel_path,labels,model_input_size,max_boxes_num,confidence_threshold=0.5,nms_threshold=0.2,rgb888p_size=[224,224],display_size=[1920,1080],debug_mode=0):
        super().__init__(kmodel_path,model_input_size,rgb888p_size,debug_mode)
        self.kmodel_path=kmodel_path
        self.labels=labels
        # 模型输入分辨率
        self.model_input_size=model_input_size
        # 阈值设置
        self.confidence_threshold=confidence_threshold
        self.nms_threshold=nms_threshold
        self.max_boxes_num=max_boxes_num
        # sensor给到AI的图像分辨率
        self.rgb888p_size=[ALIGN_UP(rgb888p_size[0],16),rgb888p_size[1]]
        # 显示分辨率
        self.display_size=[ALIGN_UP(display_size[0],16),display_size[1]]
        self.debug_mode=debug_mode
        # 检测框预置颜色值
        self.color_four=get_colors(len(self.labels))
        # 宽高缩放比例
        self.x_factor = float(self.rgb888p_size[0])/self.model_input_size[0]
        self.y_factor = float(self.rgb888p_size[1])/self.model_input_size[1]
        # Ai2d实例，用于实现模型预处理
        self.ai2d=Ai2d(debug_mode)
        # 设置Ai2d的输入输出格式和类型
        self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT,nn.ai2d_format.NCHW_FMT,np.uint8, np.uint8)

    # 配置预处理操作，这里使用了resize，Ai2d支持crop/shift/pad/resize/affine，具体代码请打开/sdcard/app/libs/AI2D.py查看
    def config_preprocess(self,input_image_size=None):
        with ScopedTiming("set preprocess config",self.debug_mode > 0):
            # 初始化ai2d预处理配置，默认为sensor给到AI的尺寸，您可以通过设置input_image_size自行修改输入尺寸
            ai2d_input_size=input_image_size if input_image_size else self.rgb888p_size
            top,bottom,left,right,self.scale=letterbox_pad_param(self.rgb888p_size,self.model_input_size)
            # 配置padding预处理
            self.ai2d.pad([0,0,0,0,top,bottom,left,right], 0, [128,128,128])
            self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
            self.ai2d.build([1,3,ai2d_input_size[1],ai2d_input_size[0]],[1,3,self.model_input_size[1],self.model_input_size[0]])

    # 自定义当前任务的后处理
    def postprocess(self,results):
        with ScopedTiming("postprocess",self.debug_mode > 0):
            new_result=results[0][0].transpose()
            det_res = aidemo.yolov8_det_postprocess(new_result.copy(),[self.rgb888p_size[1],self.rgb888p_size[0]],[self.model_input_size[1],self.model_input_size[0]],[self.display_size[1],self.display_size[0]],len(self.labels),self.confidence_threshold,self.nms_threshold,self.max_boxes_num)
            return det_res

    # 绘制结果
    def draw_result(self,osd_img,dets):
        with ScopedTiming("display_draw",self.debug_mode >0):
            has_apple=False
            if dets:
                osd_img.clear()
                for i in range(len(dets[0])):
                    x, y, w, h = map(lambda x: int(round(x, 0)), dets[0][i])
                    osd_img.draw_rectangle(x,y, w, h, color=self.color_four[dets[1][i]],thickness=4)
                    osd_img.draw_string_advanced( x , y-50,32," " + self.labels[dets[1][i]] + " " + str(round(dets[2][i],2)) , color=self.color_four[dets[1][i]])
                    if self.labels[dets[1][i]]=="apple":
                        has_apple=True
            else:
                osd_img.clear()
            return has_apple

def mp4_muxer_init(file_name,  fmp4_flag):
    mp4_cfg = k_mp4_config_s()
    mp4_cfg.config_type = K_MP4_CONFIG_MUXER
    mp4_cfg.muxer_config.file_name[:] = bytes(file_name, 'utf-8')
    mp4_cfg.muxer_config.fmp4_flag = fmp4_flag

    handle = k_u64_ptr()
    ret = kd_mp4_create(handle, mp4_cfg)
    if ret:
        raise OSError("kd_mp4_create failed.")
    return handle.value

def mp4_muxer_create_video_track(mp4_handle, width, height, video_payload_type):
    video_track_info = k_mp4_track_info_s()
    video_track_info.track_type = K_MP4_STREAM_VIDEO
    video_track_info.time_scale = 1000
    video_track_info.video_info.width = width
    video_track_info.video_info.height = height
    video_track_info.video_info.codec_id = video_payload_type
    video_track_handle = k_u64_ptr()
    ret = kd_mp4_create_track(mp4_handle, video_track_handle, video_track_info)
    if ret:
        raise OSError("kd_mp4_create_track failed.")
    return video_track_handle.value

def mp4_muxer_create_audio_track(mp4_handle,channel,sample_rate, bit_per_sample ,audio_payload_type):
    audio_track_info = k_mp4_track_info_s()
    audio_track_info.track_type = K_MP4_STREAM_AUDIO
    audio_track_info.time_scale = 1000
    audio_track_info.audio_info.channels = channel
    audio_track_info.audio_info.codec_id = audio_payload_type
    audio_track_info.audio_info.sample_rate = sample_rate
    audio_track_info.audio_info.bit_per_sample = bit_per_sample
    audio_track_handle = k_u64_ptr()
    ret = kd_mp4_create_track(mp4_handle, audio_track_handle, audio_track_info)
    if ret:
        raise OSError("kd_mp4_create_track failed.")
    return audio_track_handle.value

def ai_and_save_mp4():
    # 显示参数
    display_size=[800,480]
    # AI相关参数
    rgb888p_size=[1280,720]
    kmodel_path="/sdcard/examples/kmodel/yolov8n_224.kmodel"
    labels = ["person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat", "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch", "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase", "scissors", "teddy bear", "hair drier", "toothbrush"]
    confidence_threshold = 0.3
    nms_threshold = 0.4
    max_boxes_num = 30
    # 保存视频参数
    mp4_id=0
    mp4_size=[1280,720]
    venc_chn = VENC_CHN_ID_0
    venc_payload_type = K_PT_H264
    video_payload_type=K_MP4_CODEC_ID_H264

    # 初始化sensor
    sensor = Sensor()
    sensor.reset()
    # 设置camera 输出buffer
    # set chn0 output size
    sensor.set_framesize(w = display_size[0], h = display_size[1],chn=CAM_CHN_ID_0)
    sensor.set_pixformat(Sensor.YUV420SP,chn=CAM_CHN_ID_0)

    sensor.set_framesize(width = rgb888p_size[0], height = rgb888p_size[1],chn=CAM_CHN_ID_1)
    # set chn1 output format
    sensor.set_pixformat(Sensor.RGBP888,chn=CAM_CHN_ID_1)

    # set chn2 output format
    sensor.set_framesize(w = mp4_size[0], h = mp4_size[1],chn=CAM_CHN_ID_2)
    sensor.set_pixformat(Sensor.YUV420SP,chn=CAM_CHN_ID_2)

    sensor_bind_info = sensor.bind_info(x = 0, y = 0, chn = CAM_CHN_ID_0)
    Display.bind_layer(**sensor_bind_info, layer = Display.LAYER_VIDEO1)

    # OSD图像初始化
    osd_img = image.Image(display_size[0], display_size[1], image.ARGB8888)
    # 设置为ST7701显示，默认480x800
    Display.init(Display.ST7701, width=display_size[0], height=display_size[1], osd_num=1, to_ide=True)

    # 实例化video encoder
    encoder = Encoder()
    # 设置video encoder 输出buffer
    encoder.SetOutBufs(venc_chn, 8, mp4_size[0], mp4_size[1])




    if (venc_payload_type == K_PT_H264):
        chnAttr = ChnAttrStr(encoder.PAYLOAD_TYPE_H264, encoder.H264_PROFILE_MAIN, mp4_size[0], mp4_size[1])
    elif (venc_payload_type == K_PT_H265):
        chnAttr = ChnAttrStr(encoder.PAYLOAD_TYPE_H265, encoder.H265_PROFILE_MAIN, mp4_size[0], mp4_size[1])

    streamData = StreamData()
    # 启动camera
    sensor.run()
    # 初始化自定义目标检测实例
    ob_det=ObjectDetectionApp(kmodel_path,labels=labels,model_input_size=[224,224],max_boxes_num=max_boxes_num,confidence_threshold=confidence_threshold,nms_threshold=nms_threshold,rgb888p_size=rgb888p_size,display_size=display_size,debug_mode=0)
    ob_det.config_preprocess()

    while True:
        rgbp888_img = sensor.snapshot(chn=CAM_CHN_ID_1)
        rgbp888_np=rgbp888_img.to_numpy_ref()
        # 推理当前帧
        res=ob_det.run(rgbp888_np)
        # 绘制结果到PipeLine的osd图像
        has_apple=ob_det.draw_result(osd_img,res)
        Display.show_image(osd_img, 0, 0, Display.LAYER_OSD1)
        if has_apple:
            # 文件名
            file_name="/data/has_apple_"+str(mp4_id)+".mp4"
            print(f"正在保存视频到{file_name}...")
            # 编码器参数
            frame_count = 0
            yuv420sp_img = None
            frame_info = k_video_frame_info()
            # MP4相关参数
            idr_index = 0
            video_start_timestamp = 0
            get_first_I_frame = False
            frame_data = k_mp4_frame_data_s()
            save_idr = bytearray(mp4_size[0] * mp4_size[1] * 3 // 4)
            # mp4 muxer init
            mp4_handle = mp4_muxer_init(file_name, True)
            mp4_video_track_handle = mp4_muxer_create_video_track(mp4_handle, mp4_size[0], mp4_size[1], video_payload_type)

             # 创建编码器
            encoder.Create(venc_chn, chnAttr)
            # 开始编码
            encoder.Start(venc_chn)
            while True:
                os.exitpoint()
                yuv420sp_img = sensor.snapshot(chn=CAM_CHN_ID_2)
                if (yuv420sp_img == -1):
                    continue
                frame_info.v_frame.width = yuv420sp_img.width()
                frame_info.v_frame.height = yuv420sp_img.height()
                frame_info.v_frame.pixel_format = Sensor.YUV420SP
                frame_info.pool_id = yuv420sp_img.poolid()
                frame_info.v_frame.phys_addr[0] = yuv420sp_img.phyaddr()
                if (yuv420sp_img.width() == 800 and yuv420sp_img.height() == 480):
                    frame_info.v_frame.phys_addr[1] = frame_info.v_frame.phys_addr[0] + frame_info.v_frame.width*frame_info.v_frame.height + 1024
                elif (yuv420sp_img.width() == 1920 and yuv420sp_img.height() == 1080):
                    frame_info.v_frame.phys_addr[1] = frame_info.v_frame.phys_addr[0] + frame_info.v_frame.width*frame_info.v_frame.height + 3072
                elif (yuv420sp_img.width() == 640 and yuv420sp_img.height() == 360):
                    frame_info.v_frame.phys_addr[1] = frame_info.v_frame.phys_addr[0] + frame_info.v_frame.width*frame_info.v_frame.height + 3072
                else:
                    frame_info.v_frame.phys_addr[1] = frame_info.v_frame.phys_addr[0] + frame_info.v_frame.width*frame_info.v_frame.height
                ret = encoder.SendFrame(venc_chn,frame_info)
                if ret != 0:
                    print("encoder send frame failed")
                    continue

                ret = encoder.GetStream(venc_chn, streamData,timeout = -1) # 获取一帧或多帧码流
                if ret != 0:
                    print("encoder get stream failed")
                    continue

                # Retrieve first IDR frame and write to MP4 file. Note: The first frame must be an IDR frame.
                if not get_first_I_frame:
                    for pack_idx in range(0, streamData.pack_cnt):
                        stream_type = streamData.stream_type[pack_idx]
                        streamData.pts[pack_idx] = time.ticks_us() # 使用系统时间戳
                        if stream_type == encoder.STREAM_TYPE_I:
                            get_first_I_frame = True
                            video_start_timestamp = streamData.pts[pack_idx]
                            save_idr[idr_index:idr_index+streamData.data_size[pack_idx]] = uctypes.bytearray_at(streamData.data[pack_idx], streamData.data_size[pack_idx])
                            idr_index += streamData.data_size[pack_idx]

                            frame_data.codec_id = video_payload_type
                            frame_data.data = uctypes.addressof(save_idr)
                            frame_data.data_length = idr_index
                            frame_data.time_stamp = streamData.pts[pack_idx] - video_start_timestamp

                            ret = kd_mp4_write_frame(mp4_handle, mp4_video_track_handle, frame_data)
                            if ret:
                                raise OSError("kd_mp4_write_frame failed.")

                            break

                        elif stream_type == encoder.STREAM_TYPE_HEADER:
                            save_idr[idr_index:idr_index+streamData.data_size[pack_idx]] = uctypes.bytearray_at(streamData.data[pack_idx], streamData.data_size[pack_idx])
                            idr_index += streamData.data_size[pack_idx]
                            continue
                        else:
                            continue

                    encoder.ReleaseStream(venc_chn, streamData)
                    continue


                # Write video stream to MP4 file （not first idr frame）
                for pack_idx in range(0, streamData.pack_cnt):
                    streamData.pts[pack_idx] = time.ticks_us() # 使用系统时间戳
                    frame_data.codec_id = video_payload_type
                    frame_data.data = streamData.data[pack_idx]
                    frame_data.data_length = streamData.data_size[pack_idx]
                    frame_data.time_stamp = streamData.pts[pack_idx] - video_start_timestamp

                    #print("video size: ", streamData.data_size[pack_idx], "video type: ", streamData.stream_type[pack_idx],"video timestamp:",frame_data.time_stamp)
                    ret = kd_mp4_write_frame(mp4_handle, mp4_video_track_handle, frame_data)
                    if ret:
                        raise OSError("kd_mp4_write_frame failed.")

                encoder.ReleaseStream(venc_chn, streamData) # 释放一帧码流

                frame_count += 1
                if frame_count >= 100:
                    break

            encoder.Stop(venc_chn)
            encoder.Destroy(venc_chn)
            kd_mp4_destroy_tracks(mp4_handle)
            kd_mp4_destroy(mp4_handle)
            mp4_id+=1
            print("视频保存完成！")
        gc.collect()
    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    ob_det.deinit()
    sensor.stop()
    Display.deinit()
    time.sleep_ms(50)
    gc.collect()


if __name__=="__main__":
    ai_and_save_mp4()

