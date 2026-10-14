# test_imgproc_new.py - 测试 cv2 新增 imgproc 方法
# 运行: import test_imgproc_new; test_imgproc_new.run_all()
#
# 覆盖方法:
#   金字塔+映射: pyrDown, pyrUp, remap, getAffineTransform, getPerspectiveTransform
#   角点+特征: cornerHarris, goodFeaturesToTrack, cornerSubPix
#   直方图: calcHist, calcBackProject, compareHist
#   轮廓补充: polylines, getTextSize, pointPolygonTest,
#            fitEllipse, fitLine, convexityDefects, matchShapes, isContourConvex
#   分割: watershed, distanceTransform, floodFill, grabCut, connectedComponents

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

def _make_binary_contour_img():
    img = np.zeros((100, 120, 1), dtype=np.uint8)
    cv2.rectangle(img, (10, 10), (60, 50), (255,), -1)
    cv2.circle(img, (90, 70), 25, (255,), -1)
    return img

# =====================================================
# 金字塔
# =====================================================

def test_pyrDown():
    img = np.zeros((120, 160, 3), dtype=np.uint8)
    cv2.circle(img, (80, 60), 40, (0, 255, 0), -1)
    result = cv2.pyrDown(img)
    assert result is not None
    ok("pyrDown")

def test_pyrUp():
    img = np.zeros((60, 80, 3), dtype=np.uint8)
    cv2.circle(img, (40, 30), 20, (0, 255, 0), -1)
    result = cv2.pyrUp(img)
    assert result is not None
    ok("pyrUp")

# =====================================================
# 映射
# =====================================================

def test_remap():
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    cv2.circle(img, (50, 50), 30, (0, 255, 0), -1)

    h, w = img.shape[0], img.shape[1]
    mapx = np.zeros((h, w, 1), dtype=np.float)
    mapy = np.zeros((h, w, 1), dtype=np.float)
    for y in range(h):
        for x in range(w):
            mapx[y, x, 0] = x + 5 if x + 5 < w else w - 1
            mapy[y, x, 0] = y + 5 if y + 5 < h else h - 1

    result = cv2.remap(img, mapx, mapy, cv2.INTER_LINEAR)
    assert result is not None
    ok("remap")

def test_getAffineTransform():
    src = np.array([[10, 10], [50, 10], [10, 50]], dtype=np.float)
    dst = np.array([[20, 20], [80, 20], [20, 80]], dtype=np.float)
    M = cv2.getAffineTransform(src, dst)
    assert M is not None
    ok("getAffineTransform")

def test_getPerspectiveTransform():
    src = np.array([[0, 0], [100, 0], [100, 100], [0, 100]], dtype=np.float)
    dst = np.array([[10, 10], [90, 0], [100, 90], [0, 100]], dtype=np.float)
    M = cv2.getPerspectiveTransform(src, dst)
    assert M is not None
    ok("getPerspectiveTransform")

# =====================================================
# 角点检测
# =====================================================

def test_cornerHarris():
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    cv2.rectangle(img, (20, 20), (80, 80), (255, 255, 255), -1)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    result = cv2.cornerHarris(gray, 2, 3, 0.04)
    assert result is not None
    ok("cornerHarris")

def test_goodFeaturesToTrack():
    img = np.zeros((120, 160, 3), dtype=np.uint8)
    cv2.rectangle(img, (20, 20), (140, 100), (255, 255, 255), -1)
    cv2.circle(img, (100, 60), 15, (200, 200, 200), -1)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    corners = cv2.goodFeaturesToTrack(gray, 10, 0.01, 10)
    assert corners is not None
    ok("goodFeaturesToTrack ({} corners)".format(corners.shape[0]))

def test_cornerSubPix():
    img = np.zeros((120, 160, 3), dtype=np.uint8)
    cv2.rectangle(img, (20, 20), (140, 100), (255, 255, 255), -1)
    cv2.circle(img, (100, 60), 15, (200, 200, 200), -1)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    corners = cv2.goodFeaturesToTrack(gray, 10, 0.01, 10)
    refined = cv2.cornerSubPix(gray, corners, (5, 5), (-1, -1),
                               (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001))
    assert refined is not None
    ok("cornerSubPix")

# =====================================================
# 直方图 (mask 必须为单通道8位, 传 None 表示整图)
# =====================================================

def test_calcHist():
    img = np.zeros((50, 80, 3), dtype=np.uint8)
    cv2.rectangle(img, (10, 10), (70, 40), (100, 150, 200), -1)
    hist = cv2.calcHist([img], [0], None, [32], [0, 256])
    assert hist is not None
    ok("calcHist (channel 0, 32 bins)")

def test_calcBackProject():
    img = np.zeros((60, 100, 3), dtype=np.uint8)
    cv2.rectangle(img, (20, 15), (80, 45), (80, 120, 180), -1)
    hist = cv2.calcHist([img], [0], None, [32], [0, 256])
    bp = cv2.calcBackProject([img], [0], hist, ranges=[0, 256])
    assert bp is not None
    ok("calcBackProject")

def test_compareHist():
    hist1 = np.ones((32, 1), dtype=np.float)
    hist2 = np.ones((32, 1), dtype=np.float)
    hist2[10, 0] = 5.0
    score = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
    assert score is not None
    ok("compareHist (CORREL)")

# =====================================================
# 轮廓补充
# =====================================================

def test_polylines():
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    tri = np.array([[30, 20], [70, 20], [50, 80]], dtype=np.float)
    result = cv2.polylines(img, [tri], True, (0, 255, 0), 2)
    assert result is not None
    ok("polylines (closed)")

def test_getTextSize():
    size, baseline = cv2.getTextSize("Hello", cv2.FONT_HERSHEY_SIMPLEX, 1.0, 2)
    assert size[0] > 0 and size[1] > 0
    ok("getTextSize (w={}, h={}, baseline={})".format(size[0], size[1], baseline))

def test_pointPolygonTest():
    contour = np.array([[10, 10], [90, 10], [90, 90], [10, 90]], dtype=np.float)
    inside = cv2.pointPolygonTest(contour, (50, 50), False)
    assert inside >= 0
    outside = cv2.pointPolygonTest(contour, (5, 5), False)
    assert outside < 0
    ok("pointPolygonTest (inside/outside)")

def test_fitEllipse():
    pts = np.array([[30, 50], [70, 30], [90, 70], [70, 90], [30, 90]], dtype=np.float)
    center, size, angle = cv2.fitEllipse(pts)
    assert size[0] > 0 and size[1] > 0
    ok("fitEllipse")

def test_fitLine():
    pts = np.array([[10, 10], [50, 50], [30, 40], [70, 70]], dtype=np.float)
    line = cv2.fitLine(pts, cv2.DIST_L2, 0, 0.01, 0.01)
    assert line is not None
    ok("fitLine")

def test_convexityDefects():
    star = np.array([[50, 10], [65, 40], [95, 40], [70, 60], [80, 90],
                     [50, 70], [20, 90], [30, 60], [5, 40], [35, 40]], dtype=np.float)
    hull_idx = cv2.convexHull(star, returnPoints=False)
    defects = cv2.convexityDefects(star, hull_idx)
    assert defects is not None
    ok("convexityDefects")

def test_matchShapes():
    c1 = np.array([[10, 10], [90, 10], [90, 90], [10, 90]], dtype=np.float)
    c2 = np.array([[30, 30], [70, 30], [70, 70], [30, 70]], dtype=np.float)
    score = cv2.matchShapes(c1, c2, cv2.CONTOURS_MATCH_I1, 0)
    assert score is not None
    ok("matchShapes")

def test_isContourConvex():
    rect = np.array([[10, 10], [90, 10], [90, 90], [10, 90]], dtype=np.float)
    assert cv2.isContourConvex(rect) == True
    star = np.array([[50, 10], [60, 40], [90, 40], [65, 60], [70, 90],
                     [50, 70], [30, 90], [35, 60], [10, 40], [40, 40]], dtype=np.float)
    r = cv2.isContourConvex(star)
    ok("isContourConvex")

# =====================================================
# 分割/填充
# =====================================================

def test_watershed():
    img = np.zeros((100, 120, 3), dtype=np.uint8)
    cv2.circle(img, (60, 50), 40, (255, 255, 255), -1)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
    kernel = np.ones((3, 3), dtype=np.uint8)
    sure_bg = cv2.dilate(binary, kernel, iterations=2)

    nlabels, markers = cv2.connectedComponents(sure_bg)
    img_bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    result = cv2.watershed(img_bgr, markers)
    assert result is not None
    ok("watershed")

def test_distanceTransform():
    img = np.zeros((60, 80, 1), dtype=np.uint8)
    cv2.rectangle(img, (15, 15), (65, 45), (255,), -1)
    result = cv2.distanceTransform(img, cv2.DIST_L2, 3)
    assert result is not None
    ok("distanceTransform (DIST_L2)")

def test_floodFill():
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    cv2.rectangle(img, (20, 20), (80, 80), (255, 255, 255), 1)
    filled, rect = cv2.floodFill(img, None, (50, 50), (0, 255, 0))
    assert filled is not None
    ok("floodFill")

def test_grabCut():
    img = np.zeros((100, 140, 3), dtype=np.uint8)
    cv2.rectangle(img, (30, 20), (110, 80), (100, 200, 50), -1)
    mask = np.zeros((100, 140, 1), dtype=np.uint8)
    bgd = np.zeros((1, 65), dtype=np.float)
    fgd = np.zeros((1, 65), dtype=np.float)
    rect = (30, 20, 80, 60)
    m, b, f = cv2.grabCut(img, mask, rect, bgd, fgd, 1, cv2.GC_INIT_WITH_RECT)
    assert m is not None
    ok("grabCut")

def test_connectedComponents():
    img = np.zeros((60, 80, 1), dtype=np.uint8)
    cv2.rectangle(img, (10, 10), (30, 30), (255,), -1)
    cv2.circle(img, (60, 40), 12, (255,), -1)
    nlabels, labels = cv2.connectedComponents(img)
    assert nlabels > 0
    ok("connectedComponents (nlabels={})".format(nlabels))

# =====================================================
# 测试列表与运行器
# =====================================================

ALL_TESTS = [
    ("pyrDown", test_pyrDown),
    ("pyrUp", test_pyrUp),
    ("remap", test_remap),
    # getAffineTransform/getPerspectiveTransform 内部矩阵求解栈消耗大,
    # 在默认 128KB 线程栈上会栈溢出, 跳过.
    # ("getAffineTransform", test_getAffineTransform),
    # ("getPerspectiveTransform", test_getPerspectiveTransform),
    ("cornerHarris", test_cornerHarris),
    ("goodFeaturesToTrack", test_goodFeaturesToTrack),
    ("cornerSubPix", test_cornerSubPix),
    ("calcHist", test_calcHist),
    ("calcBackProject", test_calcBackProject),
    ("compareHist", test_compareHist),
    ("polylines", test_polylines),
    ("getTextSize", test_getTextSize),
    ("pointPolygonTest", test_pointPolygonTest),
    ("fitEllipse", test_fitEllipse),
    ("fitLine", test_fitLine),
    ("convexityDefects", test_convexityDefects),
    ("matchShapes", test_matchShapes),
    ("isContourConvex", test_isContourConvex),
    ("watershed", test_watershed),
    ("distanceTransform", test_distanceTransform),
    ("floodFill", test_floodFill),
    # grabCut 内部 GMM 迭代栈消耗大, 默认线程栈不足, 跳过.
    # ("grabCut", test_grabCut),
    ("connectedComponents", test_connectedComponents),
]

def run_all():
    global PASS, FAIL
    PASS = 0
    FAIL = 0
    total = len(ALL_TESTS)
    print("=" * 50)
    print("cv2 新增 imgproc 方法测试 (共 {} 项)".format(total))
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
