import ulab.numpy as np
import os
from time import *
import time
import utime
import sys
import ujson
import image

class ScopedTiming:
    """Optionally measure and print the elapsed time of a with block."""
    def __init__(self, info="", enable_profile=True):
        """Configure the optional elapsed-time measurement.

        Args:
            info (str): Label printed with elapsed time.
            enable_profile (bool): Whether to measure and print elapsed time.
        """
        self.info = info
        self.enable_profile = enable_profile

    def __enter__(self):
        """Start timing when profiling is enabled.

        Returns:
            ScopedTiming: This context manager.
        """
        if self.enable_profile:
            self.start_time = time.time_ns()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Print elapsed milliseconds when profiling is enabled.

        Args:
            exc_type (type or None): Exception type supplied by the context manager protocol.
            exc_value (BaseException or None): Exception supplied by the context manager protocol.
            traceback (object or None): Traceback supplied by the context manager protocol.

        Returns:
            None: Exceptions from the with block are not suppressed.
        """
        if self.enable_profile:
            elapsed_time = time.time_ns() - self.start_time
            print(f"{self.info} took {elapsed_time / 1000000:.2f} ms")

color_four = [
    (255, 220, 20, 60),
    (255, 119, 11, 32),
    (255, 0, 0, 142),
    (255, 0, 0, 230),
    (255, 106, 0, 228),
    (255, 0, 60, 100),
    (255, 0, 80, 100),
    (255, 0, 0, 70),
    (255, 0, 0, 192),
    (255, 250, 170, 30),
    (255, 100, 170, 30),
    (255, 220, 220, 0),
    (255, 175, 116, 175),
    (255, 250, 0, 30),
    (255, 165, 42, 42),
    (255, 255, 77, 255),
    (255, 0, 226, 252),
    (255, 182, 182, 255),
    (255, 0, 82, 0),
    (255, 120, 166, 157),
    (255, 110, 76, 0),
    (255, 174, 57, 255),
    (255, 199, 100, 0),
    (255, 72, 0, 118),
    (255, 255, 179, 240),
    (255, 0, 125, 92),
    (255, 209, 0, 151),
    (255, 188, 208, 182),
    (255, 0, 220, 176),
    (255, 255, 99, 164),
    (255, 92, 0, 73),
    (255, 133, 129, 255),
    (255, 78, 180, 255),
    (255, 0, 228, 0),
    (255, 174, 255, 243),
    (255, 45, 89, 255),
    (255, 134, 134, 103),
    (255, 145, 148, 174),
    (255, 255, 208, 186),
    (255, 197, 226, 255),
    (255, 171, 134, 1),
    (255, 109, 63, 54),
    (255, 207, 138, 255),
    (255, 151, 0, 95),
    (255, 9, 80, 61),
    (255, 84, 105, 51),
    (255, 74, 65, 105),
    (255, 166, 196, 102),
    (255, 208, 195, 210),
    (255, 255, 109, 65),
    (255, 0, 143, 149),
    (255, 179, 0, 194),
    (255, 209, 99, 106),
    (255, 5, 121, 0),
    (255, 227, 255, 205),
    (255, 147, 186, 208),
    (255, 153, 69, 1),
    (255, 3, 95, 161),
    (255, 163, 255, 0),
    (255, 119, 0, 170),
    (255, 0, 182, 199),
    (255, 0, 165, 120),
    (255, 183, 130, 88),
    (255, 95, 32, 0),
    (255, 130, 114, 135),
    (255, 110, 129, 133),
    (255, 166, 74, 118),
    (255, 219, 142, 185),
    (255, 79, 210, 114),
    (255, 178, 90, 62),
    (255, 65, 70, 15),
    (255, 127, 167, 115),
    (255, 59, 105, 106),
    (255, 142, 108, 45),
    (255, 196, 172, 0),
    (255, 95, 54, 80),
    (255, 128, 76, 255),
    (255, 201, 57, 1),
    (255, 246, 0, 122),
    (255, 191, 162, 208)
]

def read_json(json_path):
    """Read and parse a JSON file.

    Args:
        json_path (str): Path to the JSON file.

    Returns:
        object: Decoded JSON value.

    Notes:
        The file is closed on both success and failure. Read/parse errors
        are printed and re-raised.
    """
    try:
        with open(json_path, 'r') as file:
            data = ujson.load(file)
        return data
    except Exception as e:
        print("Error reading JSON file:", e)
        raise e

# 从本地读入图片，并实现HWC转CHW
def read_image(img_path):
    """Load an RGB888 image and create a planar array copy.

    Args:
        img_path (str): Path to the image file.

    Returns:
        tuple: (CHW ndarray, RGB888 image.Image).

    Notes:
        The array owns a contiguous copy. The returned image is retained
        by the caller and can be used separately from that array.
    """
    img_data = image.Image(img_path)
    img_rgb888=img_data.to_rgb888()
    img_hwc=img_rgb888.to_numpy_ref()
    shape=img_hwc.shape
    img_tmp = img_hwc.reshape((shape[0] * shape[1], shape[2]))
    img_tmp_trans = img_tmp.transpose()
    img_res=img_tmp_trans.copy()
    img_chw=img_res.reshape((shape[2],shape[0],shape[1]))
    return img_chw,img_rgb888

def get_colors(classes_num):
    """Select ARGB colors from the repeating class palette.

    Args:
        classes_num (int): Number of colors requested.

    Returns:
        list: ARGB tuples; empty when classes_num is not positive.
    """
    colors = []
    num_available_colors = len(color_four)
    for i in range(classes_num):
        # 使用模运算来循环获取颜色
        colors.append(color_four[i % num_available_colors])
    return colors

def center_crop_param(input_size):
    """Calculate a centered square crop.

    Args:
        input_size (list): Input [width, height], in pixels.

    Returns:
        tuple or None: (top, left, side), or None if input_size has no two dimensions.
    """
    if len(input_size)==2:
        m=min(input_size[0],input_size[1])
        top=(input_size[1]-m)//2
        left=(input_size[0]-m)//2
        return top,left,m

def letterbox_pad_param(input_size,output_size):
    """Calculate aspect-preserving padding aligned to the top left.

    Args:
        input_size (list): Input [width, height], in pixels.
        output_size (list): Target [width, height], in pixels.

    Returns:
        tuple: (top, bottom, left, right, scale_ratio).

    Notes:
        top and left are zero; padding is added on the bottom and right.
    """
    ratio_w = output_size[0] / input_size[0]  # 宽度缩放比例
    ratio_h = output_size[1] / input_size[1]   # 高度缩放比例
    ratio = min(ratio_w, ratio_h)  # 取较小的缩放比例
    new_w = int(ratio * input_size[0])  # 新宽度
    new_h = int(ratio * input_size[1])  # 新高度
    dw = (output_size[0] - new_w) / 2  # 宽度差
    dh = (output_size[1] - new_h) / 2  # 高度差
    top = int(round(0))
    bottom = int(round(dh * 2 + 0.1))
    left = int(round(0))
    right = int(round(dw * 2 - 0.1))
    return top, bottom, left, right,ratio

def center_pad_param(input_size,output_size):
    """Calculate centered, aspect-preserving letterbox padding.

    Args:
        input_size (list): Input [width, height], in pixels.
        output_size (list): Target [width, height], in pixels.

    Returns:
        tuple: (top, bottom, left, right, scale_ratio).

    Notes:
        An odd padding pixel is assigned to the bottom or right edge.
    """
    ratio_w = output_size[0] / input_size[0]  # 宽度缩放比例
    ratio_h = output_size[1] / input_size[1]   # 高度缩放比例
    ratio = min(ratio_w, ratio_h)  # 取较小的缩放比例
    new_w = int(ratio * input_size[0])  # 新宽度
    new_h = int(ratio * input_size[1])  # 新高度
    dw = (output_size[0] - new_w) / 2  # 宽度差
    dh = (output_size[1] - new_h) / 2  # 高度差
    top = int(round(dh-0.1))
    bottom = int(round(dh + 0.1))
    left = int(round(dw-0.1))
    right = output_size[0] - new_w - left
    return top, bottom, left, right,ratio

# softmax函数
def softmax(x):
    """Compute numerically stabilized softmax over the whole array.

    Args:
        x (ulab.numpy.ndarray): Values to transform.

    Returns:
        ulab.numpy.ndarray: Probabilities normalized by the global sum.

    Notes:
        The reduction is global, not per axis. The input must be nonempty.
    """
    exp_x = np.exp(x - np.max(x))
    return exp_x / np.sum(exp_x)

def sigmoid(x):
    """Apply the logistic sigmoid elementwise.

    Args:
        x (ulab.numpy.ndarray): Values to transform.

    Returns:
        ulab.numpy.ndarray or scalar: Values transformed by 1 / (1 + exp(-x)).
    """
    return 1 / (1 + np.exp(-x))

def chw2hwc(np_array):
    """Copy a CHW array into contiguous HWC layout.

    Args:
        np_array (ulab.numpy.ndarray): Three-dimensional input array.

    Returns:
        ulab.numpy.ndarray: Independent HWC array with the input dtype.

    Raises:
        Exception: The input is not three-dimensional.
    """
    if len(np_array.shape)!=3:
        raise Exception("chw2hwc input shape error,shape should be chw")
    ori_shape = (np_array.shape[0], np_array.shape[1], np_array.shape[2])
    c_hw_ = np_array.reshape((ori_shape[0], ori_shape[1] * ori_shape[2]))
    hw_c_ = c_hw_.transpose()
    new_array = hw_c_.copy()
    hwc_array = new_array.reshape((ori_shape[1], ori_shape[2], ori_shape[0]))
    return hwc_array

def hwc2chw(np_array):
    """Copy an HWC array into contiguous CHW layout.

    Args:
        np_array (ulab.numpy.ndarray): Three-dimensional input array.

    Returns:
        ulab.numpy.ndarray: Independent CHW array with the input dtype.

    Raises:
        Exception: The input is not three-dimensional.
    """
    if len(np_array.shape)!=3:
        raise Exception("hwc2chw input shape error,shape should be hwc")
    ori_shape = (np_array.shape[0], np_array.shape[1], np_array.shape[2])
    hw_c_ = np_array.reshape((ori_shape[0] * ori_shape[1], ori_shape[2]))
    c_hw_ = hw_c_.transpose()
    new_array = c_hw_.copy()
    chw_array = new_array.reshape((ori_shape[2], ori_shape[0], ori_shape[1]))
    return chw_array
