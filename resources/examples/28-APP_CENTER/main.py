# main.py - APP Center entry point and main loop

import os, time, gc
import sys

# IDE execution starts in /sdcard; local application imports live here.
APP_DIR = "/sdcard/examples/28-APP_CENTER"
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
import lvgl as lv
from media.display import Display
from libs.DisplayConfig import get_display_type
import config
import lvgl_utils
import center
import i18n
import splash
from app_display import AppDisplay
from ui_layout import UILayout

# how long the error status stays visible before returning home
ERROR_SHOW_MS   = 1500
# demo stats (fps / det count) refresh interval
STATS_PERIOD_MS = 200
WIFI_PERIOD_MS  = 1000
IDLE_GC_PERIOD_MS = 2000


def _open_wifi_monitor():
    """Return the STA singleton when this firmware/board exposes WLAN."""
    try:
        import network
        wlan_type = getattr(network, "WLAN", None)
        return wlan_type(0) if wlan_type else None
    except Exception as e:
        print("APP Center Wi-Fi monitor unavailable:", e)
        return None


def _wifi_has_ip(wlan):
    if wlan is None:
        return False
    try:
        return wlan.isconnected() and wlan.ifconfig()[0] != "0.0.0.0"
    except Exception:
        return False


def _safe_cleanup(name, callback):
    try:
        callback()
    except Exception as e:
        print("%s cleanup failed: %s" % (name, e))


def _wait_demo_thread(timeout_ms=10000):
    """Ask the demo thread to stop and wait until it is really gone.

    Deinitializing LVGL / Display while an application thread still calls
    Display.show_image would crash.
    """
    config.demo_abort = True
    app = config.running_app
    if app is not None:
        try:
            app.request_stop()
        except Exception as e:
            print("application stop request failed:", e)
    deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
    while config.demo_thread is not None and \
            time.ticks_diff(deadline, time.ticks_ms()) > 0:
        time.sleep_ms(50)
    if config.demo_thread is not None:
        print("WARNING: demo thread did not stop within %d ms" % timeout_ms)
        return False
    return True


def main():
    display_ready = False
    lvgl_ready = False
    tp_dev = None
    app_home = None
    app_splash = None
    wifi_wlan = None
    safe_to_deinit_display = True
    stats_period_ms = STATS_PERIOD_MS

    last_gc = time.ticks_ms()
    last_stats = time.ticks_ms()
    last_wifi = time.ticks_ms()
    try:
        i18n.init()
        requested_w = config.DISPLAY_WIDTH
        requested_h = config.DISPLAY_HEIGHT
        display_type = get_display_type("auto") if config.DISPLAY_TYPE is None else config.DISPLAY_TYPE
        Display.init(display_type,
                     width=requested_w,
                     height=requested_h,
                     to_ide=True, osd_num=4)
        display_ready = True

        # Always lay out against the connector's actual resolution.  This also
        # handles board-default initialization when the requested size is 0x0.
        config.DISPLAY_WIDTH = Display.width()
        config.DISPLAY_HEIGHT = Display.height()
        config.ui_layout = UILayout(config.DISPLAY_WIDTH,
                                    config.DISPLAY_HEIGHT)

        # Applications render against the physical display surface. LVGL is
        # composed above them on OSD3; its top/bottom bars may intentionally
        # cover the corresponding edges of the application image.
        config.CAM_WIN_X = 0
        config.CAM_WIN_Y = 0
        config.CAM_WIN_W = config.DISPLAY_WIDTH
        config.CAM_WIN_H = config.DISPLAY_HEIGHT
        print("APP Center display: %dx%d, UI scale %d%%" % (
            config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT,
            config.ui_layout.scale * 100 // 1024))
        print("APP Center application surface: %dx%d @ (%d, %d)" % (
            config.CAM_WIN_W, config.CAM_WIN_H,
            config.CAM_WIN_X, config.CAM_WIN_Y))
        stats_period_ms = STATS_PERIOD_MS

        config.app_display = AppDisplay(
            0, 0, config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT,
            layer=Display.LAYER_OSD0)

        lvgl_utils.lvgl_init()
        lvgl_ready = True

        import touch
        tp_dev = touch.TouchScreen()

        wifi_wlan = _open_wifi_monitor()
        config.wifi_connected = _wifi_has_ip(wifi_wlan)
        app_splash = splash.SplashScreen()
        config.app_state = "splash"

        while not config.exit_flag:
            os.exitpoint()
            lv.task_handler()

            now = time.ticks_ms()
            if config.app_state == "splash" and app_splash:
                app_splash.update(now)
                if app_splash.done:
                    previous = app_splash
                    app_home = center.HomeScreen()
                    app_splash = None
                    _safe_cleanup("splash screen", previous.clean)
                    previous = None
                    config.app_state = "home"
                    gc.collect()

            if time.ticks_diff(now, last_wifi) >= WIFI_PERIOD_MS:
                connected = _wifi_has_ip(wifi_wlan)
                if connected != config.wifi_connected:
                    config.wifi_connected = connected
                    if app_home:
                        app_home.set_wifi_connected(connected)
                    if config.active_demo:
                        config.active_demo.set_wifi_connected(connected)
                last_wifi = now

            if config.app_state == "demo_running" and config.active_demo:
                request = config.demo_ui_request
                if request is not None:
                    config.demo_ui_request = None
                    config.active_demo.handle_ui_request(request)
                if config.demo_status_text:
                    status_text = config.demo_status_text
                    status_color = config.demo_status_color
                    config.demo_status_text = ""
                    config.active_demo.set_status(status_text, status_color)

            if config.app_state == "demo_running" and config.active_demo \
                    and time.ticks_diff(now, last_stats) >= stats_period_ms:
                config.active_demo.set_fps(config.demo_fps_val)
                config.active_demo.set_det_count(config.demo_det_cnt)
                if config.tts_status:
                    st = config.tts_status
                    config.tts_status = ""
                    color = config.THEME_GREEN
                    if st == "generating":
                        color = config.THEME_ORANGE
                    elif st == "playing":
                        color = config.THEME_ACCENT
                    elif st == "error":
                        color = config.THEME_RED
                    config.active_demo.set_status(i18n.text(st), color)
                last_stats = now

            time.sleep_ms(5)

            if config.app_state == "stopping" and config.demo_thread is None:
                if config.demo_error:
                    print("Demo failed:", config.demo_error)
                    if config.active_demo:
                        # brief visual feedback before going home
                        config.active_demo.set_status(i18n.text("error"),
                                                      config.THEME_RED)
                        end = time.ticks_add(time.ticks_ms(), ERROR_SHOW_MS)
                        while time.ticks_diff(end, time.ticks_ms()) > 0:
                            lv.task_handler()
                            time.sleep_ms(20)
                    config.demo_error = None
                config.app_state = "home"
                if config.active_demo:
                    config.active_demo.clean()
                    config.active_demo = None
                config.app_display.clear()
                lvgl_utils.clear_buffers()
                app_home.reload()

            now = time.ticks_ms()
            # The worker collects between frames while an application is active.
            if config.demo_thread is None and \
                    time.ticks_diff(now, last_gc) >= IDLE_GC_PERIOD_MS:
                gc.collect()
                last_gc = now

    except KeyboardInterrupt:
        pass
    except BaseException as e:
        import sys as _s
        _s.print_exception(e)
    finally:
        # stop a possibly running demo thread BEFORE tearing down
        # LVGL / Display
        safe_to_deinit_display = _wait_demo_thread()
        config.app_state = ""
        if safe_to_deinit_display:
            config.running_app = None
            # Run the overlay's own cleanup (app-UI hooks / fonts) instead of
            # only dropping the reference, mirroring the normal stop path.
            if config.active_demo:
                _safe_cleanup("overlay", config.active_demo.clean)
            config.active_demo = None
            if tp_dev:
                _safe_cleanup("touch", tp_dev.deinit)
            if app_home:
                _safe_cleanup("home screen", app_home.clean)
            if app_splash:
                _safe_cleanup("splash screen", app_splash.clean)
            if lvgl_ready:
                _safe_cleanup("LVGL", lvgl_utils.lvgl_deinit)
            config.app_display = None
            config.ui_layout = None
            if display_ready:
                _safe_cleanup("Display", Display.deinit)
        else:
            # A stuck application may still be inside Display.show_image().
            # Keeping LVGL/Display alive is safer than tearing shared buffers
            # out from under that thread.
            print("Shared display retained because application is still active")
        gc.collect()
        if safe_to_deinit_display:
            os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
            time.sleep_ms(100)


if __name__ == "__main__":
    main()
