# test_core_arithmetic.py - 测试 cv2 core 算术/位运算/通道/归一化方法
# 运行: import test_core_arithmetic; test_core_arithmetic.run_all()
#
# 覆盖方法: add, subtract, multiply, divide, addWeighted, absdiff,
#           bitwise_and, bitwise_or, bitwise_xor, bitwise_not,
#           split, merge, mean, normalize, compare

import cv2
from ulab import numpy as np
import gc

PASS = 0
FAIL = 0

def ok(name):
    global PASS
    PASS += 1
    print("  [OK] {}".format(name))

def err(name, e):
    global FAIL
    FAIL += 1
    print("  [FAIL] {}: {}".format(name, e))

# =====================================================
# 算术运算
# =====================================================

def test_add():
    img1 = np.array([[10, 20, 30], [40, 50, 60]], dtype=np.uint8)
    img2 = np.array([[5, 5, 5], [5, 5, 5]], dtype=np.uint8)
    result = cv2.add(img1, img2)
    assert result is not None
    ok("add")

def test_subtract():
    img1 = np.array([[50, 60, 70], [80, 90, 100]], dtype=np.uint8)
    img2 = np.array([[10, 10, 10], [10, 10, 10]], dtype=np.uint8)
    result = cv2.subtract(img1, img2)
    assert result is not None
    ok("subtract")

def test_multiply():
    img1 = np.array([[10, 20], [30, 40]], dtype=np.uint8)
    img2 = np.array([[2, 2], [2, 2]], dtype=np.uint8)
    result = cv2.multiply(img1, img2)
    assert result is not None
    ok("multiply")

def test_divide():
    img1 = np.array([[100, 80], [60, 40]], dtype=np.uint8)
    img2 = np.array([[2, 2], [2, 2]], dtype=np.uint8)
    result = cv2.divide(img1, img2)
    assert result is not None
    ok("divide")

def test_addWeighted():
    img1 = np.zeros((50, 50, 3), dtype=np.uint8)
    cv2.rectangle(img1, (10, 10), (40, 40), (100, 0, 0), -1)
    img2 = np.zeros((50, 50, 3), dtype=np.uint8)
    cv2.rectangle(img2, (15, 15), (35, 35), (0, 100, 0), -1)
    result = cv2.addWeighted(img1, 0.7, img2, 0.3, 0)
    assert result is not None
    ok("addWeighted")

def test_absdiff():
    img1 = np.array([[100, 50], [200, 150]], dtype=np.uint8)
    img2 = np.array([[80, 80], [150, 100]], dtype=np.uint8)
    result = cv2.absdiff(img1, img2)
    assert result is not None
    ok("absdiff")

# =====================================================
# 位运算
# =====================================================

def test_bitwise_and():
    img1 = np.array([[255, 0], [255, 0]], dtype=np.uint8)
    img2 = np.array([[255, 255], [0, 0]], dtype=np.uint8)
    result = cv2.bitwise_and(img1, img2)
    assert result is not None
    ok("bitwise_and")

def test_bitwise_or():
    img1 = np.array([[255, 0], [0, 0]], dtype=np.uint8)
    img2 = np.array([[0, 255], [0, 0]], dtype=np.uint8)
    result = cv2.bitwise_or(img1, img2)
    assert result is not None
    ok("bitwise_or")

def test_bitwise_xor():
    img1 = np.array([[255, 0], [0, 255]], dtype=np.uint8)
    img2 = np.array([[255, 255], [0, 0]], dtype=np.uint8)
    result = cv2.bitwise_xor(img1, img2)
    assert result is not None
    ok("bitwise_xor")

def test_bitwise_not():
    img = np.array([[0, 128], [255, 64]], dtype=np.uint8)
    result = cv2.bitwise_not(img)
    assert result is not None
    ok("bitwise_not")

# =====================================================
# 通道操作
# =====================================================

def test_split():
    img = np.zeros((30, 40, 3), dtype=np.uint8)
    cv2.rectangle(img, (5, 5), (25, 20), (10, 20, 30), -1)
    channels = cv2.split(img)
    assert channels is not None
    assert len(channels) == 3
    ok("split (3 channels)")

def test_merge():
    b = np.ones((20, 30), dtype=np.uint8) * 10
    g = np.ones((20, 30), dtype=np.uint8) * 100
    r = np.ones((20, 30), dtype=np.uint8) * 200
    img = cv2.merge([b, g, r])
    assert img is not None
    ok("merge")

# =====================================================
# 统计与归一化
# =====================================================

def test_mean():
    img = np.array([[10, 20, 30], [40, 50, 60]], dtype=np.uint8)
    m = cv2.mean(img)
    assert m is not None
    ok("mean")

def test_normalize():
    img = np.array([[0, 100], [200, 255]], dtype=np.uint8)
    result = cv2.normalize(img, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX)
    assert result is not None
    ok("normalize (MINMAX)")

def test_compare():
    img1 = np.array([[50, 100], [150, 200]], dtype=np.uint8)
    img2 = np.array([[100, 100], [100, 100]], dtype=np.uint8)
    result = cv2.compare(img1, img2, cv2.CMP_GT)
    assert result is not None
    nc = cv2.countNonZero(result)
    assert nc > 0
    ok("compare (CMP_GT, nonzero={})".format(nc))

# =====================================================
# 测试列表与运行器
# =====================================================

ALL_TESTS = [
    ("add", test_add),
    ("subtract", test_subtract),
    ("multiply", test_multiply),
    ("divide", test_divide),
    ("addWeighted", test_addWeighted),
    ("absdiff", test_absdiff),
    ("bitwise_and", test_bitwise_and),
    ("bitwise_or", test_bitwise_or),
    ("bitwise_xor", test_bitwise_xor),
    ("bitwise_not", test_bitwise_not),
    ("split", test_split),
    ("merge", test_merge),
    ("mean", test_mean),
    ("normalize", test_normalize),
    ("compare", test_compare),
]

def run_all():
    global PASS, FAIL
    PASS = 0
    FAIL = 0
    total = len(ALL_TESTS)
    print("=" * 50)
    print("cv2 core 算术/位运算测试 (共 {} 项)".format(total))
    print("=" * 50)
    for i, (name, func) in enumerate(ALL_TESTS):
        gc.collect()
        try:
            func()
        except Exception as e:
            err(name, str(e))
    print("-" * 50)
    print("结果: {} 通过, {} 失败, {} 总计".format(PASS, FAIL, PASS + FAIL))
    print("=" * 50)
    if FAIL:
        raise AssertionError("{} OpenCV tests failed".format(FAIL))

__all__ = ['run_all', 'ALL_TESTS']

if __name__ == '__main__':
    run_all()
