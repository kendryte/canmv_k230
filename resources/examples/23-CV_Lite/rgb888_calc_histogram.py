# ============================================================
# MicroPython RGB888 直方图测试代码（cv_lite 扩展模块）
# RGB888 Histogram Test using cv_lite extension
# ============================================================

import time, os, sys, gc
from machine import Pin
from media.sensor import *     # 摄像头接口 / Camera interface
from media.display import *    # 显示接口 / Display interface
from media.media import *      # 媒体资源管理器 / Media manager
import _thread
import cv_lite                 # cv_lite 扩展模块，包含 histogram 函数 / C extension module for image processing
import ulab.numpy as np        # ulab 数组模块 / NumPy-like ndarray for MicroPython

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
Display.init(Display.VIRT, width=image_shape[1], height=image_shape[0], to_ide=True, quality=100)

# -------------------------------
# 初始化媒体资源管理器 / Init media manager
# -------------------------------

sensor.run()

# -------------------------------
# 启动帧率计时器 / Start FPS timer
# -------------------------------
clock = time.clock()
count = 0

# -------------------------------
# 主循环 / Main loop
# -------------------------------
while True:
    count += 1
    clock.tick()  # 记录当前帧开始时间 / Start timing

    # 拍摄一帧图像 / Capture a frame
    img = sensor.snapshot()
    img_np = img.to_numpy_ref()  # 获取 RGB888 图像引用 / Get RGB888 ndarray reference (HWC)

    # 使用 cv_lite 计算 RGB 直方图（返回 shape 为 3x256 的数组）
    # Calculate RGB888 histogram using cv_lite (3x256 array)
    hist = cv_lite.rgb888_calc_histogram(image_shape, img_np)

    # 每 30 帧打印一次最大值索引 / Print max bin index every 30 frames
    if count == 30:
        r_hist = hist[2]  # R 通道 / Red channel
        g_hist = hist[1]  # G 通道 / Green channel
        b_hist = hist[0]  # B 通道 / Blue channel
        r_max = int(np.argmax(r_hist))  # R 最大值索引 / Max index of red channel
        g_max = int(np.argmax(g_hist))  # G 最大值索引 / Max index of green channel
        b_max = int(np.argmax(b_hist))  # B 最大值索引 / Max index of blue channel
        print(f"R最大值索引: {r_max}, G最大值索引: {g_max}, B最大值索引: {b_max}")
        count = 0

    # 打印当前帧率 / Print FPS
    print("histogram:", clock.fps())

    # 显示原始图像 / Show original image
    Display.show_image(img)

    # 回收内存 / Free unused memory
    gc.collect()

# -------------------------------
# 程序退出与资源释放 / Cleanup on exit
# -------------------------------
sensor.stop()
Display.deinit()
os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
time.sleep_ms(100)

