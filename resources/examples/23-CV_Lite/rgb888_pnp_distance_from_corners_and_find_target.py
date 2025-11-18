# ============================================================
# MicroPython 轮廓检测+PnP 距离估计测试（cv_lite 扩展）
# Contour Detection + PnP Distance Estimation via cv_lite
# ============================================================

import time, os, gc
from machine import Pin
from media.sensor import *
from media.display import *
from media.media import *
import _thread
import cv_lite               # 需要实现对应的 native C 接口
import ulab.numpy as np

# -------------------------------
# 图像尺寸 / Image size
# -------------------------------
image_shape = [480, 640]

# -------------------------------
# 摄像头初始化
# -------------------------------
sensor = Sensor(id=2, fps=90)
sensor.reset()
sensor_width = sensor.width(None)
sensor_height = sensor.height(None)
# 设置采集图片的分辨率
sensor.set_framesize(w=image_shape[1], h=image_shape[0],chn=CAM_CHN_ID_0)
sensor.set_pixformat(Sensor.RGB888)

# -------------------------------
# 虚拟显示器输出
# -------------------------------
Display.init(Display.ST7701,to_ide=True, quality=50)

# -------------------------------
# 启动媒体管理器
# -------------------------------

sensor.run()

# -------------------------------
# 相机参数
# -------------------------------
# lushanpi
# camera_matrix = [
#     797.6684357000107,0.0,342.96392945469194,
#     0.0,794.0425843669741,283.9207126582295,
#     0.0,0.0,1.0
# ]
# dist_coeffs = [0.002973393824577376,1.893431891543599,0.013494792164987314,0.016771512519744052,-12.501761300350461]
# dist_len = len(dist_coeffs)

# 01studio
camera_matrix = [
    789.1207591978101,0.0,308.8211709453399,
    0.0,784.6402477892891,220.80604393744628,
    0.0,0.0,1.0
]
dist_coeffs = [-0.0032975761115662697,-0.009984467065645562,-0.01301691382446514,-0.00805834837844004,-1.063818733754765]
dist_len = len(dist_coeffs)

# -------------------------------
# 目标实际尺寸（单位 cm）
# -------------------------------
obj_width_real = 20.1
obj_height_real = 28.9

# -------------------------------
# 帧率监控
# -------------------------------
clock = time.clock()

green_rgb = (0, 255, 0)  # 泛洪填充的绿色RGB值
# 修正HSV阈值格式
green_lab_min = (0, -128, 0)
green_lab_max = (100, 0, 127)

def mid_point_rect(x0, y0, wid, heigh):
    x_mid = x0 + wid // 2
    y_mid = y0 + heigh // 2
    return (x_mid, y_mid)

# -------------------------------
# 主循环
# -------------------------------
while True:
    clock.tick()

    img565 = None
    img = sensor.snapshot()
    img_np = img.to_numpy_ref()

    # 距离估计（通过轮廓+PnP）
    res = cv_lite.rgb888_pnp_distance_from_corners(
        image_shape, img_np,
        camera_matrix, dist_coeffs, dist_len,
        obj_width_real, obj_height_real
    )
    distance=res[0]
    rect=res[1]
    corners=res[2]

    # 如果距离估计成功
    if distance > 0:
        img565 = img.to_rgb565()

        # 获取A4纸区域信息
        x, y, w, h = rect[0], rect[1], rect[2], rect[3]

        # 计算中心区域
        inner_x = x + int(w * 0.2)
        inner_y = y + int(h * 0.2)
        inner_w = int(w * 0.6)
        inner_h = int(h * 0.6)

        seed_x, seed_y = mid_point_rect(inner_x, inner_y, inner_w, inner_h)
        img565.flood_fill(int(seed_x), int(seed_y), seed_threshold=0.1, floating_thresholds=0.05,
                    color=green_rgb, invert=False, clear_background=False)

        # 检测中间区域
        green_blobs = img565.find_blobs(
            [(0, 80, -128, 90, -128, 29)], # green
            invert=True,
            roi=(int(x), int(y), int(w), int(h)),
            x_stride=1,
            y_stride=1,
            pixels_threshold=1000,
            area_threshold=1000,
            merge=True,
            margin=False
        )

        # 绘制绿色区域边框
        if green_blobs:
            largest_green = max(green_blobs, key=lambda b: b.area())

            img565.draw_rectangle(
                int(largest_green.x()), int(largest_green.y()),
                int(largest_green.w()), int(largest_green.h()),
                color=(0, 0, 255), thickness=2, fill=False
            )

            info = f"Tgt: {largest_green.w()}x{largest_green.h()}"
            img565.draw_string_advanced(10, 10 + 32 + 32, 32, info, color=(255, 255, 255))

        rect_info = f"Rect: {w}x{h}"
        img565.draw_string_advanced(10, 10 + 32, 32, rect_info, color=(255, 255, 255))

        # Draw all detected rectangles and corners for visual feedback
        img565.draw_string_advanced(10, 10, 32, "Dist: %.2fcm" % distance, color=(255, 255, 255))
        img565.draw_rectangle(x,y,w,h, color=(255, 0, 0), thickness=2)
        img565.draw_cross(corners[0][0],corners[0][1],color=(255,255,255),size=5,thickness=2)
        img565.draw_cross(corners[1][0],corners[1][1],color=(255,255,255),size=5,thickness=2)
        img565.draw_cross(corners[2][0],corners[2][1],color=(255,255,255),size=5,thickness=2)
        img565.draw_cross(corners[3][0],corners[3][1],color=(255,255,255),size=5,thickness=2)
    else:
        img.draw_string_advanced(10, 10, 32, "No Rect Found", color=(255, 0, 0))

    # 显示图像
    if img565 is not None:
        Display.show_image(img565)
    else:
        Display.show_image(img)

    print("contour_pnp:", clock.fps())
#    print("Distance:", distance)
    gc.collect()

# -------------------------------
# 释放资源
# -------------------------------
sensor.stop()
Display.deinit()
os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
time.sleep_ms(100)

