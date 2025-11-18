# ============================================================
# MicroPython 曝光增益调节测试代码（使用 cv_lite 扩展模块）
# Exposure Gain Adjustment using cv_lite extension in MicroPython
# ============================================================

import time, os, sys, gc
from machine import Pin
from media.sensor import *   # 摄像头接口 / Camera interface
from media.display import *  # 显示接口 / Display interface
from media.media import *    # 媒体资源管理器 / Media manager
import _thread
import cv_lite               # AI CV 扩展模块（包含曝光调节接口）/ AI CV extension with exposure support
import ulab.numpy as np      # ulab 数组库（用于图像数据处理）/ NumPy-like ndarray for MicroPython

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

# -------------------------------
# 初始化显示（IDE 虚拟显示模式）/ Initialize display (IDE virtual mode)
# -------------------------------
Display.init(Display.VIRT, width=image_shape[1], height=image_shape[0], to_ide=True, quality=50)

# -------------------------------
# 初始化媒体资源管理器 / Initialize media manager
# -------------------------------

sensor.run()

# -------------------------------
# 设置传感器模拟增益（可选）/ Set sensor analog gain (optional)
# -------------------------------
gain = k_sensor_gain()
gain.gain[0] = 20            # 设置通道0的增益值 / Set gain for channel 0
sensor.again(gain)           # 应用模拟增益 / Apply analog gain

# -------------------------------
# 启动帧率计时器 / Start FPS timer
# -------------------------------
clock = time.clock()

# -------------------------------
# 曝光增益因子（<1 降低亮度，>1 增加亮度）/ Exposure gain factor
# -------------------------------
exposure_gain = 2.5          # 推荐范围 0.2 ~ 3.0；1.0 表示无增益 / Recommended range: 0.2~3.0, 1.0 = no gain

# -------------------------------
# 主循环 / Main loop
# -------------------------------
while True:
    clock.tick()  # 开始计时 / Start timing

    # 拍摄一帧图像 / Capture a frame
    img = sensor.snapshot()
    img_np = img.to_numpy_ref()  # 获取 RGB888 图像数据引用 / Get RGB888 ndarray reference (HWC)

    # 调用 cv_lite 模块进行曝光调节 / Apply exposure adjustment using cv_lite module
    exposed_np = cv_lite.rgb888_adjust_exposure(image_shape, img_np, exposure_gain)

    # 包装图像用于显示 / Wrap processed image for display
    img_out = image.Image(image_shape[1], image_shape[0], image.RGB888,
                          alloc=image.ALLOC_REF, data=exposed_np)

    # 显示图像 / Show image
    Display.show_image(img_out)

    # 回收内存并输出帧率 / Cleanup memory and show FPS
    gc.collect()
    print("adjust exposure:", clock.fps())

# -------------------------------
# 释放资源 / Cleanup on exit
# -------------------------------
sensor.stop()
Display.deinit()
os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
time.sleep_ms(100)

