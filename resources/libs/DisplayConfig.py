"""Board display policy shared by AI pipelines and standalone applications."""

import os
from media.display import Display


def get_default_display_mode(board_type=None):
    """Select the example display policy for a known SDK board.

    Args:
        board_type (str or None): os.uname()[-1] board identifier; None
            queries the running firmware.

    Returns:
        str: Display mode accepted by PipeLine.

    Raises:
        ValueError: The board has no default policy; select a mode explicitly.

    Notes:
        This selects a driver, not the physically attached panel. LCD is
        preferred on supported accessory boards; the original CanMV boards
        retain HDMI. Display.init() selects the driver's default resolution.
    """
    if board_type is None:
        board_type = os.uname()[-1]
    # Policy derived from SDK configs/*defconfig, not hardware detection.
    modes = {
        "k230_canmv": "hdmi",
        "k230_canmv_v3p0": "hdmi",
        "k230_evb": "hx8399",
        "k230d_evb": "hx8399",
        "k230_canmv_rtt_evb": "nt35516",
        "k230_canmv_01studio": "st7701",
        "k230_canmv_lckfb": "st7701",
        "k230_canmv_yahboom": "st7701",
        "k230_canmv_mrt": "st7701",
        "k230_canmv_hiwonder": "st7701",
        "k230_canmv_dongshanpi": "ili9806",
        "k230_canmv_gt6700": "gc9503",
        "k230_canmv_wondermk": "jd9852",
        "k230_labplus_1956": "st7701",
        "k230d_canmv_bpi_zero": "st7701",
        "k230d_canmv_atk_dnk230d": "st7701",
        "k230d_canmv_junroc_ai_cam": "st7701",
        "k230d_canmv_lushanpi_lite": "st7701",
        "k230d_canmv_mini": "st7701",
        "k230d_labplus_ai_camera": "st7701",
        "k230d_labplus_ai_camera_v2": "st7701",
    }
    mode = modes.get(board_type)
    if mode is None:
        raise ValueError("No default display for board %s; set display_mode explicitly" % board_type)
    return mode


# PipeLine类

def get_display_type(display_mode="auto"):
    """Resolve a display mode or preserve an explicit SDK display constant.

    Args:
        display_mode (str or int): 'auto', a driver name, or a Display constant.

    Returns:
        int: Display driver type accepted by Display.init().

    Raises:
        ValueError: Auto mode is requested on an unknown board.

    Notes:
        Unknown strings retain PipeLine's legacy ST7701 fallback.
    """
    if isinstance(display_mode, int):
        return display_mode
    if display_mode == "auto":
        display_mode = get_default_display_mode()
    modes = {
        "hdmi": Display.LT9611, "lt9611": Display.LT9611,
        "lcd": Display.ST7701, "st7701": Display.ST7701,
        "hx8399": Display.HX8399, "nt35516": Display.NT35516,
        "nt35532": Display.NT35532, "gc9503": Display.GC9503,
        "aml020t": Display.AML020T, "jd9852": Display.JD9852,
        "ili9806": Display.ILI9806, "virt": Display.VIRT,
    }
    return modes.get(display_mode, Display.ST7701)


def init_display(display_mode="auto", display_size=None, **kwargs):
    """Initialize a display and return its actual application dimensions.

    Args:
        display_mode (str or int): Board policy, driver name, or Display constant.
        display_size (list or None): Requested [width, height]; None uses the
            SDK driver default. Use this argument instead of width/height kwargs.
        **kwargs: Additional Display.init options such as osd_num and to_ide.

    Returns:
        list: Actual [width, height] after display initialization.

    Notes:
        The caller owns Display.deinit(). This helper does not start a sensor
        or change AI input, decoder, or recording dimensions.
    """
    display_type = get_display_type(display_mode)
    if display_size is not None:
        kwargs["width"], kwargs["height"] = display_size
    Display.init(display_type, **kwargs)
    return [Display.width(), Display.height()]


class DisplayImage:
    """Resize packed or planar RGB888 arrays with a reusable AI2D pipeline.

    Native dependencies are imported on construction. The caller owns deinit();
    returned images reference independent copies of the resized output.
    """

    def __init__(self, display_size, planar=False):
        """Create a resizer for the actual display size.

        Args:
            display_size (list): Target [width, height], in pixels.
            planar (bool): True for CHW input, False for HWC input.
        """
        from libs.AI2D import Ai2d
        import nncase_runtime as nn
        import ulab.numpy as np
        self.width, self.height = display_size
        self.input_shape = None
        self.ai2d = Ai2d()
        try:
            self.ai2d.set_ai2d_dtype(
                nn.ai2d_format.NCHW_FMT if planar else nn.ai2d_format.RGB_packed,
                nn.ai2d_format.RGB_packed, np.uint8, np.uint8)
            self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
        except BaseException:
            try:
                self.ai2d.deinit()
            except Exception as error:
                print("DisplayImage cleanup failed:", error)
            raise

    def run(self, input_np):
        """Resize a contiguous uint8 RGB array without modifying it.

        Args:
            input_np (ulab.numpy.ndarray): CHW or HWC data as configured.

        Returns:
            image.Image: RGB888 image referencing an independent output copy.

        Notes:
            Keep borrowed source storage valid until this method returns.
            Only an input shape change rebuilds the native pipeline.
        """
        import image
        shape = tuple(input_np.shape)
        if shape != self.input_shape:
            self.ai2d.build([1] + list(shape), [1, self.height, self.width, 3])
            self.input_shape = shape
        pixels = self.ai2d.run(input_np).to_numpy()
        return image.Image(self.width, self.height, image.RGB888,
                           alloc=image.ALLOC_REF, data=pixels)

    def deinit(self):
        """Release native resize resources; failed releases can be retried."""
        self.ai2d.deinit()
        self.input_shape = None
