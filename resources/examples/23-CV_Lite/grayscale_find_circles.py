# ============================================================
# MicroPython 霍夫圆检测测试代码（使用 cv_lite 扩展模块）
# Hough Circle Detection Test using cv_lite extension
# ============================================================

import time, os, sys, gc
from machine import Pin
from media.sensor import *   # 摄像头接口 / Camera interface
from media.display import *  # 显示接口 / Display interface
from media.media import *    # 媒体资源管理器 / Media manager
import _thread
import cv_lite               # cv_lite 扩展模块（包含圆检测函数）
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
# 霍夫圆检测参数 / Hough circle detection parameters
# -------------------------------
dp = 1            # 累加器分辨率比 / Inverse ratio of resolution
minDist = 20      # 圆心最小距离 / Minimum distance between centers
param1 = 80       # Canny 高阈值 / Upper threshold for Canny edge detector
param2 = 20       # 累加器阈值 / Accumulator threshold for center detection
minRadius = 10    # 最小圆半径 / Minimum radius to detect
maxRadius = 50    # 最大圆半径 / Maximum radius to detect

# -------------------------------
# 主循环 / Main loop
# -------------------------------
while True:
    clock.tick()

    # 拍摄一帧图像 / Capture a frame
    img = sensor.snapshot()
    img_np = img.to_numpy_ref()  # 获取图像的 ndarray 引用 / Get image data reference

    # 检测圆形 / Detect circles using Hough Transform
    # 返回格式：[x1, y1, r1, x2, y2, r2, ...]
    circles = cv_lite.grayscale_find_circles(
        image_shape, img_np,
        dp, minDist,
        param1, param2,
        minRadius, maxRadius
    )

    # 遍历圆信息并绘制 / Draw each detected circle
    for i in range(0, len(circles), 3):
        x = circles[i]
        y = circles[i + 1]
        r = circles[i + 2]
        img.draw_circle(x, y, r, color=(255, 255, 0), thickness=2)  # 黄色圆 / Yellow circle

    # 显示图像 / Show processed image
    Display.show_image(img)

    # 清理内存并输出帧率 / Cleanup and print FPS
    gc.collect()
    print("findcircles:", clock.fps())

# -------------------------------
# 程序退出与资源释放 / Cleanup on exit
# -------------------------------
sensor.stop()
Display.deinit()
os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
time.sleep_ms(100)
