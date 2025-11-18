# ============================================================
# MicroPython RGB888 彩色块检测与距离估计示例（使用 cv_lite 扩展）
# RGB888 Color Blob Detection & Distance Estimation with cv_lite
# ============================================================

import time, os, sys, gc
from machine import Pin
from media.sensor import *   # 摄像头接口 / Camera interface
from media.display import *  # 显示接口 / Display interface
from media.media import *    # 媒体管理器 / Media manager
import _thread
import cv_lite               # 自定义计算机视觉模块 / Custom CV extension
import ulab.numpy as np      # MicroPython 版 NumPy / Lightweight NumPy for uPython

# -------------------------------
# 图像尺寸配置 / Image resolution
# -------------------------------
image_shape = [480, 640]  # 图像高 x 宽 / Height x Width

# -------------------------------
# 初始化摄像头 / Initialize RGB888 camera
# -------------------------------
sensor = Sensor(id=2, width=1280, height=720, fps=90)
sensor.reset()
sensor.set_framesize(width=image_shape[1], height=image_shape[0])
sensor.set_pixformat(Sensor.RGB888)  # 设置为 RGB888 格式 / Set pixel format to RGB888

# -------------------------------
# 初始化虚拟显示器 / Initialize virtual display (IDE output)
# -------------------------------
Display.init(Display.VIRT, width=image_shape[1], height=image_shape[0], to_ide=True, quality=50)

# -------------------------------
# 初始化媒体管理器 / Initialize media manager
# -------------------------------

sensor.run()  # 启动摄像头采集 / Start capturing

# -------------------------------
# 色块检测参数 / Color blob detection parameters
# -------------------------------
threshold = [120, 255, 0, 50, 0, 50]  # 颜色阈值 [Rmin, Rmax, Gmin, Gmax, Bmin, Bmax]
min_area = 10                       # 最小检测面积 / Minimum valid blob area
kernel_size = 1                      # 腐蚀膨胀核大小 / Morphological kernel size

# -------------------------------
# 相机内参与畸变系数 / Camera intrinsics and distortion
# -------------------------------
camera_matrix = [
    1601.79998, 0.0, 960.2537,
    0.0, 1600.6784, 496.5050,
    0.0, 0.0, 1.0
]
dist_coeffs = [0.16096, -0.73425, -0.01634, -0.00896, 0.41294]
dist_len = len(dist_coeffs)

# 实际 ROI 尺寸（单位：厘米）/ Real-world size of detected ROI (cm)
roi_width_real = 3.0     # 例如：色块宽 3cm / Blob width in real world
roi_height_real = 3.0    # 例如：色块高 2.8cm / Blob height in real world

# -------------------------------
# 帧率计时器 / Frame rate timer
# -------------------------------
clock = time.clock()

# -------------------------------
# 主循环 / Main loop
# -------------------------------
while True:
    clock.tick()  # 启动帧计时器 / Start FPS timer

    img = sensor.snapshot()          # 拍摄一帧 / Capture one frame
    img_np = img.to_numpy_ref()      # 获取图像 NumPy 引用 / Get NumPy reference to RGB data

    # 色块检测：返回多个色块 [x, y, w, h, ...] / Detect color blobs
    blobs = cv_lite.rgb888_find_blobs(image_shape, img_np, threshold, min_area, kernel_size)

    if len(blobs) > 0:
        # 获取第一个色块 ROI（矩形）/ Get first blob's bounding box
        roi = [blobs[0], blobs[1], blobs[2], blobs[3]]

        # 使用 PnP 估算色块距离 / Estimate distance via PnP
        distance = cv_lite.rgb888_pnp_distance(
            image_shape, img_np, roi,
            camera_matrix, dist_coeffs, dist_len,
            roi_width_real, roi_height_real
        )

        # 绘制矩形与距离文字 / Draw bounding box and distance text
        img.draw_rectangle(roi[0], roi[1], roi[2], roi[3], color=(255, 0, 0), thickness=2)
        img.draw_string_advanced(roi[0], roi[1] - 20, 32, str(distance), color=(255, 0, 0))

    # 显示图像到 IDE / Display image to IDE
    Display.show_image(img)

    # 打印当前帧率 / Print current FPS
    print("findblobs:", clock.fps())

    # 内存回收 / Garbage collection
    gc.collect()

# -------------------------------
# 资源释放 / Clean-up on exit
# -------------------------------
sensor.stop()
Display.deinit()
os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
time.sleep_ms(100)

