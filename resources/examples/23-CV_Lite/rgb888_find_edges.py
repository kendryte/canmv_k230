# ============================================================
# MicroPython 基于 cv_lite 的 RGB888 边缘检测测试代码
# RGB888 Edge Detection Test using cv_lite extension
# ============================================================

import time, os, sys, gc
from machine import Pin
from media.sensor import *    # 导入摄像头接口 / Camera interface
from media.display import *   # 导入显示接口 / Display interface
from media.media import *     # 导入媒体资源管理器 / Media manager
import _thread
import cv_lite                # 导入 cv_lite 扩展模块 / cv_lite extension
import ulab.numpy as np       # MicroPython 类 NumPy 库

# -------------------------------
# 图像尺寸设置 / Image resolution
# -------------------------------
image_shape = [480, 640]  # 高 x 宽 / Height x Width

# -------------------------------
# 初始化摄像头（RGB888格式） / Initialize camera (RGB888 format)
# -------------------------------
sensor = Sensor(id=2, width=1280, height=720,fps=90)
sensor.reset()
sensor.set_framesize(width=image_shape[1], height=image_shape[0])
sensor.set_pixformat(Sensor.RGB888)  # 设置 RGB888 像素格式 / Set RGB888 pixel format

# -------------------------------
# 初始化显示器（IDE虚拟输出） / Initialize display (IDE virtual output)
# -------------------------------
Display.init(Display.VIRT, width=image_shape[1], height=image_shape[0], to_ide=True, quality=50)

# -------------------------------
# 初始化媒体资源管理器 / Initialize media manager
# -------------------------------

sensor.run()

# -------------------------------
# 启动帧率计时器 / Start FPS timer
# -------------------------------
clock = time.clock()

# -------------------------------
# 边缘检测参数 / Edge detection parameters (Canny thresholds)
# -------------------------------
threshold1 = 50   # Canny 边缘检测低阈值 / Lower threshold for Canny
threshold2 = 80   # Canny 边缘检测高阈值 / Higher threshold for Canny

# -------------------------------
# 主循环 / Main loop
# -------------------------------
while True:
    clock.tick()

    # 拍摄一帧图像 / Capture a frame
    img = sensor.snapshot()
    img_np = img.to_numpy_ref()  # 获取 RGB888 ndarray 引用

    # 调用 cv_lite 扩展的边缘检测函数，返回灰度边缘图 ndarray
    edge_np = cv_lite.rgb888_find_edges(image_shape, img_np, threshold1, threshold2)

    # 构造灰度图像对象用于显示
    img_out = image.Image(image_shape[1], image_shape[0], image.GRAYSCALE, alloc=image.ALLOC_REF, data=edge_np)

    # 显示边缘检测结果
    Display.show_image(img_out)

    # 垃圾回收 / Garbage collect
    gc.collect()

    # 打印当前帧率 / Print FPS
    print("edges:", clock.fps())

# -------------------------------
# 退出时释放资源 / Cleanup on exit
# -------------------------------
sensor.stop()
Display.deinit()
os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
time.sleep_ms(100)

