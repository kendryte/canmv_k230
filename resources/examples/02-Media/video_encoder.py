# Video encode example
#
# Note: You will need an SD card to run this example.
#
# You can capture videos and encode them into 264/265 files

from media.vencoder import *
from media.sensor import *
from media.media import *
import time, os

def vi_bind_venc_test(file_name,width=1280, height=720):
    print("venc_test start")
    venc_chn = VENC_CHN_ID_0
    width = ALIGN_UP(width, 16)
    venc_payload_type = K_PT_H264

    # 判断文件类型
    suffix = file_name.split('.')[-1]
    if suffix == '264':
        venc_payload_type = K_PT_H264
    elif suffix == '265':
        venc_payload_type = K_PT_H265
    else:
        print("Unknown file extension")
        return

    # 初始化sensor
    sensor = Sensor()
    sensor.reset()
    # 设置camera 输出buffer
    # set chn0 output size
    sensor.set_framesize(width = width, height = height, alignment=12)
    # set chn0 output format
    sensor.set_pixformat(Sensor.YUV420SP)


    # 实例化video encoder
    encoder = Encoder()
    # 设置video encoder 输出buffer
    encoder.SetOutBufs(venc_chn, 8, width, height)

    # 绑定camera和venc
    link = MediaManager.link(sensor.bind_info()['src'], (VIDEO_ENCODE_MOD_ID, VENC_DEV_ID, venc_chn))

    if (venc_payload_type == K_PT_H264):
        chnAttr = ChnAttrStr(encoder.PAYLOAD_TYPE_H264, encoder.H264_PROFILE_MAIN, width, height)
    elif (venc_payload_type == K_PT_H265):
        chnAttr = ChnAttrStr(encoder.PAYLOAD_TYPE_H265, encoder.H265_PROFILE_MAIN, width, height)

    streamData = StreamData()

    # 创建编码器
    encoder.Create(venc_chn, chnAttr)

    # 开始编码
    encoder.Start(venc_chn)
    # 启动camera
    sensor.run()

    frame_count = 0
    print("save stream to file: ", file_name)

    with open(file_name, "wb") as fo:
        try:
            while True:
                os.exitpoint()
                encoder.GetStream(venc_chn, streamData) # 获取一帧码流

                for pack_idx in range(0, streamData.pack_cnt):
                    stream_data = uctypes.bytearray_at(streamData.data[pack_idx], streamData.data_size[pack_idx])
                    fo.write(stream_data) # 码流写文件
                    print("stream size: ", streamData.data_size[pack_idx], "stream type: ", streamData.stream_type[pack_idx])

                encoder.ReleaseStream(venc_chn, streamData) # 释放一帧码流

                frame_count += 1
                if frame_count >= 200:
                    break
        except KeyboardInterrupt as e:
            print("user stop: ", e)
        except BaseException as e:
            import sys
            sys.print_exception(e)

    # 停止camera
    sensor.stop()
    # 销毁camera和venc的绑定
    del link
    # 停止编码
    encoder.Stop(venc_chn)
    # 销毁编码器
    encoder.Destroy(venc_chn)
    print("venc_test stop")

def stream_venc_test(file_name,width=1280, height=720):
    print("venc_test start")
    venc_chn = VENC_CHN_ID_0
    width = ALIGN_UP(width, 16)
    venc_payload_type = K_PT_H264

    # 判断文件类型
    suffix = file_name.split('.')[-1]
    if suffix == '264':
        venc_payload_type = K_PT_H264
    elif suffix == '265':
        venc_payload_type = K_PT_H265
    else:
        print("Unknown file extension")
        return

    # 初始化sensor
    sensor = Sensor()
    sensor.reset()
    # 设置camera 输出buffer
    # set chn0 output size
    sensor.set_framesize(width = width, height = height, alignment=12)
    # set chn0 output format
    sensor.set_pixformat(Sensor.YUV420SP)


    # 实例化video encoder
    encoder = Encoder()
    # 设置video encoder 输出buffer
    encoder.SetOutBufs(venc_chn, 8, width, height)

    if (venc_payload_type == K_PT_H264):
        chnAttr = ChnAttrStr(encoder.PAYLOAD_TYPE_H264, encoder.H264_PROFILE_MAIN, width, height)
    elif (venc_payload_type == K_PT_H265):
        chnAttr = ChnAttrStr(encoder.PAYLOAD_TYPE_H265, encoder.H265_PROFILE_MAIN, width, height)

    streamData = StreamData()

    # 创建编码器
    encoder.Create(venc_chn, chnAttr)

    # 开始编码
    encoder.Start(venc_chn)
    # 启动camera
    sensor.run()

    frame_count = 0
    print("save stream to file: ", file_name)

    yuv420sp_img = None
    frame_info = k_video_frame_info()
    with open(file_name, "wb") as fo:
        try:
            while True:
                os.exitpoint()
                frame_info  = sensor.snapshot(chn=CAM_CHN_ID_0,dump_frame=True)
                #frame_info.v_frame.nv12_to_grayscale() # convert to grayscale
                encoder.SendFrame(venc_chn,frame_info)
                encoder.GetStream(venc_chn, streamData) # 获取一帧码流

                for pack_idx in range(0, streamData.pack_cnt):
                    stream_data = uctypes.bytearray_at(streamData.data[pack_idx], streamData.data_size[pack_idx])
                    fo.write(stream_data) # 码流写文件
                    print("stream size: ", streamData.data_size[pack_idx], "stream type: ", streamData.stream_type[pack_idx])

                encoder.ReleaseStream(venc_chn, streamData) # 释放一帧码流

                frame_count += 1
                if frame_count >= 200:
                    break
        except KeyboardInterrupt as e:
            print("user stop: ", e)
        except BaseException as e:
            import sys
            sys.print_exception(e)

    # 停止camera
    sensor.stop()
    # 停止编码
    encoder.Stop(venc_chn)
    # 销毁编码器
    encoder.Destroy(venc_chn)
    print("venc_test stop")

if __name__ == "__main__":
    os.exitpoint(os.EXITPOINT_ENABLE)
    vi_bind_venc_test("/data/test.264",800,480)  # vi绑定venc示例
    #stream_venc_test("/data/test.264",800,480)  # venc编码数据流示例
