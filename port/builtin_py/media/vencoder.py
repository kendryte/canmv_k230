import uctypes
from mpp.venc import *
from mpp.sys import *
from mpp.payload_struct import *
from mpp.venc_struct import *
from media.media import *
from mpp.video_struct import *

class ChnAttrStr:
    def __init__(self, payloadType, profile, picWidth, picHeight,bit_rate = 4000,gopLen = 30,src_frame_rate = 30,dst_frame_rate = 30,mjpeg_quality_factor = 45):
        self.payload_type = payloadType
        self.profile = profile
        self.pic_width = picWidth
        self.pic_height = picHeight
        self.gop_len = gopLen
        self.bit_rate = bit_rate
        self.src_frame_rate = src_frame_rate
        self.dst_frame_rate = dst_frame_rate
        self.mjpeg_quality_factor = mjpeg_quality_factor

class StreamData:
    def __init__(self):
        self.data = [0 for i in range(0, VENC_PACK_CNT_MAX)]
        self.phy_addr = [0 for i in range(0, VENC_PACK_CNT_MAX)]
        self.data_size = [0 for i in range(0, VENC_PACK_CNT_MAX)]
        self.stream_type = [0 for i in range(0, VENC_PACK_CNT_MAX)]
        self.pts = [0 for i in range(0, VENC_PACK_CNT_MAX)]
        self.pack_cnt = 0

class Encoder:
    PAYLOAD_TYPE_H264 = K_PT_H264
    PAYLOAD_TYPE_H265 = K_PT_H265
    PAYLOAD_TYPE_JPEG = K_PT_JPEG

    H264_PROFILE_BASELINE = VENC_PROFILE_H264_BASELINE
    H264_PROFILE_MAIN = VENC_PROFILE_H264_MAIN
    H264_PROFILE_HIGH = VENC_PROFILE_H264_HIGH
    H265_PROFILE_MAIN = VENC_PROFILE_H265_MAIN

    STREAM_TYPE_HEADER = K_VENC_HEADER
    STREAM_TYPE_I = K_VENC_I_FRAME
    STREAM_TYPE_P = K_VENC_P_FRAME

    def __init__(self):
        self.output = k_venc_stream()
        self.outbuf_num = 0
        self.private_poolid = -1

    def SetOutBufs(self, chn, buf_num, width, height):
        if (chn > VENC_CHN_ID_MAX - 1):
            raise ValueError("venc create, chn id: ", chn, " out of range 0 ~ 3")

        if buf_num and width and height:
            pool_config = k_vb_pool_config()
            pool_config.blk_cnt = buf_num
            pool_config.blk_size = ALIGN_UP(width * height * 3 // 4, VENC_ALIGN_4K)
            pool_config.mode = VB_REMAP_MODE_NOCACHE
            self.private_poolid = kd_mpi_vb_create_pool(pool_config)

    def Create(self, chn, chnAttr):
        if (chn > VENC_CHN_ID_MAX - 1):
            raise ValueError("venc create, chn id: ", chn, " out of range 0 ~ 3")

        kd_mpi_venc_attach_vb_pool(chn,self.private_poolid);

        venc_chn_attr = k_venc_chn_attr()
        venc_chn_attr.venc_attr.type = chnAttr.payload_type
        venc_chn_attr.venc_attr.pic_width = chnAttr.pic_width
        venc_chn_attr.venc_attr.pic_height = chnAttr.pic_height
        venc_chn_attr.venc_attr.profile = chnAttr.profile

        venc_chn_attr.rc_attr.rc_mode = K_VENC_RC_MODE_CBR
        venc_chn_attr.rc_attr.cbr.gop = chnAttr.gop_len
        venc_chn_attr.rc_attr.cbr.stats_time = 0
        venc_chn_attr.rc_attr.cbr.src_frame_rate = chnAttr.src_frame_rate
        venc_chn_attr.rc_attr.cbr.dst_frame_rate = chnAttr.dst_frame_rate
        venc_chn_attr.rc_attr.cbr.bit_rate = chnAttr.bit_rate

        if (chnAttr.payload_type == K_PT_JPEG):
            venc_chn_attr.rc_attr.rc_mode = K_VENC_RC_MODE_MJPEG_FIXQP
            venc_chn_attr.rc_attr.mjpeg_fixqp.src_frame_rate = 30
            venc_chn_attr.rc_attr.mjpeg_fixqp.dst_frame_rate = 30
            venc_chn_attr.rc_attr.mjpeg_fixqp.q_factor = chnAttr.mjpeg_quality_factor

        ret = kd_mpi_venc_create_chn(chn, venc_chn_attr)
        if ret != 0:
            raise OSError("mpi venc create chn failed.")

        if (chnAttr.payload_type == K_PT_H264 or chnAttr.payload_type == K_PT_H265):
            ret = kd_mpi_venc_enable_idr(chn, True)
            if ret != 0:
                raise OSError("mpi venc enable idr failed.")

    def Start(self, chn):
        if (chn > VENC_CHN_ID_MAX - 1):
            raise ValueError("venc Start, chn id: ", chn, " out of range 0 ~ 3")

        ret = kd_mpi_venc_start_chn(chn)
        if ret != 0:
            raise OSError("mpi venc start failed.")

    def GetStream(self, chn, streamData,timeout=-1):
        if (chn > VENC_CHN_ID_MAX - 1):
            raise ValueError("venc GetStream, chn id: ", chn, " out of range 0 ~ 3")

        status = k_venc_chn_status()
        ret = kd_mpi_venc_query_status(chn, status)
        if ret != 0:
            raise OSError("mpi venc query status failed.")

        if status.cur_packs > 0:
            self.output.pack_cnt = status.cur_packs
        else:
            self.output.pack_cnt = 1

        streamData.pack_cnt = self.output.pack_cnt

        buf = bytearray(uctypes.sizeof(venc_def.k_venc_pack_desc, uctypes.NATIVE) * self.output.pack_cnt)
        self.output.pack = uctypes.addressof(buf)

        ret = kd_mpi_venc_get_stream(chn, self.output, timeout)
        if ret != 0:
            #raise OSError("mpi venc get stream failed.")
            return -1

        for pack_idx in range(0, streamData.pack_cnt):
            vir_data = kd_mpi_sys_mmap(self.output._pack[pack_idx].phys_addr, self.output._pack[pack_idx].len)
            streamData.data[pack_idx] = vir_data
            streamData.data_size[pack_idx] = self.output._pack[pack_idx].len
            streamData.stream_type[pack_idx] = self.output._pack[pack_idx].type
            streamData.pts[pack_idx] = self.output._pack[pack_idx].pts
            streamData.phy_addr[pack_idx] = self.output._pack[pack_idx].phys_addr

        return 0

    def ReleaseStream(self, chn, streamData):
        if (chn > VENC_CHN_ID_MAX - 1):
            raise ValueError("venc ReleaseStream, chn id: ", chn, " out of range 0 ~ 3")

        for pack_idx in range(0, streamData.pack_cnt):
            ret = kd_mpi_sys_munmap(streamData.data[pack_idx], streamData.data_size[pack_idx])
            if ret != 0:
                raise OSError("mpi sys munmap failed.")

        ret = kd_mpi_venc_release_stream(chn, self.output)
        if ret != 0:
            raise OSError("mpi venc release stream failed.")

    def SendFrame(self, chn, frame,timeout=1000):
        if (chn > VENC_CHN_ID_MAX - 1):
            raise ValueError("venc SendFrame, chn id: ", chn, " out of range 0 ~ 3")

        ret = kd_mpi_venc_send_frame(chn, frame, timeout)
        return ret

    def Stop(self, chn):
        if (chn > VENC_CHN_ID_MAX - 1):
            raise ValueError("venc Stop, chn id: ", chn, " out of range 0 ~ 3")

        ret = kd_mpi_venc_stop_chn(chn)
        if ret != 0:
            raise OSError("mpi venc stop failed.")

        ret= kd_mpi_venc_detach_vb_pool(chn)
        if ret != 0:
            raise OSError("mpi venc detach vb pool failed.")

    def Destroy(self, chn):
        if (chn > VENC_CHN_ID_MAX - 1):
            raise ValueError("venc Destroy, chn id: ", chn, " out of range 0 ~ 3")

        ret = kd_mpi_venc_destroy_chn(chn)
        if ret != 0:
            raise OSError("mpi venc destroy failed.")

        if (self.private_poolid != -1):
            kd_mpi_vb_destory_pool(self.private_poolid)
            self.private_poolid = -1
