# runner.py - Demo thread runner, registry, and app control

import os, time, gc
import _thread
import config
import i18n
from overlay import DemoOverlay

# Keep modules isolated: a broken optional application must not prevent the
# runner or unrelated applications from loading.
DEMO_REGISTRY = {
    "face":       ("demo_face_detect", "FaceDetectionDemo"),
    "face_reg":   ("demo_face_registration", "FaceRegistrationDemo"),
    "face_rec":   ("demo_face_recognition", "FaceRecognitionDemo"),
    "person":     ("demo_person_detect", "PersonDetectionDemo"),
    "tracker":    ("demo_nanotracker", "NanoTrackerDemo"),
    "self_learn": ("demo_self_learning", "SelfLearningDemo"),
    "yolo":       ("demo_yolo_detect", "YOLODetectionDemo"),
    "hand_det":   ("demo_hand_detect", "HandDetectionDemo"),
    "pose":       ("demo_pose", "PoseEstimationDemo"),
    "body_seg":   ("demo_body_seg", "BodySegDemo"),
    "face_mesh":  ("demo_face_mesh", "FaceMeshDemo"),
    "landmark":   ("demo_face_landmark", "FaceLandmarkDemo"),
    "face_pose":  ("demo_face_pose", "FacePoseDemo"),
    "seg":        ("demo_yolo_seg", "YOLOSegDemo"),
    "obb":        ("demo_yolo_obb", "YOLOOBBDemo"),
    "face_parse": ("demo_face_parse", "FaceParseDemo"),
    "falldown":   ("demo_falldown", "FallDetectionDemo"),
    "hand_kp":    ("demo_hand_keypoint_class", "HandKeyPointClassDemo"),
    "licence":    ("demo_license_plate", "LicenceRecDemo"),
    "licence_pose": ("demo_yolo_license_plate",
                     "YoloLicenceDetectionDemo"),
    "ocr":        ("demo_ocr_rec", "OCRDetRecDemo"),
    "liveness":   ("demo_face_liveness", "FaceLivenessDemo"),
    "kws":        ("demo_keyword_spotting", "KeywordSpottingDemo"),
    "eye_gaze":   ("demo_eye_gaze", "EyeGazeDemo"),
    "tts":        ("demo_tts_zh", "TTSZHDemo"),
    "dyn_gest":   ("demo_dynamic_gesture", "DynamicGestureDemo"),
    "cv_edge":     ("demo_cv_edge", "OpenCVEdgeApp"),
    "cv_lines":    ("demo_cv_find_lines", "OpenCVFindLinesApp"),
    "cv_circles":  ("demo_cv_find_circles", "OpenCVFindCirclesApp"),
    "cv_rects":    ("demo_cv_find_rects", "OpenCVFindRectsApp"),
    "omv_edge":    ("demo_openmv_edge", "OpenMVEdgeApp"),
    "omv_lines":   ("demo_openmv_find_lines", "OpenMVFindLinesApp"),
    "omv_circles": ("demo_openmv_find_circles", "OpenMVFindCirclesApp"),
    "omv_rects":   ("demo_openmv_find_rects", "OpenMVFindRectsApp"),
    "sys_info":    ("demo_system_info", "SystemInfoDemo"),
    "wifi":        ("demo_wifi", "WiFiDemo"),
}


def _load_demo(demo_key):
    entry = DEMO_REGISTRY.get(demo_key)
    if entry is None:
        raise ValueError("unknown application: %s" % demo_key)
    module_name, class_name = entry
    module = __import__(module_name)
    return getattr(module, class_name)


def _missing_file(demo_cls):
    """Return the first missing required file, or None if all exist."""
    path = getattr(demo_cls, 'model_path', '')
    if path and not config.file_exists(path):
        return path
    for f in getattr(demo_cls, 'required_files', []):
        if not config.file_exists(f):
            return f
    return None


def _print_error(e):
    try:
        import sys as _s
        _s.print_exception(e)
    except Exception:
        print("Exception in demo thread:", e)


def _demo_thread_func(demo_key, demo_cls, session):
    app = None
    fps_count = 0
    fps_time  = time.ticks_ms()
    gc_time   = time.ticks_ms()
    config.demo_fps_val = 0.0
    config.demo_det_cnt = 0

    try:
        if config.demo_abort or config.exit_flag:
            return

        if config.app_display is None:
            raise RuntimeError("application display is not available")

        # The class owns creation and cleanup of Sensor/Media/KPU/audio/etc.
        # The runner only drives the generic application lifecycle.
        app = demo_cls.create(config.app_display)
        if config.demo_session != session:
            return
        config.running_app = app
        if config.demo_abort or config.exit_flag:
            app.request_stop()
            return
        app.open()

        if config.demo_abort or config.exit_flag:
            return

        # Model loading is not part of the processed-frame measurement.
        fps_time = time.ticks_ms()
        gc_time = fps_time
        while app.should_run() \
              and not config.exit_flag and not config.demo_abort:
            os.exitpoint()
            t0 = time.ticks_ms()

            frame_result = app.run_once()

            # Interactive applications may return None while previewing or
            # paused. Those idle loop iterations are not processed frames and
            # must not be reported as inference FPS.
            if frame_result is None:
                config.demo_fps_val = 0.0
                config.demo_det_cnt = 0
                fps_count = 0
                fps_time = time.ticks_ms()
            else:
                config.demo_det_cnt = frame_result
                fps_count += 1
                elapsed = time.ticks_diff(time.ticks_ms(), fps_time)
                if elapsed >= 1000:
                    config.demo_fps_val = fps_count * 1000.0 / elapsed
                    fps_count = 0
                    fps_time = time.ticks_ms()

            now = time.ticks_ms()
            if time.ticks_diff(now, gc_time) > 2000:
                gc.collect()
                gc_time = now

            t1 = time.ticks_diff(time.ticks_ms(), t0)
            if t1 < 5:
                time.sleep_ms(5 - t1)

    except Exception as e:
        _print_error(e)
        config.demo_error = "%s: %s" % (i18n.app_title(demo_key), e)
    finally:
        if app:
            try:
                app.close()
            except Exception as e:
                print("application close failed:", e)
            app = None
        if config.demo_session == session:
            config.running_app = None
            config.demo_abort = False
            config.demo_fps_val = 0.0
            config.demo_det_cnt = 0
            config.demo_ui_request = None
            config.demo_status_text = ""
            # If the thread dies on its own, ask the main loop to restore home.
            if config.app_state == "demo_running":
                config.app_state = "stopping"
        gc.collect()
        # Must be last: it permits UI destruction and the next application.
        if config.demo_thread == session:
            config.demo_thread = None


def start_demo(demo_key):
    if config.app_state == "demo_running" or config.demo_thread is not None:
        return
    try:
        demo_cls = _load_demo(demo_key)
    except Exception as e:
        _print_error(e)
        print("Failed to load application '%s'" % demo_key)
        return
    missing = _missing_file(demo_cls)
    if missing:
        print("Required file not found for '%s': %s" % (demo_key, missing))
        return

    if config.app_display is None:
        print("Application display is not initialized")
        return
    config.app_display.clear()

    def on_stop():
        if config.app_state != "demo_running":
            return
        config.demo_abort = True
        config.app_state = "stopping"
        app = config.running_app
        if app is not None:
            try:
                app.request_stop()
            except Exception as e:
                print("application stop request failed:", e)
        if config.active_demo:
            config.active_demo.set_status(i18n.text("stopping"),
                                          config.THEME_ORANGE)

    def on_phrase(text):
        if config.tts_text:
            return
        config.tts_text = text
        # The TTS models are loaded in the worker thread before run() consumes
        # the selected phrase.  Update the LVGL state here, in the button event
        # callback, so the user gets immediate feedback while loading proceeds.
        config.tts_status = "generating"
        if config.active_demo:
            config.active_demo.set_status(i18n.text("generating"),
                                          config.THEME_ORANGE)

    def on_action():
        app = config.running_app
        if app is None:
            if config.active_demo:
                config.active_demo.set_status(i18n.text("loading"),
                                              config.THEME_ORANGE)
            return
        callback = getattr(app, "request_action", None)
        if callback:
            callback()

    def on_name_submit(name):
        app = config.running_app
        if app is None:
            return
        callback = getattr(app, "submit_name", None)
        if callback:
            callback(name)

    def on_database_query():
        app = config.running_app
        if app is None:
            return i18n.text("application_loading")
        callback = getattr(app, "request_database_query", None)
        if callback:
            return callback()
        return False

    def on_database_clear():
        app = config.running_app
        if app is None:
            return i18n.text("application_loading")
        callback = getattr(app, "request_database_clear", None)
        if callback:
            return callback()
        return False

    def on_roi_submit(x, y, w, h):
        app = config.running_app
        if app is None:
            return
        callback = getattr(app, "submit_roi", None)
        if callback:
            callback(x, y, w, h)

    overlay = None
    try:
        config.demo_error = None
        config.demo_abort = False
        config.app_state = "demo_running"
        config.tts_text = ""
        config.tts_status = ""
        config.demo_ui_request = None
        config.demo_status_text = ""
        config.demo_status_color = config.THEME_GREEN
        config.demo_session += 1
        session = config.demo_session
        is_audio = getattr(demo_cls, 'is_audio_only', False)
        phrases = getattr(demo_cls, 'tts_phrases', None)
        action_label = getattr(demo_cls, 'ui_action_label', None)
        name_input = getattr(demo_cls, 'ui_name_input', False)
        name_title = getattr(demo_cls, 'ui_name_title', None)
        name_placeholder = getattr(demo_cls, 'ui_name_placeholder', None)
        roi_select = getattr(demo_cls, 'ui_roi_select', False)
        database = getattr(demo_cls, 'ui_database', False)
        database_title = getattr(demo_cls, 'ui_database_title', None)
        localized_ui = getattr(demo_cls, 'localized_ui', None)
        if localized_ui:
            try:
                ui_text = localized_ui()
                action_label = ui_text.get("action_label", action_label)
                name_title = ui_text.get("name_title", name_title)
                name_placeholder = ui_text.get(
                    "name_placeholder", name_placeholder)
                database_title = ui_text.get(
                    "database_title", database_title)
            except Exception as e:
                print("application UI translation failed:", e)
        app_ui_factory = getattr(demo_cls, 'create_app_ui', None)
        show_stats = getattr(demo_cls, 'ui_show_stats', True)
        overlay = DemoOverlay(i18n.app_title(demo_key), on_stop, on_stop,
                              is_audio_only=is_audio,
                              phrases=phrases,
                              on_phrase=on_phrase if phrases else None,
                              action_label=action_label,
                              on_action=on_action if action_label else None,
                              on_name_submit=on_name_submit
                              if name_input else None,
                              name_title=name_title,
                              name_placeholder=name_placeholder,
                              roi_select=roi_select,
                              on_roi=on_roi_submit if roi_select else None,
                              database=database,
                              database_title=database_title,
                              on_database_query=on_database_query
                              if database else None,
                              on_database_clear=on_database_clear
                              if database else None,
                              app_ui_factory=app_ui_factory,
                              show_stats=show_stats)
        config.active_demo = overlay
        # sentinel BEFORE the thread starts; cleared by the thread itself.
        # (assigning the return value of start_new_thread would race with
        # a fast-exiting thread that already set demo_thread = None)
        config.demo_thread = session
        _thread.start_new_thread(
            _demo_thread_func, (demo_key, demo_cls, session)
        )
    except Exception as e:
        _print_error(e)
        config.demo_thread = None
        config.demo_error = "failed to start '%s': %s" % (demo_key, e)
        if overlay:
            config.active_demo = overlay
        # reuse the main loop's stopping-cleanup path to get back home
        config.app_state = "stopping"
