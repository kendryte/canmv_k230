# touch.py - Touch screen input driver for LVGL
# Supports both physical touch (TOUCH 0) and IDE virtual touch concurrently
# via two independent LVGL indev objects.

import lvgl as lv

# machine.TOUCH event codes (see TOUCH docs): 2 = pressed, 3 = moved
_EVT_PRESSED = 2
_EVT_MOVED   = 3


class TouchScreen:
    def __init__(self):
        # ---- physical (hardware) touch ----
        self.x = 0
        self.y = 0
        self.state = lv.INDEV_STATE.RELEASED
        self._point = lv.point_t({"x": 0, "y": 0})
        self._err_logged = False
        self.indev_drv = lv.indev_create()
        self.indev_drv.set_type(lv.INDEV_TYPE.POINTER)
        self.indev_drv.set_read_cb(self._read_cb)
        try:
            from machine import TOUCH
            import config
            self.touch = TOUCH(0, range_x=config.DISPLAY_WIDTH,
                               range_y=config.DISPLAY_HEIGHT)
        except Exception as e:
            print("TouchScreen: no touch device:", e)
            self.touch = None

        # ---- IDE virtual touch ----
        self.vx = 0
        self.vy = 0
        self.vstate = lv.INDEV_STATE.RELEASED
        self._vpoint = lv.point_t({"x": 0, "y": 0})
        self._verr_logged = False
        self.vtouch = None
        self.vtouch_indev = None
        self._init_virtual_touch()

    def _init_virtual_touch(self):
        try:
            from machine import TOUCH
            import config
            self.vtouch = TOUCH(TOUCH.DEV_IDE,
                                range_x=config.DISPLAY_WIDTH,
                                range_y=config.DISPLAY_HEIGHT)
            self.vtouch_indev = lv.indev_create()
            self.vtouch_indev.set_type(lv.INDEV_TYPE.POINTER)
            self.vtouch_indev.set_read_cb(self._vtouch_read_cb)
            print("TouchScreen: IDE virtual touch enabled")
        except Exception as e:
            print("TouchScreen: virtual touch unavailable:", e)
            self.vtouch = None
            self.vtouch_indev = None

    def _read_cb(self, driver, data):
        if self.touch is None:
            data.state = lv.INDEV_STATE.RELEASED
            return
        try:
            tp = self.touch.read(1)
            if tp and len(tp) > 0:
                self.x = tp[0].x
                self.y = tp[0].y
                if tp[0].event in (_EVT_PRESSED, _EVT_MOVED):
                    self.state = lv.INDEV_STATE.PRESSED
                else:
                    self.state = lv.INDEV_STATE.RELEASED
            else:
                self.state = lv.INDEV_STATE.RELEASED
        except Exception as e:
            if not self._err_logged:
                self._err_logged = True
                print("TouchScreen read error:", e)
            self.state = lv.INDEV_STATE.RELEASED
        self._point.x = self.x
        self._point.y = self.y
        data.point = self._point
        data.state = self.state

    def _vtouch_read_cb(self, driver, data):
        if self.vtouch is None:
            data.state = lv.INDEV_STATE.RELEASED
            return
        try:
            pts = self.vtouch.read(1)
            if pts and len(pts) > 0:
                self.vx = pts[0].x
                self.vy = pts[0].y
                if pts[0].event in (_EVT_PRESSED, _EVT_MOVED):
                    self.vstate = lv.INDEV_STATE.PRESSED
                else:
                    self.vstate = lv.INDEV_STATE.RELEASED
            else:
                self.vstate = lv.INDEV_STATE.RELEASED
        except Exception as e:
            if not self._verr_logged:
                self._verr_logged = True
                print("TouchScreen vtouch read error:", e)
            self.vstate = lv.INDEV_STATE.RELEASED
        self._vpoint.x = self.vx
        self._vpoint.y = self.vy
        data.point = self._vpoint
        data.state = self.vstate

    def deinit(self):
        """Detach input callbacks before LVGL and TOUCH are destroyed."""
        for indev in (self.indev_drv, self.vtouch_indev):
            if indev is not None:
                try:
                    indev.delete()
                except Exception:
                    pass
        self.indev_drv = None
        self.vtouch_indev = None
        for dev in (self.touch, self.vtouch):
            if dev is not None:
                try:
                    dev.deinit()
                except Exception:
                    pass
        self.touch = None
        self.vtouch = None
