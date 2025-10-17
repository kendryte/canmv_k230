import uctypes

k_vo_point_desc = {
    "x": 0 | uctypes.UINT32,
    "y": 4 | uctypes.UINT32,
}

def k_vo_point_parse(s, kwargs):
    s.x = kwargs.get("x", 0)
    s.y = kwargs.get("y", 0)

k_vo_size_desc = {
    "width": 0 | uctypes.UINT32,
    "height": 4 | uctypes.UINT32,
}

def k_vo_size_parse(s, kwargs):
    s.width = kwargs.get("width", 0)
    s.height = kwargs.get("height", 0)

k_vo_scaler_attr_desc = {
    "out_size": (0, k_vo_size_desc),
    "stride": 8 | uctypes.UINT32,
}

def k_vo_scaler_attr_parse(s, kwargs):
    out_size = kwargs.get("out_size", {})
    k_vo_size_parse(s.out_size, out_size)
    s.stride = kwargs.get("stride", 0)

k_vo_display_resolution_desc = {
    "pclk": 0 | uctypes.UINT32,
    "phyclk": 4 | uctypes.UINT32,
    "htotal": 8 | uctypes.UINT32,
    "hdisplay": 12 | uctypes.UINT32,
    "hsync_len": 16 | uctypes.UINT32,
    "hback_porch": 20 | uctypes.UINT32,
    "hfront_porch": 24 | uctypes.UINT32,
    "vtotal": 28 | uctypes.UINT32,
    "vdisplay": 32 | uctypes.UINT32,
    "vsync_len": 36 | uctypes.UINT32,
    "vback_porch": 40 | uctypes.UINT32,
    "vfront_porch": 44 | uctypes.UINT32,
}

def k_vo_display_resolution_parse(s, kwargs):
    s.pclk = kwargs.get("pclk", 0)
    s.phyclk = kwargs.get("phyclk", 0)
    s.htotal = kwargs.get("htotal", 0)
    s.hdisplay = kwargs.get("hdisplay", 0)
    s.hsync_len = kwargs.get("hsync_len", 0)
    s.hback_porch = kwargs.get("hback_porch", 0)
    s.hfront_porch = kwargs.get("hfront_porch", 0)
    s.vtotal = kwargs.get("vtotal", 0)
    s.vdisplay = kwargs.get("vdisplay", 0)
    s.vsync_len = kwargs.get("vsync_len", 0)
    s.vback_porch = kwargs.get("vback_porch", 0)
    s.vfront_porch = kwargs.get("vfront_porch", 0)

k_vo_mipi_phy_attr_desc = {
    "n": 0 | uctypes.UINT32,
    "m": 4 | uctypes.UINT32,
    "voc": 8 | uctypes.UINT32,
    "phy_lan_num": 12 | uctypes.UINT32,
    "hs_freq": 16 | uctypes.UINT32,
}

def k_vo_mipi_phy_attr_parse(s, kwargs):
    s.n = kwargs.get("n", 0)
    s.m = kwargs.get("m", 0)
    s.voc = kwargs.get("voc", 0)
    s.phy_lan_num = kwargs.get("phy_lan_num", 0)
    s.hs_freq = kwargs.get("hs_freq", 0)

k_vo_pub_attr_desc = {
    "bg_color": 0 | uctypes.UINT32,
    "intf_type": 4 | uctypes.UINT32,
    "intf_sync": 8 | uctypes.UINT32,
    "sync_info": 16 | uctypes.UINT64,
    "_sync_info": (16 | uctypes.PTR, k_vo_display_resolution_desc),
}

def k_vo_pub_attr_parse(s, kwargs):
    s.bg_color = kwargs.get("bg_color", 0)
    s.intf_type = kwargs.get("intf_type", 0)
    s.intf_sync = kwargs.get("intf_sync", 0)
    s.sync_info = kwargs.get("sync_info", 0)

k_vo_user_sync_info_desc = {
    "pre_div": 0 | uctypes.UINT32,
    "clk_en": 4 | uctypes.UINT32,
}

def k_vo_user_sync_info_parse(s, kwargs):
    s.pre_div = kwargs.get("pre_div", 0)
    s.clk_en = kwargs.get("clk_en", 0)

k_vo_wbc_attr_desc = {
    "blk_cnt": 0 | uctypes.UINT32,
    "dump_size": (4, k_vo_size_desc),
}

def k_vo_wbc_attr_parse(s, kwargs):
    target_size = kwargs.get("target_size", {})
    k_vo_size_parse(s.target_size, target_size)
    s.pixel_format = kwargs.get("pixel_format", 0)
    s.stride = kwargs.get("stride", 0)
    s.y_phy_addr = kwargs.get("y_phy_addr", 0)

k_vo_dsi_attr_desc = {
    "resolution": (0, k_vo_display_resolution_desc),
    "lan_num": 48 | uctypes.UINT32,
    "cmd_mode": 52 | uctypes.UINT32,
    "work_mode": 56 | uctypes.UINT32,
    "lp_div": 60 | uctypes.UINT32,
}

def k_vo_dsi_attr_parse(s, kwargs):
    resolution = kwargs.get("resolution", {})
    k_vo_display_resolution_parse(s.resolution, resolution)
    s.lan_num = kwargs.get("lan_num", 0)
    s.cmd_mode = kwargs.get("cmd_mode", 0)
    s.work_mode = kwargs.get("work_mode", 0)
    s.lp_div = kwargs.get("lp_div", 0)

k_vo_wbc_frame_attr_desc = {
    "target_size": (0, k_vo_size_desc),
    "pixel_format": 8 | uctypes.UINT32,
    "stride": 12 | uctypes.UINT32,
    "y_phy_addr": 16 | uctypes.UINT64,
}

def k_vo_wbc_frame_attr_parse(s, kwargs):
    target_size = kwargs.get("target_size", {})
    k_vo_size_parse(s.target_size, target_size)
    s.pixel_format = kwargs.get("pixel_format", 0)
    s.stride = kwargs.get("stride", 0)
    s.y_phy_addr = kwargs.get("y_phy_addr", 0)

k_vo_video_layer_attr_desc = {
    "display_rect": (0, k_vo_point_desc),
    "img_size": (8, k_vo_size_desc),
    "pixel_format": 16 | uctypes.UINT32,
    "stride": 20 | uctypes.UINT32,
    "func": 24 | uctypes.UINT32,
    "scaler_attr": (28, k_vo_scaler_attr_desc),
}

def k_vo_video_layer_attr_parse(s, kwargs):
    display_rect = kwargs.get("display_rect", {})
    k_vo_point_parse(s.display_rect, kwargs)
    img_size = kwargs.get("img_size", {})
    k_vo_size_parse(s.img_size, kwargs)
    s.pixel_format = kwargs.get("pixel_format", 0)
    s.stride = kwargs.get("stride", 0)
    s.func = kwargs.get("func", 0)
    scaler_attr = kwargs.get("scaler_attr", {})
    k_vo_scaler_attr_parse(s.scaler_attr, kwargs)

k_vo_video_osd_attr_desc = {
    "display_rect": (0, k_vo_point_desc),
    "img_size": (8, k_vo_size_desc),
    "pixel_format": 16 | uctypes.UINT32,
    "stride": 20 | uctypes.UINT32,
    "global_alpha": 24 | uctypes.UINT8,
}

def k_vo_video_osd_attr_parse(s, kwargs):
    display_rect = kwargs.get("display_rect", {})
    k_vo_point_parse(s.display_rect, kwargs)
    img_size = kwargs.get("img_size", {})
    k_vo_size_parse(s.img_size, kwargs)
    s.pixel_format = kwargs.get("pixel_format", 0)
    s.stride = kwargs.get("stride", 0)
    s.global_alpha = kwargs.get("global_alpha", 0)

k_vo_draw_frame_desc = {
    "draw_en": 0 | uctypes.UINT32,
    "line_x_start": 4 | uctypes.UINT32,
    "line_y_start": 8 | uctypes.UINT32,
    "line_x_end": 12 | uctypes.UINT32,
    "line_y_end": 16 | uctypes.UINT32,
    "frame_num": 20 | uctypes.UINT32,
}

def k_vo_draw_frame_parse(s, kwargs):
    s.draw_en = kwargs.get("draw_en", 0)
    s.line_x_start = kwargs.get("line_x_start", 0)
    s.line_y_start = kwargs.get("line_y_start", 0)
    s.line_x_end = kwargs.get("line_x_end", 0)
    s.line_y_end = kwargs.get("line_y_end", 0)
    s.frame_num = kwargs.get("frame_num", 0)

k_vo_video_layer_attr_p_desc = {
    "layer": 0 | uctypes.UINT32,
    "attr": 8 | uctypes.UINT64,
    "_attr": (8 | uctypes.PTR, k_vo_video_layer_attr_desc),
}

def k_vo_video_layer_attr_p_parse(s, kwargs):
    s.layer = kwargs.get("layer", 0)
    s.attr = kwargs.get("attr", 0)

k_vo_mirror_mode_p_desc = {
    "layer": 0 | uctypes.UINT32,
    "mode": 4 | uctypes.UINT32,
}

def k_vo_mirror_mode_p_parse(s, kwargs):
    s.layer = kwargs.get("layer", 0)
    s.mode = kwargs.get("mode", 0)

k_vo_rotation_p_desc = {
    "layer": 0 | uctypes.UINT32,
    "mode": 4 | uctypes.UINT32,
}

def k_vo_rotation_p_parse(s, kwargs):
    s.layer = kwargs.get("layer", 0)
    s.mode = kwargs.get("mode", 0)

k_vo_gray_p_desc = {
    "layer": 0 | uctypes.UINT32,
    "gray": 4 | uctypes.UINT32,
}

def k_vo_gray_p_parse(s, kwargs):
    s.layer = kwargs.get("layer", 0)
    s.gray = kwargs.get("gray", 0)

k_vo_scaler_attr_p_desc = {
    "layer": 0 | uctypes.UINT32,
    "attr": 8 | uctypes.UINT64,
    "_attr": (8 | uctypes.PTR, k_vo_scaler_attr_desc),
}

def k_vo_scaler_attr_p_parse(s, kwargs):
    s.layer = kwargs.get("layer", 0)
    s.attr = kwargs.get("attr", 0)

k_vo_priority_p_desc = {
    "layer": 0 | uctypes.UINT32,
    "priority": 4 | uctypes.INT32,
}

def k_vo_priority_p_parse(s, kwargs):
    s.layer = kwargs.get("layer", 0)
    s.priority = kwargs.get("priority", 0)

k_vo_layer_pos_p_desc = {
    "layer": 0 | uctypes.UINT32,
    "display_pos": 8 | uctypes.UINT64,
    "_display_pos": (8 | uctypes.PTR, k_vo_point_desc),
}

def k_vo_layer_pos_p_parse(s, kwargs):
    s.layer = kwargs.get("layer", 0)
    s.display_pos = kwargs.get("display_pos", 0)

k_vo_osd_alpha_grade_p_desc = {
    "layer": 0 | uctypes.UINT32,
    "grade": 4 | uctypes.UINT32,
}

def k_vo_osd_alpha_grade_p_parse(s, kwargs):
    s.layer = kwargs.get("layer", 0)
    s.grade = kwargs.get("grade", 0)

k_vo_osd_pix_format_p_desc = {
    "layer": 0 | uctypes.UINT32,
    "format": 4 | uctypes.UINT32,
}

def k_vo_osd_pix_format_p_parse(s, kwargs):
    s.layer = kwargs.get("layer", 0)
    s.format = kwargs.get("format", 0)

k_vo_osd_stride_p_desc = {
    "layer": 0 | uctypes.UINT32,
    "stride": 4 | uctypes.UINT32,
}

def k_vo_osd_stride_p_parse(s, kwargs):
    s.layer = kwargs.get("layer", 0)
    s.stride = kwargs.get("stride", 0)

k_vo_osd_attr_p_desc = {
    "layer": 0 | uctypes.UINT32,
    "attr": 8 | uctypes.UINT64,
    "_attr": (8 | uctypes.PTR, k_vo_video_osd_attr_desc),
}

def k_vo_osd_attr_p_parse(s, kwargs):
    s.layer = kwargs.get("layer", 0)
    s.attr = kwargs.get("attr", 0)

k_vo_osd_rb_swap_p_desc = {
    "layer": 0 | uctypes.UINT32,
    "rb_swap": 4 | uctypes.UINT32,
}

def k_vo_osd_rb_swap_p_parse(s, kwargs):
    s.layer = kwargs.get("layer", 0)
    s.rb_swap = kwargs.get("rb_swap", 0)

k_vo_osd_dma_map_p_desc = {
    "layer": 0 | uctypes.UINT32,
    "map": 4 | uctypes.UINT32,
}

def k_vo_osd_dma_map_p_parse(s, kwargs):
    s.layer = kwargs.get("layer", 0)
    s.map = kwargs.get("map", 0)

k_vo_dsi_send_cmd_p_desc = {
    "data": (0 | uctypes.ARRAY, 100 | uctypes.UINT8),
    "cmd_len": 100 | uctypes.INT32,
}

def k_vo_dsi_send_cmd_p_parse(s, kwargs):
    s.cmd_len = kwargs.get("cmd_len", 0)

k_vo_dsi_read_cmd_p_desc = {
    "send_data": (0 | uctypes.ARRAY, 10 | uctypes.UINT8),
    "rv_data": (10 | uctypes.ARRAY, 10 | uctypes.UINT32),
    "cmd_len": 52 | uctypes.INT32,
}

def k_vo_dsi_read_cmd_p_parse(s, kwargs):
    s.cmd_len = kwargs.get("cmd_len", 0)

k_vo_phyaddr_desc = {
    "layer": 0 | uctypes.UINT32,
    "phy_addr": 8 | uctypes.UINT64,
}

def k_vo_phyaddr_parse(s, kwargs):
    s.layer = kwargs.get("layer", 0)
    s.phy_addr = kwargs.get("phy_addr", 0)
