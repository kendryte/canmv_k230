import uctypes

k_vicap_mclk_desc = {
    "id": 0 | uctypes.UINT32,
    "mclk_sel": 4 | uctypes.UINT32,
    "mclk_div": 8 | uctypes.UINT8,
    "mclk_en": 9 | uctypes.UINT8,
}

def k_vicap_mclk_parse(s, kwargs):
    s.id = kwargs.get("id", 0)
    s.mclk_sel = kwargs.get("mclk_sel", 0)
    s.mclk_div = kwargs.get("mclk_div", 0)
    s.mclk_en = kwargs.get("mclk_en", 0)

k_vicap_flash_ctrl_desc = {
    "is_3d_mode": 0 | uctypes.UINT32,
    "sensor_sel": 4 | uctypes.UINT32,
    "flash_mode": 8 | uctypes.UINT32,
    "first_frame": 12 | uctypes.UINT32,
    "glitch_filter": 16 | uctypes.UINT16,
}

def k_vicap_flash_ctrl_parse(s, kwargs):
    s.is_3d_mode = kwargs.get("is_3d_mode", 0)
    s.sensor_sel = kwargs.get("sensor_sel", 0)
    s.flash_mode = kwargs.get("flash_mode", 0)
    s.first_frame = kwargs.get("first_frame", 0)
    s.glitch_filter = kwargs.get("glitch_filter", 0)

k_vicap_vi_ipi_attr_desc = {
    "work_mode": 0 | uctypes.UINT32,
    "data_type": 4 | uctypes.UINT32,
    "is_csi_sync_event": 8 | uctypes.UINT32,
    "hsa": 12 | uctypes.UINT32,
    "hbp": 16 | uctypes.UINT32,
}

def k_vicap_vi_ipi_attr_parse(s, kwargs):
    s.work_mode = kwargs.get("work_mode", 0)
    s.data_type = kwargs.get("data_type", 0)
    s.is_csi_sync_event = kwargs.get("is_csi_sync_event", 0)
    s.hsa = kwargs.get("hsa", 0)
    s.hbp = kwargs.get("hbp", 0)

k_vicap_window_desc = {
    "h_start": 0 | uctypes.UINT16,
    "v_start": 2 | uctypes.UINT16,
    "width": 4 | uctypes.UINT16,
    "height": 6 | uctypes.UINT16,
}

def k_vicap_window_parse(s, kwargs):
    s.h_start = kwargs.get("h_start", 0)
    s.v_start = kwargs.get("v_start", 0)
    s.width = kwargs.get("width", 0)
    s.height = kwargs.get("height", 0)

k_vicap_isp_pipe_ctrl_bits_desc = {
    "ae_enable": 0 | uctypes.BFUINT32 | 0 << uctypes.BF_POS | 1 << uctypes.BF_LEN,
    "af_enable": 0 | uctypes.BFUINT32 | 1 << uctypes.BF_POS | 1 << uctypes.BF_LEN,
    "ahdr_enable": 0 | uctypes.BFUINT32 | 2 << uctypes.BF_POS | 1 << uctypes.BF_LEN,
    "awb_enable": 0 | uctypes.BFUINT32 | 3 << uctypes.BF_POS | 1 << uctypes.BF_LEN,
    "ccm_enable": 0 | uctypes.BFUINT32 | 4 << uctypes.BF_POS | 1 << uctypes.BF_LEN,
    "compress_enable": 0 | uctypes.BFUINT32 | 5 << uctypes.BF_POS | 1 << uctypes.BF_LEN,
    "expand_enable": 0 | uctypes.BFUINT32 | 6 << uctypes.BF_POS | 1 << uctypes.BF_LEN,
    "cnr_enable": 0 | uctypes.BFUINT32 | 7 << uctypes.BF_POS | 1 << uctypes.BF_LEN,
    "ynr_enable": 0 | uctypes.BFUINT32 | 8 << uctypes.BF_POS | 1 << uctypes.BF_LEN,
    "cproc_enable": 0 | uctypes.BFUINT32 | 9 << uctypes.BF_POS | 1 << uctypes.BF_LEN,
    "dci_enable": 0 | uctypes.BFUINT32 | 10 << uctypes.BF_POS | 1 << uctypes.BF_LEN,
    "demosaic_enable": 0 | uctypes.BFUINT32 | 11 << uctypes.BF_POS | 1 << uctypes.BF_LEN,
    "dg_enable": 0 | uctypes.BFUINT32 | 12 << uctypes.BF_POS | 1 << uctypes.BF_LEN,
    "dpcc_enable": 0 | uctypes.BFUINT32 | 13 << uctypes.BF_POS | 1 << uctypes.BF_LEN,
    "dpf_enable": 0 | uctypes.BFUINT32 | 14 << uctypes.BF_POS | 1 << uctypes.BF_LEN,
    "ee_enable": 0 | uctypes.BFUINT32 | 15 << uctypes.BF_POS | 1 << uctypes.BF_LEN,
    "gc_enable": 0 | uctypes.BFUINT32 | 16 << uctypes.BF_POS | 1 << uctypes.BF_LEN,
    "ge_enable": 0 | uctypes.BFUINT32 | 17 << uctypes.BF_POS | 1 << uctypes.BF_LEN,
    "gtm_enable": 0 | uctypes.BFUINT32 | 18 << uctypes.BF_POS | 1 << uctypes.BF_LEN,
    "lsc_enable": 0 | uctypes.BFUINT32 | 19 << uctypes.BF_POS | 1 << uctypes.BF_LEN,
    "lut3d_enable": 0 | uctypes.BFUINT32 | 20 << uctypes.BF_POS | 1 << uctypes.BF_LEN,
    "pdaf_enable": 0 | uctypes.BFUINT32 | 21 << uctypes.BF_POS | 1 << uctypes.BF_LEN,
    "rgbir_enable": 0 | uctypes.BFUINT32 | 22 << uctypes.BF_POS | 1 << uctypes.BF_LEN,
    "wb_enable": 0 | uctypes.BFUINT32 | 23 << uctypes.BF_POS | 1 << uctypes.BF_LEN,
    "wdr_enable": 0 | uctypes.BFUINT32 | 24 << uctypes.BF_POS | 1 << uctypes.BF_LEN,
    "dnr3_enable": 0 | uctypes.BFUINT32 | 25 << uctypes.BF_POS | 1 << uctypes.BF_LEN,
    "dnr2_enable": 0 | uctypes.BFUINT32 | 26 << uctypes.BF_POS | 1 << uctypes.BF_LEN,
    "roi_enable": 0 | uctypes.BFUINT32 | 27 << uctypes.BF_POS | 1 << uctypes.BF_LEN,
    "reserved_enable": 0 | uctypes.BFUINT32 | 28 << uctypes.BF_POS | 4 << uctypes.BF_LEN,
}

k_vicap_isp_pipe_ctrl_desc = {
    "bits": (0, k_vicap_isp_pipe_ctrl_bits_desc),
    "data": 0 | uctypes.UINT32,
}

def k_vicap_isp_pipe_ctrl_parse(s, kwargs):
    s.data = kwargs.get("data", 0)

k_vicap_sensor_info_desc = {
    "name": 0 | uctypes.UINT64,
    "dbname": 8 | uctypes.UINT64,
    "width": 8+8 | uctypes.UINT16,
    "height": 10+8 | uctypes.UINT16,
    "csi_num": 12+8 | uctypes.UINT32,
    "mipi_lanes": 16+8 | uctypes.UINT32,
    "source_id": 20+8 | uctypes.UINT32,
    "is_3d_sensor": 24+8 | uctypes.UINT32,
    "phy_freq": 28+8 | uctypes.UINT32,
    "data_type": 32+8 | uctypes.UINT32,
    "hdr_mode": 36+8 | uctypes.UINT32,
    "flash_mode": 40+8 | uctypes.UINT32,
    "first_frame": 44+8 | uctypes.UINT32,
    "glitch_filter": 48+8 | uctypes.UINT16,
    "fps": 50+8 | uctypes.UINT16,
    "type": 52+8 | uctypes.UINT32,
}

def k_vicap_sensor_info_parse(s, kwargs):
    s.name = kwargs.get("name", 0)
    s.dbname = kwargs.get("dbname", 0)
    s.width = kwargs.get("width", 0)
    s.height = kwargs.get("height", 0)
    s.csi_num = kwargs.get("csi_num", 0)
    s.mipi_lanes = kwargs.get("mipi_lanes", 0)
    s.source_id = kwargs.get("source_id", 0)
    s.is_3d_sensor = kwargs.get("is_3d_sensor", 0)
    s.phy_freq = kwargs.get("phy_freq", 0)
    s.data_type = kwargs.get("data_type", 0)
    s.hdr_mode = kwargs.get("hdr_mode", 0)
    s.flash_mode = kwargs.get("flash_mode", 0)
    s.first_frame = kwargs.get("first_frame", 0)
    s.glitch_filter = kwargs.get("glitch_filter", 0)
    s.fps = kwargs.get("fps", 0)
    s.type = kwargs.get("type", 0)

k_vicap_chn_attr_desc = {
    "out_win": (0, k_vicap_window_desc),
    "crop_win": (8, k_vicap_window_desc),
    "scale_win": (16, k_vicap_window_desc),
    "crop_enable": 24 | uctypes.UINT32,
    "scale_enable": 28 | uctypes.UINT32,
    "chn_enable": 32 | uctypes.UINT32,
    "pix_format": 36 | uctypes.UINT32,
    "buffer_num": 40 | uctypes.UINT32,
    "buffer_size": 44 | uctypes.UINT32,
    "buffer_pool_id": 48 | uctypes.UINT32,
    "alignment": 52 | uctypes.UINT8,
    "fps": 53 | uctypes.UINT8,
}

def k_vicap_chn_attr_parse(s, kwargs):
    out_win = kwargs.get("out_win", {})
    k_vicap_window_parse(s.out_win, out_win)
    crop_win = kwargs.get("crop_win", {})
    k_vicap_window_parse(s.crop_win, crop_win)
    scale_win = kwargs.get("scale_win", {})
    k_vicap_window_parse(s.scale_win, scale_win)
    s.crop_enable = kwargs.get("crop_enable", 0)
    s.scale_enable = kwargs.get("scale_enable", 0)
    s.chn_enable = kwargs.get("chn_enable", 0)
    s.pix_format = kwargs.get("pix_format", 0)
    s.buffer_num = kwargs.get("buffer_num", 0)
    s.buffer_size = kwargs.get("buffer_size", 0)
    s.alignment = kwargs.get("alignment", 0)
    s.fps = kwargs.get("fps", 0)

k_vicap_dev_attr_desc = {
    "acq_win": (0, k_vicap_window_desc),
    "mode": 8 | uctypes.UINT32,
    "input_type": 12 | uctypes.UINT32,
    "image_pat": 16 | uctypes.UINT32,
    "pipe_ctrl": (20, k_vicap_isp_pipe_ctrl_desc),
    "cpature_frame": 24 | uctypes.UINT32,
    "sensor_info": (32, k_vicap_sensor_info_desc),
    "dw_enable": 88+8 | uctypes.UINT32,
    "dev_enable": 92+8 | uctypes.UINT32,
    "buffer_num": 96+8 | uctypes.UINT32,
    "buffer_size": 100+8 | uctypes.UINT32,
    "buffer_pool_id": 104+8 | uctypes.UINT32,
    "mirror": 108+8 | uctypes.UINT32,
    "fastboot": 112+8 | uctypes.UINT8
}

def k_vicap_dev_attr_parse(s, kwargs):
    acq_win = kwargs.get("acq_win", {})
    k_vicap_window_parse(s.acq_win, acq_win)
    s.mode = kwargs.get("mode", 0)
    s.input_type = kwargs.get("input_type", 0)
    s.image_pat = kwargs.get("image_pat", 0)
    pipe_ctrl = kwargs.get("pipe_ctrl", {})
    k_vicap_isp_pipe_ctrl_parse(s.pipe_ctrl, pipe_ctrl)
    s.cpature_frame = kwargs.get("cpature_frame", 0)
    sensor_info = kwargs.get("sensor_info", {})
    k_vicap_sensor_info_parse(s.sensor_info, sensor_info)
    s.dw_enable = kwargs.get("dw_enable", 0)
    s.dev_enable = kwargs.get("dev_enable", 0)
    s.buffer_num = kwargs.get("buffer_num", 0)
    s.buffer_size = kwargs.get("buffer_size", 0)
    s.mirror = kwargs.get("mirror", 0)
    s.fastboot = kwargs.get("fastboot", 0)

k_vicap_sensor_attr_desc = {
    "dev_num": 0 | uctypes.UINT32,
    "chn_num": 4 | uctypes.UINT32,
    "sensor_fd": 8 | uctypes.INT32,
}

def k_vicap_sensor_attr_parse(s, kwargs):
    s.dev_num = kwargs.get("dev_num", 0)
    s.chn_num = kwargs.get("chn_num", 0)
    s.sensor_fd = kwargs.get("sensor_fd", 0)

k_vicap_timerstamp_desc = {
    "stc_mode": 0 | uctypes.UINT32,
    "is_clear": 4 | uctypes.UINT32,
    "is_open": 8 | uctypes.UINT32,
    "load_new_val": 12 | uctypes.UINT32,
    "mode": 16 | uctypes.UINT32,
}

def k_vicap_timerstamp_parse(s, kwargs):
    s.stc_mode = kwargs.get("stc_mode", 0)
    s.is_clear = kwargs.get("is_clear", 0)
    s.is_open = kwargs.get("is_open", 0)
    s.load_new_val = kwargs.get("load_new_val", 0)
    s.mode = kwargs.get("mode", 0)

k_vicap_drop_frame_desc = {
    "m": 0 | uctypes.UINT8,
    "n": 1 | uctypes.UINT8,
    "mode": 4 | uctypes.UINT32,
}

def k_vicap_drop_frame_parse(s, kwargs):
    s.m = kwargs.get("m", 0)
    s.n = kwargs.get("n", 0)
    s.mode = kwargs.get("mode", 0)

k_vicap_vb_info_desc = {
    "phys_addr": (0 | uctypes.ARRAY, 3 | uctypes.UINT64),
    "virt_addr": 24 | uctypes.UINT64,
    "pool_id": 32 | uctypes.INT32,
    "dev_num": 36 | uctypes.INT32,
    "chn_num": 40 | uctypes.INT32,
    "width": 44 | uctypes.UINT32,
    "height": 48 | uctypes.UINT32,
    "format": 52 | uctypes.UINT32,
    "alignment": 56 | uctypes.UINT8,
    "fill_light_state": 57 | uctypes.UINT8,
    "frame_num": 60 | uctypes.UINT32,
    "timestamp": 64 | uctypes.UINT64,
}

def k_vicap_vb_info_parse(s, kwargs):
    s.virt_addr = kwargs.get("virt_addr", 0)
    s.pool_id = kwargs.get("pool_id", 0)
    s.dev_num = kwargs.get("dev_num", 0)
    s.chn_num = kwargs.get("chn_num", 0)
    s.width = kwargs.get("width", 0)
    s.height = kwargs.get("height", 0)
    s.format = kwargs.get("format", 0)
    s.alignment = kwargs.get("alignment", 0)
    s.fill_light_state = kwargs.get("fill_light_state", 0)
    s.frame_num = kwargs.get("frame_num", 0)
    s.timestamp = kwargs.get("timestamp", 0)

k_vicap_attr_info_desc = {
    "vicap_dev": 0 | uctypes.UINT32,
    "vicap_chn": 4 | uctypes.UINT32,
    "sensor_type": 8 | uctypes.UINT32,
    "out_width": 12 | uctypes.UINT32,
    "out_height": 16 | uctypes.UINT32,
    "pixel_format": 20 | uctypes.UINT32,
    "pipe_ctrl": (24, k_vicap_isp_pipe_ctrl_desc),
    "dw_en": 28 | uctypes.UINT32,
    "crop_en": 32 | uctypes.UINT32,
    "buf_size": 36 | uctypes.UINT32,
}

def k_vicap_attr_info_parse(s, kwargs):
    s.vicap_dev = kwargs.get("vicap_dev", 0)
    s.vicap_chn = kwargs.get("vicap_chn", 0)
    s.sensor_type = kwargs.get("sensor_type", 0)
    s.out_width = kwargs.get("out_width", 0)
    s.out_height = kwargs.get("out_height", 0)
    s.pixel_format = kwargs.get("pixel_format", 0)
    pipe_ctrl = kwargs.get("pipe_ctrl", {})
    k_vicap_isp_pipe_ctrl_parse(s.pipe_ctrl, pipe_ctrl)
    s.dw_en = kwargs.get("dw_en", 0)
    s.crop_en = kwargs.get("crop_en", 0)
    s.buf_size = kwargs.get("buf_size", 0)

k_vicap_dev_set_info_desc = {
    "vicap_dev": 0 | uctypes.UINT32,
    "sensor_type": 4 | uctypes.UINT32,
    "pipe_ctrl": (8, k_vicap_isp_pipe_ctrl_desc),
    "dw_en": 12 | uctypes.UINT32,
}

def k_vicap_dev_set_info_parse(s, kwargs):
    s.vicap_dev = kwargs.get("vicap_dev", 0)
    s.sensor_type = kwargs.get("sensor_type", 0)
    pipe_ctrl = kwargs.get("pipe_ctrl", {})
    k_vicap_isp_pipe_ctrl_parse(s.pipe_ctrl, pipe_ctrl)
    s.dw_en = kwargs.get("dw_en", 0)

k_vicap_chn_set_info_desc = {
    "vicap_dev": 0 | uctypes.UINT32,
    "vicap_chn": 4 | uctypes.UINT32,
    "crop_en": 8 | uctypes.UINT32,
    "scale_en": 12 | uctypes.UINT32,
    "chn_en": 16 | uctypes.UINT32,
    "out_width": 20 | uctypes.UINT32,
    "out_height": 24 | uctypes.UINT32,
    "crop_h_start": 28 | uctypes.UINT32,
    "crop_v_start": 32 | uctypes.UINT32,
    "pixel_format": 36 | uctypes.UINT32,
    "buf_size": 40 | uctypes.UINT32,
    "alignment": 44 | uctypes.UINT8,
}

def k_vicap_chn_set_info_parse(s, kwargs):
    s.vicap_dev = kwargs.get("vicap_dev", 0)
    s.vicap_chn = kwargs.get("vicap_chn", 0)
    s.crop_en = kwargs.get("crop_en", {})
    s.scale_en = kwargs.get("scale_en", 0)
    s.chn_en = kwargs.get("chn_en", 0)
    s.out_width = kwargs.get("out_width", 0)
    s.out_height = kwargs.get("out_height", 0)
    s.crop_h_start = kwargs.get("crop_h_start", 0)
    s.crop_v_start = kwargs.get("crop_v_start", 0)
    s.pixel_format = kwargs.get("pixel_format", 0)
    s.buf_size = kwargs.get("buf_size", 0)
    s.alignment = kwargs.get("alignment", 0)

k_vicap_probe_config_desc = {
    "csi": 0 | uctypes.UINT32,
    "width": 4 | uctypes.UINT32,
    "height": 8 | uctypes.UINT32,
    "fps": 12 | uctypes.UINT32,
    "def_mirror": 16 | uctypes.UINT32,
    "name": (20 | uctypes.ARRAY, 32 | uctypes.UINT8),
}

def k_vicap_probe_config_parse(s, kwargs):
    s.csi = kwargs.get("csi", 0)
    s.width = kwargs.get("width", 0)
    s.height = kwargs.get("height", 0)
    s.fps = kwargs.get("fps", 0)
    s.def_mirror = kwargs.get("def_mirror", 0)
    s.name[:] = kwargs.get("name", "").encode()

k_sensor_gain_desc = {
    "gain": (0 | uctypes.ARRAY, 4 | uctypes.FLOAT32)  # Offset 0, array of 4 floats
}

def k_sensor_gain_parse(s, kwargs):
    pass
