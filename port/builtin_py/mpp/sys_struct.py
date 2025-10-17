import uctypes
from mpp import sys_def

K_ID_CMPI = const(0)
K_ID_LOG = const(1)
K_ID_MMZ = const(2)
K_ID_MMZ_USER_DEV = const(3)
K_ID_VB = const(4)
K_ID_SYS = const(5)
K_ID_VI = const(6)
K_ID_VPROC = const(7)
K_ID_VREC = const(8)
K_ID_VENC = const(9)
K_ID_VDEC = const(10)
K_ID_VO = const(11)
K_ID_AI = const(12)
K_ID_AREC = const(13)
K_ID_AENC = const(14)
K_ID_ADEC = const(15)
K_ID_AO = const(16)
K_ID_DPU = const(17)
K_ID_V_VI = const(18)
K_ID_V_VO = const(19)
K_ID_DMA = const(20)
K_ID_VICAP = const(21)
K_ID_DW200 = const(22)
K_ID_PM = const(23)
K_ID_NONAI_2D = const(24)
K_ID_BUTT = const(25)

def k_mpp_chn(**kwargs):
    layout = uctypes.NATIVE
    buf = bytearray(uctypes.sizeof(sys_def.k_mpp_chn_desc, layout))
    s = uctypes.struct(uctypes.addressof(buf), sys_def.k_mpp_chn_desc, layout)
    sys_def.k_mpp_chn_parse(s, kwargs)
    return s

def k_mpp_bind_dest(**kwargs):
    layout = uctypes.NATIVE
    buf = bytearray(uctypes.sizeof(sys_def.k_mpp_bind_dest_desc, layout))
    s = uctypes.struct(uctypes.addressof(buf), sys_def.k_mpp_bind_dest_desc, layout)
    sys_def.k_mpp_bind_dest_parse(s, kwargs)
    return s

def k_log_level_conf(**kwargs):
    layout = uctypes.NATIVE
    buf = bytearray(uctypes.sizeof(sys_def.k_log_level_conf_desc, layout))
    s = uctypes.struct(uctypes.addressof(buf), sys_def.k_log_level_conf_desc, layout)
    sys_def.k_log_level_conf_parse(s, kwargs)
    return s

def k_sys_virmem_info(**kwargs):
    layout = uctypes.NATIVE
    buf = bytearray(uctypes.sizeof(sys_def.k_sys_virmem_info_desc, layout))
    s = uctypes.struct(uctypes.addressof(buf), sys_def.k_sys_virmem_info_desc, layout)
    sys_def.k_sys_virmem_info_parse(s, kwargs)
    return s
