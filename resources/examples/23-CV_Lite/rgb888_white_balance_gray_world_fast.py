# ============================================================
# MicroPython 加速灰度世界白平衡测试代码（cv_lite 扩展模块）
# Fast Gray World White Balance Test using cv_lite extension
# ============================================================

import time, os, sys, gc
from machine import Pin
from media.sensor import *   # 摄像头接口 / Camera interface
from media.display import *  # 显示接口 / Display interface
from media.media import *    # 媒体资源管理器 / Media manager
import _thread
import cv_lite               # cv_lite 图像处理扩展模块 / cv_lite C extension module
import ulab.numpy as np      # ulab 数组模块 / NumPy-like ndarray for MicroPython

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
# 主循环 / Main loop
# -------------------------------
while True:
    clock.tick()  # 记录当前帧开始时间 / Start timing

    # 拍摄一帧图像 / Capture a frame
    img = sensor.snapshot()
    img_np = img.to_numpy_ref()  # 获取 RGB888 图像引用 / Get RGB888 ndarray reference (HWC)

    # 使用 cv_lite 进行加速灰度世界白平衡处理
    # Apply fast gray world white balance
    balanced_np = cv_lite.rgb888_white_balance_gray_world_fast(image_shape, img_np)

    # 包装图像用于显示 / Wrap processed image for display
    img_out = image.Image(image_shape[1], image_shape[0], image.RGB888,alloc=image.ALLOC_REF, data=balanced_np)

    # 显示图像 / Show image
    Display.show_image(img_out)

    # 回收内存并打印帧率 / Cleanup and show FPS
    gc.collect()
    print("gray world wb fast:", clock.fps())

# -------------------------------
# 程序退出与资源释放 / Cleanup on exit
# -------------------------------
sensor.stop()
Display.deinit()
os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
time.sleep_ms(100)

