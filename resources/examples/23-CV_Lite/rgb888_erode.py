# ============================================================
# MicroPython 图像腐蚀测试代码（使用 cv_lite 扩展模块）
# Image Erosion Test using cv_lite extension (RGB888 -> GRAY)
# ============================================================

import time, os, sys, gc
from machine import Pin
from media.sensor import *   # 摄像头接口 / Camera interface
from media.display import *  # 显示接口 / Display interface
from media.media import *    # 媒体资源管理器 / Media manager
import _thread
import cv_lite               # cv_lite 扩展模块（含腐蚀接口）/ AI CV extension (erode function)
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
Display.init(Display.VIRT, width=image_shape[1], height=image_shape[0], to_ide=True, quality=50)

# -------------------------------
# 初始化媒体资源管理器 / Init media manager
# -------------------------------

sensor.run()

# -------------------------------
# 启动帧率计时器 / Start FPS timer
# -------------------------------
clock = time.clock()

# -------------------------------
# 腐蚀算法参数设置 / Erosion parameters
# -------------------------------
kernel_size = 3         # 卷积核尺寸（必须为奇数，如 3, 5, 7）/ Kernel size (must be odd)
iterations = 1          # 腐蚀迭代次数 / Number of erosion passes
threshold_value = 100   # 二值化阈值（0=使用 Otsu 自动阈值）/ Threshold for binarization (0 = Otsu)

# -------------------------------
# 主循环 / Main loop
# -------------------------------
while True:
    clock.tick()  # 开始计时 / Start frame timing

    # 获取一帧图像 / Capture a frame
    img = sensor.snapshot()
    img_np = img.to_numpy_ref()  # 获取 RGB888 ndarray 引用 / Get RGB888 ndarray reference (HWC)

    # 应用腐蚀操作（自动转换为灰度后进行） / Apply erosion (converts RGB to gray internally)
    eroded_np = cv_lite.rgb888_erode(
        image_shape,
        img_np,
        kernel_size,
        iterations,
        threshold_value
    )

    # 构造图像用于显示（灰度格式） / Wrap eroded grayscale image for display
    img_out = image.Image(image_shape[1], image_shape[0], image.GRAYSCALE,
                          alloc=image.ALLOC_REF, data=eroded_np)

    # 显示腐蚀后的图像 / Show eroded image
    Display.show_image(img_out)

    # 清理内存并打印帧率 / Cleanup and print FPS
    gc.collect()
    print("erode fps:", clock.fps())

# -------------------------------
# 程序退出与资源释放 / Cleanup on exit
# -------------------------------
sensor.stop()
Display.deinit()
os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
time.sleep_ms(100)

