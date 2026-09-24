import os
import ujson
from media.sensor import *
from media.display import *
from media.media import *
from libs.Utils import ScopedTiming
import ulab.numpy as np
import image
import gc
import sys
import time

from libs.DisplayConfig import get_default_display_mode, get_display_type
class PipeLine:
    """Manage sensor capture, video display and the application OSD image."""
    def __init__(self,rgb888p_size=[224,224],display_mode="hdmi",display_size=None,osd_layer_num=1,debug_mode=0):
        # sensor给AI的图像分辨率
        """Store pipeline settings without initializing hardware.

        Args:
            rgb888p_size (list or None): RGB planar input [width, height], in pixels.
            display_mode (str): Driver name, or 'auto' for the board policy.
                Other unrecognized mode names retain the ST7701 fallback.
            display_size (list or None): Display [width, height], in pixels.
            osd_layer_num (int): Number of OSD layers requested from Display.
            debug_mode (int): Enable timing output when greater than zero.

        Notes:
            The RGB planar width is aligned to 16 pixels. Call create() before
            capture and destroy() to release initialized hardware.
        """
        self.rgb888p_size=[ALIGN_UP(rgb888p_size[0],16),rgb888p_size[1]]
        # 视频输出VO图像分辨率
        if display_size is None:
            self.display_size=None
        else:
            self.display_size=[display_size[0],display_size[1]]
        # 视频显示模式，支持："lcd"(default st7701), "hdmi"(default lt9611), "lt9611", "st7701", "hx8399", "nt35516", "nt35532", "gc9503", "aml020t", "jd9852", "ili9806", "virt"；若选择"virt"，可通过display_size自定义分辨率
        self.display_mode=get_default_display_mode() if display_mode == "auto" else display_mode
        # sensor对象
        self.sensor=None
        # osd显示Image对象
        self.osd_img=None
        self.cur_frame=None
        self.debug_mode=debug_mode
        self.osd_layer_num = osd_layer_num
        self.crop_param=[0,0,0,0]
        self._display_ready = False
        self._video_bound = False
        self._sensor_reset = False

    # PipeLine初始化函数
    def create(self,sensor=None,sensor_id=None,hmirror=None,vflip=None,fps=60,to_ide=True,crop_vertical=False):
        """Initialize capture, display, OSD storage and video binding.

        Args:
            sensor (Sensor or None): Sensor to configure and manage, or None to create one.
            sensor_id (int or None): Sensor ID used when creating a sensor.
            hmirror (bool or None): Horizontal mirroring; None preserves the sensor setting.
            vflip (bool or None): Vertical flipping; None preserves the sensor setting.
            fps (int): Requested sensor frame rate; some boards/drivers use 30 FPS.
            to_ide (bool): Enable display output to the IDE.
            crop_vertical (bool): Center-crop the 1920x1080 source to the display aspect ratio.

        Returns:
            None.

        Raises:
            RuntimeError: The pipeline is already initialized.

        Notes:
            A supplied sensor is configured and stopped by this pipeline.
            The actual Display dimensions replace the requested display_size.
            Initialization failures trigger partial-resource cleanup.
        """
        if self.sensor is not None or self._display_ready:
            raise RuntimeError("PipeLine must be destroyed before create")
        try:
            with ScopedTiming("init PipeLine",self.debug_mode > 0):
                if self.display_mode=="nt35516":
                    fps=30
                # 默认 FPS
                default_fps = 30
                # 支持指定 FPS 的板子类型
                fps_map = {
                    "k230d_canmv_bpi_zero": default_fps,
                    "k230_canmv_lckfb": default_fps,
                    "k230d_canmv_atk_dnk230d": default_fps,
                }

                # 获取板子类型
                brd = os.uname()[-1]
                # 决定使用的 FPS
                board_fps = fps_map.get(brd, fps)
                # 初始化 sensor
                if sensor_id is not None:
                    self.sensor = sensor if sensor is not None else Sensor(id=sensor_id, fps=board_fps)
                else:
                    self.sensor = sensor if sensor is not None else Sensor(fps=board_fps)
                # 重置并设置镜像/翻转
                self.sensor.reset()
                self._sensor_reset = True
                if isinstance(hmirror, bool):
                    self.sensor.set_hmirror(hmirror)
                if isinstance(vflip, bool):
                    self.sensor.set_vflip(vflip)


                display_type = get_display_type(self.display_mode)

                # Call init
                if self.display_size:
                    Display.init(
                        display_type,
                        width=self.display_size[0],
                        height=self.display_size[1],
                        osd_num=self.osd_layer_num,
                        to_ide=to_ide
                    )
                else:
                    Display.init(
                        display_type,
                        osd_num=self.osd_layer_num,
                        to_ide=to_ide
                    )

                self._display_ready = True
                self.display_size = [Display.width(), Display.height()]

                if crop_vertical:
                    r=1080/self.display_size[1]
                    crop_w=int(r*self.display_size[0])
                    crop_h=1080
                    crop_x=(1920-crop_w)//2
                    crop_y=0
                    self.crop_param=[crop_x,crop_y,crop_w,crop_h]
                    # 通道0直接给到显示VO，格式为YUV420
                    self.sensor.set_framesize(w = self.display_size[0], h = self.display_size[1],chn=CAM_CHN_ID_0,crop=(crop_x,crop_y,crop_w,crop_h))
                    self.sensor.set_pixformat(Sensor.YUV420SP, chn=CAM_CHN_ID_0)
                    # 通道2给到AI做算法处理，格式为RGB888
                    self.sensor.set_framesize(w = self.rgb888p_size[0], h = self.rgb888p_size[1], chn=CAM_CHN_ID_2,crop=(crop_x,crop_y,crop_w,crop_h))
                    self.sensor.set_pixformat(Sensor.RGBP888, chn=CAM_CHN_ID_2)
                else:
                    # 通道0直接给到显示VO，格式为YUV420
                    self.sensor.set_framesize(w = self.display_size[0], h = self.display_size[1],chn=CAM_CHN_ID_0)
                    self.sensor.set_pixformat(Sensor.YUV420SP, chn=CAM_CHN_ID_0)
                    # 通道2给到AI做算法处理，格式为RGB888
                    self.sensor.set_framesize(w = self.rgb888p_size[0], h = self.rgb888p_size[1], chn=CAM_CHN_ID_2)
                    self.sensor.set_pixformat(Sensor.RGBP888, chn=CAM_CHN_ID_2)

                # OSD图像初始化
                self.osd_img = image.Image(self.display_size[0], self.display_size[1], image.ARGB8888)

                sensor_bind_info = self.sensor.bind_info(x = 0, y = 0, chn = CAM_CHN_ID_0)
                Display.bind_layer(**sensor_bind_info, layer = Display.LAYER_VIDEO1)
                self._video_bound = True

                # 启动sensor
                self.sensor.run()
        except BaseException:
            try:
                self.destroy()
            except Exception as error:
                print("PipeLine initialization cleanup failed:", error)
            raise

    # 获取一帧图像数据，返回格式为ulab的array数据
    def get_frame(self):
        """Capture an RGB planar frame from sensor channel 2.

        Returns:
            ulab.numpy.ndarray: Borrowed CHW view of the captured frame.

        Notes:
            Process the view before the next get_frame() or destroy() call.
            Copy the array when it must outlive the captured frame.
        """
        with ScopedTiming("get a frame",self.debug_mode > 0):
            self.cur_frame = self.sensor.snapshot(chn=CAM_CHN_ID_2)
            input_np=self.cur_frame.to_numpy_ref()
            return input_np

    # 在屏幕上显示osd_img
    def show_image(self,flag=None):
        """Present osd_img on display OSD layer 3.

        Args:
            flag (int or None): Optional flag forwarded to Display.show_image().

        Returns:
            None.
        """
        with ScopedTiming("show result",self.debug_mode > 0):
            if flag is None:
                Display.show_image(self.osd_img, 0, 0, Display.LAYER_OSD3)
            else:
                Display.show_image(self.osd_img, 0, 0, Display.LAYER_OSD3,flag=flag)

    def get_display_size(self):
        """Get the pipeline's current display dimensions.

        Returns:
            list or None: Internal [width, height] list, possibly None before create().

        Notes:
            After create(), dimensions are queried from Display. The returned
            list is shared with the pipeline, not copied.
        """
        return self.display_size

    # PipeLine销毁函数
    def destroy(self):
        """Release video binding, display, sensor and image references.

        Returns:
            None.

        Raises:
            Exception: The first cleanup error after the applicable cleanup steps.

        Notes:
            Completed cleanup steps are skipped on retry. If display teardown
            fails, resources still needed by the active video path are retained.
        """
        with ScopedTiming("deinit PipeLine", self.debug_mode > 0):
            os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
            error = None
            if self._video_bound:
                try:
                    Display.disable_layer(Display.LAYER_VIDEO1)
                    self._video_bound = False
                except Exception as exc:
                    error = exc
            # Display must stop scanning buffers before Sensor/VB is released.
            if self._display_ready:
                try:
                    Display.deinit()
                    self._display_ready = False
                    self._video_bound = False
                except Exception as exc:
                    if error is None:
                        error = exc
            if self.sensor is not None and not self._video_bound:
                try:
                    if self._sensor_reset:
                        self.sensor.stop()
                    else:
                        # SDK stop() rejects an unreset/already-reset device unless
                        # called through its partial-initialization cleanup path.
                        self.sensor.stop(is_del=True)
                    self.sensor = None
                    self._sensor_reset = False
                except Exception as exc:
                    self._sensor_reset = False
                    if error is None:
                        error = exc
            if self.sensor is None:
                self.cur_frame = None
            if not self._display_ready:
                self.osd_img = None
            if error is not None:
                raise error
