# test_imgcodecs_memory.py - 测试 cv2 内存编解码方法
# 运行: import test_imgcodecs_memory; test_imgcodecs_memory.run_all()
#
# 覆盖方法: imdecode, imencode

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

def test_imdecode():
    img = np.zeros((60, 80, 3), dtype=np.uint8)
    cv2.circle(img, (40, 30), 25, (0, 255, 0), -1)
    cv2.rectangle(img, (10, 10), (30, 20), (255, 0, 0), -1)

    success, buf = cv2.imencode(".png", img)
    assert success, "imencode failed"
    assert len(buf) > 0

    decoded = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    assert decoded is not None
    ok("imdecode")

def test_imencode():
    img = np.zeros((60, 80, 3), dtype=np.uint8)
    cv2.circle(img, (40, 30), 25, (0, 255, 0), 2)
    cv2.putText(img, "test", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

    success, buf = cv2.imencode(".png", img)
    assert success, "imencode returned False"
    assert buf is not None
    assert len(buf) > 0
    ok("imencode (len={})".format(len(buf)))

def test_imencode_params():
    img = np.zeros((30, 40, 3), dtype=np.uint8)
    cv2.circle(img, (20, 15), 12, (0, 200, 100), -1)

    success, buf = cv2.imencode(".jpg", img, [1, 50])  # IMWRITE_JPEG_QUALITY=1
    assert success, "imencode with params failed"
    assert len(buf) > 0
    ok("imencode with params (JPEG quality=50, len={})".format(len(buf)))

def test_roundtrip_grayscale():
    img = np.zeros((40, 50, 1), dtype=np.uint8)
    cv2.rectangle(img, (10, 10), (40, 30), (200,), -1)

    success, buf = cv2.imencode(".png", img)
    assert success

    decoded = cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)
    assert decoded is not None
    ok("imdecode/imencode roundtrip (grayscale)")

ALL_TESTS = [
    ("imdecode", test_imdecode),
    ("imencode", test_imencode),
    ("imencode_params", test_imencode_params),
    ("roundtrip_grayscale", test_roundtrip_grayscale),
]

def run_all():
    global PASS, FAIL
    PASS = 0
    FAIL = 0
    total = len(ALL_TESTS)
    print("=" * 50)
    print("cv2 内存编解码测试 (共 {} 项)".format(total))
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
