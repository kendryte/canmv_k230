# ============================================================
# MicroPython 灰度图边缘检测测试代码（使用 cv_lite 扩展模块）
# Grayscale Edge Detection (Canny) Test using cv_lite extension
# ============================================================

import time, os, sys, gc
from machine import Pin
from media.sensor import *   # 摄像头接口 / Camera interface
from media.display import *  # 显示接口 / Display interface
from media.media import *    # 媒体资源管理器 / Media manager
import _thread
import cv_lite               # cv_lite 扩展模块（包含边缘检测）
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
sensor.set_pixformat(Sensor.GRAYSCALE)  # 设置为灰度图像输出 / Grayscale mode

# --------------------------------------
# 初始化显示模块（IDE 虚拟显示模式）
# Initialize display (IDE virtual mode)
# --------------------------------------
Display.init(Display.VIRT, width=image_shape[1], height=image_shape[0],
             to_ide=True, quality=50)

# -------------------------------
# 初始化媒体资源管理器 / Init media manager
# -------------------------------

sensor.run()

# -------------------------------
# 启动帧率计时器 / Start FPS timer
# -------------------------------
clock = time.clock()

# -------------------------------
# 边缘检测参数 / Canny edge detection thresholds
# -------------------------------
threshold1 = 50  # 低阈值 / Lower threshold
threshold2 = 80  # 高阈值 / Upper threshold

# -------------------------------
# 主循环 / Main loop
# -------------------------------
while True:
    clock.tick()

    # 拍摄一帧图像 / Capture a frame
    img = sensor.snapshot()
    img_np = img.to_numpy_ref()  # 获取 ndarray 引用 / Get ndarray reference

    # 调用 cv_lite 扩展执行边缘检测 / Perform edge detection
    # 返回灰度边缘图像 ndarray / Returns edge image ndarray
    edge_np = cv_lite.grayscale_find_edges(
        image_shape, img_np, threshold1, threshold2)

    # 包装边缘图像用于显示 / Wrap ndarray as image for display
    img_out = image.Image(image_shape[1], image_shape[0], image.GRAYSCALE,
                          alloc=image.ALLOC_REF, data=edge_np)

    # 显示边缘图像 / Show edge image
    Display.show_image(img_out)

    # 清理内存并打印帧率 / Cleanup and print FPS
    gc.collect()
    print("edges:", clock.fps())

# -------------------------------
# 程序退出与资源释放 / Cleanup on exit
# -------------------------------
sensor.stop()
Display.deinit()
os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
time.sleep_ms(100)

