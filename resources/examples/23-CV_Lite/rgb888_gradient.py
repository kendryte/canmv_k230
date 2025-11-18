# gradient_test.py
# 梯度变换测试脚本 / Morphological Gradient Test Script

import time, os, gc
from machine import Pin
from media.sensor import *     # 摄像头接口 / Camera interface
from media.display import *    # 显示接口 / Display interface
from media.media import *      # 媒体资源管理器 / Media manager
import cv_lite                 # AI CV扩展模块 / AI CV extension module
import ulab.numpy as np

# ================================
# 图像尺寸 / Image size [Height, Width]
# ================================
image_shape = [480, 640]

# ================================
# 初始化摄像头 / Initialize camera (RGB888格式)
# ================================
sensor = Sensor(id=2, width=1280, height=720,fps=90)
sensor.reset()
sensor.set_framesize(width=image_shape[1], height=image_shape[0])
sensor.set_pixformat(Sensor.RGB888)

# ================================
# 初始化显示器 / Initialize display (IDE虚拟显示)
# ================================
Display.init(Display.VIRT, width=image_shape[1], height=image_shape[0], to_ide=True)

# ================================
# 初始化媒体资源管理器 / Initialize media manager
# ================================

sensor.run()

# ================================
# 启动帧率计时器 / Start FPS timer
# ================================
clock = time.clock()

# ================================
# 梯度操作参数 / Morphological Gradient parameters
# ================================
kernel_size = 3        # 卷积核尺寸（建议奇数）/ Kernel size (recommended odd)
iterations = 1         # 形态学迭代次数 / Morphology iterations
threshold_value = 100  # 二值化阈值（0=使用 Otsu 自动阈值）/ Threshold value (0=use Otsu)

# ================================
# 主循环 / Main loop
# ================================
while True:
    clock.tick()

    # 获取图像并转为 ndarray / Capture image and convert to ndarray
    img = sensor.snapshot()
    img_np = img.to_numpy_ref()

    # 调用梯度操作（Gradient = 膨胀 - 腐蚀）/ Call morphological gradient (dilate - erode)
    result_np = cv_lite.rgb888_gradient(image_shape, img_np, kernel_size, iterations, threshold_value)

    # 构造灰度图像用于显示 / Construct grayscale image for display
    img_out = image.Image(image_shape[1], image_shape[0], image.GRAYSCALE,
                          alloc=image.ALLOC_REF, data=result_np)

    # 显示图像 / Show image
    Display.show_image(img_out)

    # 垃圾回收并打印帧率 / Garbage collect and print FPS
    gc.collect()
    print("gradient fps:", clock.fps())

# ================================
# 资源释放 / Release resources
# ================================
sensor.stop()
Display.deinit()
os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
time.sleep_ms(100)

