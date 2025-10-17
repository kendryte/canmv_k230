from mpp import *

MAX_MEDIA_BUFFER_POOLS = 16 #FIX VALUE

MAX_MEDIA_LINK_COUNT = 8

# K230 CanMV meida module define
AUDIO_IN_MOD_ID = K_ID_AI          # audio in device module
AUDIO_OUT_MOD_ID = K_ID_AO         # audio out device module

AUDIO_ENCODE_MOD_ID = K_ID_AENC    # audio encode device module
AUDIO_DECODE_MOD_ID = K_ID_ADEC    # audio decode device module

CAMERA_MOD_ID = K_ID_VI            # camera cdevice module

DISPLAY_MOD_ID = K_ID_VO            # display device module

DMA_MOD_ID = K_ID_DMA              # DMA device module

DPU_MOD_ID = K_ID_DPU              # DPU device module

VIDEO_ENCODE_MOD_ID = K_ID_VENC    # video encode device module
VIDEO_DECODE_MOD_ID = K_ID_VDEC    # video decode device module

NONAI_2D_CSC_MOD_ID = K_ID_NONAI_2D


# audio device id definition
# TODO

# camera device id definition
CAM_DEV_ID_0 = VICAP_DEV_ID_0
CAM_DEV_ID_1 = VICAP_DEV_ID_1
CAM_DEV_ID_2 = VICAP_DEV_ID_2
CAM_DEV_ID_MAX = VICAP_DEV_ID_MAX

# display device id definition
DISPLAY_DEV_ID = K_VO_DISPLAY_DEV_ID

# DMA device id definition
# TODO

# DPU device id definition
# TODO

# video encode device id definition
VENC_DEV_ID = const(0)

# video decode device id definition
# TODO
VDEC_DEV_ID = const(0)

# audio channel id definition
# TODO

# camera channel id definition
CAM_CHN_ID_0 = VICAP_CHN_ID_0
CAM_CHN_ID_1 = VICAP_CHN_ID_1
CAM_CHN_ID_2 = VICAP_CHN_ID_2
CAM_CHN_ID_MAX = VICAP_CHN_ID_MAX

# display channel id definition
DISPLAY_CHN_ID_0 = K_VO_DISPLAY_CHN_ID0
DISPLAY_CHN_ID_1 = K_VO_DISPLAY_CHN_ID1
DISPLAY_CHN_ID_2 = K_VO_DISPLAY_CHN_ID2
DISPLAY_CHN_ID_3 = K_VO_DISPLAY_CHN_ID3
DISPLAY_CHN_ID_4 = K_VO_DISPLAY_CHN_ID4
DISPLAY_CHN_ID_5 = K_VO_DISPLAY_CHN_ID5
DISPLAY_CHN_ID_6 = K_VO_DISPLAY_CHN_ID6

# DMA channel id definition
# TODO

# DPU channel id definition
# TODO

# video encode channel id definition
VENC_CHN_ID_0 = const(0)
VENC_CHN_ID_1 = const(1)
VENC_CHN_ID_2 = const(2)
VENC_CHN_ID_3 = const(3)
VENC_CHN_ID_MAX = VENC_MAX_CHN_NUMS
VENC_PACK_CNT_MAX = const(12)

# video decode channel id definition
VDEC_CHN_ID_0 = const(0)
VDEC_CHN_ID_1 = const(1)
VDEC_CHN_ID_2 = const(2)
VDEC_CHN_ID_3 = const(3)
VDEC_CHN_ID_MAX = VDEC_MAX_CHN_NUMS

# data align up
ALIGN_UP = VICAP_ALIGN_UP

VB_INVALID_POOLID = 0xFFFFFFFF
VB_INVALID_HANDLE = 0xFFFFFFFF

from _media import _MediaManager

class MediaManager:
    Buffer = _MediaManager.Buffer
    VBPool = _MediaManager.VBPool

    @staticmethod
    def init(*args, **kwargs):
        print("deprecated function")

    @staticmethod
    def deinit(*args, **kwargs):
        print("deprecated function")

    @staticmethod
    def _config(*args, **kwargs):
        raise RuntimeError("deprecated function")

    @staticmethod
    def config_comm_pool(*args, **kwargs):
        raise RuntimeError("deprecated function")

    @staticmethod
    def link(src, dst):
        if not isinstance(src, tuple):
            raise TypeError("src is not a tuple")
        if len(src) != 3:
            raise TypeError("src size shoule be 3")

        src_mpp = k_mpp_chn()
        src_mpp.mod_id = src[0]
        src_mpp.dev_id = src[1]
        src_mpp.chn_id = src[2]

        if not isinstance(dst, tuple):
            raise TypeError("dst is not a tuple")
        if len(dst) != 3:
            raise TypeError("dst size shoule be 3")

        dst_mpp = k_mpp_chn()
        dst_mpp.mod_id = dst[0]
        dst_mpp.dev_id = dst[1]
        dst_mpp.chn_id = dst[2]

        if dst_mpp.mod_id == DISPLAY_MOD_ID and dst_mpp.dev_id == DISPLAY_DEV_ID:
            if src_mpp.mod_id == CAMERA_MOD_ID:
                from .sensor import Sensor
                from .display import Display

                sensor = Sensor._devs[src_mpp.dev_id]
                if isinstance(sensor, Sensor):
                    sensor._set_chn_fps(chn = src_mpp.chn_id, fps = Display.fps())

        return _MediaManager._link(src_mpp, dst_mpp)
