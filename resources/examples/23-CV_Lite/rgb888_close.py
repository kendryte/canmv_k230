# ============================================================
# MicroPython 图像闭运算测试代码（使用 cv_lite 扩展模块）
# Image Closing (Dilate + Erode) Test using cv_lite extension
# ============================================================

import time, os, gc
from machine import Pin
from media.sensor import *   # 摄像头接口 / Camera interface
from media.display import *  # 显示接口 / Display interface
from media.media import *    # 媒体资源管理器 / Media manager
import cv_lite               # cv_lite 扩展模块（含闭操作）/ AI CV extension (close function)
import ulab.numpy as np      # NumPy-like ndarray for MicroPython

# -------------------------------
# 图像尺寸设置 / Image resolution
# -------------------------------
image_shape = [480, 640]  # 高 x 宽 / Height x Width

# -------------------------------
# 初始化摄像头 / Initialize camera
# -------------------------------
sensor = Sensor(id=2, width=1280, height=720,fps=90)
sensor.reset()
sensor.set_framesize(width=image_shape[1], height=image_shape[0])
sensor.set_pixformat(Sensor.RGB888)  # 设置像素格式为 RGB888 / Set pixel format to RGB888

# --------------------------------------
# 初始化显示模块（IDE 虚拟显示模式）
# Initialize display (IDE virtual mode)
# --------------------------------------
Display.init(Display.VIRT, width=image_shape[1], height=image_shape[0], to_ide=True)

# -------------------------------
# 初始化媒体资源管理器 / Init media manager
# -------------------------------

sensor.run()

# -------------------------------
# 启动帧率计时器 / Start FPS timer
# -------------------------------
clock = time.clock()

# -------------------------------
# 闭操作参数设置 / Closing parameters
# -------------------------------
kernel_size = 3         # 卷积核尺寸（建议为奇数）/ Kernel size (recommended odd)
iterations = 1          # 操作迭代次数 / Number of morphological passes
threshold_value = 100   # 二值化阈值（0=使用 Otsu 自动阈值）/ Threshold for binarization (0 = Otsu)

# -------------------------------
# 主循环 / Main loop
# -------------------------------
while True:
    clock.tick()  # 开始计时 / Start frame timing

    # 获取图像帧 / Capture a frame
    img = sensor.snapshot()
    img_np = img.to_numpy_ref()  # 获取 RGB888 ndarray 引用 / Get RGB888 ndarray reference (HWC)

    # 应用闭操作（先膨胀后腐蚀）/ Apply closing (dilate then erode)
    result_np = cv_lite.rgb888_close(
        image_shape,
        img_np,
        kernel_size,
        iterations,
        threshold_value
    )

    # 构造图像对象（灰度图）用于显示 / Wrap processed grayscale image for display
    img_out = image.Image(image_shape[1], image_shape[0], image.GRAYSCALE,
                          alloc=image.ALLOC_REF, data=result_np)

    # 显示闭操作后的图像 / Show closed image
    Display.show_image(img_out)

    # 清理内存并输出帧率 / Cleanup and print FPS
    gc.collect()
    print("close fps:", clock.fps())

# -------------------------------
# 程序退出与资源释放 / Cleanup on exit
# -------------------------------
sensor.stop()                      # 停止摄像头 / Stop sensor
Display.deinit()                   # 关闭显示输出 / Deinitialize display
os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)  # 设置退出点 / Set safe exit point
time.sleep_ms(100)                # 稍作延时 / Delay
              # 释放媒体资源 / Release media resources
