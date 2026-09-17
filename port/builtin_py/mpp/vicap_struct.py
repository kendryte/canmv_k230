import uctypes
from mpp import vicap_def

VICAP_MIN_FRAME_COUNT = const(3)
VICAP_MAX_FRAME_COUNT = const(10)
VICAP_MCM_FRAME_COUNT = const(4)

VICAP_ALIGN_1K = const(0x400)
VICAP_ALIGN_4K = const(0x1000)

VICAP_CSI0 = const(1)
VICAP_CSI1 = const(2)
VICAP_CSI2 = const(3)

VICAP_IPI1 = const(1)
VICAP_IPI2 = const(2)
VICAP_IPI3 = const(3)

VICAP_PLL0_CLK_DIV4 = const(5)
VICAP_PLL1_CLK_DIV3 = const(8)
VICAP_PLL1_CLK_DIV4 = const(9)

VICAP_MCLK0 = const(1)
VICAP_MCLK1 = const(2)
VICAP_MCLK2 = const(3)

# lane_pref for Sensor()/list_mode() / k_vicap_probe_config (0/1/2 only).
# Not the firmware k_vicap_mipi_lanes hardware enum (C: 2LANE=1, 4LANE=3).
VICAP_MIPI_ANY = const(0)
VICAP_MIPI_2LANE = const(1)
VICAP_MIPI_4LANE = const(2)

VICAP_MIPI_PHY_800M = const(1)
VICAP_MIPI_PHY_1200M = const(2)
VICAP_MIPI_PHY_1600M = const(3)

VICAP_CSI_DATA_TYPE_RAW8 = const(0x2A)
VICAP_CSI_DATA_TYPE_RAW10 = const(0x2B)
VICAP_CSI_DATA_TYPE_RAW12 = const(0x2C)
VICAP_CSI_DATA_TYPE_RAW16 = const(0x2E)

VICAP_CSI_CAMERA_MODE = const(0)
VICAP_CSI_CONTROL_MODE = const(1)

VICAP_FLASH_FOLLOW_STROBE = const(0)
VICAP_FLASH_FOLLOW_STROBE_BASE_PWM = const(1)
VICAP_FLASH_NORMAL_PWM = const(2)
VICAP_FLASH_DISABLE = const(3)

VICAP_VI_DVP_PORT0 = const(0)
VICAP_VI_DVP_PORT1 = const(1)
VICAP_VI_DVP_PORT2 = const(2)
VICAP_VI_DVP_PORT_MAX = const(3)

VICAP_SOURCE_CSI0 = const(0)
VICAP_SOURCE_CSI1 = const(1)
VICAP_SOURCE_CSI1_FS_TR0 = const(2)
VICAP_SOURCE_CSI1_FS_TR1 = const(3)
VICAP_SOURCE_CSI2 = const(4)

VICAP_VCID_HDR_2FRAME = const(0)
VICAP_VCID_HDR_3FRAME = const(1)
VICAP_SONY_HDR_3FRAME = const(2)
VICAP_SONY_HDR_2FRAME = const(3)
VICAP_LINERA_MODE = const(4)

VICAP_VI_FIRST_FRAME_FS_TR0 = const(0)
VICAP_VI_FIRST_FRAME_FS_TR1 = const(1)

VICAP_WORK_ONLINE_MODE = const(0)
VICAP_WORK_OFFLINE_MODE = const(1)
VICAP_WORK_LOAD_IMAGE_MODE = const(2)
VICAP_WORK_ONLY_MCM_MODE = const(3)
VICAP_WORK_SW_TILE_MODE = const(4)
VICAP_WORK_MCM_MIPI_MODE = const(5)

VICAP_INPUT_TYPE_SENSOR = const(0)
VICAP_INPUT_TYPE_IMAGE = const(1)

VICAP_DEV_ID_0 = const(0)
VICAP_DEV_ID_1 = const(1)
VICAP_DEV_ID_2 = const(2)
VICAP_DEV_ID_MAX = const(3)

VICAP_CHN_ID_0 = const(0)
VICAP_CHN_ID_1 = const(1)
VICAP_CHN_ID_2 = const(2)
VICAP_CHN_ID_MAX = const(3)

VICAP_DUMP_YUV = const(0)
VICAP_DUMP_RGB = const(1)
VICAP_DUMP_RAW = const(2)

VICAP_DATABASE_PARSE_XML_JSON = const(0)
VICAP_DATABASE_PARSE_HEADER = const(1)

STC_27M_CLK = const(0)
STC_1M_CLK = const(1)
STC_90K_CLK = const(2)

def VICAP_ALIGN_UP(addr, size):
    return ((addr) + ((size) - 1)) & (~((size) - 1))

def k_vicap_mclk(**kwargs):
    layout = uctypes.NATIVE
    buf = bytearray(uctypes.sizeof(vicap_def.k_vicap_mclk_desc, layout))
    s = uctypes.struct(uctypes.addressof(buf), vicap_def.k_vicap_mclk_desc, layout)
    vicap_def.k_vicap_mclk_parse(s, kwargs)
    return s

def k_vicap_flash_ctrl(**kwargs):
    layout = uctypes.NATIVE
    buf = bytearray(uctypes.sizeof(vicap_def.k_vicap_flash_ctrl_desc, layout))
    s = uctypes.struct(uctypes.addressof(buf), vicap_def.k_vicap_flash_ctrl_desc, layout)
    vicap_def.k_vicap_flash_ctrl_parse(s, kwargs)
    return s

def k_vicap_vi_ipi_attr(**kwargs):
    layout = uctypes.NATIVE
    buf = bytearray(uctypes.sizeof(vicap_def.k_vicap_vi_ipi_attr_desc, layout))
    s = uctypes.struct(uctypes.addressof(buf), vicap_def.k_vicap_vi_ipi_attr_desc, layout)
    vicap_def.k_vicap_vi_ipi_attr_parse(s, kwargs)
    return s

def k_vicap_window(**kwargs):
    layout = uctypes.NATIVE
    buf = bytearray(uctypes.sizeof(vicap_def.k_vicap_window_desc, layout))
    s = uctypes.struct(uctypes.addressof(buf), vicap_def.k_vicap_window_desc, layout)
    vicap_def.k_vicap_window_parse(s, kwargs)
    return s

def k_vicap_isp_pipe_ctrl(**kwargs):
    layout = uctypes.NATIVE
    buf = bytearray(uctypes.sizeof(vicap_def.k_vicap_isp_pipe_ctrl_desc, layout))
    s = uctypes.struct(uctypes.addressof(buf), vicap_def.k_vicap_isp_pipe_ctrl_desc, layout)
    vicap_def.k_vicap_isp_pipe_ctrl_parse(s, kwargs)
    return s

def k_vicap_sensor_info(**kwargs):
    layout = uctypes.NATIVE
    buf = bytearray(uctypes.sizeof(vicap_def.k_vicap_sensor_info_desc, layout))
    s = uctypes.struct(uctypes.addressof(buf), vicap_def.k_vicap_sensor_info_desc, layout)
    vicap_def.k_vicap_sensor_info_parse(s, kwargs)
    return s

def k_vicap_chn_attr(**kwargs):
    layout = uctypes.NATIVE
    buf = bytearray(uctypes.sizeof(vicap_def.k_vicap_chn_attr_desc, layout))
    s = uctypes.struct(uctypes.addressof(buf), vicap_def.k_vicap_chn_attr_desc, layout)
    vicap_def.k_vicap_chn_attr_parse(s, kwargs)
    return s

def k_vicap_dev_attr(**kwargs):
    layout = uctypes.NATIVE
    buf = bytearray(uctypes.sizeof(vicap_def.k_vicap_dev_attr_desc, layout))
    s = uctypes.struct(uctypes.addressof(buf), vicap_def.k_vicap_dev_attr_desc, layout)
    vicap_def.k_vicap_dev_attr_parse(s, kwargs)
    return s

def k_vicap_sensor_attr(**kwargs):
    layout = uctypes.NATIVE
    buf = bytearray(uctypes.sizeof(vicap_def.k_vicap_sensor_attr_desc, layout))
    s = uctypes.struct(uctypes.addressof(buf), vicap_def.k_vicap_sensor_attr_desc, layout)
    vicap_def.k_vicap_sensor_attr_parse(s, kwargs)
    return s

def k_vicap_timerstamp(**kwargs):
    layout = uctypes.NATIVE
    buf = bytearray(uctypes.sizeof(vicap_def.k_vicap_timerstamp_desc, layout))
    s = uctypes.struct(uctypes.addressof(buf), vicap_def.k_vicap_timerstamp_desc, layout)
    vicap_def.k_vicap_timerstamp_parse(s, kwargs)
    return s

def k_vicap_drop_frame(**kwargs):
    layout = uctypes.NATIVE
    buf = bytearray(uctypes.sizeof(vicap_def.k_vicap_drop_frame_desc, layout))
    s = uctypes.struct(uctypes.addressof(buf), vicap_def.k_vicap_drop_frame_desc, layout)
    vicap_def.k_vicap_drop_frame_parse(s, kwargs)
    return s

def k_vicap_vb_info(**kwargs):
    layout = uctypes.NATIVE
    buf = bytearray(uctypes.sizeof(vicap_def.k_vicap_vb_info_desc, layout))
    s = uctypes.struct(uctypes.addressof(buf), vicap_def.k_vicap_vb_info_desc, layout)
    vicap_def.k_vicap_vb_info_parse(s, kwargs)
    return s

def k_vicap_attr_info(**kwargs):
    layout = uctypes.NATIVE
    buf = bytearray(uctypes.sizeof(vicap_def.k_vicap_attr_info_desc, layout))
    s = uctypes.struct(uctypes.addressof(buf), vicap_def.k_vicap_attr_info_desc, layout)
    vicap_def.k_vicap_attr_info_parse(s, kwargs)
    return s

def k_vicap_dev_set_info(**kwargs):
    layout = uctypes.NATIVE
    buf = bytearray(uctypes.sizeof(vicap_def.k_vicap_dev_set_info_desc, layout))
    s = uctypes.struct(uctypes.addressof(buf), vicap_def.k_vicap_dev_set_info_desc, layout)
    vicap_def.k_vicap_dev_set_info_parse(s, kwargs)
    return s

def k_vicap_chn_set_info(**kwargs):
    layout = uctypes.NATIVE
    buf = bytearray(uctypes.sizeof(vicap_def.k_vicap_chn_set_info_desc, layout))
    s = uctypes.struct(uctypes.addressof(buf), vicap_def.k_vicap_chn_set_info_desc, layout)
    vicap_def.k_vicap_chn_set_info_parse(s, kwargs)
    return s

def k_vicap_probe_config(**kwargs):
    layout = uctypes.NATIVE
    buf = bytearray(uctypes.sizeof(vicap_def.k_vicap_probe_config_desc, layout))
    s = uctypes.struct(uctypes.addressof(buf), vicap_def.k_vicap_probe_config_desc, layout)
    vicap_def.k_vicap_probe_config_parse(s, kwargs)
    return s

def k_sensor_gain(**kwargs):
    layout = uctypes.NATIVE
    buf = bytearray(uctypes.sizeof(vicap_def.k_sensor_gain_desc, layout))
    s = uctypes.struct(uctypes.addressof(buf), vicap_def.k_sensor_gain_desc, layout)
    vicap_def.k_sensor_gain_parse(s, kwargs)
    return s
