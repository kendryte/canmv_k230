# test_all_cv2.py - 逐方法测试所有 cv2 OpenCV 封装函数
# 运行: import test_all_cv2; test_all_cv2.run_all()

import cv2
from ulab import numpy as np
import gc

PASS = 0
FAIL = 0

# =====================================================
# 辅助函数
# =====================================================

def make_test_img(w=200, h=150, ch=3):
    """创建带形状的测试图像"""
    img = np.zeros((h, w, ch), dtype=np.uint8)
    if ch >= 3:
        cv2.rectangle(img, (10, 10), (80, 60), (0, 0, 255), -1)
        cv2.circle(img, (140, 80), 35, (0, 255, 0), -1)
        cv2.rectangle(img, (30, 100), (160, 130), (255, 0, 0), -1)
    elif ch == 1:
        cv2.rectangle(img, (10, 10), (80, 60), (255,), -1)
        cv2.circle(img, (140, 80), 35, (255,), -1)
    return img

def _make_binary_contour_img():
    """创建带白色形状的8位单通道图像, 直接可用于 findContours"""
    img = np.zeros((100, 120, 1), dtype=np.uint8)
    cv2.rectangle(img, (10, 10), (60, 50), (255,), -1)
    cv2.circle(img, (90, 70), 25, (255,), -1)
    return img

def ok(name):
    global PASS
    PASS += 1
    print("  [OK] {}".format(name))

def err(name, e):
    global FAIL
    FAIL += 1
    print("  [FAIL] {}: {}".format(name, e))

# =====================================================
# core 模块
# =====================================================

def test_inRange():
    """cv2.inRange - 颜色范围过滤"""
    img = make_test_img()
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lo = np.array([0, 50, 50], dtype=np.uint8)
    hi = np.array([10, 255, 255], dtype=np.uint8)
    mask = cv2.inRange(hsv, lo, hi)
    assert mask is not None
    ok("inRange")

def test_convertScaleAbs():
    """cv2.convertScaleAbs - 缩放取绝对值转8位"""
    img = make_test_img(ch=1)
    img_f = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float)
    result = cv2.convertScaleAbs(img_f, alpha=2, beta=10)
    assert result is not None
    ok("convertScaleAbs")

def test_minMaxLoc():
    """cv2.minMaxLoc - 查找最小最大值位置"""
    img = make_test_img(ch=1)
    minVal, maxVal, minLoc, maxLoc = cv2.minMaxLoc(img)
    assert maxVal >= minVal
    ok("minMaxLoc")

def test_LUT():
    """cv2.LUT - 查找表映射"""
    img = np.zeros((10, 10), dtype=np.uint8)
    img[0, 0] = 100
    lut = np.zeros((256, 1), dtype=np.uint8)
    lut[100, 0] = 200
    result = cv2.LUT(img, lut)
    assert result is not None
    ok("LUT")

def test_countNonZero():
    """cv2.countNonZero - 统计非零像素数"""
    img = make_test_img(ch=1)
    cnt = cv2.countNonZero(img)
    assert cnt > 0
    ok("countNonZero (cnt={})".format(cnt))

def test_flip():
    """cv2.flip - 图像翻转"""
    img = make_test_img()
    f0 = cv2.flip(img, 0)   # 垂直
    f1 = cv2.flip(img, 1)   # 水平
    f2 = cv2.flip(img, -1)  # 对角线
    assert f0 is not None and f1 is not None and f2 is not None
    ok("flip (0/1/-1)")

def test_rotate():
    """cv2.rotate - 图像旋转"""
    img = make_test_img()
    r90 = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    r180 = cv2.rotate(img, cv2.ROTATE_180)
    r270 = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    assert r90 is not None and r180 is not None and r270 is not None
    ok("rotate (90/180/270)")

def test_transpose():
    """cv2.transpose - 矩阵转置"""
    img = make_test_img(ch=1)
    t = cv2.transpose(img)
    assert t is not None
    ok("transpose")

# =====================================================
# imgproc - 图像滤波
# =====================================================

def test_Canny():
    """cv2.Canny - 边缘检测"""
    gray = cv2.cvtColor(make_test_img(), cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 80, 200)
    assert edges is not None
    ok("Canny")

def test_GaussianBlur():
    """cv2.GaussianBlur - 高斯模糊"""
    img = make_test_img()
    result = cv2.GaussianBlur(img, (5, 5), 0)
    assert result is not None
    ok("GaussianBlur")

def test_blur():
    """cv2.blur - 均值模糊"""
    img = make_test_img()
    result = cv2.blur(img, (5, 5))
    assert result is not None
    ok("blur")

def test_medianBlur():
    """cv2.medianBlur - 中值模糊"""
    img = make_test_img()
    result = cv2.medianBlur(img, 5)
    assert result is not None
    ok("medianBlur")

def test_bilateralFilter():
    """cv2.bilateralFilter - 双边滤波"""
    img = make_test_img()
    result = cv2.bilateralFilter(img, 9, 75, 75)
    assert result is not None
    ok("bilateralFilter")

def test_boxFilter():
    """cv2.boxFilter - 方框滤波"""
    img = make_test_img(ch=1)
    result = cv2.boxFilter(img, -1, (5, 5))
    assert result is not None
    ok("boxFilter")

def test_filter2D():
    """cv2.filter2D - 自定义卷积核"""
    img = make_test_img(ch=1)
    kernel = np.ones((3, 3), dtype=np.float) / 9.0
    result = cv2.filter2D(img, -1, kernel)
    assert result is not None
    ok("filter2D")

def test_Sobel():
    """cv2.Sobel - Sobel 边缘检测"""
    gray = cv2.cvtColor(make_test_img(), cv2.COLOR_BGR2GRAY)
    sx = cv2.Sobel(gray, cv2.CV_8U, 1, 0)
    sy = cv2.Sobel(gray, cv2.CV_8U, 0, 1)
    assert sx is not None and sy is not None
    ok("Sobel")

def test_Scharr():
    """cv2.Scharr - Scharr 边缘检测"""
    gray = cv2.cvtColor(make_test_img(), cv2.COLOR_BGR2GRAY)
    sx = cv2.Scharr(gray, cv2.CV_8U, 1, 0)
    sy = cv2.Scharr(gray, cv2.CV_8U, 0, 1)
    assert sx is not None and sy is not None
    ok("Scharr")

def test_Laplacian():
    """cv2.Laplacian - 拉普拉斯边缘检测"""
    gray = cv2.cvtColor(make_test_img(), cv2.COLOR_BGR2GRAY)
    result = cv2.Laplacian(gray, cv2.CV_8U)
    assert result is not None
    ok("Laplacian")

def test_erode():
    """cv2.erode - 腐蚀"""
    gray = cv2.cvtColor(make_test_img(), cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
    kernel = np.ones((3, 3), dtype=np.uint8)
    result = cv2.erode(binary, kernel)
    assert result is not None
    ok("erode")

def test_dilate():
    """cv2.dilate - 膨胀"""
    gray = cv2.cvtColor(make_test_img(), cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
    kernel = np.ones((3, 3), dtype=np.uint8)
    result = cv2.dilate(binary, kernel)
    assert result is not None
    ok("dilate")

def test_morphologyEx():
    """cv2.morphologyEx - 形态学操作"""
    gray = cv2.cvtColor(make_test_img(), cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
    kernel = np.ones((3, 3), dtype=np.uint8)
    opened = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    assert opened is not None and closed is not None
    ok("morphologyEx (OPEN/CLOSE)")

def test_getStructuringElement():
    """cv2.getStructuringElement - 获取结构元素"""
    k1 = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    k2 = cv2.getStructuringElement(cv2.MORPH_CROSS, (5, 5))
    k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    assert k1 is not None and k2 is not None and k3 is not None
    ok("getStructuringElement (RECT/CROSS/ELLIPSE)")

# =====================================================
# imgproc - 阈值与颜色转换
# =====================================================

def test_threshold():
    """cv2.threshold - 全局阈值"""
    gray = cv2.cvtColor(make_test_img(), cv2.COLOR_BGR2GRAY)
    ret, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
    assert binary is not None
    ret2, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_OTSU)
    assert otsu is not None
    ok("threshold (BINARY/OTSU)")

def test_adaptiveThreshold():
    """cv2.adaptiveThreshold - 自适应阈值"""
    gray = cv2.cvtColor(make_test_img(), cv2.COLOR_BGR2GRAY)
    result = cv2.adaptiveThreshold(gray, 255,
                                    cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                    cv2.THRESH_BINARY, 11, 2)
    assert result is not None
    ok("adaptiveThreshold")

def test_cvtColor():
    """cv2.cvtColor - 颜色空间转换"""
    img = make_test_img()
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    assert gray is not None and hsv is not None and rgb is not None and lab is not None
    ok("cvtColor (GRAY/HSV/RGB/LAB)")

def test_resize():
    """cv2.resize - 图像缩放"""
    img = make_test_img()
    small = cv2.resize(img, (100, 75))
    big = cv2.resize(img, (400, 300))
    assert small is not None and big is not None
    ok("resize (缩小/放大)")

def test_warpAffine():
    """cv2.warpAffine - 仿射变换"""
    img = make_test_img()
    M = np.array([[1, 0, 20], [0, 1, 30]], dtype=np.float)
    result = cv2.warpAffine(img, M, (200, 150))
    assert result is not None
    ok("warpAffine")

def test_warpPerspective():
    """cv2.warpPerspective - 透视变换"""
    img = make_test_img()
    M = np.array([[1, 0, 10], [0, 1, 10], [0, 0, 1]], dtype=np.float)
    result = cv2.warpPerspective(img, M, (200, 150))
    assert result is not None
    ok("warpPerspective")

def test_getRotationMatrix2D():
    """cv2.getRotationMatrix2D - 获取旋转矩阵"""
    M = cv2.getRotationMatrix2D((100, 75), 45, 1.0)
    assert M is not None
    ok("getRotationMatrix2D")

def test_equalizeHist():
    """cv2.equalizeHist - 直方图均衡化"""
    gray = cv2.cvtColor(make_test_img(), cv2.COLOR_BGR2GRAY)
    result = cv2.equalizeHist(gray)
    assert result is not None
    ok("equalizeHist")

# =====================================================
# imgproc - 绘图函数
# =====================================================

def test_line():
    """cv2.line - 画线"""
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    result = cv2.line(img, (10, 10), (90, 90), (0, 255, 0), 2)
    result = cv2.line(img, (90, 10), (10, 90), (255, 0, 0), 3, cv2.LINE_AA)
    assert result is not None
    ok("line")

def test_rectangle():
    """cv2.rectangle - 画矩形"""
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    result = cv2.rectangle(img, (10, 10), (90, 90), (0, 255, 0), 2)
    result = cv2.rectangle(img, (30, 30), (70, 70), (255, 0, 0), -1)
    assert result is not None
    ok("rectangle")

def test_circle():
    """cv2.circle - 画圆"""
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    result = cv2.circle(img, (50, 50), 40, (0, 255, 0), 2)
    result = cv2.circle(img, (50, 50), 20, (255, 0, 0), -1)
    assert result is not None
    ok("circle")

def test_ellipse():
    """cv2.ellipse - 画椭圆"""
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    result = cv2.ellipse(img, (50, 50), (40, 25), 30, 0, 360, (0, 255, 0), 2)
    result = cv2.ellipse(img, (50, 50), (30, 15), 0, 0, 180, (255, 0, 0), -1)
    assert result is not None
    ok("ellipse")

def test_putText():
    """cv2.putText - 绘制文字"""
    img = np.zeros((60, 200, 3), dtype=np.uint8)
    result = cv2.putText(img, "Hello cv2!", (10, 40),
                          cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    assert result is not None
    ok("putText")

def test_arrowedLine():
    """cv2.arrowedLine - 画箭头"""
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    result = cv2.arrowedLine(img, (10, 50), (90, 50), (0, 255, 0), 2)
    assert result is not None
    ok("arrowedLine")

def test_drawMarker():
    """cv2.drawMarker - 绘制标记"""
    img = np.zeros((100, 200, 3), dtype=np.uint8)
    result = cv2.drawMarker(img, (50, 50), (0, 255, 0), cv2.MARKER_CROSS, 20, 2)
    result = cv2.drawMarker(img, (100, 50), (255, 0, 0), cv2.MARKER_STAR, 15, 2)
    result = cv2.drawMarker(img, (150, 50), (0, 0, 255), cv2.MARKER_DIAMOND, 15, 2)
    assert result is not None
    ok("drawMarker (CROSS/STAR/DIAMOND)")

def test_fillPoly():
    """cv2.fillPoly - 填充多边形"""
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    tri = np.array([[20, 20], [80, 20], [50, 80]], dtype=np.float)
    result = cv2.fillPoly(img, [tri], (0, 255, 0), cv2.LINE_AA)
    assert result is not None
    ok("fillPoly")

# =====================================================
# imgproc - 结构分析
# =====================================================

def test_findContours():
    """cv2.findContours - 查找轮廓"""
    img = np.zeros((80, 120, 1), dtype=np.uint8)
    cv2.rectangle(img, (10, 10), (60, 50), (255,), -1)
    contours, hierarchy = cv2.findContours(img, cv2.RETR_EXTERNAL,
                                            cv2.CHAIN_APPROX_SIMPLE)
    assert len(contours) > 0, "no contours found"
    ok("findContours ({} contours)".format(len(contours)))

def test_drawContours():
    """cv2.drawContours - 绘制轮廓"""
    img = _make_binary_contour_img()
    contours, _ = cv2.findContours(img, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
    canvas = np.zeros((150, 200, 3), dtype=np.uint8)
    result = cv2.drawContours(canvas, contours, -1, (0, 255, 0), 2)
    assert result is not None
    ok("drawContours")

def test_contourArea():
    """cv2.contourArea - 轮廓面积"""
    img = _make_binary_contour_img()
    contours, _ = cv2.findContours(img, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
    for cnt in contours:
        area = cv2.contourArea(cnt)
        assert area > 0
    ok("contourArea")

def test_arcLength():
    """cv2.arcLength - 轮廓周长"""
    img = _make_binary_contour_img()
    contours, _ = cv2.findContours(img, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
    peri = cv2.arcLength(contours[0], True)
    assert peri > 0
    ok("arcLength (perimeter={:.1f})".format(peri))

def test_boundingRect():
    """cv2.boundingRect - 外接矩形"""
    img = _make_binary_contour_img()
    contours, _ = cv2.findContours(img, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
    x, y, w, h = cv2.boundingRect(contours[0])
    assert w > 0 and h > 0
    ok("boundingRect (x={},y={},w={},h={})".format(x, y, w, h))

def test_approxPolyDP():
    """cv2.approxPolyDP - 多边形近似"""
    img = _make_binary_contour_img()
    contours, _ = cv2.findContours(img, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
    peri = cv2.arcLength(contours[0], True)
    approx = cv2.approxPolyDP(contours[0], 0.02 * peri, True)
    assert approx is not None
    ok("approxPolyDP")

def test_convexHull():
    """cv2.convexHull - 凸包"""
    img = _make_binary_contour_img()
    contours, _ = cv2.findContours(img, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
    hull = cv2.convexHull(contours[0])
    assert hull is not None
    ok("convexHull")

def test_minAreaRect():
    """cv2.minAreaRect - 最小外接旋转矩形"""
    img = _make_binary_contour_img()
    contours, _ = cv2.findContours(img, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
    center, size, angle = cv2.minAreaRect(contours[0])
    assert size[0] > 0 and size[1] > 0
    ok("minAreaRect")

def test_minEnclosingCircle():
    """cv2.minEnclosingCircle - 最小外接圆"""
    img = _make_binary_contour_img()
    contours, _ = cv2.findContours(img, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
    center, radius = cv2.minEnclosingCircle(contours[0])
    assert radius > 0
    ok("minEnclosingCircle (radius={:.1f})".format(radius))

def test_matchTemplate():
    """cv2.matchTemplate - 模板匹配"""
    img = np.zeros((60, 80, 1), dtype=np.uint8)
    cv2.rectangle(img, (15, 15), (50, 40), (255,), -1)
    templ = np.zeros((15, 15, 1), dtype=np.uint8)
    cv2.rectangle(templ, (3, 3), (12, 12), (255,), -1)
    result = cv2.matchTemplate(img, templ, cv2.TM_CCOEFF_NORMED)
    assert result is not None
    del result, img, templ
    gc.collect()
    ok("matchTemplate")

def test_moments():
    """cv2.moments - 图像矩"""
    img = make_test_img()
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
    m = cv2.moments(binary)
    assert 'm00' in m
    ok("moments (m00={:.1f})".format(m['m00']))

# =====================================================
# imgproc - 特征检测
# =====================================================

def test_HoughLines():
    """cv2.HoughLines - 霍夫直线检测"""
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    cv2.line(img, (10, 50), (90, 50), (255, 255, 255), 2)
    cv2.line(img, (50, 10), (50, 90), (255, 255, 255), 2)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLines(edges, 1, np.pi / 180, 80)
    assert lines is not None
    ok("HoughLines ({} lines)".format(lines.shape[0]))

def test_HoughLinesP():
    """cv2.HoughLinesP - 概率霍夫直线检测"""
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    cv2.line(img, (10, 50), (90, 50), (255, 255, 255), 2)
    cv2.line(img, (50, 10), (50, 90), (255, 255, 255), 2)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 50, minLineLength=30)
    assert lines is not None
    ok("HoughLinesP ({} lines)".format(lines.shape[0]))

def test_HoughCircles():
    """cv2.HoughCircles - 霍夫圆检测"""
    img = np.zeros((150, 200, 3), dtype=np.uint8)
    cv2.circle(img, (80, 75), 50, (255, 255, 255), 2)
    cv2.circle(img, (150, 75), 35, (255, 255, 255), 2)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    circles = cv2.HoughCircles(gray, 3, dp=1, minDist=40,
                                param1=100, param2=30, minRadius=20)
    assert circles is not None
    ok("HoughCircles ({} circles)".format(circles.shape[0]))

# =====================================================
# imgcodecs 模块
# =====================================================

def test_imread():
    """cv2.imread - 读取图像"""
    # 先写入一张图片
    img = make_test_img()
    cv2.imwrite("/data/_test_imread.png", img)
    loaded = cv2.imread("/data/_test_imread.png")
    assert loaded is not None
    ok("imread")

def test_imwrite():
    """cv2.imwrite - 保存图像"""
    img = make_test_img()
    result = cv2.imwrite("/data/_test_imwrite.png", img)
    assert result == True
    ok("imwrite")

# =====================================================
# highgui 模块
# =====================================================

def test_waitKey():
    """cv2.waitKey - 等待按键 (非阻塞)"""
    key = cv2.waitKey(1)  # 等待1ms
    assert key == -1  # 超时无按键返回-1
    ok("waitKey")

def test_waitKeyEx():
    """cv2.waitKeyEx - 增强等待按键"""
    key = cv2.waitKeyEx(1)
    assert key == -1
    ok("waitKeyEx")

# =====================================================
# 运行所有测试
# =====================================================

ALL_TESTS = [
    # core
    ("inRange", test_inRange),
    ("convertScaleAbs", test_convertScaleAbs),
    ("minMaxLoc", test_minMaxLoc),
    ("LUT", test_LUT),
    ("countNonZero", test_countNonZero),
    ("flip", test_flip),
    ("rotate", test_rotate),
    ("transpose", test_transpose),
    # imgproc - filtering
    ("Canny", test_Canny),
    ("GaussianBlur", test_GaussianBlur),
    ("blur", test_blur),
    ("medianBlur", test_medianBlur),
    ("bilateralFilter", test_bilateralFilter),
    ("boxFilter", test_boxFilter),
    ("filter2D", test_filter2D),
    ("Sobel", test_Sobel),
    ("Scharr", test_Scharr),
    ("Laplacian", test_Laplacian),
    ("erode", test_erode),
    ("dilate", test_dilate),
    ("morphologyEx", test_morphologyEx),
    ("getStructuringElement", test_getStructuringElement),
    # imgproc - threshold & color
    ("threshold", test_threshold),
    ("adaptiveThreshold", test_adaptiveThreshold),
    ("cvtColor", test_cvtColor),
    ("resize", test_resize),
    ("warpAffine", test_warpAffine),
    ("warpPerspective", test_warpPerspective),
    ("getRotationMatrix2D", test_getRotationMatrix2D),
    ("equalizeHist", test_equalizeHist),
    # imgproc - drawing
    ("line", test_line),
    ("rectangle", test_rectangle),
    ("circle", test_circle),
    ("ellipse", test_ellipse),
    ("putText", test_putText),
    ("arrowedLine", test_arrowedLine),
    ("drawMarker", test_drawMarker),
    ("fillPoly", test_fillPoly),
    # imgproc - structural analysis
    ("findContours", test_findContours),
    ("drawContours", test_drawContours),
    ("contourArea", test_contourArea),
    ("arcLength", test_arcLength),
    ("boundingRect", test_boundingRect),
    ("approxPolyDP", test_approxPolyDP),
    ("convexHull", test_convexHull),
    ("minAreaRect", test_minAreaRect),
    ("minEnclosingCircle", test_minEnclosingCircle),
    ("moments", test_moments),
    # imgproc - feature detection
    ("HoughLines", test_HoughLines),
    ("HoughLinesP", test_HoughLinesP),
    ("HoughCircles", test_HoughCircles),
    # imgcodecs
    ("imread", test_imread),
    ("imwrite", test_imwrite),
    # highgui
    ("waitKey", test_waitKey),
    ("waitKeyEx", test_waitKeyEx),
    # matchTemplate放在最后(大内存分配,避免影响其他测试)
    ("matchTemplate", test_matchTemplate),
]

def run_all():
    global PASS, FAIL
    PASS = 0
    FAIL = 0
    total = len(ALL_TESTS)
    gc.threshold(8192)  # 降低 GC 阈值, 8KB 触发自动回收
    print("=" * 50)
    print("cv2 全部方法测试 (共 {} 项)".format(total))
    print("=" * 50)
    for i, (name, func) in enumerate(ALL_TESTS):
        gc.collect()
        try:
            func()
        except Exception as e:
            err(name, str(e))
        gc.collect()
    print("-" * 50)
    print("Result: {} OK, {} FAIL, {} total".format(PASS, FAIL, total))
    print("=" * 50)
    print("-" * 50)
    print("结果: {} 通过, {} 失败, {} 总计".format(PASS, FAIL, PASS + FAIL))
    print("=" * 50)
    if FAIL:
        raise AssertionError("{} OpenCV tests failed".format(FAIL))

def run_failed():
    """仅运行之前失败的测试 (用于调试)"""
    global PASS, FAIL
    PASS = 0
    FAIL = 0
    total = len(ALL_TESTS)
    for i, (name, func) in enumerate(ALL_TESTS):
        try:
            func()
        except Exception as e:
            err(name, str(e))
        gc.collect()
    print("-" * 50)
    print("结果: {} 通过, {} 失败".format(PASS, FAIL))
    if FAIL:
        raise AssertionError("{} OpenCV tests failed".format(FAIL))

__all__ = ['run_all', 'run_failed', 'ALL_TESTS']

if __name__ == '__main__':
    run_all()
