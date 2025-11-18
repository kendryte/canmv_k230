import uctypes

k_venc_attr_desc = {
    "type": 0 | uctypes.UINT32,
    "pic_width": 4 | uctypes.UINT32,
    "pic_height": 8 | uctypes.UINT32,
    "profile": 12 | uctypes.UINT32,
}

def k_venc_attr_parse(s, kwargs):
    s.type = kwargs.get("type", 0)
    s.pic_width = kwargs.get("pic_width", 0)
    s.pic_height = kwargs.get("pic_height", 0)
    s.profile = kwargs.get("profile", 0)

k_venc_cbr_desc = {
    "gop": 0 | uctypes.UINT32,
    "stats_time": 4 | uctypes.UINT32,
    "src_frame_rate": 8 | uctypes.UINT32,
    "dst_frame_rate": 12 | uctypes.UINT32,
    "bit_rate": 16 | uctypes.UINT32,
}

def k_venc_cbr_parse(s, kwargs):
    s.gop = kwargs.get("gop", 0)
    s.stats_time = kwargs.get("stats_time", 0)
    s.src_frame_rate = kwargs.get("src_frame_rate", 0)
    s.dst_frame_rate = kwargs.get("dst_frame_rate", 0)
    s.bit_rate = kwargs.get("bit_rate", 0)

k_venc_vbr_desc = {
    "gop": 0 | uctypes.UINT32,
    "stats_time": 4 | uctypes.UINT32,
    "src_frame_rate": 8 | uctypes.UINT32,
    "dst_frame_rate": 12 | uctypes.UINT32,
    "max_bit_rate": 16 | uctypes.UINT32,
    "bit_rate": 20 | uctypes.UINT32,
}

def k_venc_vbr_parse(s, kwargs):
    s.gop = kwargs.get("gop", 0)
    s.stats_time = kwargs.get("stats_time", 0)
    s.src_frame_rate = kwargs.get("src_frame_rate", 0)
    s.dst_frame_rate = kwargs.get("dst_frame_rate", 0)
    s.max_bit_rate = kwargs.get("max_bit_rate", 0)
    s.bit_rate = kwargs.get("bit_rate", 0)

k_venc_fixqp_desc = {
    "gop": 0 | uctypes.UINT32,
    "src_frame_rate": 4 | uctypes.UINT32,
    "dst_frame_rate": 8 | uctypes.UINT32,
    "i_qp": 12 | uctypes.UINT32,
    "p_qp": 16 | uctypes.UINT32,
}

def k_venc_fixqp_parse(s, kwargs):
    s.gop = kwargs.get("gop", 0)
    s.src_frame_rate = kwargs.get("src_frame_rate", 0)
    s.dst_frame_rate = kwargs.get("dst_frame_rate", 0)
    s.i_qp = kwargs.get("i_qp", 0)
    s.p_qp = kwargs.get("p_qp", 0)

k_venc_mjpeg_fixqp_desc = {
    "src_frame_rate": 0 | uctypes.UINT32,
    "dst_frame_rate": 4 | uctypes.UINT32,
    "q_factor": 8 | uctypes.UINT32,
}

def k_venc_mjpeg_fixqp_parse(s, kwargs):
    s.src_frame_rate = kwargs.get("src_frame_rate", 0)
    s.dst_frame_rate = kwargs.get("dst_frame_rate", 0)
    s.q_factor = kwargs.get("q_factor", 0)

k_venc_rc_attr_desc = {
    "rc_mode": 0 | uctypes.UINT32,
    "cbr": (4, k_venc_cbr_desc),
    "vbr": (4, k_venc_vbr_desc),
    "fixqp": (4, k_venc_fixqp_desc),
    "mjpeg_fixqp": (4, k_venc_mjpeg_fixqp_desc),
}

def k_venc_rc_attr_parse(s, kwargs):
    s.rc_mode = kwargs.get("rc_mode", 0)

k_venc_chn_attr_desc = {
    "venc_attr": (0, k_venc_attr_desc),
    "rc_attr": (16, k_venc_rc_attr_desc),
}

def k_venc_chn_attr_parse(s, kwargs):
    pass

k_venc_pack_desc = {
    "phys_addr": 0 | uctypes.UINT64,
    "len": 8 | uctypes.UINT32,
    "pts": 16 | uctypes.UINT64,
    "type": 24 | uctypes.UINT32,
}

def k_venc_pack_parse(s, kwargs):
    s.phys_addr = kwargs.get("phys_addr", 0)
    s.len = kwargs.get("len", 0)
    s.pts = kwargs.get("pts", 0)
    s.type = kwargs.get("type", 0)

k_venc_stream_desc = {
    "pack": 0 | uctypes.UINT64,
    "_pack": (0 | uctypes.PTR, k_venc_pack_desc),
    "pack_cnt": 8 | uctypes.UINT32,
}

def k_venc_stream_parse(s, kwargs):
    s.pack = kwargs.get("pack", 0)
    s.pack_cnt = kwargs.get("pack_cnt", 0)

k_venc_stream_info_desc = {
    "u32PicBytesNum": 0 | uctypes.UINT32,
    "u32PicCnt": 4 | uctypes.UINT32,
    "u32StartQp": 8 | uctypes.UINT32,
    "u32MeanQp": 12 | uctypes.UINT32,
}

def k_venc_stream_info_parse(s, kwargs):
    s.u32PicBytesNum = kwargs.get("u32PicBytesNum", 0)
    s.u32PicCnt = kwargs.get("u32PicCnt", 0)
    s.u32StartQp = kwargs.get("u32StartQp", 0)
    s.u32MeanQp = kwargs.get("u32MeanQp", 0)

k_venc_chn_status_desc = {
    "cur_packs": 0 | uctypes.UINT32,
    "release_pic_pts": 8 | uctypes.UINT64,
    "end_of_stream": 16 | uctypes.UINT32,
    "stream_info": (24, k_venc_stream_info_desc),
}

def k_venc_chn_status_parse(s, kwargs):
    s.cur_packs = kwargs.get("cur_packs", 0)
    s.release_pic_pts = kwargs.get("release_pic_pts", 0)
    s.end_of_stream = kwargs.get("end_of_stream", 0)
    stream_info = kwargs.get("stream_info", {})
    k_venc_stream_info_parse(s.stream_info, stream_info)

k_venc_h265_sao_desc = {
    "slice_sao_luma_flag": 0 | uctypes.UINT32,
    "slice_sao_chroma_flag": 4 | uctypes.UINT32,
}

def k_venc_h265_sao_parse(s, kwargs):
    s.slice_sao_luma_flag = kwargs.get("slice_sao_luma_flag", 0)
    s.slice_sao_chroma_flag = kwargs.get("slice_sao_chroma_flag", 0)

k_venc_rect_desc = {
    "left": 0 | uctypes.UINT32,
    "right": 4 | uctypes.UINT32,
    "top": 8 | uctypes.UINT32,
    "bottom": 12 | uctypes.UINT32,
}

def k_venc_rect_parse(s, kwargs):
    s.left = kwargs.get("left", 0)
    s.right = kwargs.get("right", 0)
    s.top = kwargs.get("top", 0)
    s.bottom = kwargs.get("bottom", 0)

k_venc_roi_attr_desc = {
    "idx": 0 | uctypes.UINT32,
    "enable": 4 | uctypes.UINT32,
    "is_abs_qp": 8 | uctypes.UINT32,
    "qp": 12 | uctypes.UINT32,
    "rect": (16, k_venc_rect_desc),
}

def k_venc_roi_attr_parse(s, kwargs):
    s.idx = kwargs.get("idx", 0)
    s.enable = kwargs.get("enable", 0)
    s.is_abs_qp = kwargs.get("is_abs_qp", 0)
    s.qp = kwargs.get("qp", 0)
    rect = kwargs.get("rect", {})
    k_venc_rect_parse(s.rect, rect)

k_venc_h264_entropy_desc = {
    "entropy_coding_mode": 0 | uctypes.UINT32,
    "cabac_init_idc": 4 | uctypes.UINT8,
}

def k_venc_h264_entropy_parse(s, kwargs):
    s.entropy_coding_mode = kwargs.get("entropy_coding_mode", 0)
    s.cabac_init_idc = kwargs.get("cabac_init_idc", 0)

k_venc_h265_entropy_desc = {
    "cabac_init_flag": 0 | uctypes.UINT8,
}

def k_venc_h265_entropy_parse(s, kwargs):
    s.cabac_init_flag = kwargs.get("cabac_init_flag", 0)

k_venc_2d_csc_attr_desc = {
    "dst_fmt": 0 | uctypes.UINT32,
}

def k_venc_2d_csc_attr_parse(s, kwargs):
    s.dst_fmt = kwargs.get("dst_fmt", 0)

k_venc_2d_osd_attr_desc = {
    "width": 0 | uctypes.UINT16,
    "height": 2 | uctypes.UINT16,
    "startx": 4 | uctypes.UINT16,
    "starty": 6 | uctypes.UINT16,
    "phys_addr": (8 | uctypes.ARRAY, 3 | uctypes.UINT32),
    "bg_alpha": 20 | uctypes.UINT8,
    "osd_alpha": 21 | uctypes.UINT8,
    "video_alpha": 22 | uctypes.UINT8,
    "add_order": 24 | uctypes.UINT32,
    "bg_color": 28 | uctypes.UINT32,
    "fmt": 32 | uctypes.UINT32,
}

def k_venc_2d_osd_attr_parse(s, kwargs):
    s.width = kwargs.get("width", 0)
    s.height = kwargs.get("height", 0)
    s.startx = kwargs.get("startx", 0)
    s.starty = kwargs.get("starty", 0)
    s.phys_addr = kwargs.get("phys_addr", 0)
    s.bg_alpha = kwargs.get("bg_alpha", 0)
    s.osd_alpha = kwargs.get("osd_alpha", 0)
    s.video_alpha = kwargs.get("video_alpha", 0)
    s.add_order = kwargs.get("add_order", 0)
    s.bg_color = kwargs.get("bg_color", 0)
    s.fmt = kwargs.get("fmt", 0)

k_venc_2d_border_attr_desc = {
    "width": 0 | uctypes.UINT16,
    "height": 2 | uctypes.UINT16,
    "line_width": 4 | uctypes.UINT16,
    "color": 8 | uctypes.UINT32,
    "startx": 12 | uctypes.UINT16,
    "starty": 14 | uctypes.UINT16,
}

def k_venc_2d_border_attr_parse(s, kwargs):
    s.width = kwargs.get("width", 0)
    s.height = kwargs.get("height", 0)
    s.line_width = kwargs.get("line_width", 0)
    s.color = kwargs.get("color", 0)
    s.startx = kwargs.get("startx", 0)
    s.starty = kwargs.get("starty", 0)

k_venc_2d_coef_attr_desc = {
    "coef": (0 | uctypes.ARRAY, 12 | uctypes.INT16),
}

def k_venc_2d_coef_attr_parse(s, kwargs):
    pass
