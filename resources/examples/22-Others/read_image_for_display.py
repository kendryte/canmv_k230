"""
Script: read_image_for_display.py
脚本名称：read_image_for_display.py

Description:
    This script reads an image from the file system, resizes it using Ai2d utilities
    to match the target display resolution (e.g., ST7701 or LT9611), and prepares it
    for display on an embedded system.

    The script handles image format conversion between HWC and CHW layouts required
    by Ai2d, configures the resizing parameters, and returns a resized image object
    compatible with the system display interface.

脚本说明：
    本脚本从文件系统读取图片，使用 Ai2d 工具缩放以适配目标显示分辨率（如 ST7701 或 LT9611），
    并为嵌入式系统上的图像显示做好准备。

    脚本处理 HWC 与 CHW 图像布局的转换，配置缩放参数，并返回适配屏幕分辨率的图像对象，
    供显示接口使用。

Author: Canaan Developer
作者：Canaan 开发者
"""

from media.display import *
from media.media import *
import nncase_runtime as nn
import ulab.numpy as np
import gc


def read_image_for_display(display_mode,image_path):
    # 屏幕显示分辨率
    output_w=800
    output_h=480
    if display_mode=="st7701":
        output_w=800
        output_h=480
    elif display_mode=="lt9611":
        output_w=1920
        output_h=1080
    else:
        output_w=800
        output_h=480
    # 读入图片
    img_ori=image.Image(image_path).to_rgb888()
    print(img_ori)
    # ST7701只能显示800*480分辨率的图像，需要使用ai2d做resize，实现适配屏幕

    # 读入的图片是HWC的，需要使用transpose将数据转成CHW，用于创建ai2d输入tensor,[H,W,C]->[H*W,C]->[C,H*W]->[C,H,W]
    img_ori_hwc=img_ori.to_numpy_ref()
    shape_input=img_ori_hwc.shape
    img_tmp = img_ori_hwc.reshape((shape_input[0] * shape_input[1], shape_input[2]))
    img_tmp_trans = img_tmp.transpose().copy()
    img_ori_chw=img_tmp_trans.reshape((shape_input[2],shape_input[0],shape_input[1]))
    # 构建ai2d的输入和输出tensor，并构造ai2d实例，进行resize配置，并执行resize
    ai2d_input_tensor = nn.from_numpy(img_ori_chw)
    ai2d_output_np = np.ones((1,3,output_h,output_w),dtype=np.uint8)
    ai2d_output_tensor = nn.from_numpy(ai2d_output_np)
    ai2d=nn.ai2d()
    ai2d.set_dtype(nn.ai2d_format.NCHW_FMT, nn.ai2d_format.NCHW_FMT, np.uint8, np.uint8)
    ai2d.set_resize_param(True,nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
    ai2d_builder = ai2d.build([1,3,img_ori_chw.shape[1],img_ori_chw.shape[2]], [1,3,output_h,output_w])
    ai2d_builder.run(ai2d_input_tensor, ai2d_output_tensor)
    # 输出tensor转numpy.ndarray
    ai2d_output_np=ai2d_output_tensor.to_numpy()[0]
    # 输出为CHW，创建Image实例需要使用HWC排布的数据，使用transpose,[C,H,W]->[C,H*W]->[H*W,C]->[H,W,C]
    shape_output=ai2d_output_np.shape
    img_tmp_ = ai2d_output_np.reshape((shape_output[0],shape_output[1]*shape_output[2]))
    img_tmp_trans_ = img_tmp_.transpose().copy()
    img_out_hwc=img_tmp_trans_.reshape((shape_output[1],shape_output[2],shape_output[0]))
    img_out = image.Image(output_w, output_h, image.RGB888, alloc=image.ALLOC_REF,data =img_out_hwc)
    return img_out


Display.init(Display.ST7701,width = 800, height = 480,to_ide=True)
  #初始化media资源管理器
img_path="/sdcard/examples/utils/test.jpg"
img=read_image_for_display("st7701",img_path)
while True:
    Display.show_image(img)
gc.collect()
