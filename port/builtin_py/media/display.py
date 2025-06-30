from mpp import *
from mpp.connector import *
from mpp.vo import *
from media.media import *
import image
import machine
import os

class Display:
    VIRT            = const(300)
    DEBUGGER        = const(301)
    ST7701          = const(302)
    HX8399          = const(303)
    ILI9806         = const(304)
    LT9611          = const(305)
    ILI9881         = const(306)
    NT35516         = const(307)

    # define VO channel
    LAYER_VIDEO1 = K_VO_DISPLAY_CHN_ID1
    LAYER_VIDEO2 = K_VO_DISPLAY_CHN_ID2
    LAYER_OSD0 = K_VO_DISPLAY_CHN_ID3
    LAYER_OSD1 = K_VO_DISPLAY_CHN_ID4
    LAYER_OSD2 = K_VO_DISPLAY_CHN_ID5
    LAYER_OSD3 = K_VO_DISPLAY_CHN_ID6

    # osd layer support rotate and mirror
    # video layer 1 support all
    # video layer 2 not support any
    FLAG_ROTATION_0        = K_ROTATION_0
    FLAG_ROTATION_90       = K_ROTATION_90
    FLAG_ROTATION_180      = K_ROTATION_180
    FLAG_ROTATION_270      = K_ROTATION_270
    FLAG_MIRROR_NONE       = K_VO_MIRROR_NONE
    FLAG_MIRROR_HOR        = K_VO_MIRROR_HOR
    FLAG_MIRROR_VER        = K_VO_MIRROR_VER
    FLAG_MIRROR_BOTH       = K_VO_MIRROR_BOTH

    # osd layer not support
    FLAG_GRAY_ENABLE       = K_VO_GRAY_ENABLE
    FLAG_GRAY_DISABLE      = K_VO_GRAY_DISABLE

    # only video0 support, but we can't use it
    # FLAG_VO_SCALER_ENABLE  = K_VO_SCALER_ENABLE
    # FLAG_VO_SCALER_DISABLE = K_VO_SCALER_DISABLE

    _is_inited = False
    _osd_layer_num = 1
    _write_back_to_ide = False
    _panel_flag = None

    _width = 0
    _height = 0
    _connector_info = None
    _connector_type = None

    _layer_cfgs = [None for i in range(0, K_VO_MAX_CHN_NUMS)]
    _layer_bind_cfg = [None for i in range(0, K_VO_MAX_CHN_NUMS)]

    _layer_rotate_buffer = None
    _layer_disp_buffers = [None for i in range(0, K_VO_MAX_CHN_NUMS)]
    _layer_configured = [False for i in range(0, K_VO_MAX_CHN_NUMS)]

    class LayerConfig:
        def __init__(self, layer, rect, pix_format, flag, alpha):
            if not isinstance(rect, tuple) or len(rect) != 4:
                raise ValueError("rect should be (x, y, w, h)")
            if not (Display.LAYER_VIDEO1 <= layer <= Display.LAYER_OSD3):
                raise IndexError(f"layer({layer}) out of range")

            self.layer = layer
            self.rect = rect
            self.pix_format = pix_format
            self.flag = flag
            self.alpha = alpha

        def __del__(self):
            pass

        def __eq__(self, o):
            if isinstance(o, Display.LayerConfig):
                if self.layer != o.layer:
                    return False
                if self.rect != o.rect:
                    return False
                if self.pix_format != o.pix_format:
                    return False
                if self.flag != o.flag:
                    return False
                if self.alpha != o.alpha:
                    return False

                return True
            else:
                return False

    class BindConfig:
        def __init__(self, src, dst, layer_config):
            if not isinstance(src, tuple) or len(src) != 3:
                raise ValueError("src should be (mod, dec, layer)")
            if not isinstance(dst, tuple) or len(dst) != 3:
                raise ValueError("dst should be (mod, dec, layer)")

            if not isinstance(layer_config, Display.LayerConfig):
                raise TypeError("layer_config is not Display.LayerConfig")

            self.src = src
            self.dst = dst
            self.layer_config = layer_config

            self.linker = None

        def bind(self):
            self.linker = MediaManager.link(self.src, self.dst)

        def __del__(self):
            self.linker.destroy()

    # src (mod, dev, layer)
    # layer
    # rect (x, y, w, h)
    # pix_format
    # alpha
    # flag
    @classmethod
    def bind_layer(cls, **kwargs):
        # if cls._is_inited:
        #     raise AssertionError("please run Display.bind_layer() before Display.init()")

        src = kwargs.get('src', None)
        if src is None:
            raise ValueError("src should be set")
        if not isinstance(src, tuple) or len(src) != 3:
            raise ValueError(f"src should be (mod, dec, layer)")

        layer = kwargs.get('layer', None)
        layer = layer if layer is not None else Display.LAYER_VIDEO1

        if layer > K_VO_MAX_CHN_NUMS:
            raise IndexError(f"layer({layer}) out of range")

        dst = (DISPLAY_MOD_ID, DISPLAY_DEV_ID, layer)

        rect = kwargs.get('rect', (0, 0, 0, 0)) # w and h set to 0 for unset
        if not isinstance(rect, tuple) or len(rect) != 4:
            raise ValueError("rect should be (x, y, w, h)")

        pix_format = kwargs.get('pix_format', PIXEL_FORMAT_YVU_PLANAR_420)

        alpha = 255
        if 'alpha' in kwargs:
            alpha = kwargs.get('alpha')
            if (Display.LAYER_VIDEO1 <= layer <= Display.LAYER_VIDEO2):
                print(f"layer({layer}) not support alpha, ignore it.")

        brd = os.uname()[-1]
        if brd == "k230d_canmv_atk_dnk230d":
            flag = kwargs.get('flag', Display.FLAG_ROTATION_90)
        else:
            flag = kwargs.get('flag', 0)

        if cls._layer_bind_cfg[layer] is not None:
            cls.unbind_layer(layer)
            cls._layer_bind_cfg[layer] = None
            print(f"bind_layer: layer({layer}) haver been bind, auto unbind it.")

        layer_config = Display.LayerConfig(layer, rect, pix_format, flag, alpha)
        cls._layer_bind_cfg[layer] = Display.BindConfig(src, dst, layer_config)

        if cls._is_inited:
            cls._layer_bind_cfg[layer].bind()

            if (Display.LAYER_VIDEO1 <= layer <= Display.LAYER_VIDEO2):
                cls.__config_video_layer(layer_config)
            elif (Display.LAYER_OSD0 <= layer <= Display.LAYER_OSD3):
                cls._layer_configured[layer] = cls.__config_osd_layer(layer_config)

    @classmethod
    def unbind_layer(cls, layer):
        if isinstance(cls._layer_bind_cfg[layer], Display.BindConfig):
            cls._layer_bind_cfg[layer].__del__()
            cls._layer_bind_cfg[layer] = None
        else:
            print(f"unbind layer({layer}) failed.")

    # type
    # width
    # height
    # to_ide
    # osd_num
    @classmethod
    def init(cls, type = None, width = None, height = None, osd_num = 1, to_ide = False, flag = None, fps = None, quality = 90):
        if cls._is_inited:
            print("Already run Display.init()")
            return

        _type = type
        if _type is None:
            raise ValueError("please run Display.init(type=)")

        cls._osd_layer_num = osd_num
        cls._write_back_to_ide = to_ide

        cls._panel_flag = flag

        if _type >= Display.VIRT:
            if _type == Display.VIRT:
                cls._write_back_to_ide = True
                cls._connector_type = DSI_VIRTUAL_DEVICE
            elif _type == Display.DEBUGGER:
                cls._connector_type = DSI_DEBUGGER_DEVICE
            elif _type == Display.ST7701:
                brd = os.uname()[-1]
                if brd == "k230d_canmv_atk_dnk230d":
                    _width = width if width is not None else 640
                    _height = height if height is not None else 480
                    _flag = flag if flag is not None else Display.FLAG_ROTATION_90
                else:
                    _width = width if width is not None else 800
                    _height = height if height is not None else 480
                    _flag = flag if flag is not None else Display.FLAG_ROTATION_90

                if _width == 800 and _height == 480:
                    cls._panel_flag = _flag
                    cls._connector_type = ST7701_V1_MIPI_2LAN_480X800_30FPS
                elif _width == 480 and _height == 800:
                    cls._connector_type = ST7701_V1_MIPI_2LAN_480X800_30FPS
                elif _width == 854 and _height == 480:
                    cls._panel_flag = _flag
                    cls._connector_type = ST7701_V1_MIPI_2LAN_480X854_30FPS
                elif _width == 480 and _height == 854:
                    cls._connector_type = ST7701_V1_MIPI_2LAN_480X854_30FPS
                elif _width == 640 and _height == 480:
                    cls._panel_flag = _flag
                    cls._connector_type = ST7701_V1_MIPI_2LAN_480X640_30FPS
                elif _width == 480 and _height == 640:
                    cls._connector_type = ST7701_V1_MIPI_2LAN_480X640_30FPS
                elif _width == 368 and _height == 544:
                    cls._connector_type = ST7701_V1_MIPI_2LAN_368X544_60FPS
                elif _width == 544 and _height == 368:
                    cls._panel_flag = _flag
                    cls._connector_type = ST7701_V1_MIPI_2LAN_368X544_60FPS
                else:
                    raise ValueError(f"ST7701 unsupoort {_width}x{_height}")

                _width = None
                _height = None
                _flag = None
            elif _type == Display.HX8399:
                _width = width if width is not None else 1920
                _height = height if height is not None else 1080
                _flag = flag if flag is not None else Display.FLAG_ROTATION_90

                if _width == 1920 and _height == 1080:
                    cls._panel_flag = _flag
                    cls._connector_type = HX8399_V2_MIPI_4LAN_1080X1920_30FPS
                elif _width == 1080 and _height == 1920:
                    cls._connector_type = HX8399_V2_MIPI_4LAN_1080X1920_30FPS
                else:
                    raise ValueError(f"HX8399 unsupoort {_width}x{_height}")

                _width = None
                _height = None
                _flag = None
            elif _type == Display.ILI9806:
                _width = width if width is not None else 800
                _height = height if height is not None else 480
                _flag = flag if flag is not None else Display.FLAG_ROTATION_90

                if _width == 800 and _height == 480:
                    cls._panel_flag = _flag
                    cls._connector_type = ILI9806_MIPI_2LAN_480X800_30FPS
                elif _width == 480 and _height == 800:
                    cls._connector_type = ILI9806_MIPI_2LAN_480X800_30FPS
                else:
                    raise ValueError(f"ILI9806 unsupoort {_width}x{_height}")

                _width = None
                _height = None
                _flag = None
            elif _type == Display.LT9611:
                _width = width if width is not None else 1920
                _height = height if height is not None else 1080
                _fps = fps if fps is not None else 30

                if _width == 1920 and _height == 1080 and _fps == 60:
                    cls._connector_type = LT9611_MIPI_4LAN_1920X1080_60FPS
                # elif _width == 1920 and _height == 1080 and _fps == 50:
                #     cls._connector_type = LT9611_MIPI_4LAN_1920X1080_50FPS
                elif _width == 1920 and _height == 1080 and _fps == 30:
                    cls._connector_type = LT9611_MIPI_4LAN_1920X1080_30FPS
                elif _width == 1280 and _height == 720 and _fps == 60:
                    cls._connector_type = LT9611_MIPI_4LAN_1280X720_60FPS
                elif _width == 1280 and _height == 720 and _fps == 50:
                    cls._connector_type = LT9611_MIPI_4LAN_1280X720_50FPS
                elif _width == 1280 and _height == 720 and _fps == 30:
                    cls._connector_type = LT9611_MIPI_4LAN_1280X720_30FPS
                elif _width == 640 and _height == 480:
                    cls._connector_type = LT9611_MIPI_4LAN_640X480_60FPS
                else:
                    raise ValueError(f"LT9611 unsupoort {_width}x{_height}@{_fps}")

                _width = None
                _height = None
                _fps = None
            elif _type == Display.ILI9881:
                _width = width if width is not None else 1280
                _height = height if height is not None else 800
                _flag = flag if flag is not None else Display.FLAG_ROTATION_90

                if _width == 1280 and _height == 800:
                    cls._panel_flag = _flag
                    cls._connector_type = ILI9881_MIPI_4LAN_800X1280_60FPS
                elif _width == 800 and _height == 1280:
                    cls._connector_type = ILI9881_MIPI_4LAN_800X1280_60FPS
                else:
                    raise ValueError(f"ILI9806 unsupoort {_width}x{_height}")

                _width = None
                _height = None
                _flag = None
            elif _type == Display.NT35516:
                _width = width if width is not None else 960
                _height = height if height is not None else 540
                _flag = flag if flag is not None else Display.FLAG_ROTATION_90

                if _width == 960 and _height == 540:
                    cls._panel_flag = _flag
                    cls._connector_type = NT35516_MIPI_2LAN_540X960_30FPS
                elif _width == 540 and _height == 960:
                    cls._connector_type = NT35516_MIPI_2LAN_540X960_30FPS
                else:
                    raise ValueError(f"NT35516 unsupoort {_width}x{_height}")

                _width = None
                _height = None
                _flag = None
            else:
                raise AssertionError(f"Unsupport display type {_type}")
        else:
            cls._connector_type = _type

        cls._connector_info = k_connector_info()
        ret = kd_mpi_get_connector_info(cls._connector_type, cls._connector_info)
        if ret != 0:
            raise RuntimeError("Get display device info failed.")

        if cls._connector_type == DSI_VIRTUAL_DEVICE:
            _width = width if width is not None else 640
            _height = height if height is not None else 480
            _fps = fps if fps is not None else 90
            if _width & 7:
                raise ValueError("width must be an integral multiple of 8 pixels")
            cls._connector_info.resolution.hdisplay = _width
            cls._connector_info.resolution.vdisplay = _height
            cls._connector_info.resolution.pclk = _fps

        cls._width = cls._connector_info.resolution.hdisplay
        cls._height = cls._connector_info.resolution.vdisplay

        if 0 == cls._width or 0 == cls._height:
            raise RuntimeError(f"Can't open display device or invalid configure for virt display")

        connector_fd = kd_mpi_connector_open(uctypes.string_at(cls._connector_info.connector_name))
        if 0 > connector_fd:
            raise RuntimeError(f"Can't open display device")

        kd_mpi_connector_power_set(connector_fd, 1)
        kd_mpi_connector_init(connector_fd, cls._connector_info)
        kd_mpi_connector_close(connector_fd)

        if cls._connector_type == ST7701_V1_MIPI_2LAN_368X544_60FPS and cls._height == 552:
            cls._height = 544

        if cls._write_back_to_ide:
            config = k_vb_config()
            config.max_pool_cnt = 1
            config.comm_pool[0].blk_size = cls._width * cls._height * 2
            config.comm_pool[0].blk_cnt = 4
            config.comm_pool[0].mode = VB_REMAP_MODE_NOCACHE

            # configure buffer for image compress in media.init()
            # config.comm_pool[1].blk_size = (cls._width * cls._height + 0xfff) & ~0xfff
            # config.comm_pool[1].blk_cnt = 2
            # config.comm_pool[1].mode = VB_REMAP_MODE_NOCACHE

            # for vo_wbc rotate
            # if cls._panel_flag != None:
            #     config.max_pool_cnt = 3
            #     config.comm_pool[2].blk_size = cls._width * cls._height * 2
            #     config.comm_pool[2].blk_cnt = 1
            #     config.comm_pool[2].mode = VB_REMAP_MODE_NOCACHE

            ret = MediaManager._config(config)
            if not ret:
                raise RuntimeError(f"Display configure buffer for ide failed.")
            config = None

            if not isinstance(quality, int):
                quality = 90
            if quality < 10:
                quality = 90

            ide_dbg_set_vo_wbc(quality, cls._width, cls._height)
        else:
            ide_dbg_set_vo_wbc(0, 0, 0)

        # must have one for disp
        if cls._osd_layer_num < 1:
            cls._osd_layer_num = 1

        config = k_vb_config()
        config.max_pool_cnt = 1
        config.comm_pool[0].blk_size = cls._width * cls._height * 4
        config.comm_pool[0].blk_cnt = cls._osd_layer_num + 2 # additional two for rotate
        config.comm_pool[0].mode = VB_REMAP_MODE_NOCACHE
        ret = MediaManager._config(config)
        if not ret:
            raise RuntimeError(f"Display configure buffer failed.")
        config = None

        for i in range(0, K_VO_MAX_CHN_NUMS):
            if isinstance(cls._layer_bind_cfg[i], Display.BindConfig):
                cls._layer_bind_cfg[i].bind()

                if (Display.LAYER_VIDEO1 <= i <= Display.LAYER_VIDEO2):
                    cls.__config_video_layer(cls._layer_bind_cfg[i].layer_config)
                elif (Display.LAYER_OSD0 <= i <= Display.LAYER_OSD3):
                    cls._layer_configured[i] = cls.__config_osd_layer(cls._layer_bind_cfg[i].layer_config)

        cls._is_inited = True

    @classmethod
    def deinit(cls):
        if not cls._is_inited:
            print("did't call Display.init()")
            return

        # disable all layer
        for i in range(0, K_VO_MAX_CHN_NUMS):
            if isinstance(cls._layer_cfgs[i], Display.LayerConfig):
                cls._disable_layer(i)

        # poweroff
        connector_fd = kd_mpi_connector_open(uctypes.string_at(cls._connector_info.connector_name))
        kd_mpi_connector_power_set(connector_fd, 0)
        kd_mpi_connector_close(connector_fd)

        ide_dbg_set_vo_wbc(False, 0, 0)
        ide_dbg_vo_wbc_deinit()
        kd_display_reset()

        # unbind all layer
        for i in range(0, K_VO_MAX_CHN_NUMS):
            if isinstance(cls._layer_bind_cfg[i], Display.BindConfig):
                cls._layer_bind_cfg[i].__del__()
                cls._layer_bind_cfg[i] = None

        # release all layer buffers
        if isinstance(cls._layer_rotate_buffer, MediaManager.Buffer):
            cls._layer_rotate_buffer.destroy()
            cls._layer_rotate_buffer = None

        for i in range(0, K_VO_MAX_CHN_NUMS):
            if isinstance(cls._layer_disp_buffers[i], MediaManager.Buffer):
                cls._layer_disp_buffers[i].destroy()
                cls._layer_disp_buffers[i] = None

        cls._osd_layer_num = 1
        cls._write_back_to_ide = False
        cls._panel_flag = None

        cls._connector_info = None
        cls._connector_type = None

        cls._width = 0
        cls._height = 0

        cls._is_inited = False

    # layer
    @classmethod
    def width(cls, layer = None):
        if layer == None:
            if cls._panel_flag is not None:
                if cls._panel_flag == Display.FLAG_ROTATION_90 or cls._panel_flag == Display.FLAG_ROTATION_270:
                    return cls._height
                else:
                    return cls._width
            else:
                return cls._width
        else:
            if layer > K_VO_MAX_CHN_NUMS:
                raise IndexError(f"layer({layer}) out of range")

            if isinstance(cls._layer_cfgs[layer], Display.LayerConfig):
                return cls._layer_cfgs[layer].rect[1]
            else:
                print(f"layer({layer}) is not configured")
                return 0

    # layer
    @classmethod
    def height(cls, layer = None):
        if layer == None:
            if cls._panel_flag is not None:
                if cls._panel_flag == Display.FLAG_ROTATION_90 or cls._panel_flag == Display.FLAG_ROTATION_270:
                    return cls._width
                else:
                    return cls._height
            else:
                return cls._height
        else:
            if layer > K_VO_MAX_CHN_NUMS:
                raise IndexError(f"layer({layer}) out of range")

            if isinstance(cls._layer_cfgs[layer], Display.LayerConfig):
                return cls._layer_cfgs[layer].rect[3]
            else:
                print(f"layer({layer}) is not configured")
                return 0

    @classmethod
    def fps(cls, layer = None):
        if cls._connector_type == DSI_VIRTUAL_DEVICE:
            return cls._connector_info.resolution.pclk
        else:
            htotal = cls._connector_info.resolution.htotal
            vtotal = cls._connector_info.resolution.vtotal
            pclk = cls._connector_info.resolution.pclk

            fps = pclk * 1000 // htotal // vtotal

            return fps if fps < 200 else 0

    @classmethod
    def _disable_layer(cls, layer):
        if layer > K_VO_MAX_CHN_NUMS:
            raise IndexError(f"layer({layer}) out of range")

        if isinstance(cls._layer_cfgs[layer], Display.LayerConfig):
            if cls._layer_configured[layer]:
                if (Display.LAYER_VIDEO1 <= layer <= Display.LAYER_VIDEO2):
                    vb_mgmt_disable_video_layer(layer)
                elif (Display.LAYER_OSD0 <= layer <= Display.LAYER_OSD3):
                    vb_mgmt_disable_osd_layer(layer - Display.LAYER_OSD0)
            else:
                print(f"error state on _disable_layer {layer}")

            cls._layer_cfgs[layer].__del__()
            cls._layer_cfgs[layer] = None

        cls._layer_configured[layer] = False

    @classmethod
    def __config_video_layer(cls, layer_config):
        if not isinstance(layer_config, Display.LayerConfig):
            raise TypeError("layer_config is not Display.LayerConfig")

        if cls._layer_cfgs[layer_config.layer] == layer_config:
            print(f"layer({layer_config.layer}) config not changed.")
            return

        if not (Display.LAYER_VIDEO1 <= layer_config.layer <= Display.LAYER_VIDEO2):
            raise IndexError(f"layer({layer_config.layer}) out of range")

        if layer_config.pix_format != PIXEL_FORMAT_YUV_SEMIPLANAR_420:
            raise AssertionError("bind video layer only support format PIXEL_FORMAT_YUV_SEMIPLANAR_420")

        cls._disable_layer(layer_config.layer)

        width = layer_config.rect[2]
        height = layer_config.rect[3]

        if width == 0:
            width = cls._width
        if height == 0:
            height = cls._height

        if cls._panel_flag is not None:
            layer_config.flag = cls._panel_flag

        if layer_config.flag & Display.FLAG_ROTATION_90 == Display.FLAG_ROTATION_90 or layer_config.flag & Display.FLAG_ROTATION_270 == Display.FLAG_ROTATION_270:
            if layer_config.layer == Display.LAYER_VIDEO2:
                raise ValueError("Bind to video layer enable rotation 90/180 only support Display.LAYER_VIDEO1")

            temp = width
            width = height
            height = temp

        if width == 0 or height == 0 or width & 7:
            raise ValueError("width must be an integral multiple of 8 pixels")

        offset = k_vo_point()
        offset.x = layer_config.rect[0]
        offset.y = layer_config.rect[1]

        img_size = k_vo_size()
        img_size.width = width
        img_size.height = height

        video_attr = k_vo_video_layer_attr()
        video_attr.pixel_format = layer_config.pix_format

        video_attr.func = layer_config.flag

        if layer_config.pix_format == PIXEL_FORMAT_YUV_SEMIPLANAR_420:
            video_attr.stride = (width // 8 - 1) + ((height - 1) << 16)
        else:
            raise ValueError(f"video layer not support pix_format ({layer_config.pix_format})")

        struct_copy(offset, video_attr.display_rect)
        struct_copy(img_size, video_attr.img_size)

        kd_mpi_vo_set_video_layer_attr(layer_config.layer, video_attr)
        vb_mgmt_enable_video_layer(layer_config.layer)

        cls._layer_cfgs[layer_config.layer] = layer_config
        cls._layer_configured[layer_config.layer] = True

    @classmethod
    def __config_osd_layer(cls, layer_config) -> bool:
        if not isinstance(layer_config, Display.LayerConfig):
            raise TypeError("layer_config is not Display.LayerConfig")

        if cls._layer_cfgs[layer_config.layer] == layer_config:
            # print(f"layer({layer_config.layer}) config not changed.")
            return True

        cls._disable_layer(layer_config.layer)

        width = layer_config.rect[2]
        height = layer_config.rect[3]
        pixelformat = layer_config.pix_format

        if width == 0:
            width = cls._width
        if height == 0:
            height = cls._height

        if width == 0 or height == 0 or width & 7:
            raise ValueError("width must be an integral multiple of 8 pixels")

        offset = k_vo_point()
        offset.x = layer_config.rect[0]
        offset.y = layer_config.rect[1]

        img_size = k_vo_size()
        img_size.width = width
        img_size.height = height

        osd_attr = k_vo_video_osd_attr()
        osd_attr.global_alpha = layer_config.alpha
        osd_attr.pixel_format = pixelformat

        if (pixelformat == PIXEL_FORMAT_ARGB_8888 or pixelformat == PIXEL_FORMAT_ABGR_8888 or pixelformat == PIXEL_FORMAT_BGRA_8888):
            osd_attr.stride = (width * 4) // 8
        elif (pixelformat == PIXEL_FORMAT_RGB_888 or pixelformat == PIXEL_FORMAT_BGR_888):
            osd_attr.stride = (width * 3) // 8
        elif (pixelformat == PIXEL_FORMAT_RGB_565_LE or pixelformat == PIXEL_FORMAT_BGR_565_LE):
            osd_attr.stride = (width * 2) // 8
        elif (pixelformat == PIXEL_FORMAT_RGB_MONOCHROME_8BPP):
            osd_attr.stride = (width) // 8
        else:
            raise ValueError(f"osd layer not support pix_format ({pixelformat})")

        struct_copy(offset, osd_attr.display_rect)
        struct_copy(img_size, osd_attr.img_size)
        kd_mpi_vo_set_video_osd_attr(layer_config.layer - Display.LAYER_OSD0, osd_attr)

        cls._layer_cfgs[layer_config.layer] = layer_config
        # cls._layer_configured[layer_config.layer] = True
        return True

    @classmethod
    def _config_layer(cls, layer, rect, pix_format, flag, alpha = 255):
        if not (Display.LAYER_VIDEO1 <= layer <= Display.LAYER_OSD3):
            raise IndexError(f"layer({layer}) out of range")

        if not isinstance(rect, tuple) or len(rect) != 4:
            raise ValueError("rect should be (x, y, w, h)")

        # width
        if rect[2] & 7:
            raise ValueError("width must be an integral multiple of 8 pixels")

        layer_config = Display.LayerConfig(layer, rect, pix_format, flag, alpha)

        if (Display.LAYER_VIDEO1 <= layer <= Display.LAYER_VIDEO2):
            cls.__config_video_layer(layer_config)
        elif (Display.LAYER_OSD0 <= layer <= Display.LAYER_OSD3):
            cls.__config_osd_layer(layer_config)

        del layer_config

    # image
    # layer
    # x
    # y
    # alpha
    # flag
    @classmethod
    def show_image(cls, img, x = 0, y = 0, layer = None, alpha = 255, flag = None):
        if layer == None:
            layer = Display.LAYER_OSD0
        if not (Display.LAYER_OSD0 <= layer <= Display.LAYER_OSD3):
            raise AssertionError(f"layer({layer}) is out of range.")

        width = img.width()
        height = img.height()
        _format = img.format()

        if width & 7:
            raise ValueError("Image width must be an integral multiple of 8 pixels")
        if width * height > cls._width * cls._height:
            raise ValueError("Image size is too large")

        if _format == image.ARGB8888:
            pixelformat = PIXEL_FORMAT_ARGB_8888
        elif _format == image.BGRA8888:
            pixelformat = PIXEL_FORMAT_BGRA_8888
        elif _format == image.RGB888:
            pixelformat = PIXEL_FORMAT_RGB_888
        elif _format == image.RGB565:
            pixelformat = PIXEL_FORMAT_RGB_565_LE
        elif _format == image.GRAYSCALE:
            pixelformat = PIXEL_FORMAT_RGB_MONOCHROME_8BPP
        else:
            raise ValueError(f"Image format({_format}) not support")

        stride = 1

        if (pixelformat == PIXEL_FORMAT_ARGB_8888 or pixelformat == PIXEL_FORMAT_ABGR_8888 or pixelformat == PIXEL_FORMAT_BGRA_8888):
            stride = 4
        elif (pixelformat == PIXEL_FORMAT_RGB_888 or pixelformat == PIXEL_FORMAT_BGR_888):
            stride = 3
        elif (pixelformat == PIXEL_FORMAT_RGB_565_LE or pixelformat == PIXEL_FORMAT_BGR_565_LE):
            stride = 2
        elif (pixelformat == PIXEL_FORMAT_RGB_MONOCHROME_8BPP):
            stride = 1
        else:
            stride = 1

        if cls._layer_disp_buffers[layer] == None:
            buf_cnt = 0
            for i in range(0, K_VO_MAX_CHN_NUMS):
                if isinstance(cls._layer_disp_buffers[i], MediaManager.Buffer):
                    buf_cnt += 1

            if buf_cnt > cls._osd_layer_num:
                raise RuntimeError(f"please increase Display.config(osd_num=) or becareful the layer")
            try:
                cls._layer_disp_buffers[layer] = MediaManager.Buffer.get(4 * cls._width * cls._height)
            except Exception as e:
                raise RuntimeError(f"get display buffer failed")
            # finally:
            #     print(f"get disp buffer {cls._layer_disp_buffers[layer]}")

        if flag is None:
            flag = 0

            if cls._panel_flag is not None:
                flag = cls._panel_flag

        if flag != 0:
            if cls._layer_rotate_buffer == None:
                try:
                    cls._layer_rotate_buffer = MediaManager.Buffer.get(4 * cls._width * cls._height)
                except Exception as e:
                    raise RuntimeError(f"get rotate buffer failed")
                # finally:
                #     print(f"get rotate buffer {cls._layer_rotate_buffer}")

            _x, _y, _w, _h = x, y, width, height

            _rotate = flag & 0x0F

            if _rotate & Display.FLAG_ROTATION_0 == Display.FLAG_ROTATION_0:
                pass
            elif _rotate & Display.FLAG_ROTATION_90 == Display.FLAG_ROTATION_90:
                x = cls._width - _h - _y
                y = _x
                width = _h
                height = _w
            elif _rotate & Display.FLAG_ROTATION_180 == Display.FLAG_ROTATION_180:
                pass
            elif _rotate & Display.FLAG_ROTATION_270 == Display.FLAG_ROTATION_270:
                x = cls._width - _h - _y
                y = _x
                width = _h
                height = _w
            else:
                print(f"not support rotate {_rotate}")

            input_frame = k_video_frame_info()
            input_frame.pool_id = cls._layer_rotate_buffer.pool_id
            input_frame.v_frame.width = _w
            input_frame.v_frame.height = _h
            input_frame.v_frame.stride[0] = _w * stride
            input_frame.v_frame.pixel_format = pixelformat
            input_frame.v_frame.phys_addr[0] = cls._layer_rotate_buffer.phys_addr
            input_frame.v_frame.virt_addr[0] = cls._layer_rotate_buffer.virt_addr

            output_frame = k_video_frame_info()
            output_frame.v_frame.width = width
            output_frame.v_frame.height = height
            output_frame.v_frame.stride[0] = width * stride
            output_frame.v_frame.virt_addr[0] = cls._layer_disp_buffers[layer].virt_addr

            machine.mem_copy(cls._layer_rotate_buffer.virt_addr, img.virtaddr(), img.size())
            kd_mpi_vo_osd_rotation(flag, input_frame, output_frame)

            # cls._layer_rotate_buffer.__del__()
            # cls._layer_rotate_buffer = None
        else:
            machine.mem_copy(cls._layer_disp_buffers[layer].virt_addr, img.virtaddr(), img.size())

        cls._config_layer(layer, (x, y, width, height), pixelformat, flag, alpha)

        if cls._layer_configured[layer]:
            return

        frame_info = k_video_frame_info()
        frame_info.mod_id = K_ID_VO
        frame_info.pool_id = cls._layer_disp_buffers[layer].pool_id
        frame_info.v_frame.width = width
        frame_info.v_frame.height = height
        frame_info.v_frame.pixel_format = pixelformat
        frame_info.v_frame.stride[0] = width * stride
        frame_info.v_frame.phys_addr[0] = cls._layer_disp_buffers[layer].phys_addr
        frame_info.v_frame.virt_addr[0] = cls._layer_disp_buffers[layer].virt_addr

        kd_mpi_vo_chn_insert_frame(layer, frame_info)
        vb_mgmt_enable_osd_layer(layer - Display.LAYER_OSD0)

        cls._layer_configured[layer] = True
