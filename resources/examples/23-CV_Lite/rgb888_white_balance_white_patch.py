import time, os, sys, gc
from machine import Pin
from media.sensor import *   # 摄像头接口
from media.display import *  # 显示接口
from media.media import *    # 媒体资源管理器
import _thread
import cv_lite                 # cv_lite扩展模块（包含白平衡接口）
import ulab.numpy as np

# 图像尺寸
image_shape = [480, 640]

# 初始化摄像头
sensor = Sensor(id=2, width=1280, height=720,fps=90)
sensor.reset()
sensor.set_framesize(width=image_shape[1], height=image_shape[0])
sensor.set_pixformat(Sensor.RGB888)

# 初始化显示（IDE虚拟显示）
Display.init(Display.VIRT, width=image_shape[1], height=image_shape[0], to_ide=True, quality=50)

# 初始化媒体资源

sensor.run()

# 启动帧率计时器
clock = time.clock()

while True:
    clock.tick()

    # 拍摄一帧图像
    img = sensor.snapshot()
    img_np = img.to_numpy_ref()  # RGB888 原始图像（ulab ndarray）

    # 调用 cv_lite 扩展模块进行灰度世界白平衡（可调节强度）
    balanced_np = cv_lite.rgb888_white_balance_white_patch(image_shape, img_np)

    # 构造 RGB888 显示图像
    img_out = image.Image(image_shape[1], image_shape[0], image.RGB888,
                          alloc=image.ALLOC_REF, data=balanced_np)

    # 显示图像
    Display.show_image(img_out)

    # 清理并打印帧率
    gc.collect()
    print("white patch wb fast:", clock.fps())

# 释放资源
sensor.stop()
Display.deinit()
os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
time.sleep_ms(100)

