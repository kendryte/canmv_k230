# i18n.py - Lightweight language service for the APP Center UI shell

# Language selection is intentionally kept out of every frame-processing path.
# Applications query it only while creating UI or publishing a state change.

LANG_ZH = "zh_CN"
LANG_EN = "en_US"
LANGUAGE_FILE = "/sdcard/app_center_language.txt"

_language = LANG_ZH


_TEXT = {
    LANG_ZH: {
        "app_center": "K230 应用中心",
        "app_description": "应用说明",
        "language_name": "中文",
        "switch_language": "EN",
        "running": "运行中",
        "stopping": "正在停止",
        "loading": "正在加载...",
        "application_loading": "应用正在加载",
        "generating": "生成中...",
        "playing": "播放中...",
        "ready": "就绪",
        "done": "完成",
        "error": "出错",
        "ui_error": "界面出错",
        "database": "数据库",
        "query_data": "查询数据",
        "clear_data": "清空数据",
        "search": "搜索",
        "results": "结果: %d / %d",
        "no_data": "暂无数据",
        "database_busy": "数据库忙",
        "query_failed": "查询失败",
        "clear_confirm": "确认清空全部注册数据？",
        "cancel": "取消",
        "confirm_clear": "确认清空",
        "save": "保存",
        "name_title": "输入注册姓名",
        "name_placeholder": "Name",
        "track_start": "开始跟踪",
        "track_reselect": "重新选框",
        "track_pause": "暂停画面",
        "det_count": "检测: %d",
    },
    LANG_EN: {
        "app_center": "K230 Application Center",
        "app_description": "About this app",
        "language_name": "English",
        "switch_language": "中文",
        "running": "Running",
        "stopping": "Stopping",
        "loading": "Loading...",
        "application_loading": "Application is loading",
        "generating": "Generating...",
        "playing": "Playing...",
        "ready": "Ready",
        "done": "Done",
        "error": "Error",
        "ui_error": "UI Error",
        "database": "Database",
        "query_data": "Query",
        "clear_data": "Clear",
        "search": "Search",
        "results": "Results: %d / %d",
        "no_data": "No data",
        "database_busy": "Database is busy",
        "query_failed": "Query failed",
        "clear_confirm": "Clear all registered data?",
        "cancel": "Cancel",
        "confirm_clear": "Clear",
        "save": "Save",
        "name_title": "Enter registration name",
        "name_placeholder": "Name",
        "track_start": "Start tracking",
        "track_reselect": "Select again",
        "track_pause": "Pause frame",
        "det_count": "Det: %d",
    },
}


_APP_TITLES = {
    "wifi": ("Wi-Fi连接", "Wi-Fi"),
    "sys_info": ("系统信息", "System Info"),
    "face": ("人脸检测", "Face Detection"),
    "face_reg": ("人脸注册", "Face Enrollment"),
    "face_rec": ("人脸识别", "Face Recognition"),
    "person": ("行人检测", "Person Detection"),
    "tracker": ("单目标跟踪", "Object Tracking"),
    "self_learn": ("自学习分类", "Self-Learning"),
    "yolo": ("物体检测", "Object Detection"),
    "hand_det": ("手掌检测", "Hand Detection"),
    "pose": ("姿态估计", "Pose Estimation"),
    "body_seg": ("人体分割", "Body Segmentation"),
    "face_mesh": ("人脸网格", "Face Mesh"),
    "landmark": ("人脸关键点", "Face Landmarks"),
    "seg": ("YOLO 分割", "YOLO Segmentation"),
    "obb": ("YOLO OBB", "YOLO OBB"),
    "face_pose": ("人脸姿态", "Face Pose"),
    "face_parse": ("人脸解析", "Face Parsing"),
    "falldown": ("跌倒检测", "Fall Detection"),
    "hand_kp": ("手势识别", "Gesture Recognition"),
    "licence": ("车牌识别", "Plate Recognition"),
    "licence_pose": ("YOLO车牌检测", "YOLO Plate Detection"),
    "ocr": ("OCR 识别", "OCR"),
    "liveness": ("活体检测", "Face Liveness"),
    "kws": ("关键词唤醒", "Keyword Spotting"),
    "eye_gaze": ("视线估计", "Gaze Estimation"),
    "tts": ("语音合成", "Chinese TTS"),
    "dyn_gest": ("动态手势", "Dynamic Gesture"),
    "cv_edge": ("OpenCV 边缘", "OpenCV Edges"),
    "cv_lines": ("OpenCV 直线", "OpenCV Lines"),
    "cv_circles": ("OpenCV 圆形", "OpenCV Circles"),
    "cv_rects": ("OpenCV 矩形", "OpenCV Rectangles"),
    "omv_edge": ("OpenMV 边缘", "OpenMV Edges"),
    "omv_lines": ("OpenMV 直线", "OpenMV Lines"),
    "omv_circles": ("OpenMV 圆形", "OpenMV Circles"),
    "omv_rects": ("OpenMV 矩形", "OpenMV Rectangles"),
}

_APP_DESCRIPTIONS = {
    "wifi": (
        "扫描附近的 Wi-Fi 网络，并完成连接、断开和连接状态查看。",
        "Scans nearby Wi-Fi networks and manages connections and status."
    ),
    "sys_info": (
        "查看芯片 ID、温度、时间、内存和网络等设备运行信息。",
        "Shows device details such as chip ID, temperature, time, memory, and network."
    ),
    "face": (
        "实时检测画面中的人脸，并标出人脸位置和置信度。",
        "Detects faces in real time and displays their locations and confidence."
    ),
    "face_reg": (
        "采集人脸特征并绑定姓名，建立本地人脸识别数据库。",
        "Captures a face with a name and stores it in the local recognition database."
    ),
    "face_rec": (
        "将实时检测到的人脸与本地数据库比对，识别已注册人员。",
        "Matches detected faces against the local database to identify enrolled people."
    ),
    "person": (
        "实时检测画面中的行人，并显示检测框和置信度。",
        "Detects people in real time and displays bounding boxes and confidence."
    ),
    "tracker": (
        "选择一个目标后持续跟踪其位置和大小，适合单目标跟踪演示。",
        "Tracks the position and size of one selected target across frames."
    ),
    "self_learn": (
        "采集少量样本创建自定义类别，并对画面内容进行相似度分类。",
        "Learns custom classes from a few samples and classifies objects by similarity."
    ),
    "yolo": (
        "使用 YOLO 模型识别多类常见物体，并显示类别、位置和置信度。",
        "Uses YOLO to detect common object classes with labels, boxes, and confidence."
    ),
    "hand_det": (
        "检测画面中的手掌，为手势和手部关键点应用提供目标区域。",
        "Detects palms and provides hand regions for gesture and keypoint tasks."
    ),
    "pose": (
        "检测人体关键点并绘制骨架，用于展示人体姿态估计。",
        "Detects body keypoints and draws a skeleton for human pose estimation."
    ),
    "body_seg": (
        "逐像素分离人体与背景，实时生成彩色人体分割结果。",
        "Separates people from the background at pixel level in real time."
    ),
    "face_mesh": (
        "估计高密度三维人脸网格，展示脸部表面的细致结构。",
        "Estimates a dense 3D face mesh to visualize detailed facial geometry."
    ),
    "landmark": (
        "定位人脸上的关键特征点，可用于对齐和表情分析等任务。",
        "Locates facial landmarks for alignment and facial analysis tasks."
    ),
    "seg": (
        "同时检测物体并生成实例掩码，区分画面中的不同目标。",
        "Detects objects and produces an instance mask for each target."
    ),
    "obb": (
        "使用旋转检测框识别具有方向的目标，适合倾斜物体场景。",
        "Detects oriented objects with rotated bounding boxes."
    ),
    "face_pose": (
        "估计人脸的俯仰、偏航和翻滚角度，显示头部朝向。",
        "Estimates face pitch, yaw, and roll to show head orientation."
    ),
    "face_parse": (
        "对人脸区域进行语义分割，区分皮肤、五官和头发等部分。",
        "Segments a face into semantic regions such as skin, features, and hair."
    ),
    "falldown": (
        "结合人体检测与姿态信息判断人员是否发生跌倒。",
        "Uses person and pose information to detect possible falls."
    ),
    "hand_kp": (
        "定位手部关键点并识别静态手势类别。",
        "Locates hand keypoints and recognizes static hand gestures."
    ),
    "licence": (
        "检测车牌区域并识别车牌字符，输出完整车牌号码。",
        "Detects license plates and recognizes their characters."
    ),
    "licence_pose": (
        "使用 YOLO 定位车牌及其四个角点，为透视校正提供坐标。",
        "Locates plates and their four corners for perspective correction."
    ),
    "ocr": (
        "检测图片中的文字区域并识别文本内容。",
        "Detects text regions in an image and recognizes their content."
    ),
    "liveness": (
        "分析人脸是否来自真实人员，用于演示活体检测。",
        "Analyzes whether a detected face belongs to a live person."
    ),
    "kws": (
        "监听麦克风音频并识别预设关键词，实现离线语音唤醒。",
        "Listens for predefined keywords to demonstrate offline voice wake-up."
    ),
    "eye_gaze": (
        "根据眼部和人脸信息估计视线方向。",
        "Estimates the direction of a person's gaze from facial and eye features."
    ),
    "tts": (
        "将输入的中文文本转换为语音并通过音频设备播放。",
        "Converts Chinese text into speech and plays it through the audio device."
    ),
    "dyn_gest": (
        "连续分析手部动作，识别方向等动态手势。",
        "Analyzes hand motion over time to recognize dynamic gestures."
    ),
    "cv_edge": (
        "使用 OpenCV 提取图像边缘，展示经典边缘检测效果。",
        "Uses OpenCV to extract image edges with a classic vision pipeline."
    ),
    "cv_lines": (
        "使用 OpenCV 在实时画面中检测直线。",
        "Uses OpenCV to detect straight lines in the live image."
    ),
    "cv_circles": (
        "使用 OpenCV 在实时画面中检测圆形。",
        "Uses OpenCV to detect circles in the live image."
    ),
    "cv_rects": (
        "使用 OpenCV 在实时画面中检测矩形轮廓。",
        "Uses OpenCV to detect rectangular contours in the live image."
    ),
    "omv_edge": (
        "使用 OpenMV 图像接口提取边缘，展示轻量视觉处理。",
        "Uses OpenMV image APIs for lightweight edge extraction."
    ),
    "omv_lines": (
        "使用 OpenMV 图像接口检测实时画面中的直线。",
        "Uses OpenMV image APIs to detect lines in the live image."
    ),
    "omv_circles": (
        "使用 OpenMV 图像接口检测实时画面中的圆形。",
        "Uses OpenMV image APIs to detect circles in the live image."
    ),
    "omv_rects": (
        "使用 OpenMV 图像接口检测实时画面中的矩形。",
        "Uses OpenMV image APIs to detect rectangles in the live image."
    ),
}


def init():
    """Load the saved language. Invalid/missing data falls back to Chinese."""
    global _language
    try:
        with open(LANGUAGE_FILE, "r") as f:
            saved = f.read().strip()
        if saved in (LANG_ZH, LANG_EN):
            _language = saved
    except Exception:
        _language = LANG_ZH
    return _language


def language():
    return _language


def is_chinese():
    return _language == LANG_ZH


def text(key, *values):
    table = _TEXT.get(_language, _TEXT[LANG_ZH])
    value = table.get(key, _TEXT[LANG_ZH].get(key, key))
    if values:
        try:
            return value % values
        except Exception:
            return value
    return value


def app_title(code):
    pair = _APP_TITLES.get(code)
    if pair is None:
        return code
    return pair[0] if _language == LANG_ZH else pair[1]


def app_description(code):
    pair = _APP_DESCRIPTIONS.get(code)
    if pair is None:
        return app_title(code)
    return pair[0] if _language == LANG_ZH else pair[1]


def set_language(value, persist=True):
    global _language
    if value not in (LANG_ZH, LANG_EN):
        return False
    if value == _language:
        return True
    _language = value
    if persist:
        try:
            with open(LANGUAGE_FILE, "w") as f:
                f.write(value)
        except Exception as e:
            # A read-only SD card must not prevent the UI from switching for
            # the current session.
            print("APP Center language save failed:", e)
    return True


def toggle():
    target = LANG_EN if _language == LANG_ZH else LANG_ZH
    set_language(target)
    return target
