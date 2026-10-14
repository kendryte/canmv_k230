# demo_feature_detect.py - OpenCV MicroPython 特征检测示例
# 演示: 轮廓查找, 霍夫变换(直线/圆), 模板匹配, 矩

import cv2
from ulab import numpy as np


def make_shapes_image():
    """创建包含各种形状的测试图像"""
    img = np.zeros((300, 400, 3), dtype=np.uint8)
    # 矩形
    cv2.rectangle(img, (30, 30), (150, 120), (255, 255, 255), -1)
    # 圆形
    cv2.circle(img, (280, 80), 55, (255, 255, 255), -1)
    # 三角形
    tri = np.array([[200, 260], [320, 260], [260, 170]], dtype=np.float)
    cv2.fillPoly(img, [tri], (255, 255, 255), cv2.LINE_AA)
    return img


def demo_contours():
    """轮廓查找与分析"""
    print("=== 轮廓查找示例 ===")
    img = make_shapes_image()
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)

    # 查找轮廓
    contours, hierarchy = cv2.findContours(binary,
                                           cv2.RETR_EXTERNAL,
                                           cv2.CHAIN_APPROX_SIMPLE)
    print("找到轮廓数:", len(contours))

    # 分析每个轮廓
    result = img.copy()
    for i, cnt in enumerate(contours):
        area = cv2.contourArea(cnt)
        perimeter = cv2.arcLength(cnt, True)
        x, y, w, h = cv2.boundingRect(cnt)
        print("  轮廓{}: 面积={:.1f} 周长={:.1f} 边界框=({},{},{},{})".format(
            i, area, perimeter, x, y, w, h))

        # 绘制边界框和轮廓
        cv2.drawContours(result, contours, i, (0, 255, 0), 2)
        cv2.rectangle(result, (x, y), (x + w, y + h), (0, 0, 255), 2)

    cv2.imwrite("/data/contours.png", result)
    print("轮廓绘制完成")


def demo_hough_lines():
    """霍夫直线检测"""
    print("\n=== 霍夫直线检测示例 ===")
    img = np.zeros((300, 400, 3), dtype=np.uint8)

    # 画一些直线
    cv2.line(img, (10, 50), (390, 80), (255, 255, 255), 2)
    cv2.line(img, (50, 250), (350, 150), (255, 255, 255), 2)
    cv2.line(img, (100, 10), (200, 290), (255, 255, 255), 2)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)

    # 标准霍夫变换
    lines = cv2.HoughLines(edges, 1, np.pi / 180, 100)
    print("HoughLines 检测到:", lines.shape[0] if lines is not None else 0, "条线")

    # 概率霍夫变换 (更适用于线段)
    lines_p = cv2.HoughLinesP(edges, 1, np.pi / 180, 50, minLineLength=50)
    print("HoughLinesP 检测到:", lines_p.shape[0] if lines_p is not None else 0, "条线段")

    if lines_p is not None:
        result = img.copy()
        for i in range(lines_p.shape[0]):
            x1, y1, x2, y2 = lines_p[i, 0], lines_p[i, 1], lines_p[i, 2], lines_p[i, 3]
            cv2.line(result, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
        cv2.imwrite("/data/hough_lines.png", result)
        print("霍夫直线绘制完成")


def demo_hough_circles():
    """霍夫圆检测"""
    print("\n=== 霍夫圆检测示例 ===")
    img = np.zeros((300, 400, 3), dtype=np.uint8)

    # 画一些圆
    cv2.circle(img, (100, 150), 60, (255, 255, 255), 2)
    cv2.circle(img, (250, 120), 40, (255, 255, 255), 2)
    cv2.circle(img, (200, 230), 30, (255, 255, 255), 2)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # 使用霍夫梯度法
    circles = cv2.HoughCircles(gray, 3, dp=1, minDist=30,
                               param1=100, param2=30)

    if circles is not None:
        n = circles.shape[0]
        print("检测到", n, "个圆")
        result = img.copy()
        for i in range(n):
            cx, cy, r = circles[i, 0], circles[i, 1], circles[i, 2]
            cv2.circle(result, (int(cx), int(cy)), int(r), (0, 255, 0), 2)
        cv2.imwrite("/data/hough_circles.png", result)
    else:
        print("未检测到圆")


def demo_template_matching():
    """模板匹配"""
    print("\n=== 模板匹配示例 ===")
    # 创建大图和小模板
    img = np.zeros((200, 300, 3), dtype=np.uint8)
    cv2.rectangle(img, (20, 20), (280, 180), (100, 100, 100), -1)
    cv2.rectangle(img, (80, 60), (180, 140), (200, 200, 200), -1)

    templ = np.zeros((60, 60, 3), dtype=np.uint8)
    cv2.rectangle(templ, (10, 10), (50, 50), (200, 200, 200), -1)

    gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray_templ = cv2.cvtColor(templ, cv2.COLOR_BGR2GRAY)

    # 模板匹配
    result = cv2.matchTemplate(gray_img, gray_templ, cv2.TM_CCOEFF_NORMED)

    # 找到最佳匹配位置
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    print("最佳匹配位置:", max_loc, "置信度:", max_val)

    # 在图上标注匹配位置
    h, w = gray_templ.shape[0], gray_templ.shape[1]
    cv2.rectangle(img, max_loc, (max_loc[0] + w, max_loc[1] + h),
                  (0, 255, 0), 2)
    cv2.putText(img, "Match", (max_loc[0], max_loc[1] - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    cv2.imwrite("/data/template_match.png", img)
    print("模板匹配完成")


if __name__ == "__main__":
    demo_contours()
    demo_hough_lines()
    demo_hough_circles()
    demo_template_matching()
    print("\n所有特征检测示例完成!")
