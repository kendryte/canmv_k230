# demo_filters.py - OpenCV MicroPython 图像滤波示例
# 演示: 模糊, 边缘检测, 形态学操作, 直方图均衡化

import cv2
from ulab import numpy as np


def make_test_image():
    """创建带形状的测试图像"""
    img = np.zeros((240, 320, 3), dtype=np.uint8)
    cv2.rectangle(img, (30, 30), (130, 130), (0, 0, 255), -1)
    cv2.circle(img, (220, 100), 60, (0, 255, 0), -1)
    cv2.rectangle(img, (80, 150), (280, 210), (255, 0, 0), -1)
    return img


def demo_blur():
    """各种模糊滤波器"""
    print("=== 模糊滤波示例 ===")
    img = make_test_image()

    # 均值模糊
    blurred = cv2.blur(img, (5, 5))
    cv2.imwrite("/data/blurred.png", blurred)
    print("blur 完成")

    # 高斯模糊
    gaussian = cv2.GaussianBlur(img, (5, 5), 0)
    cv2.imwrite("/data/gaussian.png", gaussian)
    print("GaussianBlur 完成")

    # 中值模糊
    median = cv2.medianBlur(img, 5)
    cv2.imwrite("/data/median.png", median)
    print("medianBlur 完成")

    # 双边滤波 (保留边缘)
    bilateral = cv2.bilateralFilter(img, 9, 75, 75)
    cv2.imwrite("/data/bilateral.png", bilateral)
    print("bilateralFilter 完成")


def demo_edge_detection():
    """边缘检测"""
    print("\n=== 边缘检测示例 ===")
    img = make_test_image()
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Canny 边缘检测
    edges = cv2.Canny(gray, 100, 200)
    cv2.imwrite("/data/canny.png", edges)
    print("Canny 完成, 边缘数:", cv2.countNonZero(edges))

    # Sobel 算子
    sobel_x = cv2.Sobel(gray, cv2.CV_8U, 1, 0)
    sobel_y = cv2.Sobel(gray, cv2.CV_8U, 0, 1)
    print("Sobel 完成")

    # Laplacian 算子
    laplacian = cv2.Laplacian(gray, cv2.CV_8U)
    cv2.imwrite("/data/laplacian.png", laplacian)
    print("Laplacian 完成")


def demo_morphology():
    """形态学操作"""
    print("\n=== 形态学操作示例 ===")
    img = make_test_image()
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)

    # 结构元素
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))

    # 腐蚀
    eroded = cv2.erode(binary, kernel)
    print("erode 完成")

    # 膨胀
    dilated = cv2.dilate(binary, kernel)
    print("dilate 完成")

    # 开运算 (先腐蚀后膨胀, 去除噪声)
    opened = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    print("MORPH_OPEN 完成")

    # 闭运算 (先膨胀后腐蚀, 填充空洞)
    closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    print("MORPH_CLOSE 完成")


def demo_threshold():
    """阈值化"""
    print("\n=== 阈值化示例 ===")
    img = make_test_image()
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 全局阈值
    _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
    print("全局阈值 threshold:", _)

    # 大津法 (Otsu)
    _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_OTSU)
    print("Otsu 阈值:", _)

    # 自适应阈值
    adaptive = cv2.adaptiveThreshold(gray, 255,
                                     cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY, 11, 2)
    cv2.imwrite("/data/adaptive.png", adaptive)
    print("adaptiveThreshold 完成")


def demo_equalize_hist():
    """直方图均衡化"""
    print("\n=== 直方图均衡化示例 ===")
    img = make_test_image()
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    equalized = cv2.equalizeHist(gray)
    cv2.imwrite("/data/equalized.png", equalized)
    print("equalizeHist 完成")


if __name__ == "__main__":
    demo_blur()
    demo_edge_detection()
    demo_morphology()
    demo_threshold()
    demo_equalize_hist()
    print("\n所有滤波示例完成!")
