# demo_basic_ops.py - OpenCV MicroPython 基础操作示例
# 演示: 图像读取/写入, 颜色空间转换, 缩放, 旋转

import cv2
from ulab import numpy as np

def demo_read_write():
    """读取和写入图像"""
    print("=== imread / imwrite 示例 ===")
    # 读取图像 (支持 BMP, PNG 等格式)
    img = cv2.imread("/sdcard/test.jpg")
    if img is None:
        print("未找到 /sdcard/test.jpg, 使用空图像演示")
        img = np.zeros((240, 320, 3), dtype=np.uint8)
        # 画一些内容
        cv2.circle(img, (160, 120), 80, (0, 255, 0), 2)
        cv2.putText(img, "OpenCV", (90, 120), cv2.FONT_HERSHEY_SIMPLEX,
                    1, (255, 0, 0), 2)

    print("图像 shape:", img.shape)

    # 写入图像
    success = cv2.imwrite("/data/output.png", img)
    print("写入结果:", "成功" if success else "失败")


def demo_color_conversion():
    """颜色空间转换"""
    print("\n=== cvtColor 示例 ===")
    img = np.zeros((240, 320, 3), dtype=np.uint8)
    cv2.rectangle(img, (50, 50), (270, 190), (255, 0, 0), -1)

    # 各种颜色空间转换
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    print("BGR -> Gray shape:", gray.shape)

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    print("BGR -> HSV shape:", hsv.shape)

    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    print("BGR -> LAB shape:", lab.shape)


def demo_resize_rotate():
    """图像缩放和旋转"""
    print("\n=== resize / rotate 示例 ===")
    img = np.zeros((240, 320, 3), dtype=np.uint8)
    cv2.circle(img, (160, 120), 100, (0, 200, 200), -1)

    # 缩放
    small = cv2.resize(img, (160, 120))
    print("缩小到 160x120 shape:", small.shape)

    big = cv2.resize(img, (640, 480))
    print("放大到 640x480 shape:", big.shape)

    # 旋转
    rotated = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    print("顺时针90度 shape:", rotated.shape)

    flipped = cv2.flip(img, 1)  # 水平翻转
    print("水平翻转 shape:", flipped.shape)


if __name__ == "__main__":
    demo_read_write()
    demo_color_conversion()
    demo_resize_rotate()
    print("\n所有基础操作示例完成!")
