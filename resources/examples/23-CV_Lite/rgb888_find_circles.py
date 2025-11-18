# ============================================================
# MicroPython 基于 cv_lite 的 RGB888 霍夫圆检测测试代码
# RGB888 Hough Circle Detection Test using cv_lite extension
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
# 初始化显示器（IDE虚拟显示） / Initialize display (IDE virtual output)
# -------------------------------
Display.init(Display.VIRT, width=image_shape[1], height=image_shape[0], to_ide=True, quality=100)

# -------------------------------
# 初始化媒体资源管理器 / Initialize media manager
# -------------------------------

sensor.run()

# -------------------------------
# 启动帧率计时器 / Start FPS timer
# -------------------------------
clock = time.clock()

# -------------------------------
# 霍夫圆检测参数 / Hough Circle parameters
# -------------------------------
dp = 1           # 累加器分辨率与图像分辨率的反比 / Inverse ratio of accumulator resolution
minDist = 30     # 检测到的圆心最小距离 / Minimum distance between detected centers
param1 = 80      # Canny边缘检测高阈值 / Higher threshold for Canny edge detection
param2 = 20      # 霍夫变换圆心检测阈值 / Threshold for center detection in accumulator
minRadius = 10   # 检测圆最小半径 / Minimum circle radius
maxRadius = 50   # 检测圆最大半径 / Maximum circle radius

# -------------------------------
# 主循环 / Main loop
# -------------------------------
while True:
    clock.tick()

    # 拍摄一帧图像 / Capture a frame
    img = sensor.snapshot()
    img_np = img.to_numpy_ref()  # 获取 RGB888 ndarray 引用

    # 调用 cv_lite 扩展的霍夫圆检测函数，返回圆参数列表 [x, y, r, ...]
    circles = cv_lite.rgb888_find_circles(
        image_shape, img_np, dp, minDist, param1, param2, minRadius, maxRadius
    )

    # 遍历检测到的圆形，绘制圆形框
    for i in range(0, len(circles), 3):
        x = circles[i]
        y = circles[i + 1]
        r = circles[i + 2]
        img.draw_circle(x, y, r, color=(255, 0, 0), thickness=2)  # 红色圆圈

    # 显示带有检测圆的图像 / Display image with circles drawn
    Display.show_image(img)

    # 垃圾回收 / Garbage collect
    gc.collect()

    # 打印帧率 / Print FPS
    print("findcircles:", clock.fps())

# -------------------------------
# 程序退出时释放资源 / Cleanup on exit
# -------------------------------
sensor.stop()
Display.deinit()
os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
time.sleep_ms(100)

