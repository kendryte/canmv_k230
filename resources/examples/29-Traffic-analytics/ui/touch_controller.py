import time
from machine import TOUCH
import config


class _Device:
    def __init__(self, tp, name):
        self.tp = tp
        self.name = name
        self.contact = False

    def read_press(self):
        points = self.tp.read(1)

        if not points or points[0].event == TOUCH.EVENT_UP:
            self.contact = False
            return None
        if self.contact:
            return None                  
        self.contact = True

        # returns the touch coordinate
        return (int(points[0].x), int(points[0].y))

    
class TouchInput:
    def __init__(self, display_size=None, index=config.TOUCH_INDEX):
        # LCD touch screen
        self.devices = []
        try:
            self.devices.append(_Device(TOUCH(index), "panel"))
        except Exception as err:
            print("[touch] panel init failed:", err)

        # IDE touch device
        if config.TOUCH_ALLOW_IDE and display_size is not None:
            try:
                ide = TOUCH(TOUCH.DEV_IDE, range_x=int(display_size[0]), range_y=int(display_size[1]))
                self.devices.append(_Device(ide, "ide"))
            except Exception as err:
                print("[touch] IDE touch unavailable:", err)
        self.pending = None
        self._last_ms = -config.TOUCH_DEBOUNCE_MS

    def poll(self):
        press = self.read_press()
        if press is not None:
            self.pending = press
        return press

    def take_press(self):
        press = self.pending
        self.pending = None
        return press

    def read_press(self):
        press = None
        for device in self.devices:
            found = device.read_press()
            if found is not None and press is None:
                press = found
        if press is None:
            return None

        now = time.ticks_ms()
        if time.ticks_diff(now, self._last_ms) < config.TOUCH_DEBOUNCE_MS:
            return None
        self._last_ms = now
        return press



class TouchController:
    def __init__(self, display_size):
        self._touch = TouchInput(display_size)
        self._w = display_size[0]
        self._h = display_size[1]

    def poll(self):
        self._touch.poll()

    def take_tap(self):
        press = self._touch.take_press()
        if press is None:
            return None
        x, y = press

        # Swap X and Y axes if required by the hardware.
        if config.TOUCH_SWAP_XY:
            x, y = y, x

        # Mirror the X axis if the touchscreen is reversed.
        if config.TOUCH_FLIP_X:
            x = self._w - 1 - x

        # Mirror the Y axis if the touchscreen is reversed.
        if config.TOUCH_FLIP_Y:
            y = self._h - 1 - y
        x = max(0, min(self._w - 1, x))
        y = max(0, min(self._h - 1, y))
        return (x, y)
