import uctypes

k_vdec_chn_attr_desc = {
    "type": 0 | uctypes.UINT32,
    "mode": 4 | uctypes.UINT32,
    "pic_width": 8 | uctypes.UINT32,
    "pic_height": 12 | uctypes.UINT32,
    "stream_buf_size": 16 | uctypes.UINT32,
}

def k_vdec_chn_attr_parse(s, kwargs):
    s.type = kwargs.get("type", 0)
    s.mode = kwargs.get("mode", 0)
    s.pic_width = kwargs.get("pic_width", 0)
    s.pic_height = kwargs.get("pic_height", 0)
    s.stream_buf_size = kwargs.get("stream_buf_size", 0)

k_vdec_supplement_info_desc = {
    "type": 0 | uctypes.UINT32,
    "is_valid_frame": 4 | uctypes.UINT32,
    "end_of_stream": 8 | uctypes.UINT32,
}

def k_vdec_supplement_info_parse(s, kwargs):
    s.type = kwargs.get("type", 0)
    s.is_valid_frame = kwargs.get("is_valid_frame", 0)
    s.end_of_stream = kwargs.get("end_of_stream", 0)

k_vdec_stream_desc = {
    "end_of_stream": 0 | uctypes.UINT32,
    "pts": 8 | uctypes.UINT64,
    "len": 16 | uctypes.UINT32,
    "phy_addr": 24 | uctypes.UINT64,
}

def k_vdec_stream_parse(s, kwargs):
    s.end_of_stream = kwargs.get("end_of_stream", 0)
    s.pts = kwargs.get("pts", 0)
    s.len = kwargs.get("len", 0)
    s.phy_addr = kwargs.get("phy_addr", 0)

k_vdec_dec_err_desc = {
    "set_pic_buf_size_err": 0 | uctypes.INT32,
    "format_err": 4 | uctypes.INT32,
    "stream_unsupport": 8 | uctypes.INT32,
}

def k_vdec_dec_err_parse(s, kwargs):
    s.set_pic_buf_size_err = kwargs.get("set_pic_buf_size_err", 0)
    s.format_err = kwargs.get("format_err", 0)
    s.stream_unsupport = kwargs.get("stream_unsupport", 0)

k_vdec_chn_status_desc = {
    "type": 0 | uctypes.UINT32,
    "is_started": 4 | uctypes.UINT32,
    "recv_stream_frames": 8 | uctypes.UINT32,
    "dec_stream_frames": 12 | uctypes.UINT32,
    "dec_err": (16, k_vdec_dec_err_desc),
    "width": 28 | uctypes.UINT32,
    "height": 32 | uctypes.UINT32,
    "latest_frame_pts": 40 | uctypes.UINT64,
    "end_of_stream": 48 | uctypes.UINT32,
}

def k_vdec_chn_status_parse(s, kwargs):
    s.type = kwargs.get("type", 0)
    s.is_started = kwargs.get("is_started", 0)
    s.recv_stream_frames = kwargs.get("recv_stream_frames", 0)
    s.dec_stream_frames = kwargs.get("dec_stream_frames", 0)
    #s.dec_err = kwargs.get("dec_err", 0)
    s.width = kwargs.get("width", 0)
    s.height = kwargs.get("height", 0)
    s.latest_frame_pts = kwargs.get("latest_frame_pts", 0)
    s.end_of_stream = kwargs.get("end_of_stream", 0)

k_vdec_dsl_size_desc = {
    "dsl_frame_width": 0 | uctypes.UINT32,
    "dsl_frame_height": 4 | uctypes.UINT32,
}

def k_vdec_dsl_size_parse(s, kwargs):
    s.dsl_frame_width = kwargs.get("dsl_frame_width", 0)
    s.dsl_frame_height = kwargs.get("dsl_frame_height", 0)

k_vdec_dsl_ratio_desc = {
    "dsl_ratio_hor": 0 | uctypes.UINT8,
    "dsl_ratio_ver": 1 | uctypes.UINT8,
}

def k_vdec_dsl_ratio_parse(s, kwargs):
    s.dsl_ratio_hor = kwargs.get("dsl_ratio_hor", 0)
    s.dsl_ratio_ver = kwargs.get("dsl_ratio_ver", 0)

k_vdec_downscale_desc = {
    "dsl_mode": 0 | uctypes.UINT32,
    "dsl_size": (4, k_vdec_dsl_size_desc),
    "dsl_ratio": (4, k_vdec_dsl_ratio_desc),
}

def k_vdec_downscale_parse(s, kwargs):
    s.dsl_mode = kwargs.get("dsl_mode", 0)
