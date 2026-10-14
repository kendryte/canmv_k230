# demo_drawing.py - OpenCV MicroPython 绘图函数示例
# 演示: 直线, 矩形, 圆, 椭圆, 文本, 箭头, 多边形填充

import cv2
from ulab import numpy as np


def demo_shapes():
    """基本形状绘制"""
    print("=== 基本图形绘制 ===")
    # 创建黑色画布
    img = np.zeros((300, 400, 3), dtype=np.uint8)

    # 直线
    cv2.line(img, (10, 10), (390, 10), (0, 255, 0), 2)
    cv2.line(img, (10, 290), (390, 290), (0, 255, 0), 2)
    cv2.line(img, (10, 10), (10, 290), (0, 255, 0), 2)
    cv2.line(img, (390, 10), (390, 290), (0, 255, 0), 2)

    # 矩形 (填充和空心)
    cv2.rectangle(img, (50, 50), (150, 150), (255, 0, 0), -1)  # 填充
    cv2.rectangle(img, (200, 50), (350, 150), (0, 0, 255), 3)  # 空心

    # 圆形
    cv2.circle(img, (100, 220), 50, (0, 255, 255), -1)
    cv2.circle(img, (300, 220), 50, (0, 255, 255), 2)

    print("基本图形绘制完成")
    cv2.imwrite("/data/shapes.png", img)


def demo_text():
    """文字绘制"""
    print("\n=== 文字绘制示例 ===")
    img = np.zeros((200, 400, 3), dtype=np.uint8)

    # 不同字体和大小
    cv2.putText(img, "Hello OpenCV!", (20, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    cv2.putText(img, "MicroPython+K230", (20, 100),
                cv2.FONT_HERSHEY_DUPLEX, 0.7, (255, 0, 0), 1)
    cv2.putText(img, "cv2 Example", (20, 140),
                cv2.FONT_HERSHEY_SCRIPT_SIMPLEX, 0.9, (0, 255, 255), 2)

    # 斜体
    cv2.putText(img, "Italic Style", (20, 180),
                cv2.FONT_HERSHEY_SIMPLEX | cv2.FONT_ITALIC, 0.7, (255, 255, 0), 1)

    print("文字绘制完成")
    cv2.imwrite("/data/text.png", img)


def demo_ellipse_arrow():
    """椭圆和箭头"""
    print("\n=== 椭圆和箭头示例 ===")
    img = np.zeros((250, 400, 3), dtype=np.uint8)

    # 椭圆
    cv2.ellipse(img, (150, 125), (100, 80), 0, 0, 360, (255, 0, 0), 2)
    cv2.ellipse(img, (250, 125), (80, 100), 45, 0, 180, (0, 255, 0), 3)

    # 带箭头的线
    cv2.arrowedLine(img, (20, 230), (380, 20), (0, 255, 255), 2)

    print("椭圆和箭头绘制完成")
    cv2.imwrite("/data/ellipse_arrow.png", img)


def demo_fill_poly():
    """多边形填充"""
    print("\n=== 多边形填充示例 ===")
    img = np.zeros((250, 400, 3), dtype=np.uint8)

    # 三角形
    tri = np.array([[200, 30], [300, 200], [100, 200]], dtype=np.float)
    cv2.fillPoly(img, [tri], (255, 0, 0), cv2.LINE_AA)

    # 五角星
    pts = np.array([
        [60, 40], [80, 90], [130, 90], [85, 120], [100, 170],
        [60, 140], [20, 170], [35, 120], [0, 90], [40, 90]
    ], dtype=np.float)
    cv2.fillPoly(img, [pts], (0, 255, 255), cv2.LINE_AA)

    print("多边形填充完成")
    cv2.imwrite("/data/polygon.png", img)


def demo_markers():
    """标记绘制"""
    print("\n=== 标记绘制示例 ===")
    img = np.zeros((150, 400, 3), dtype=np.uint8)

    cv2.drawMarker(img, (50, 50), (0, 255, 0), cv2.MARKER_CROSS, 20, 2)
    cv2.drawMarker(img, (150, 50), (0, 255, 0), cv2.MARKER_STAR, 20, 2)
    cv2.drawMarker(img, (250, 50), (0, 255, 0), cv2.MARKER_DIAMOND, 20, 2)
    cv2.drawMarker(img, (350, 50), (0, 255, 0), cv2.MARKER_SQUARE, 20, 2)

    cv2.drawMarker(img, (50, 120), (255, 0, 0), cv2.MARKER_TILTED_CROSS, 15, 2)
    cv2.drawMarker(img, (150, 120), (255, 0, 0), cv2.MARKER_TRIANGLE_UP, 15, 2)
    cv2.drawMarker(img, (250, 120), (255, 0, 0), cv2.MARKER_TRIANGLE_DOWN, 15, 2)

    print("标记绘制完成")
    cv2.imwrite("/data/markers.png", img)


if __name__ == "__main__":
    demo_shapes()
    demo_text()
    demo_ellipse_arrow()
    demo_fill_poly()
    demo_markers()
    print("\n所有绘图示例完成!")
