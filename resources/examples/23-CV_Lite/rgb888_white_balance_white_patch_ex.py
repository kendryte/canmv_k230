# ============================================================
# MicroPython 快速白点白平衡测试代码（cv_lite 扩展模块）
# Fast White Patch White Balance Demo using cv_lite extension
# ============================================================

import time, os, sys, gc
from machine import Pin
from media.sensor import *   # 摄像头接口 / Camera interface
from media.display import *  # 显示接口 / Display interface
from media.media import *    # 媒体资源管理器 / Media manager
import _thread
import cv_lite               # 自定义图像处理模块（C 扩展） / Custom C extension module for image processing
import ulab.numpy as np      # 数组运算库 / NumPy-like array for MicroPython

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
sensor.set_pixformat(Sensor.RGB888)  # 设置像素格式为 RGB888

# --------------------------------------
# 初始化显示模块（IDE 虚拟显示模式）
# Initialize display (IDE virtual mode)
# --------------------------------------
Display.init(Display.VIRT, width=image_shape[1], height=image_shape[0], to_ide=True, quality=50)

# -------------------------------
# 初始化媒体资源 / Init media system
# -------------------------------

sensor.run()

# -------------------------------
# 启动帧率计时器 / Start FPS timer
# -------------------------------
clock = time.clock()

# -------------------------------
# 白平衡参数 / White balance config
# -------------------------------
top_percent = 5.0          # 用于白点估计的最亮像素百分比 / Top N% brightest pixels used for white patch
gain_clip = 2.5            # 最大增益限制 / Limit gain to avoid over-brightening
brightness_boost = 1.1     # 提亮因子 / Global brightness scaling

# -------------------------------
# 主循环 / Main loop
# -------------------------------
while True:
    clock.tick()  # 记录当前帧开始时间 / Start timing

    # 拍摄一帧图像 / Capture one frame
    img = sensor.snapshot()
    img_np = img.to_numpy_ref()  # 获取图像数据引用（ulab ndarray）

    # 执行白点白平衡处理 / Apply white patch white balance with parameters
    balanced_np = cv_lite.rgb888_white_balance_white_patch_ex(
        image_shape, img_np,
        top_percent,
        gain_clip,
        brightness_boost
    )

    # 包装图像用于显示 / Wrap balanced image as displayable image object
    img_out = image.Image(image_shape[1], image_shape[0], image.RGB888,
                          alloc=image.ALLOC_REF, data=balanced_np)

    # 显示图像 / Show image on display
    Display.show_image(img_out)

    # 回收垃圾，打印帧率 / Cleanup and show FPS
    gc.collect()
    print("white patch wb ex:", clock.fps())

# -------------------------------
# 退出处理 / Exit cleanup
# -------------------------------
sensor.stop()
Display.deinit()
os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
time.sleep_ms(100)

