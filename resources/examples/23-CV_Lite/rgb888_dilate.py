# ============================================================
# MicroPython 图像膨胀测试代码（使用 cv_lite 扩展模块）
# Image Dilation Test using cv_lite extension (RGB888 -> GRAY)
# ============================================================

import time, os, gc
from machine import Pin
from media.sensor import *   # 摄像头接口 / Camera interface
from media.display import *  # 显示接口 / Display interface
from media.media import *    # 媒体资源管理器 / Media manager
import cv_lite               # cv_lite 扩展模块（含膨胀接口）/ AI CV extension (dilate function)
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
Display.init(Display.VIRT, width=image_shape[1], height=image_shape[0], to_ide=True)

# -------------------------------
# 初始化媒体资源管理器 / Init media manager
# -------------------------------

sensor.run()

# -------------------------------
# 启动帧率计时器 / Start FPS timer
# -------------------------------
clock = time.clock()

# -------------------------------
# 膨胀算法参数设置 / Dilation parameters
# -------------------------------
kernel_size = 3         # 卷积核尺寸 / Kernel size (推荐为奇数，但部分实现支持偶数)
iterations = 1          # 膨胀迭代次数 / Number of dilation passes
threshold_value = 100   # 二值化阈值（0=使用 Otsu 自动阈值）/ Threshold for binarization (0 = Otsu)

# -------------------------------
# 主循环 / Main loop
# -------------------------------
while True:
    clock.tick()  # 开始计时 / Start frame timing

    # 获取一帧图像 / Capture a frame
    img = sensor.snapshot()
    img_np = img.to_numpy_ref()  # 获取 RGB888 ndarray 引用 / Get RGB888 ndarray reference

    # 应用膨胀操作（内部先转换为灰度再膨胀）/ Apply dilation (converts RGB to gray internally)
    result_np = cv_lite.rgb888_dilate(
        image_shape,
        img_np,
        kernel_size,
        iterations,
        threshold_value
    )

    # 构造图像用于显示（灰度格式） / Wrap dilated grayscale image for display
    img_out = image.Image(image_shape[1], image_shape[0], image.GRAYSCALE,
                          alloc=image.ALLOC_REF, data=result_np)

    # 显示膨胀处理结果 / Show dilated image
    Display.show_image(img_out)

    # 清理内存并输出帧率 / Cleanup and print FPS
    gc.collect()
    print("dilate fps:", clock.fps())

# -------------------------------
# 程序退出与资源释放 / Cleanup on exit
# -------------------------------
sensor.stop()
Display.deinit()
os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
time.sleep_ms(100)

