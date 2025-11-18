# ============================================================
# MicroPython 灰度图连通域（Blob）检测测试代码（cv_lite）
# Grayscale Blob Detection Test using cv_lite extension
# ============================================================

import time, os, sys, gc
from machine import Pin
from media.sensor import *   # 摄像头模块 / Camera interface
from media.display import *  # 显示模块 / Display interface
from media.media import *    # 媒体管理器 / Media manager
import _thread
import cv_lite               # cv_lite 扩展模块（包含 blob 检测函数）
import ulab.numpy as np      # 轻量 NumPy（用于 ndarray 图像处理）

# -------------------------------
# 图像尺寸设置 / Image resolution
# -------------------------------
image_shape = [480, 640]  # 高 x 宽 / Height x Width

# -------------------------------
# 初始化摄像头 / Initialize camera
# -------------------------------
sensor = Sensor(id=2, width=1280, height=720,fps=90)  # 构建 Sensor 对象
sensor.reset()                                                      # 复位摄像头
sensor.set_framesize(width=image_shape[1], height=image_shape[0])  # 设置帧大小
sensor.set_pixformat(Sensor.GRAYSCALE)                              # 设置为灰度图输出

# --------------------------------------
# 初始化显示模块（IDE 虚拟显示模式）
# Initialize display (IDE virtual mode)
# --------------------------------------
Display.init(Display.VIRT, width=image_shape[1], height=image_shape[0],
             to_ide=True, quality=50)

# -------------------------------
# 初始化媒体资源管理器 / Init media manager
# -------------------------------

sensor.run()  # 启动摄像头图像流

# -------------------------------
# 连通域检测参数 / Blob detection params
# -------------------------------
threshold = [230, 255]   # 二值化阈值范围（亮区域）/ Threshold range for binarization
min_area = 10            # 最小目标面积 / Minimum area to keep
kernel_size = 1          # 腐蚀核大小（可用于降噪）/ Erosion kernel size
clock = time.clock()     # 帧率计时器

# -------------------------------
# 主循环 / Main loop
# -------------------------------
while True:
    clock.tick()

    # 获取一帧图像 / Capture a frame
    img = sensor.snapshot()
    img_np = img.to_numpy_ref()  # 获取图像数据引用 / Get ndarray reference

    # 执行灰度图二值连通域检测 / Perform blob detection on thresholded grayscale image
    blob = cv_lite.grayscale_find_blobs(
        image_shape, img_np,
        threshold[0], threshold[1],
        min_area, kernel_size
    )

    # 若检测到连通区域 / If blobs found
    if len(blob) > 0:
        # blob = [x, y, w, h]
        img.draw_rectangle(blob[0], blob[1], blob[2], blob[3],
                           color=(0, 0, 0), thickness=2)  # 绘制黑色矩形

    # 显示图像 / Show image
    Display.show_image(img)

    # 清理内存并打印帧率 / Cleanup and print FPS
    gc.collect()
    print("findblobs:", clock.fps())

# -------------------------------
# 程序退出与资源释放 / Cleanup on exit
# -------------------------------
sensor.stop()
Display.deinit()
os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
time.sleep_ms(100)

