import uctypes
from mpp import connector_def

HX8399_V2_MIPI_4LAN_1080X1920_30FPS = const(0)
ILI9806_MIPI_2LAN_480X800_30FPS     = const(1)
ILI9881_MIPI_4LAN_800X1280_60FPS    = const(2)
NT35516_MIPI_2LAN_536X960_30FPS     = const(5)
NT35532_MIPI_2LAN_1080X1920_30FPS   = const(6)
GC9503_MIPI_2LAN_480X800_60FPS      = const(7)
ST7102_MIPI_2LAN_480X640_60FPS      = const(8)
AML020T_MIPI_2LAN_480X360_30FPS     = const(9)

ST7701_V1_MIPI_2LAN_480X800_30FPS   = const(20)
ST7701_V1_MIPI_2LAN_480X854_30FPS   = const(21)
ST7701_V1_MIPI_2LAN_480X640_30FPS   = const(22)
ST7701_V1_MIPI_2LAN_368X544_60FPS   = const(23)

LT9611_MIPI_4LAN_1920X1080_30FPS    = const(101)
LT9611_MIPI_4LAN_1920X1080_60FPS    = const(102)
LT9611_MIPI_4LAN_1280X720_60FPS     = const(110)
LT9611_MIPI_4LAN_1280X720_50FPS     = const(111)
LT9611_MIPI_4LAN_1280X720_30FPS     = const(112)
LT9611_MIPI_4LAN_640X480_60FPS      = const(120)

DSI_VIRTUAL_DEVICE                  = const(200)
DSI_DEBUGGER_DEVICE                 = const(201)

def k_connectori_phy_attr(**kwargs):
    layout = uctypes.NATIVE
    buf = bytearray(uctypes.sizeof(connector_def.k_connectori_phy_attr_desc, layout))
    s = uctypes.struct(uctypes.addressof(buf), connector_def.k_connectori_phy_attr_desc, layout)
    connector_def.k_connectori_phy_attr_parse(s, kwargs)
    return s

def k_connector_info(**kwargs):
    layout = uctypes.NATIVE
    buf = bytearray(uctypes.sizeof(connector_def.k_connector_info_desc, layout))
    s = uctypes.struct(uctypes.addressof(buf), connector_def.k_connector_info_desc, layout)
    connector_def.k_connector_info_parse(s, kwargs)
    return s
