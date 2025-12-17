import uctypes
from mpp import libogg_def

def kd_ogg_muxer_params(**kwargs):
    layout = uctypes.NATIVE
    buf = bytearray(uctypes.sizeof(libogg_def.kd_ogg_muxer_params_desc, layout))
    s = uctypes.struct(uctypes.addressof(buf), libogg_def.kd_ogg_muxer_params_desc, layout)
    libogg_def.kd_ogg_muxer_params_parse(s, kwargs)
    return s

def kd_ogg_demuxer_params(**kwargs):
    layout = uctypes.NATIVE
    buf = bytearray(uctypes.sizeof(libogg_def.kd_ogg_demuxer_params_desc, layout))
    s = uctypes.struct(uctypes.addressof(buf), libogg_def.kd_ogg_demuxer_params_desc, layout)
    libogg_def.kd_ogg_demuxer_params_parse(s, kwargs)
    return s

def kd_ogg_frame_params(**kwargs):
    layout = uctypes.NATIVE
    buf = bytearray(uctypes.sizeof(libogg_def.kd_ogg_frame_params_desc, layout))
    s = uctypes.struct(uctypes.addressof(buf), libogg_def.kd_ogg_frame_params_desc, layout)
    libogg_def.kd_ogg_frame_params_parse(s, kwargs)
    return s

def kd_ogg_frame_params_ex(**kwargs):
    layout = uctypes.NATIVE
    buf = bytearray(uctypes.sizeof(libogg_def.kd_ogg_frame_params_ex_desc, layout))
    s = uctypes.struct(uctypes.addressof(buf), libogg_def.kd_ogg_frame_params_ex_desc, layout)
    libogg_def.kd_ogg_frame_params_ex_parse(s, kwargs)
    return s

def kd_ogg_page_params_ex(**kwargs):
    layout = uctypes.NATIVE
    buf = bytearray(uctypes.sizeof(libogg_def.kd_ogg_page_params_ex_desc, layout))
    s = uctypes.struct(uctypes.addressof(buf), libogg_def.kd_ogg_page_params_ex_desc, layout)
    libogg_def.kd_ogg_page_params_ex_parse(s, kwargs)
    return s