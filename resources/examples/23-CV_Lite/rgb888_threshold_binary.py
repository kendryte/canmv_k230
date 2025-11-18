# binary_test.py
# 二值化测试脚本 / Binary Thresholding Test Script

import time, os, sys, gc
from machine import Pin
from media.sensor import *     # 摄像头接口 / Camera interface
from media.display import *    # 显示接口 / Display interface
from media.media import *      # 媒体资源管理器 / Media manager
import _thread
import cv_lite                 # cv_lite扩展模块（内含二值化接口）/ cv_lite extension with binary threshold
import ulab.numpy as np

# ================================
# 图像尺寸 / Image size [Height, Width]
# ================================
image_shape = [480, 640]

# ================================
# 初始化摄像头 / Initialize camera
# ================================
sensor = Sensor(id=2, width=640, height=480)
sensor.reset()
sensor.set_framesize(width=640, height=480)
sensor.set_pixformat(Sensor.RGB888)

# ================================
# 初始化显示器（IDE虚拟显示）/ Initialize display (IDE virtual output)
# ================================
Display.init(Display.VIRT, width=640, height=480, to_ide=True, quality=50)

# ================================
# 初始化媒体资源管理器 / Initialize media manager
# ================================

sensor.run()

# ================================
# 启动帧率计时器 / Start FPS timer
# ================================
clock = time.clock()

# ================================
# 二值化参数 / Binary threshold parameters
# ================================
thresh = 130    # 阈值 / Threshold value
maxval = 255    # 最大值（白）/ Maximum value (white)

# ================================
# 主循环 / Main loop
# ================================
while True:
    clock.tick()

    # 拍摄一帧图像 / Capture a frame
    img = sensor.snapshot()
    img_np = img.to_numpy_ref()

    # 调用二值化接口（返回 ndarray）/ Call binary threshold function (returns ndarray)
    binary_np = cv_lite.rgb888_threshold_binary(image_shape, img_np, thresh, maxval)

    # 构造灰度图像用于显示 / Construct grayscale image for display
    img_out = image.Image(image_shape[1], image_shape[0], image.GRAYSCALE,
                          alloc=image.ALLOC_REF, data=binary_np)

    # 显示图像 / Show image
    Display.show_image(img_out)

    # 垃圾回收 & 打印FPS / Garbage collect and print FPS
    gc.collect()
    print("binary:", clock.fps())

# ================================
# 资源释放 / Release resources
# ================================
sensor.stop()
Display.deinit()
os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
time.sleep_ms(100)

