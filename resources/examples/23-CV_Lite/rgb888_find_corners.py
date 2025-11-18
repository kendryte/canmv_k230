# ============================================================
# MicroPython 基于 cv_lite 的 RGB888 角点检测测试代码
# RGB888 Corner Detection Test using cv_lite extension
# ============================================================

import time, os, sys, gc
from machine import Pin
from media.sensor import *     # 摄像头接口 / Camera interface
from media.display import *    # 显示接口 / Display interface
from media.media import *      # 媒体资源管理器 / Media manager
import _thread
import cv_lite                 # cv_lite扩展模块 / cv_lite extension module
import ulab.numpy as np

# -------------------------------
# 图像尺寸 [高, 宽] / Image size [Height, Width]
# -------------------------------
image_shape = [240, 320]

# -------------------------------
# 初始化摄像头（RGB888格式） / Initialize camera (RGB888 format)
# -------------------------------
sensor = Sensor(id=2, width=1280, height=720,fps=90)
sensor.reset()
sensor.set_framesize(width=image_shape[1], height=image_shape[0])
sensor.set_pixformat(Sensor.RGB888)

# -------------------------------
# 初始化显示器（IDE虚拟显示输出） / Initialize display (IDE virtual output)
# -------------------------------
Display.init(Display.VIRT, width=image_shape[1], height=image_shape[0], to_ide=True, quality=50)

# -------------------------------
# 初始化媒体资源管理器并启动摄像头 / Init media manager and start camera
# -------------------------------

sensor.run()

# -------------------------------
# 启动帧率计时器 / Start FPS timer
# -------------------------------
clock = time.clock()

# -------------------------------
# 可调参数（建议调试时调整）/ Adjustable parameters (recommended for tuning)
# -------------------------------
max_corners       = 20        # 最大角点数 / Maximum number of corners
quality_level     = 0.01      # Shi-Tomasi质量因子 / Corner quality factor (0.01 ~ 0.1)
min_distance      = 20.0      # 最小角点距离 / Minimum distance between corners

# -------------------------------
# 主循环 / Main loop
# -------------------------------
while True:
    clock.tick()

    # 拍摄当前帧图像 / Capture current frame
    img = sensor.snapshot()
    img_np = img.to_numpy_ref()  # 获取 RGB888 ndarray 引用 / Get RGB888 ndarray reference

    # 调用角点检测函数，返回角点数组 [x0, y0, x1, y1, ...]
    corners = cv_lite.rgb888_find_corners(
        image_shape, img_np,
        max_corners,
        quality_level,
        min_distance
    )

    # 遍历角点数组，绘制角点 / Draw detected corners
    for i in range(0, len(corners), 2):
        x = corners[i]
        y = corners[i + 1]
        img.draw_circle(x, y, 3, color=(0, 255, 0), fill=True)

    # 显示图像 / Display image with corners
    Display.show_image(img)

    # 进行垃圾回收 / Perform garbage collection
    gc.collect()

    # 打印当前帧率和角点数量 / Print current FPS and number of corners
    print("fps:", clock.fps(), "| corners:", len(corners) // 2)

# -------------------------------
# 退出时释放资源 / Cleanup on exit
# -------------------------------
sensor.stop()
Display.deinit()
os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
time.sleep_ms(100)

