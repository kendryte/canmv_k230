from mpp import *
from mpp.vicap import *
from media.media import *
from _media import py_video_frame_info
import image
import machine
import os
import time

# MPP: acq width > VICAP_SENSOR_MAX_WIDTH (3072) requires VICAP_WORK_SW_TILE_MODE
VICAP_SENSOR_MAX_WIDTH = const(3072)
VICAP_SENSOR_MAX_HEIGHT = const(2160)

CAM_OUT_WIDTH_MIN = const(64)
CAM_OUT_HEIGHT_MIN = const(64)

# NOTE:This is a private class for internal use only!!!
#      Don't edit it arbitrarily!!!

class Sensor:
    RGB565   = PIXEL_FORMAT_RGB_565
    RGB888   = PIXEL_FORMAT_RGB_888
    RGBP888  = PIXEL_FORMAT_RGB_888_PLANAR
    YUV420SP = PIXEL_FORMAT_YUV_SEMIPLANAR_420
    GRAYSCALE = PIXEL_FORMAT_GRAYSCALE

    DATABASE_PARSE_XML_JSON = VICAP_DATABASE_PARSE_XML_JSON
    DATABASE_PARSE_BIN = VICAP_DATABASE_PARSE_HEADER

    # QQSIF           #: 88x60
    # QQQQVGA         #: 40x30
    # QQQVGA          #: 80x60
    # HQQQQVGA        #: 30x20
    # HQQQVGA         #: 60x40
    # B64X32          #: 64x32 (for use with Image.find_displacement())
    QQCIF       = const(0)    #: 88x72
    QCIF        = const(1)    #: 176x144
    CIF         = const(2)    #: 352x288
    QSIF        = const(3)    #: 176x120
    SIF         = const(4)    #: 352x240
    QQVGA       = const(5)    #: 160x120
    QVGA        = const(6)    #: 320x240
    VGA         = const(7)    #: 640x480
    HQQVGA      = const(8)    #: 120x80
    HQVGA       = const(9)    #: 240x160
    HVGA        = const(10)   #: 480x320
    B64X64      = const(11)   #: 64x64
    B128X64     = const(12)   #: 128x64
    B128X128    = const(13)   #: 128x128
    B160X160    = const(14)   #: 160x160
    B320X320    = const(15)   #: 320x320
    QQVGA2      = const(16)   #: 128x160
    WVGA        = const(17)   #: 720x480
    WVGA2       = const(18)   #: 752x480
    SVGA        = const(19)   #: 800x600
    XGA         = const(20)   #: 1024x768
    WXGA        = const(21)   #: 1280x768
    SXGA        = const(22)   #: 1280x1024
    SXGAM       = const(23)   #: 1280x960
    UXGA        = const(24)   #: 1600x1200
    HD          = const(25)   #: 1280x720
    FHD         = const(26)   #: 1920x1080
    QHD         = const(27)   #: 2560x1440
    QXGA        = const(28)   #: 2048x1536
    WQXGA       = const(29)   #: 2560x1600
    WQXGA2      = const(30)   #: 2592x1944

    FRAME_SIZE_INVAILD = const(31)
    # Reboot only after this many snapshot failures land inside the rolling window.
    SNAPSHOT_FAILURE_LIMIT = const(3)
    # Rolling failure window in milliseconds for auto_reboot snapshot calls.
    SNAPSHOT_FAILURE_WINDOW_MS = const(10000)
    # VICAP stops the capture pipeline asynchronously before deinit can release it.
    VICAP_STOP_STREAM_DELAY_MS = const(100)

    _devs = [None for i in range(0, CAM_DEV_ID_MAX)]
    _csis = [False for i in range(0, CAM_DEV_ID_MAX)]

    @staticmethod
    def _calculate_crop(sensor_width, sensor_height, target_width, target_height):
        """Internal helper method.
        Args:
            sensor_width: Sensor width in pixels.
            sensor_height: Sensor height in pixels.
            target_width: Target width in pixels.
            target_height: Target height in pixels.
        """
        scale = min(sensor_width // target_width, sensor_height // target_height)
        crop_width = int(target_width * scale)
        crop_height = int(target_height * scale)
        crop_x = (sensor_width - crop_width) // 2
        crop_y = (sensor_height - crop_height) // 2

        return (crop_x, crop_y, crop_width, crop_height)

    @classmethod
    def deinit(cls):
        """Release media resources.
        """
        for i in range(0, CAM_DEV_ID_MAX):
            if isinstance(cls._devs[i], Sensor):
                cls._devs[i].stop(is_del = True)

    @classmethod
    def _is_mcm_device(cls) -> bool:
        """Internal helper method.
        """
        cnt = 0
        for i in range(0, CAM_DEV_ID_MAX):
            if isinstance(cls._devs[i], Sensor):
                cnt = cnt + 1
        return True if cnt > 1 else False

    @classmethod
    def _needs_sw_tile_mode(cls, w, h):
        """Internal helper method.
        Args:
            w: Value for w.
            h: Value for h.
        """
        return w > VICAP_SENSOR_MAX_WIDTH or h > VICAP_SENSOR_MAX_HEIGHT

    def _apply_database_parse_mode(self):
        """Internal helper method.
        """
        if self._database_parse_mode is None:
            return
        ret = kd_mpi_vicap_set_database_parse_mode(self._dev_id, self._database_parse_mode)
        if ret:
            raise RuntimeError("sensor(%d) run error, set database parse mode failed(%d)" % (self._dev_id, ret))

    @classmethod
    def _check_mcm_sw_tile_at_run(cls):
        """4K (SW_TILE) mode only supports one sensor; check at run() only."""
        sw_devs = []
        sensor_cnt = 0
        for i in range(0, CAM_DEV_ID_MAX):
            s = cls._devs[i]
            if isinstance(s, Sensor) and s._dev_attr.dev_enable:
                sensor_cnt += 1
                if s._dev_attr.mode == VICAP_WORK_SW_TILE_MODE:
                    sw_devs.append(i)
        if sensor_cnt > 1 and sw_devs:
            raise RuntimeError(
                "4K (SW_TILE) mode only supports one sensor, but %d sensors are "
                "enabled and dev %s requires SW_TILE (acq width > %d)"
                % (sensor_cnt, sw_devs, VICAP_SENSOR_MAX_WIDTH)
            )

    @classmethod
    def _apply_work_mode_for_resolution(cls, sensor):
        """Internal helper method.
        Args:
            sensor: Value for sensor.
        """
        w = sensor._dev_attr.acq_win.width
        h = sensor._dev_attr.acq_win.height
        if cls._needs_sw_tile_mode(w, h):
            sensor._dev_attr.mode = VICAP_WORK_SW_TILE_MODE
            sensor._dev_attr.buffer_num = 6
            sensor._dev_attr.buffer_size = ALIGN_UP(w * h * 2, VICAP_ALIGN_4K)
        else:
            sensor._dev_attr.mode = VICAP_WORK_ONLINE_MODE
            sensor._dev_attr.buffer_num = sensor._dft_input_buff_num
            sensor._dev_attr.buffer_size = 0

    @classmethod
    def _handle_mcm_device(cls):
        """Internal helper method.
        """
        if not cls._is_mcm_device():
            return
        for i in range(0, CAM_DEV_ID_MAX):
            if isinstance(cls._devs[i], Sensor):
                cls._devs[i]._set_inbufs()

    @classmethod
    def _run_mcm_device(cls):
        """Internal helper method.
        """
        if not cls._is_mcm_device():
            return

        for i in range(0, CAM_DEV_ID_MAX):
            if isinstance(cls._devs[i], Sensor):
                sensor = cls._devs[i]
                if not sensor._dev_attr.dev_enable or sensor._is_started:
                    continue
                sensor._apply_database_parse_mode()

                ret = kd_mpi_vicap_set_dev_attr(i, sensor._dev_attr)
                if ret:
                    raise RuntimeError(f"sensor({i}) run error, set dev attr failed({ret})")

                # vicap channel attr set
                for chn_num in range(0, VICAP_CHN_ID_MAX):
                    if not sensor._chn_attr[chn_num].chn_enable:
                        continue
                    sensor._calculate_buffer_size(chn_num)

                    ret = kd_mpi_vicap_set_chn_attr(i, chn_num, sensor._chn_attr[chn_num])
                    if ret:
                        raise RuntimeError(f"sensor({i}) run error, set chn({chn_num}) attr failed({ret})")

        for i in range(0, CAM_DEV_ID_MAX):
            if isinstance(cls._devs[i], Sensor):
                sensor = cls._devs[i]
                if not sensor._dev_attr.dev_enable or sensor._is_started:
                    continue
                sensor._vicap_init_started = True
                ret = kd_mpi_vicap_init(i)
                if ret:
                    # if sensor._framesize[chn_num] is None:
                    #     print(f"sensor({sensor._dev_id}) chn({chn_num}) not call `set_framesize`, at now should reboot board to fix it.")

                    # if sensor._pixel_format[chn_num] is None:
                    #     print(f"sensor({sensor._dev_id}) chn({chn_num}) not call `set_pixformat`, at now should reboot board to fix it.")

                    raise RuntimeError(f"sensor({i}) run error, vicap init failed({ret})")

                sensor_attr = k_vicap_sensor_attr()
                sensor_attr.dev_num = i
                if 0x00 != kd_mpi_vicap_get_sensor_fd(sensor_attr):
                    raise RuntimeError(f"sensor({i}) run error, get sensor fd failed({ret})")
                sensor.fd = sensor_attr.sensor_fd

        for i in range(0, CAM_DEV_ID_MAX):
            if isinstance(cls._devs[i], Sensor):
                sensor = cls._devs[i]
                if not sensor._dev_attr.dev_enable or sensor._is_started:
                    continue
                print(f"sensor({i}), mode {sensor._dev_attr.mode}, buffer_num {sensor._dev_attr.buffer_num}, buffer_size {sensor._dev_attr.buffer_size}")
                sensor._vicap_stream_start_started = True
                ret = kd_mpi_vicap_start_stream(i)
                if ret:
                    raise RuntimeError(f"sensor({i}) run error, vicap start stream failed({ret})")

                sensor._is_started = True
                sensor._vb_mgmt_registered = True
                vb_mgmt_vicap_dev_inited(i)


    @classmethod
    def _get_dev_id(self):
        """Internal helper method.
        """
        dev_id = 0
        all_used = True
        for i in range(0, CAM_DEV_ID_MAX):
            if Sensor._csis[i]:
                dev_id = dev_id + 1
            else:
                all_used = False

        if all_used is True:
            return None

        return dev_id

    # id
    # type
    # force
    # lane_pref / fps / width / height (auto-detect)
    def __init__(self, **kwargs):
        """Initialize Sensor (auto-detect or fixed type).

        Args:
            id: CSI bus index (0/1/2). Default: board default sensor CSI.
            type: Optional fixed sensor type; skips adapt_get when set.
            force: Re-init even if this CSI is already in use.
            fps, width, height: Hint for kd_mpi_sensor_adapt_get_ex (defaults 60, 1920, 1080).
            lane_pref: MIPI lane preference when 2LANE/4LANE share the same WxH@fps.
                Default VICAP_MIPI_2LANE (1). Also: VICAP_MIPI_ANY (0), VICAP_MIPI_4LANE (2).
                Example: Sensor(id=0, lane_pref=VICAP_MIPI_4LANE)
            database_parse_mode: ISP DB parse mode (XML/JSON or BIN).
        """
        self._database_parse_mode = kwargs.get('database_parse_mode', None)
        if self._database_parse_mode is not None and self._database_parse_mode not in (VICAP_DATABASE_PARSE_XML_JSON, VICAP_DATABASE_PARSE_HEADER):
            raise ValueError("database_parse_mode should be Sensor.DATABASE_PARSE_XML_JSON or Sensor.DATABASE_PARSE_BIN")

        self._dft_input_buff_num = 4
        self._dft_output_buff_num = 4

        def_mirror = 0
        dft_sensor_id = get_default_sensor()

        self._csi_bus = kwargs.get('id', dft_sensor_id)
        if (self._csi_bus > CAM_DEV_ID_MAX - 1):
            raise AssertionError(f"invaild sensor id {self._csi_bus}, should < {CAM_DEV_ID_MAX - 1}")

        force = kwargs.get('force', False)
        if not force and Sensor._csis[self._csi_bus]:
            raise OSError(f"sensor({self._csi_bus}) is already inited.")

        brd = os.uname()[-1]
        if brd.startswith("k230d"):
            self._dft_output_buff_num = 3
        del brd

        arg_type = kwargs.get('type', None)
        if arg_type is not None:
            self._type = arg_type
        else:
            info = k_vicap_sensor_info()
            cfg = k_vicap_probe_config()
            cfg.csi = self._csi_bus
            cfg.fps = kwargs.get('fps', 60)
            cfg.width = kwargs.get('width', 1920)
            cfg.height = kwargs.get('height', 1080)
            lane_pref = kwargs.get('lane_pref', VICAP_MIPI_2LANE)
            if lane_pref < 0 or lane_pref > 2:
                raise ValueError(
                    "lane_pref must be VICAP_MIPI_ANY/2LANE/4LANE (0/1/2)"
                )
            ret = kd_mpi_sensor_adapt_get_ex(cfg, info, lane_pref)
            if 0 != ret:
                raise RuntimeError(
                    "Can not found sensor on %s (probe %sx%s@%s, lane_pref=%s)"
                    % (self._csi_bus, cfg.width, cfg.height, cfg.fps, lane_pref)
                )

            def_mirror = cfg.def_mirror
            self._type = info.type
            print(f"find sensor {cfg.name.decode()}, type {info.type}, output {info.width}x{info.height}@{info.fps}")

        if (self._type > SENSOR_TYPE_MAX - 1):
            raise AssertionError(f"invaild sensor type {self._type}, should < {SENSOR_TYPE_MAX - 1}")

        self._dev_id = self._get_dev_id()
        if self._dev_id is None:
            raise AssertionError(f"too many csi devs")

        self._dev_attr = k_vicap_dev_attr()
        self._chn_attr = [k_vicap_chn_attr() for i in range(0, VICAP_CHN_ID_MAX)]
        self._buf_init = [False for i in range(0, VICAP_CHN_ID_MAX)]
        self._buf_in_init = False
        # set the default value
        self._dev_attr.buffer_num = self._dft_input_buff_num
        self._dev_attr.buffer_pool_id = VB_INVALID_POOLID
        self._dev_attr.mode = VICAP_WORK_ONLINE_MODE
        # self._dev_attr.mode = VICAP_WORK_OFFLINE_MODE
        self._dev_attr.input_type = VICAP_INPUT_TYPE_SENSOR
        self._dev_attr.mirror = def_mirror
        self._dev_attr.fastboot = 0

        self.fd = -1
        self.sensor_name = ""

        self._is_started = False
        # Native calls can be interrupted before their Python assignments run.
        self._vicap_init_started = False
        self._vicap_stream_start_started = False
        self._vb_mgmt_registered = False

        for i in range(0, VICAP_CHN_ID_MAX):
            self._chn_attr[i].buffer_num = self._dft_output_buff_num

        self._imgs = [None for i in range(0, VICAP_CHN_ID_MAX)]
        self._is_rgb565 = [False for i in range(0, VICAP_CHN_ID_MAX)]
        self._is_grayscale = [False for i in range(0, VICAP_CHN_ID_MAX)]

        self._framesize = [None for i in range(0, VICAP_CHN_ID_MAX)]
        self._pixel_format = [None for i in range(0, VICAP_CHN_ID_MAX)]
        self._snapshot_failure_ticks = [0] * Sensor.SNAPSHOT_FAILURE_LIMIT
        self._snapshot_failure_count = 0
        self._snapshot_failure_index = 0

        Sensor._csis[self._csi_bus] = True
        Sensor._devs[self._dev_id] = self

    def __del__(self):
        """Release resources held by this object.
        """
        self.stop(is_del = True)

    def __str__(self):
        """Return a string representation of this object.
        """
        pass

    def _set_inbufs(self):
        """Internal helper method.
        """
        if not self._dev_attr.dev_enable:
            raise AssertionError("should call reset() first")

        # if (self._dev_id > CAM_DEV_ID_MAX - 1):
        #     raise AssertionError(f"invaild sensor id {self._dev_id}, should < {CAM_DEV_ID_MAX - 1}")

        if self._buf_in_init:
            return
        self._buf_in_init = True

        if self._dev_attr.mode == VICAP_WORK_SW_TILE_MODE:
            return

        self._dev_attr.mode = VICAP_WORK_OFFLINE_MODE
        self._dev_attr.buffer_num = self._dft_input_buff_num
        self._dev_attr.buffer_size = ALIGN_UP((self._dev_attr.acq_win.width * self._dev_attr.acq_win.height * 2), VICAP_ALIGN_4K)

    def _calculate_buffer_size(self, chn):
        """Internal helper method.
        Args:
            chn: Media channel number.
        """
        if not self._chn_attr[chn].chn_enable:
            return

        pix_format = self._chn_attr[chn].pix_format

        # Check if the necessary configuration is available
        if not pix_format:
             raise RuntimeError(f"sensor({self._dev_id}) chn({chn}) pixel format not set before run")

        out_width = self._chn_attr[chn].out_win.width
        out_height = self._chn_attr[chn].out_win.height
        in_width = self._dev_attr.acq_win.width
        in_height = self._dev_attr.acq_win.height

        if out_width == 0 or out_height == 0:
            # This check is necessary if run is called before set_framesize, but set_framesize 
            # is typically mandatory for a valid output window. Assuming set_framesize is called.
            # If chn_enable is True, framesize must have been set.
            raise RuntimeError(f"sensor({self._dev_id}) chn({chn}) frame size not set before run")

        buf_size = 0
        if pix_format == PIXEL_FORMAT_YUV_SEMIPLANAR_420:
            buf_size = ALIGN_UP((out_width * out_height * 3 // 2), VICAP_ALIGN_4K)
        elif pix_format in [PIXEL_FORMAT_RGB_888, PIXEL_FORMAT_RGB_888_PLANAR]:
            buf_size = ALIGN_UP((out_width * out_height * 3), VICAP_ALIGN_4K)
        elif pix_format in [PIXEL_FORMAT_RGB_BAYER_10BPP, PIXEL_FORMAT_RGB_BAYER_12BPP, \
                            PIXEL_FORMAT_RGB_BAYER_14BPP, PIXEL_FORMAT_RGB_BAYER_16BPP]:
            # For Bayer formats, it often uses the acquisition window size for the buffer
            # and may also adjust the output window to match acquisition window size.
            # The logic below from the original code implicitly sets out_win to in_win 
            # and uses in_win for size calculation.
            self._chn_attr[chn].out_win.width = in_width
            self._chn_attr[chn].out_win.height = in_height
            buf_size = ALIGN_UP((in_width * in_height * 2), VICAP_ALIGN_4K)
        else:
            raise RuntimeError(f"sensor({self._dev_id}) chn({chn}) pixel format ({pix_format}) not supported for buffer size calculation")

        self._chn_attr[chn].buffer_size = buf_size
        self._chn_attr[chn].buffer_pool_id = VB_INVALID_POOLID

    def wrap(func):
        """Perform this media operation.
        Args:
            func: Value for func.
        """
        def wrapper(*args, **kwargs):
            """Perform this media operation.
            Args:
                args: Additional positional arguments.
                kwargs: Additional keyword arguments.
            """
            print(f"not support {func.__name__} now...")

            raise NotImplementedError(f"{func.__name__}")

            return func(*args, **kwargs)

        return wrapper

    def reset(self):
        """Reset and initialize the device.
        """
        # if (self._type > SENSOR_TYPE_MAX - 1):
        #     raise AssertionError(f"invaild sensor type {self._type}, should < {SENSOR_TYPE_MAX - 1}")

        # if (self._dev_id > CAM_DEV_ID_MAX - 1):
        #     raise AssertionError(f"invaild sensor id {self._dev_id}, should < {CAM_DEV_ID_MAX - 1}")

        ret = kd_mpi_vicap_get_sensor_info(self._type, self._dev_attr.sensor_info)
        if ret:
            raise RuntimeError("sensor({self._dev_id}) get info failed({ret})")

        self._dev_attr.acq_win.h_start = 0
        self._dev_attr.acq_win.v_start = 0
        self._dev_attr.acq_win.width = self._dev_attr.sensor_info.width
        self._dev_attr.acq_win.height = self._dev_attr.sensor_info.height

        Sensor._apply_work_mode_for_resolution(self)
        self._dev_attr.input_type = VICAP_INPUT_TYPE_SENSOR
        self._dev_attr.dev_enable = True
        self._dev_attr.pipe_ctrl.data = 0xffffffff
        self._dev_attr.pipe_ctrl.bits.af_enable = 0
        self._dev_attr.pipe_ctrl.bits.ahdr_enable = 0
        self._dev_attr.dw_enable = 0
        self._dev_attr.cpature_frame = 0

        self.sensor_name = uctypes.string_at(self._dev_attr.sensor_info.name)

        if self.sensor_name.startswith("sc132gs_csi"):
            if self._dev_attr.sensor_info.width == 640 and self._dev_attr.sensor_info.height == 480:
                self._dev_attr.pipe_ctrl.bits.ae_enable = 0 # disable ae
                self._dev_attr.pipe_ctrl.bits.dnr3_enable = 0 # disable 3dnr
            elif self._dev_attr.sensor_info.width == 1080 and self._dev_attr.sensor_info.height == 1280:
                self._set_inbufs()

        Sensor._handle_mcm_device()

    @wrap
    def sleep(self, enable):
        """Perform this media operation.
        Args:
            enable: State to set; omit to read the current state.
        """
        pass

    @wrap
    def shutdown(self, enable):
        """Perform this media operation.
        Args:
            enable: State to set; omit to read the current state.
        """
        pass

    @wrap
    def flush(self, enable):
        """Perform this media operation.
        Args:
            enable: State to set; omit to read the current state.
        """
        pass

    class dumped_image:
        def __init__(self, dev_id, chn):
            """Initialize the object.
            Args:
                dev_id: Value for dev_id.
                chn: Media channel number.
            """
            self.id = dev_id
            self.chn = chn
            self.phys = None
            self.virt = None
            self.size = None

        def push_phys(self, phys):
            """Perform this media operation.
            Args:
                phys: Value for phys.
            """
            self.phys = phys

        def push_virt(self, virt, size):
            """Perform this media operation.
            Args:
                virt: Value for virt.
                size: Value for size.
            """
            self.virt = virt
            self.size = size

        def release(self):
            """Perform this media operation.
            """
            if isinstance(self.virt, int) and isinstance(self.size, int):
                if self.virt > 0 and self.size > 0:
                    ret = kd_mpi_sys_munmap(self.virt, self.size)
                    self.virt = None
                    self.size = None
                    if ret:
                        raise AssertionError("release image failed (1)")

            if isinstance(self.phys, int) and self.phys > 0:
                frame_info = k_video_frame_info()
                frame_info.v_frame.phys_addr[0] = self.phys
                ret = kd_mpi_vicap_dump_release(self.id, self.chn, frame_info)
                if ret:
                    raise AssertionError("release image failed (2)")
                self.phys = None

    # for snapshot
    @staticmethod
    def _release_image(img):
        """Internal helper method.
        Args:
            img: Value for img.
        """
        if is_vb_mgmt_vicap_image(img):
            vb_mgmt_release_vicap_frame(img)

    # for snapshot
    def _release_all_chn_image(self):
        """Internal helper method.
        """
        for chn in range(0, VICAP_CHN_ID_MAX):
            self._release_image(self._imgs[chn])
            self._imgs[chn] = None

    def _dumped_image(self, chn = CAM_CHN_ID_0):
        """Internal helper method.
        Args:
            chn: Media channel number.
        """
        if is_vb_mgmt_vicap_image(self._imgs[chn]):
            return self._imgs[chn]
        return None

    def _reset_snapshot_failure_state(self):
        """Internal helper method.
        """
        self._snapshot_failure_count = 0
        self._snapshot_failure_index = 0

    def _record_snapshot_failure(self, chn, ret):
        """Internal helper method.
        Args:
            chn: Media channel number.
            ret: Value for ret.
        """
        now = time.ticks_ms()

        self._snapshot_failure_ticks[self._snapshot_failure_index] = now
        if self._snapshot_failure_count < Sensor.SNAPSHOT_FAILURE_LIMIT:
            self._snapshot_failure_count += 1

        self._snapshot_failure_index += 1
        if self._snapshot_failure_index >= Sensor.SNAPSHOT_FAILURE_LIMIT:
            self._snapshot_failure_index = 0

        if self._snapshot_failure_count >= Sensor.SNAPSHOT_FAILURE_LIMIT:
            oldest_tick = self._snapshot_failure_ticks[self._snapshot_failure_index]
            if time.ticks_diff(now, oldest_tick) <= Sensor.SNAPSHOT_FAILURE_WINDOW_MS:
                print(
                    f"sensor({self._dev_id}) snapshot chn({chn}) failed {Sensor.SNAPSHOT_FAILURE_LIMIT} times in {Sensor.SNAPSHOT_FAILURE_WINDOW_MS // 1000}s, rebooting..."
                )
                machine.reset()

    def snapshot(self, chn = CAM_CHN_ID_0, timeout = 1000, dump_frame = False, auto_reboot = False):
        """Capture one image from the selected camera channel.
        Args:
            chn: Media channel number.
            timeout: Timeout in milliseconds.
            dump_frame: Value for dump_frame.
            auto_reboot: Value for auto_reboot.
        """
        if not self._dev_attr.dev_enable:
            raise AssertionError("should call reset() first")

        # if (self._dev_id > CAM_DEV_ID_MAX - 1):
        #     raise AssertionError(f"invaild sensor id {self._dev_id}, should < {CAM_DEV_ID_MAX - 1}")

        if (chn > CAM_CHN_ID_MAX - 1):
            raise AssertionError(f"invaild chn id {chn}, should < {CAM_CHN_ID_MAX - 1}")

        if is_vb_mgmt_vicap_image(self._imgs[chn]):
            self._release_image(self._imgs[chn])
            self._imgs[chn] = None

        cfg = vb_mgmt_dump_vicap_config()
        cfg.dev_num = self._dev_id
        cfg.chn_num = chn
        cfg.foramt = VICAP_DUMP_YUV
        cfg.milli_sec = timeout

        dumped_img = vb_mgmt_vicap_image()

        ret = vb_mgmt_dump_vicap_frame(cfg, dumped_img)
        if ret != 0:
            if auto_reboot:
                self._record_snapshot_failure(chn, ret)
            raise RuntimeError(f"sensor({self._dev_id}) snapshot chn({chn}) failed({ret})")

        if auto_reboot:
            self._reset_snapshot_failure_state()

        self._imgs[chn] = dumped_img

        if dump_frame:
            return py_video_frame_info(dumped_img.vf_info)

        phys_addr = dumped_img.vf_info.v_frame.phys_addr[0]
        virt_addr = dumped_img.vf_info.v_frame.virt_addr[0]
        img_width = dumped_img.vf_info.v_frame.width
        img_height = dumped_img.vf_info.v_frame.height
        fmt = dumped_img.vf_info.v_frame.pixel_format

        if fmt == PIXEL_FORMAT_YUV_SEMIPLANAR_420:
            img_fmt = image.YUV420
        elif fmt == PIXEL_FORMAT_RGB_888:
            img_fmt = image.RGB888
        elif fmt == PIXEL_FORMAT_RGB_888_PLANAR or fmt == PIXEL_FORMAT_BGR_888_PLANAR: # FIXME: remove BGR888P
            img_fmt = image.RGBP888
        else:
            raise RuntimeError(f"sensor({self._dev_id}) snapshot chn({chn}) not support pixelformat({fmt})")

        img = None

        if virt_addr:
            if self._is_rgb565[chn] and (img_fmt == image.RGB888):
                img = image.Image(img_width, img_height, img_fmt, cvt_565 = True, alloc=image.ALLOC_VB, phyaddr=phys_addr, virtaddr=virt_addr, poolid=dumped_img.vf_info.pool_id)
            elif self._is_grayscale[chn] and (img_fmt == image.YUV420):
                img = image.Image(img_width, img_height, image.GRAYSCALE, cvt_565 = False, alloc=image.ALLOC_VB, phyaddr=phys_addr, virtaddr=virt_addr, poolid=dumped_img.vf_info.pool_id)
            else:
                img = image.Image(img_width, img_height, img_fmt, alloc=image.ALLOC_VB, phyaddr=phys_addr, virtaddr=virt_addr, poolid=dumped_img.vf_info.pool_id)
        else:
            raise RuntimeError(f"sensor({self._dev_id}) snapshot chn({chn}) mmap failed")

        return img

    @wrap
    def skip_frames(self, **kwargs):
        """Skip frames while sensor controls stabilize.
        Args:
            kwargs: Additional keyword arguments.
        """
        pass

    def width(self, chn = CAM_CHN_ID_0):
        """Return the output width for a camera channel.
        Args:
            chn: Media channel number.
        """
        if not self._dev_attr.dev_enable:
            raise AssertionError("should call reset() first")

        if chn is not None:
            if (chn > CAM_CHN_ID_MAX - 1):
                raise AssertionError(f"invaild chn id {chn}, should < {CAM_CHN_ID_MAX - 1}")

            return self._chn_attr[chn].out_win.width
        return self._dev_attr.sensor_info.width

    def height(self, chn = CAM_CHN_ID_0):
        """Return the output height for a camera channel.
        Args:
            chn: Media channel number.
        """
        if not self._dev_attr.dev_enable:
            raise AssertionError("should call reset() first")

        if chn is not None:
            if (chn > CAM_CHN_ID_MAX - 1):
                raise AssertionError(f"invaild chn id {chn}, should < {CAM_CHN_ID_MAX - 1}")

            return self._chn_attr[chn].out_win.height
        return self._dev_attr.sensor_info.height

    @wrap
    def get_fb(self):
        """Return the current frame buffer.
        """
        pass

    @wrap
    def get_id(self):
        """Return the sensor model ID.
        """
        # if not self._dev_attr.dev_enable or self._dev_id > CAM_DEV_ID_MAX - 1:
        #     raise ValueError(f"invalid param, dev({self._dev_id})")
        # return self._dev_id
        pass

    def get_type(self):
        """Return the sensor type.
        """
        # if not self._dev_attr.dev_enable or self._dev_id > CAM_DEV_ID_MAX - 1:
        #     raise ValueError(f"invalid param, dev({self._dev_id})")
        return self._type

    @wrap
    def alloc_extra_fb(self, width, height, pixformat):
        """Allocate an additional frame buffer.
        Args:
            width: Width in pixels.
            height: Height in pixels.
            pixformat: Pixel format.
        """
        pass

    @wrap
    def dealloc_extra_fb(self):
        """Release the additional frame buffer.
        """
        pass

    def set_pixformat(self, pix_format, chn = CAM_CHN_ID_0):
        """Set the pixel format for a camera channel.
        Args:
            pix_format: Pixel format.
            chn: Media channel number.
        """
        if not self._dev_attr.dev_enable:
            raise AssertionError("should call reset() first")

        # if (self._dev_id > CAM_DEV_ID_MAX - 1):
        #     raise AssertionError(f"invaild sensor id {self._dev_id}, should < {CAM_DEV_ID_MAX - 1}")

        if (chn > CAM_CHN_ID_MAX - 1):
            raise AssertionError(f"invaild chn id {chn}, should < {CAM_CHN_ID_MAX - 1}")

        self._is_rgb565[chn] = False
        if pix_format == Sensor.RGB565:
            self._is_rgb565[chn] = True
            pix_format = PIXEL_FORMAT_RGB_888
        elif pix_format == Sensor.GRAYSCALE:
            self._is_grayscale[chn] = True
            pix_format = PIXEL_FORMAT_YUV_SEMIPLANAR_420

        self._chn_attr[chn].pix_format = pix_format
        self._chn_attr[chn].chn_enable = True

        self._pixel_format[chn] = pix_format

    def get_pixformat(self, chn = CAM_CHN_ID_0):
        """Return the pixel format for a camera channel.
        Args:
            chn: Media channel number.
        """
        if not self._dev_attr.dev_enable:
            raise AssertionError("should call reset() first")

        # if (self._dev_id > CAM_DEV_ID_MAX - 1):
        #     raise AssertionError(f"invaild sensor id {self._dev_id}, should < {CAM_DEV_ID_MAX - 1}")

        if (chn > CAM_CHN_ID_MAX - 1):
            raise AssertionError(f"invaild chn id {chn}, should < {CAM_CHN_ID_MAX - 1}")

        return self._chn_attr[chn].pix_format

    @staticmethod
    def _parse_framesize(framesize):
        """Internal helper method.
        Args:
            framesize: Target frame size.
        """
        sizes = [
            (88, 72),           #QQCIF
            (176, 144),         #QCIF
            (352, 288),         #CIF
            (176, 120),         #QSIF
            (352, 240),         #SIF
            (160, 120),         #QQVGA
            (320, 240),         #QVGA
            (640, 480),         #VGA
            (120, 80),          #HQQVGA
            (240, 160),         #HQVGA
            (480, 320),         #HVGA
            (64, 64),           #B64X64
            (128, 64),          #B128X64
            (128, 128),         #B128X128
            (160, 160),         #B160X160
            (320, 320),         #B320X320
            (128, 160),         #QQVGA2
            (720, 480),         #WVGA
            (752, 480),         #WVGA2
            (800, 600),         #SVGA
            (1024, 768),        #XGA
            (1280, 768),        #WXGA
            (1280, 1024),       #SXGA
            (1280, 960),        #SXGAM
            (1600, 1200),       #UXGA
            (1280, 720),        #HD
            (1920, 1080),       #FHD
            (2560, 1440),       #QHD
            (2048, 1536),       #QXGA
            (2560, 1600),       #WQXGA
            (2592, 1944),       #WQXGA2
        ]

        if 0 <= framesize < len(sizes):
            return sizes[framesize]
        else:
            return 0, 0

    def set_framesize(self, framesize = FRAME_SIZE_INVAILD, chn = CAM_CHN_ID_0, alignment=0, crop = None, **kwargs):
        """Set the output frame size and crop settings.
        Args:
            framesize: Target frame size.
            chn: Media channel number.
            alignment: Output size alignment requirement.
            crop: Optional crop region.
            kwargs: Additional keyword arguments.
        """
        if not self._dev_attr.dev_enable:
            raise AssertionError("should call reset() first")

        # if (self._dev_id > CAM_DEV_ID_MAX - 1):
        #     raise AssertionError(f"invaild sensor id {self._dev_id}, should < {CAM_DEV_ID_MAX - 1}")

        if (chn > CAM_CHN_ID_MAX - 1):
            raise AssertionError(f"invaild chn id {chn}, should < {CAM_CHN_ID_MAX - 1}")

        if 'w' in kwargs and 'h' in kwargs:
            width = kwargs.get('w', 0)
            height = kwargs.get('h', 0)
        elif 'width' in kwargs and 'height' in kwargs:
            width = kwargs.get('width', 0)
            height = kwargs.get('height', 0)
        else:
            width, height = Sensor._parse_framesize(framesize)

        if width % 16 != 0:
            width = ALIGN_UP(width, 16)
            print(f"Warning: sensor({self._dev_id}) chn({chn}) set_framesize align up width to {width}")

        if width > self._dev_attr.acq_win.width or width < CAM_OUT_WIDTH_MIN:
            raise AssertionError(f"sensor({self._dev_id}) chn({chn}) set_framesize invaild width({width}), should be {CAM_OUT_WIDTH_MIN} - {self._dev_attr.acq_win.width}")

        if height > self._dev_attr.acq_win.height or height < CAM_OUT_HEIGHT_MIN:
            raise AssertionError(f"sensor({self._dev_id}) chn({chn}) set_framesize invaild height({height}), should be {CAM_OUT_HEIGHT_MIN} - {self._dev_attr.acq_win.height}")

        crop_enable = False
        crop_x, crop_y, crop_w, crop_h = 0, 0, 0, 0

        if crop is True:
            crop_enable = True
            crop_x, crop_y, crop_w, crop_h = Sensor._calculate_crop(self._dev_attr.acq_win.width, self._dev_attr.acq_win.height, width, height)
        elif isinstance(crop, tuple) or isinstance(crop, list):
            if len(crop) == 4:
                crop_enable = True
                crop_x, crop_y, crop_w, crop_h = crop
            else:
                raise AssertionError(f"sensor({self._dev_id}) chn({chn}) set_framesize invaild crop({crop}), should be (x, y, w, h)")

        if crop_enable:
            if crop_w < width or crop_h < height:
                raise AssertionError(f"sensor({self._dev_id}) chn({chn}) set_framesize invaild crop_w({crop_w}), should be >= {width}")
            if crop_x < 0 or crop_x + crop_w > self._dev_attr.acq_win.width:
                raise AssertionError(f"sensor({self._dev_id}) chn({chn}) set_framesize invaild crop_x({crop_x}), should be 0 - {self._dev_attr.acq_win.width - crop_w}")
            if crop_y < 0 or crop_y + crop_h > self._dev_attr.acq_win.height:
                raise AssertionError(f"sensor({self._dev_id}) chn({chn}) set_framesize invaild crop_y({crop_y}), should be 0 - {self._dev_attr.acq_win.height - crop_h}")

        self._chn_attr[chn].chn_enable = True
        self._chn_attr[chn].crop_enable = False
        self._chn_attr[chn].scale_enable = False

        # output window
        self._chn_attr[chn].out_win.h_start = 0
        self._chn_attr[chn].out_win.v_start = 0
        self._chn_attr[chn].out_win.width = width
        self._chn_attr[chn].out_win.height = height
        self._chn_attr[chn].alignment = alignment

        if crop_enable:
            # crop window
            self._chn_attr[chn].crop_enable = True
            self._chn_attr[chn].crop_win.h_start = crop_x
            self._chn_attr[chn].crop_win.v_start = crop_y
            self._chn_attr[chn].crop_win.width = crop_w
            self._chn_attr[chn].crop_win.height = crop_h

            self._chn_attr[chn].scale_enable = True
            self._chn_attr[chn].scale_win.h_start = 0
            self._chn_attr[chn].scale_win.v_start = 0
            self._chn_attr[chn].scale_win.width = width
            self._chn_attr[chn].scale_win.height = height

        self._framesize[chn] = (width, height)

    def get_framesize(self, chn = CAM_CHN_ID_0):
        """Return the output frame size for a camera channel.
        Args:
            chn: Media channel number.
        """
        if not self._dev_attr.dev_enable:
            raise AssertionError("should call reset() first")

        # if (self._dev_id > CAM_DEV_ID_MAX - 1):
        #     raise AssertionError(f"invaild sensor id {self._dev_id}, should < {CAM_DEV_ID_MAX - 1}")

        if (chn > CAM_CHN_ID_MAX - 1):
            raise AssertionError(f"invaild chn id {chn}, should < {CAM_CHN_ID_MAX - 1}")

        print("please use width() and height()")

        return self._framesize[chn]
        # return (self._chn_attr[chn].out_win.width, self._chn_attr[chn].out_win.height)

    @wrap
    def set_framerate(self, rate):
        """Set the sample rate.
        Args:
            rate: Audio sample rate in Hz.
        """
        pass

    @wrap
    def get_framerate(self):
        """Return the sample rate.
        """
        pass

    @wrap
    def set_windowing(self, roi):
        """Set the sensor capture region.
        Args:
            roi: Region of interest.
        """
        pass

    @wrap
    def get_windowing(self):
        """Return the sensor capture region.
        """
        pass

    @wrap
    def set_contrast(self, constrast):
        """Set image contrast.
        Args:
            constrast: Image contrast.
        """
        pass

    @wrap
    def set_brightness(self, brightness):
        """Set image brightness.
        Args:
            brightness: Image brightness.
        """
        pass

    @wrap
    def set_saturation(self, saturation):
        """Set image saturation.
        Args:
            saturation: Image saturation.
        """
        pass

    @wrap
    def set_quality(self, quality):
        """Set JPEG image quality.
        Args:
            quality: Image quality.
        """
        pass

    @wrap
    def set_colorbar(self, enable):
        """Enable or disable the sensor color-bar test pattern.
        Args:
            enable: State to set; omit to read the current state.
        """
        pass

    @wrap
    def set_auto_gain(self, enable, **kwargs):
        """Enable or disable automatic gain control.
        Args:
            enable: State to set; omit to read the current state.
            kwargs: Additional keyword arguments.
        """
        pass

    @wrap
    def get_gain_db(self):
        """Return the current analog gain in dB.
        """
        pass

    @wrap
    def set_auto_whitebal(self, enable, **kwargs):
        """Enable or disable automatic white balance.
        Args:
            enable: State to set; omit to read the current state.
            kwargs: Additional keyword arguments.
        """
        pass

    @wrap
    def get_rgb_gain_db(self):
        """Return the current RGB gains in dB.
        """
        pass

    @wrap
    def set_auto_blc(self, enable, **kwargs):
        """Enable or disable automatic black-level correction.
        Args:
            enable: State to set; omit to read the current state.
            kwargs: Additional keyword arguments.
        """
        pass

    @wrap
    def get_blc_regs(self):
        """Return black-level correction register values.
        """
        pass

    def set_hmirror(self, enable):
        """Enable or disable horizontal mirroring.
        Args:
            enable: State to set; omit to read the current state.
        """
        if not self._dev_attr.dev_enable:
            raise AssertionError("should call reset() first")

        # if (self._dev_id > CAM_DEV_ID_MAX - 1):
        #     raise AssertionError(f"invaild sensor id {self._dev_id}, should < {CAM_DEV_ID_MAX - 1}")

        if enable:
            self._dev_attr.mirror = self._dev_attr.mirror | 1
        else:
            self._dev_attr.mirror = self._dev_attr.mirror & (~(1))

    def get_hmirror(self) -> bool:
        """Return whether horizontal mirroring is enabled.
        """
        if not self._dev_attr.dev_enable:
            raise AssertionError("should call reset() first")

        # if (self._dev_id > CAM_DEV_ID_MAX - 1):
        #     raise AssertionError(f"invaild sensor id {self._dev_id}, should < {CAM_DEV_ID_MAX - 1}")

        if self._dev_attr.mirror & 1:
            return True
        else:
            return False

    def set_vflip(self, enable):
        """Enable or disable vertical flipping.
        Args:
            enable: State to set; omit to read the current state.
        """
        if not self._dev_attr.dev_enable:
            raise AssertionError("should call reset() first")

        # if (self._dev_id > CAM_DEV_ID_MAX - 1):
        #     raise AssertionError(f"invaild sensor id {self._dev_id}, should < {CAM_DEV_ID_MAX - 1}")

        if enable:
            self._dev_attr.mirror = self._dev_attr.mirror | 2
        else:
            self._dev_attr.mirror = self._dev_attr.mirror & (~(2))

    def get_vflip(self) -> bool:
        """Return whether vertical flipping is enabled.
        """
        if not self._dev_attr.dev_enable:
            raise AssertionError("should call reset() first")

        # if (self._dev_id > CAM_DEV_ID_MAX - 1):
        #     raise AssertionError(f"invaild sensor id {self._dev_id}, should < {CAM_DEV_ID_MAX - 1}")

        if self._dev_attr.mirror & 2:
            return True
        else:
            return False

    @wrap
    def set_transpose(self, enable):
        """Enable or disable image transposition.
        Args:
            enable: State to set; omit to read the current state.
        """
        pass

    @wrap
    def get_transpose(self):
        """Return whether image transposition is enabled.
        """
        pass

    @wrap
    def set_auto_rotation(self, enable):
        """Enable or disable automatic rotation.
        Args:
            enable: State to set; omit to read the current state.
        """
        pass

    @wrap
    def get_auto_rotation(self):
        """Return whether automatic rotation is enabled.
        """
        pass

    @wrap
    def set_framebuffers(self, count):
        """Set the frame-buffer count.
        Args:
            count: Number of frame buffers.
        """
        pass

    @wrap
    def get_framebuffers(self):
        """Return the frame-buffer count.
        """
        pass

    @wrap
    def disable_delays(self, **kwargs):
        """Disable configuration delays.
        Args:
            kwargs: Additional keyword arguments.
        """
        pass

    @wrap
    def disable_full_flush(self, **kwargs):
        """Disable full-frame flushing.
        Args:
            kwargs: Additional keyword arguments.
        """
        pass

    @wrap
    def set_lens_correction(self, enabld, radi, coef):
        """Configure lens-correction parameters.
        Args:
            enabld: Value for enabld.
            radi: Value for radi.
            coef: Value for coef.
        """
        pass

    @wrap
    def set_vsync_callback(self, cb):
        """Register a vertical-sync callback.
        Args:
            cb: Callback function to register.
        """
        pass

    @wrap
    def set_frame_callback(self, cb):
        """Register a frame-completion callback.
        Args:
            cb: Callback function to register.
        """
        pass

    @wrap
    def ioctl(self, **kwargs):
        """Perform a sensor-specific control operation.
        Args:
            kwargs: Additional keyword arguments.
        """
        pass

    @wrap
    def set_color_palette(self, palette):
        """Set the image color palette.
        Args:
            palette: Color palette.
        """
        pass

    @wrap
    def get_color_palette(self):
        """Return the current image color palette.
        """
        pass

    @wrap
    def __write_reg(self, address, value):
        """Internal helper method.
        Args:
            address: Register address.
            value: Value to write.
        """
        pass

    @wrap
    def __read_reg(self, address):
        """Internal helper method.
        Args:
            address: Register address.
        """
        pass

    def again(self, again = None):
        """Get or set sensor analog gain.
        Args:
            again: Analog gain value; omit to read the current value.
        """
        if self.fd < 0:
            raise RuntimeError("can't get sensor fd")

        if again is None:
            # Get: 返回 k_sensor_gain 对象
            gain = k_sensor_gain()
            kd_mpi_sensor_again_get(self.fd, gain)
            return gain
        else:
            # Set: 接受 float 参数，自动封装成 k_sensor_gain 对象
            gain_obj = k_sensor_gain()
            gain_obj.gain[0] = again
            return kd_mpi_sensor_again_set(self.fd, gain_obj)

    # custom method
    def run(self):
        """Start the device.
        """
        if not self._dev_attr.dev_enable:
            raise AssertionError("should call reset() first")

        # if (self._dev_id > CAM_DEV_ID_MAX - 1):
        #     raise AssertionError(f"invaild sensor id {self._dev_id}, should < {CAM_DEV_ID_MAX - 1}")

        Sensor._check_mcm_sw_tile_at_run()

        if Sensor._is_mcm_device():
            return Sensor._run_mcm_device()

        if self._is_started:
            return

        self._apply_database_parse_mode()

        ret = kd_mpi_vicap_set_dev_attr(self._dev_id, self._dev_attr)
        if ret:
            raise RuntimeError(f"sensor({self._dev_id}) run error, set dev attr failed({ret})")

        # vicap channel attr set
        for chn_num in range(0, VICAP_CHN_ID_MAX):
            if not self._chn_attr[chn_num].chn_enable:
                continue
            self._calculate_buffer_size(chn_num)

            ret = kd_mpi_vicap_set_chn_attr(self._dev_id, chn_num, self._chn_attr[chn_num])
            if ret:
                raise RuntimeError(f"sensor({self._dev_id}) run error, set chn({chn_num}) attr failed({ret})")

        self._vicap_init_started = True
        ret = kd_mpi_vicap_init(self._dev_id)
        if ret:
            # if self._framesize[chn_num] is None:
            #     print(f"sensor({self._dev_id}) chn({chn_num}) not call `set_framesize`, at now should reboot board to fix it.")

            # if self._pixel_format[chn_num] is None:
            #     print(f"sensor({self._dev_id}) chn({chn_num}) not call `set_pixformat`, at now should reboot board to fix it.")

            raise RuntimeError(f"sensor({self._dev_id}) run error, vicap init failed({ret})")

        sensor_attr = k_vicap_sensor_attr()
        sensor_attr.dev_num = self._dev_id
        if 0x00 != kd_mpi_vicap_get_sensor_fd(sensor_attr):
            raise RuntimeError(f"sensor({self._dev_id}) run error, get sensor fd failed({ret})")
        self.fd = sensor_attr.sensor_fd

        print(f"sensor({self._dev_id}), mode {self._dev_attr.mode}, buffer_num {self._dev_attr.buffer_num}, buffer_size {self._dev_attr.buffer_size}")
        self._vicap_stream_start_started = True
        ret = kd_mpi_vicap_start_stream(self._dev_id)
        if ret:
            raise RuntimeError(f"sensor({self._dev_id}) run error, vicap start stream failed({ret})")

        self._is_started = True
        self._vb_mgmt_registered = True
        vb_mgmt_vicap_dev_inited(self._dev_id)

    def stop(self, is_del = False):
        """Stop processing.
        Args:
            is_del: Value for is_del.
        """
        # if (self._dev_id > CAM_DEV_ID_MAX - 1):
        #     raise AssertionError(f"invaild sensor id {self._dev_id}, should < {CAM_DEV_ID_MAX - 1}")

        # is_del = kwargs.get('is_del', False)

        if not is_del and not self._dev_attr.dev_enable:
            raise AssertionError("should call reset() first")

        cleanup_needed = (
            self._vicap_init_started
            or self._vicap_stream_start_started
            or self._is_started
        )
        was_started = self._is_started

        if not is_del and not cleanup_needed:
            print("warning: sensor not call run()")

        self._release_all_chn_image()

        stop_error = 0
        deinit_error = 0
        if cleanup_needed:
            if self._vicap_stream_start_started or was_started:
                ret = kd_mpi_vicap_stop_stream(self._dev_id)
                if ret:
                    stop_error = ret

                time.sleep_ms(Sensor.VICAP_STOP_STREAM_DELAY_MS)

            if self._vicap_init_started:
                ret = kd_mpi_vicap_deinit(self._dev_id)
                if ret:
                    deinit_error = ret

            if self._vb_mgmt_registered and not deinit_error:
                vb_mgmt_vicap_dev_deinited(self._dev_id)

        self._dev_attr.dev_enable = False
        self._is_started = False
        self._vicap_init_started = False
        self._vicap_stream_start_started = False
        self._vb_mgmt_registered = False

        Sensor._csis[self._csi_bus] = False
        Sensor._devs[self._dev_id] = None

        # Preserve the old error behavior for a fully started sensor, but do
        # not replace an IDE interrupt with a cleanup error for partial state.
        if not is_del and was_started:
            if stop_error:
                raise RuntimeError(f"sensor({self._dev_id}) stop error, stop stream failed({stop_error})")
            if deinit_error:
                raise RuntimeError(f"sensor({self._dev_id}) stop error, vicap deinit failed({deinit_error})")

    def _set_chn_fps(self, chn = CAM_CHN_ID_0, fps = 30):
        """Internal helper method.
        Args:
            chn: Media channel number.
            fps: Value for fps.
        """
        if (chn > CAM_CHN_ID_MAX - 1):
            raise AssertionError(f"invaild chn id {chn}, should < {CAM_CHN_ID_MAX - 1}")

        if fps != 0 and abs(self._dev_attr.sensor_info.fps - fps) > 3:
            self._chn_attr[chn].fps = fps

    def bind_info(self, x = 0, y = 0, chn = CAM_CHN_ID_0):
        """Return media channel binding information.
        Args:
            x: Horizontal coordinate in pixels.
            y: Vertical coordinate in pixels.
            chn: Media channel number.
        """
        if not self._dev_attr.dev_enable:
            raise AssertionError("should call reset() first")

        # if (self._dev_id > CAM_DEV_ID_MAX - 1):
        #     raise AssertionError(f"invaild sensor id {self._dev_id}, should < {CAM_DEV_ID_MAX - 1}")

        if (chn > CAM_CHN_ID_MAX - 1):
            raise AssertionError(f"invaild chn id {chn}, should < {CAM_CHN_ID_MAX - 1}")

        width = self.width(chn)
        height = self.height(chn)
        pix_format = self.get_pixformat(chn)

        kwargs = {
            'src': (CAMERA_MOD_ID, self._dev_id, chn),
            'rect': (x, y, width, height),
            'pix_format': pix_format,
        }

        return kwargs

    def auto_focus(self, enable = None):
        """Get or set automatic focus.
        Args:
            enable: State to set; omit to read the current state.
        """
        if self._is_started:
            raise RuntimeError("call should before Sensor.run()")
        return kd_mpi_auto_focus(self._dev_id, enable)

    def focus_pos(self, pos = None):
        """Get or set the lens focus position.
        Args:
            pos: Position or frame index.
        """
        if self.fd < 0:
            raise RuntimeError("can't get sensor fd")
        return kd_mpi_focus_pos(self.fd, pos)

    def focus_caps(self):
        """Return lens focus capabilities.
        """
        if self.fd < 0:
            raise RuntimeError("can't get sensor fd")
        return kd_mpi_sensor_get_focus_caps(self.fd)

    def get_exposure_time_range(self):
        """Return the sensor exposure-time range.
        """
        if self.fd < 0:
            raise RuntimeError("can't get sensor fd")
        return kd_mpi_sensor_get_exposure_time_range(self.fd)

    def auto_exposure(self, enable=None):
        """Get or set automatic exposure.
        Args:
            enable: State to set; omit to read the current state.
        """
        if not hasattr(self, '_dev_attr'):
            raise RuntimeError("should call reset() first")
        
        if enable is None:
            # Get current auto exposure status
            return bool(self._dev_attr.pipe_ctrl.bits.ae_enable)
        else:
            # Set auto exposure status
            self._dev_attr.pipe_ctrl.bits.ae_enable = 1 if enable else 0
            return True


    def exposure(self, exposure_us=None):
        """Get or set sensor exposure time.
        Args:
            exposure_us: Exposure time in microseconds; omit to read the current value.
        """
        if self.fd < 0:
            raise RuntimeError("can't get sensor fd")

        if not hasattr(self, '_dev_attr'):
            raise RuntimeError("should call run() first")
                
        if exposure_us is None:
            # Get exposure time (底层返回秒，转换为微秒)
            time_sec = kd_mpi_sensor_intg_time_get(self.fd)
            if time_sec is None:
                return None
            return time_sec * 1000000.0
        else:
            if self._dev_attr.pipe_ctrl.bits.ae_enable:
                raise RuntimeError("now is auto_ae mode,you need close auto_ae first")
            # Set exposure time (微秒转换为秒)
            time_sec = exposure_us / 1000000.0
            return kd_mpi_sensor_intg_time_set(self.fd, time_sec)


    @staticmethod
    def list_mode(id=None, lane_pref=VICAP_MIPI_2LANE):
        """List supported sensor resolution and frame-rate modes.

        Args:
            id: CSI bus index (0/1/2). Default: board default sensor CSI.
            lane_pref: Same as Sensor(..., lane_pref=...); default VICAP_MIPI_2LANE.
        """
        # 获取默认传感器 ID
        if id is None:
            id = get_default_sensor()

        if (id > CAM_DEV_ID_MAX - 1):
            raise AssertionError(f"invaild sensor id {id}, should < {CAM_DEV_ID_MAX - 1}")

        if lane_pref < 0 or lane_pref > 2:
            raise ValueError(
                "lane_pref must be VICAP_MIPI_ANY/2LANE/4LANE (0/1/2)"
            )

        # 使用 kd_mpi_sensor_adapt_get_ex 获取传感器信息
        info = k_vicap_sensor_info()
        cfg = k_vicap_probe_config()
        cfg.csi = id
        cfg.fps = 30  # 默认帧率
        cfg.width = 640  # 默认宽度
        cfg.height = 480  # 默认高度
        ret = kd_mpi_sensor_adapt_get_ex(cfg, info, lane_pref)
        if 0 != ret:
            raise RuntimeError(
                "Can not found sensor on CSI %s (probe %sx%s@%s, lane_pref=%s)"
                % (id, cfg.width, cfg.height, cfg.fps, lane_pref)
            )
        
        # 获取传感器名称
        sensor_name = cfg.name.decode()
        
        # 调用 MPI 层接口获取模式列表
        modes = kd_mpi_sensor_list_mode(sensor_name)
        
        if modes is None:
            return (sensor_name, [])
        
        # 打印格式化输出
        print(f"Sensor Mode List (CSI {id}, {sensor_name}):")
        print("-" * 45)
        print(f"{'Index':<6} {'Resolution':<15} {'FPS':<6}")
        print("-" * 45)
        for i, mode in enumerate(modes):
            resolution = f"{mode['width']}x{mode['height']}"
            print(f"{i:<6} {resolution:<15} {mode['fps']:<6}")
        print("-" * 45)
        print(f"Total: {len(modes)} modes")
        
        return (sensor_name, modes)

    def get_again_range(self):
        """Return the supported analog-gain range.
        """
        if self.fd < 0:
            raise RuntimeError("can't get sensor fd")
        
        return kd_mpi_sensor_get_gain_range(self.fd)
