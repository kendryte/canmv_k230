import uctypes

kd_ogg_muxer_params_desc = {
    "filename": (0 | uctypes.ARRAY, 128 | uctypes.UINT8),
    "sample_rate": 128 | uctypes.UINT32,
    "channels": 132 | uctypes.UINT32,
    "serial_no": 136 | uctypes.UINT32,
}

def kd_ogg_muxer_params_parse(s, kwargs):
    s.filename[:] = kwargs.get("filename", "").encode()
    s.sample_rate = kwargs.get("sample_rate", 0)
    s.channels = kwargs.get("channels", 0)
    s.serial_no = kwargs.get("serial_no", 0)

kd_ogg_demuxer_params_desc = {
    "filename": (0 | uctypes.ARRAY, 128 | uctypes.UINT8),
    "sample_rate": 128 | uctypes.UINT32,
    "channels": 132 | uctypes.UINT32,
}

def kd_ogg_demuxer_params_parse(s, kwargs):
    s.filename[:] = kwargs.get("filename", "").encode()
    s.sample_rate = kwargs.get("sample_rate", 0)
    s.channels = kwargs.get("channels", 0)

kd_ogg_frame_params_desc = {
    "data": 0 | uctypes.UINT64,
    "len": 8 | uctypes.UINT32,
    "frame_samples": 12 | uctypes.UINT32,
}

def kd_ogg_frame_params_parse(s, kwargs):
    s.data = kwargs.get("data", 0)
    s.len = kwargs.get("len", 0)
    s.frame_samples = kwargs.get("frame_samples", 0)