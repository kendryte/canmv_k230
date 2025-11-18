# ============================================================
# MicroPython 灰度图二值化测试代码（使用 cv_lite 扩展模块）
# Grayscale Binary Thresholding Test using cv_lite extension
# ============================================================

import time, os, sys, gc
from machine import Pin
from media.sensor import *   # 摄像头接口 / Camera interface
from media.display import *  # 显示接口 / Display interface
from media.media import *    # 媒体资源管理器 / Media manager
import _thread
import cv_lite               # cv_lite 扩展模块（包含二值化接口）
import ulab.numpy as np      # MicroPython 的类 NumPy 库

# -------------------------------
# 图像尺寸设置 / Image resolution
# -------------------------------
image_shape = [480, 640]  # 高 x 宽 / Height x Width

# -------------------------------
# 初始化摄像头（灰度模式） / Initialize camera (grayscale)
# -------------------------------
sensor = Sensor(id=2, width=1280, height=720,fps=90)
sensor.reset()
sensor.set_framesize(width=image_shape[1], height=image_shape[0])
sensor.set_pixformat(Sensor.GRAYSCALE)  # 灰度图格式 / Grayscale format

# -------------------------------
# 初始化显示（IDE 虚拟显示） / Initialize display (IDE virtual mode)
# -------------------------------
Display.init(Display.VIRT, width=image_shape[1], height=image_shape[0],
             to_ide=True, quality=50)

# -------------------------------
# 初始化媒体资源管理器 / Initialize media manager
# -------------------------------

sensor.run()

# -------------------------------
# 启动帧率计时器 / Start FPS timer
# -------------------------------
clock = time.clock()

# -------------------------------
# 二值化参数设置 / Binary threshold parameters
# -------------------------------
thresh = 130   # 阈值 / Threshold value
maxval = 255   # 最大值，二值化后白色像素值 / Max value for white pixels

# -------------------------------
# 主循环 / Main loop
# -------------------------------
while True:
    clock.tick()

    # 拍摄一帧图像 / Capture a frame
    img = sensor.snapshot()
    img_np = img.to_numpy_ref()  # 获取 ndarray 引用 / Get ndarray reference

    # 调用 cv_lite 扩展进行二值化处理
    # 返回二值化后的灰度图 ndarray / Returns binary image ndarray
    binary_np = cv_lite.grayscale_threshold_binary(image_shape, img_np, thresh, maxval)

    # 构造用于显示的灰度图像对象 / Wrap ndarray as grayscale image for display
    img_out = image.Image(image_shape[1], image_shape[0], image.GRAYSCALE,
                          alloc=image.ALLOC_REF, data=binary_np)

    # 显示二值化结果 / Show binary image
    Display.show_image(img_out)

    # 清理内存并打印帧率 / Garbage collect and print FPS
    gc.collect()
    print("binary:", clock.fps())

# -------------------------------
# 退出释放资源 / Cleanup on exit
# -------------------------------
sensor.stop()
Display.deinit()
os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
time.sleep_ms(100)

