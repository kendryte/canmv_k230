# ============================================================
# MicroPython 图像畸变校正测试代码（使用 cv_lite 扩展模块）
# Image Undistortion Test using cv_lite extension
# ============================================================

import time, os, gc
from machine import Pin
from media.sensor import *
from media.display import *
from media.media import *
import cv_lite
import ulab.numpy as np

# -------------------------------
# 图像尺寸设置 / Image resolution
# -------------------------------
image_shape = [480, 640]  # 高 x 宽 / Height x Width

# -------------------------------
# 初始化摄像头 / Initialize camera
# -------------------------------
sensor = Sensor(id=2, width=1280, height=720, fps=90)
sensor.reset()
sensor.set_framesize(width=image_shape[1], height=image_shape[0])
sensor.set_pixformat(Sensor.RGB888)

# -------------------------------
# 初始化显示模块 / Initialize display
# -------------------------------
Display.init(Display.VIRT, width=image_shape[1], height=image_shape[0], to_ide=True)

# -------------------------------
# 初始化媒体资源管理器 / Init media manager
# -------------------------------

sensor.run()

# -------------------------------
# 相机内参与畸变系数 / Camera intrinsics & distortion
# -------------------------------
camera_matrix = [1601.79998, 0.0, 960.2537,0.0, 1600.6784, 496.5050,0.0, 0.0, 1.0]
dist_coeffs = [0.16096, -0.73425, -0.01634, -0.00896, 0.41294]
dist_len=len(dist_coeffs)


# -------------------------------
# 启动帧率计时器 / Start FPS timer
# -------------------------------
clock = time.clock()

# -------------------------------
# 主循环 / Main loop
# -------------------------------
while True:
    clock.tick()

    # 获取图像帧
    img = sensor.snapshot()
    img_np = img.to_numpy_ref()  # 获取 RGB888 图像 ndarray 引用 (HWC)

    # 畸变校正
    result_np = cv_lite.rgb888_undistort(image_shape,img_np,camera_matrix,dist_coeffs,dist_len)
    # 快速畸变校正
    # result_np = cv_lite.rgb888_undistort_fast(image_shape,img_np,camera_matrix,dist_coeffs,dist_len)
    # 带优化相机矩阵畸变校正
    # result_np = cv_lite.rgb888_undistort_new_cam_mat(image_shape,img_np,camera_matrix,dist_coeffs,dist_len)

    # 构造图像对象用于显示
    img_out = image.Image(image_shape[1], image_shape[0], image.RGB888,
                          alloc=image.ALLOC_REF, data=result_np)

    # 显示矫正后的图像
    Display.show_image(img_out)

    # 内存管理与帧率打印
    gc.collect()
    print("undistort fps:", clock.fps())

# -------------------------------
# 程序退出与资源释放 / Cleanup on exit
# -------------------------------
sensor.stop()
Display.deinit()
os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
time.sleep_ms(100)

