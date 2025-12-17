import uctypes

kd_ogg_muxer_params_desc = {
    "filename": (0 | uctypes.ARRAY, 128 | uctypes.UINT8),
    "sample_rate": 128 | uctypes.UINT32,
    "channels": 132 | uctypes.UINT32,
    "serial_no": 136 | uctypes.UINT32,
    "write_cb": 144 | uctypes.UINT64,
    "user_data": 152 | uctypes.UINT64,
}

def kd_ogg_muxer_params_parse(s, kwargs):
    s.filename[:] = kwargs.get("filename", "").encode()
    s.sample_rate = kwargs.get("sample_rate", 0)
    s.channels = kwargs.get("channels", 0)
    s.serial_no = kwargs.get("serial_no", 0)
    s.write_cb = kwargs.get("write_cb", 0)
    s.user_data = kwargs.get("user_data", 0)

kd_ogg_demuxer_params_desc = {
    "filename": (0 | uctypes.ARRAY, 128 | uctypes.UINT8),
    "write_cb": 128 | uctypes.UINT64,
    "user_data": 136 | uctypes.UINT64,
    "sample_rate": 144 | uctypes.UINT32,
    "channels": 148 | uctypes.UINT32,
}

def kd_ogg_demuxer_params_parse(s, kwargs):
    s.filename[:] = kwargs.get("filename", "").encode()
    s.write_cb = kwargs.get("write_cb", 0)
    s.user_data = kwargs.get("user_data", 0)
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

kd_ogg_frame_params_ex_desc = {
    "data": 0 | uctypes.UINT64,
    "len": 8 | uctypes.UINT32,
    "frame_samples": 12 | uctypes.UINT32,
    "out_page": 16 | uctypes.UINT64,
    "out_page_size": 24 | uctypes.UINT64,
}

def kd_ogg_frame_params_ex_parse(s, kwargs):
    s.data = kwargs.get("data", 0)
    s.len = kwargs.get("len", 0)
    s.frame_samples = kwargs.get("frame_samples", 0)
    s.out_page = kwargs.get("out_page", 0)
    s.out_page_size = kwargs.get("out_page_size", 0)

kd_ogg_page_params_ex_desc = {
    "page_data": 0 | uctypes.UINT64,
    "page_size": 8 | uctypes.UINT32,
    "out_frame": 16 | uctypes.UINT64,
    "out_frame_size": 24 | uctypes.UINT64,
}
def kd_ogg_page_params_ex_parse(s, kwargs):
    s.page_data = kwargs.get("page_data", 0)
    s.page_size = kwargs.get("page_size", 0)
    s.out_frame = kwargs.get("out_frame", 0)
    s.out_frame_size = kwargs.get("out_frame_size", 0)