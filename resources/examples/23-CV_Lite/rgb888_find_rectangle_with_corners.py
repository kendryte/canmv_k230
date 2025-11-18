# ============================================================
# MicroPython RGB888矩形检测测试代码（使用 cv_lite 扩展模块）,带角点
# Grayscale Rectangle Detection Test using cv_lite extension
# ============================================================

import time, os, sys, gc
from machine import Pin
from media.sensor import *     # 摄像头接口 / Camera interface
from media.display import *    # 显示接口 / Display interface
from media.media import *      # 媒体资源管理器 / Media manager
import _thread
import cv_lite                 # cv_lite扩展模块 / cv_lite extension (C bindings)
import ulab.numpy as np        # MicroPython NumPy类库

# -------------------------------
# 图像尺寸设置 / Image resolution
# -------------------------------
image_shape = [480, 640]  # 高 x 宽 / Height x Width

# -------------------------------
# 初始化摄像头（RGB888模式） / Initialize camera (rgb888 mode)
# -------------------------------
sensor = Sensor(id=2, fps = 90)
sensor.reset()
sensor_width = sensor.width(None)
sensor_height = sensor.height(None)
sensor.set_framesize(width=image_shape[1], height=image_shape[0])
sensor.set_pixformat(Sensor.RGB888)  # RGB888格式 / rgb888 format

# -------------------------------
# 初始化显示器（IDE虚拟输出） / Initialize display (IDE virtual output)
# -------------------------------
Display.init(Display.VIRT, width=image_shape[1], height=image_shape[0],
             to_ide=True, quality=50)

# -------------------------------
# 初始化媒体系统 / Initialize media system
# -------------------------------

sensor.run()

# -------------------------------
# 可选增益设置（亮度/对比度调节）/ Optional sensor gain setting
# -------------------------------
gain = k_sensor_gain()
gain.gain[0] = 20
sensor.again(gain)

# -------------------------------
# 启动帧率计时 / Start FPS timer
# -------------------------------
clock = time.clock()

# -------------------------------
# 矩形检测可调参数 / Adjustable rectangle detection parameters
# -------------------------------
canny_thresh1      = 50        # Canny 边缘检测低阈值 / Canny low threshold
canny_thresh2      = 150       # Canny 边缘检测高阈值 / Canny high threshold
approx_epsilon     = 0.04      # 多边形拟合精度比例（越小拟合越精确）/ Polygon approximation accuracy
area_min_ratio     = 0.001     # 最小面积比例（相对于图像总面积）/ Min area ratio
max_angle_cos      = 0.3       # 最大角度余弦（越小越接近矩形）/ Max cosine of angle between edges
gaussian_blur_size = 5         # 高斯模糊核尺寸（奇数）/ Gaussian blur kernel size

# -------------------------------
# 主循环 / Main loop
# -------------------------------
while True:
    clock.tick()

    # 拍摄一帧图像 / Capture a frame
    img = sensor.snapshot()
    img_np = img.to_numpy_ref()

    # 调用底层矩形检测函数
    # 返回格式：[[x0, y0, w0, h0, c1.x, c1.y, c2.x, c2.y, c3.x, c3.y, c4,x, c4.y], [x1, y1, w1, h1,c1.x, c1.y, c2.x, c2.y, c3.x, c3.y, c4,x, c4.y], ...]
    rects = cv_lite.rgb888_find_rectangles_with_corners(
        image_shape, img_np,
        canny_thresh1, canny_thresh2,
        approx_epsilon,
        area_min_ratio,
        max_angle_cos,
        gaussian_blur_size
    )
    # 遍历检测到的矩形并绘制矩形框和角点
    for i in range(len(rects)):
        r = rects[i]
        img.draw_rectangle(r[0],r[1], r[2], r[3], color=(255, 255, 255), thickness=2)
        img.draw_cross(r[4],r[5],color=(255,255,255),size=5,thickness=2)
        img.draw_cross(r[6],r[7],color=(255,255,255),size=5,thickness=2)
        img.draw_cross(r[8],r[9],color=(255,255,255),size=5,thickness=2)
        img.draw_cross(r[10],r[11],color=(255,255,255),size=5,thickness=2)

    # 显示图像 / Show image
    Display.show_image(img)

    # 垃圾回收 & 输出帧率/ Garbage collect and print FPS
    gc.collect()
    print("fps:", clock.fps())

# -------------------------------
# 程序退出与资源释放 / Cleanup on exit
# -------------------------------
sensor.stop()
Display.deinit()
os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
time.sleep_ms(100)

