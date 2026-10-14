# demo_image_processing.py - OpenCV MicroPython 综合图像处理管道示例
# 演示: 多步骤视觉处理管道 (滤波 -> 阈值 -> 形态学 -> 轮廓检测)

import cv2
from ulab import numpy as np


def make_noisy_shapes():
    """创建带噪声的形状图像"""
    # 使用渐变而非随机 (ulab 没有 np.random)
    img = np.zeros((300, 400, 3), dtype=np.uint8)

    # 添加一些"噪声"纹理: 使用棋盘格图案
    for y in range(0, 300, 20):
        for x in range(0, 400, 20):
            if (x // 20 + y // 20) % 2 == 0:
                cv2.rectangle(img, (x, y), (x + 19, y + 19), (40, 40, 40), -1)

    # 叠加大形状
    cv2.rectangle(img, (50, 50), (180, 180), (220, 220, 220), -1)
    cv2.circle(img, (300, 150), 70, (200, 200, 200), -1)
    return img


def process_pipeline_1():
    """处理管道1: 边缘检测管道"""
    print("=== 管道1: 边缘检测 ===")
    img = make_noisy_shapes()

    # 1. 转灰度
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    print("1. cvtColor -> 灰度", gray.shape)

    # 2. 高斯模糊去噪
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    print("2. GaussianBlur -> 去噪")

    # 3. Canny 边缘检测
    edges = cv2.Canny(blurred, 80, 200)
    print("3. Canny -> 边缘检测")

    # 4. 膨胀边缘 (加粗)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    thick_edges = cv2.dilate(edges, kernel)
    print("4. dilate -> 加粗边缘")

    cv2.imwrite("/data/pipeline_edges.png", thick_edges)
    print("边缘检测管道完成!")
    return thick_edges


def process_pipeline_2():
    """处理管道2: 目标检测管道"""
    print("\n=== 管道2: 目标检测 ===")
    img = make_noisy_shapes()

    # 1. 转灰度
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 2. 高斯模糊
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # 3. 自适应阈值
    binary = cv2.adaptiveThreshold(blurred, 255,
                                   cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY, 15, 2)
    print("3. adaptiveThreshold -> 二值化")

    # 4. 形态学闭运算 (填充小孔)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    print("4. MORPH_CLOSE -> 填充空洞")

    # 5. 查找并分析轮廓
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
    print("5. findContours -> 找到", len(contours), "个轮廓")

    # 6. 过滤并标注
    result = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > 500:  # 过滤小轮廓
            # 边界框
            x, y, w, h = cv2.boundingRect(cnt)
            cv2.rectangle(result, (x, y), (x + w, y + h), (0, 255, 0), 2)

            # 近似多边形
            epsilon = 0.02 * cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, epsilon, True)

            # 凸包
            hull = cv2.convexHull(cnt)

            # 面积
            cv2.putText(result, "A={:.0f}".format(area), (x, y - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 0), 1)

    print("6. 轮廓分析完成, 有效轮廓数:", 
          sum(1 for c in contours if cv2.contourArea(c) > 500))

    cv2.imwrite("/data/pipeline_objects.png", result)
    print("目标检测管道完成!")
    return result


def process_pipeline_3():
    """处理管道3: inRange 颜色过滤"""
    print("\n=== 管道3: 颜色过滤 ===")
    # 创建彩色测试图像
    img = np.zeros((300, 400, 3), dtype=np.uint8)
    cv2.rectangle(img, (20, 20), (180, 120), (0, 0, 255), -1)  # 红色
    cv2.rectangle(img, (200, 20), (380, 120), (0, 255, 0), -1)  # 绿色
    cv2.rectangle(img, (20, 150), (180, 280), (255, 0, 0), -1)  # 蓝色
    cv2.circle(img, (300, 220), 60, (0, 200, 200), -1)  # 青色

    # 1. BGR 转 HSV (便于颜色过滤)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    print("1. cvtColor BGR->HSV")

    # 2. 提取红色区域 (HSV 中红色跨越 0/180)
    # 低红色
    lower_red1 = np.array([0, 100, 100], dtype=np.uint8)
    upper_red1 = np.array([10, 255, 255], dtype=np.uint8)
    mask1 = cv2.inRange(hsv, lower_red1, upper_red1)

    # 高红色
    lower_red2 = np.array([160, 100, 100], dtype=np.uint8)
    upper_red2 = np.array([180, 255, 255], dtype=np.uint8)
    mask2 = cv2.inRange(hsv, lower_red2, upper_red2)

    # 合并红色掩码 (GaussianBlur 演示去噪)
    red_mask = cv2.GaussianBlur(mask1, (5, 5), 0)
    print("2. inRange -> 红色掩码")

    # 3. 提取绿色
    lower_green = np.array([40, 100, 100], dtype=np.uint8)
    upper_green = np.array([80, 255, 255], dtype=np.uint8)
    green_mask = cv2.inRange(hsv, lower_green, upper_green)
    print("3. inRange -> 绿色掩码")

    # 4. 提取蓝色
    lower_blue = np.array([100, 100, 100], dtype=np.uint8)
    upper_blue = np.array([130, 255, 255], dtype=np.uint8)
    blue_mask = cv2.inRange(hsv, lower_blue, upper_blue)
    print("4. inRange -> 蓝色掩码")

    # 结果可视化
    result = img.copy()
    result[:, :, :] = 0  # 清空

    # 将检测到的颜色画回原图
    # (这里需要用 numpy 操作或像素级循环, 为简化仅计数)
    print("  红色像素:", cv2.countNonZero(mask1) + cv2.countNonZero(mask2))
    print("  绿色像素:", cv2.countNonZero(green_mask))
    print("  蓝色像素:", cv2.countNonZero(blue_mask))

    # 对红色掩码做形态学处理
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    clean_red = cv2.morphologyEx(mask1, cv2.MORPH_OPEN, kernel)
    print("5. 形态学清理完成")

    cv2.imwrite("/data/pipeline_color.png", clean_red.reshape((300, 400, 1)))
    print("颜色过滤管道完成!")


def demo_memory_optimization():
    """演示如何重用 dst 缓冲区来减少内存分配"""
    print("\n=== 内存优化示例 ===")
    img = make_noisy_shapes()

    # 预分配输出缓冲区
    gray = np.zeros((img.shape[0], img.shape[1]), dtype=np.uint8)
    blurred = np.zeros(gray.shape, dtype=np.uint8)
    edges = np.zeros(gray.shape, dtype=np.uint8)

    # 第一次调用: 分配新输出 (默认)
    _ = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    print("1. cvtColor (默认分配)")

    # 第二次调用: 重用 dst 缓冲区 (更快)
    _ = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY, dst=gray)
    print("2. cvtColor (dst 复用)")

    _ = cv2.GaussianBlur(gray, (5, 5), 0, dst=blurred)
    print("3. GaussianBlur (dst 复用)")

    _ = cv2.Canny(blurred, 80, 200, edges=edges)
    print("4. Canny (dst 复用)")

    print("内存优化: 关键图像复用 dst 参数可显著减少 GC 开销")


if __name__ == "__main__":
    process_pipeline_1()
    process_pipeline_2()
    process_pipeline_3()
    demo_memory_optimization()
    print("\n所有图像处理管道示例完成!")
