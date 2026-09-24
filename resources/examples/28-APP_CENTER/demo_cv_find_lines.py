# demo_cv_find_lines.py - Independent OpenCV line detection application

import time
import cv2
from ulab import numpy as np
from media.sensor import Sensor
from media.display import Display
from app_contract import Application


class OpenCVFindLinesApp(Application):
    name = "OpenCV 直线"
    model_path = ""
    required_files = []
    is_audio_only = False

    SENSOR_WIDTH = 1280
    SENSOR_HEIGHT = 960
    SENSOR_ID = 2
    SENSOR_FPS = 90
    FRAME_WIDTH = 320
    FRAME_HEIGHT = 240
    FRAME_FORMAT = Sensor.RGB888
    DISPLAY_LAYER = Display.LAYER_OSD0

    def __init__(self):
        Application.__init__(self)
        self.sensor = None
        self.frame = None
        self.display_x = 0
        self.display_y = 0

    def open(self):
        if self._opened or self.stop_req:
            return
        sensor = Sensor(id=self.SENSOR_ID,
                        width=self.SENSOR_WIDTH,
                        height=self.SENSOR_HEIGHT,
                        fps=self.SENSOR_FPS)
        self.sensor = sensor
        sensor.reset()
        sensor.set_framesize(width=self.FRAME_WIDTH,
                             height=self.FRAME_HEIGHT)
        sensor.set_pixformat(self.FRAME_FORMAT)
        sensor.run()
        time.sleep_ms(500)
        if self.stop_req:
            return
        self.display_x = self.display.x + \
            (self.display.width - self.FRAME_WIDTH) // 2
        self.display_y = self.display.y + \
            (self.display.height - self.FRAME_HEIGHT) // 2
        self.start()
        self._opened = True

    def run_once(self):
        self.frame = self.sensor.snapshot()
        frame_np = self.frame.to_numpy_ref()
        gray = cv2.cvtColor(frame_np, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 60, 150)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 60,
                                minLineLength=40, maxLineGap=15)
        count = 0
        if lines is not None:
            count = lines.shape[0]
            for i in range(count):
                x1, y1, x2, y2 = (lines[i, 0], lines[i, 1],
                                  lines[i, 2], lines[i, 3])
                cv2.line(frame_np, (int(x1), int(y1)),
                         (int(x2), int(y2)), (0, 255, 0), 2)
        self.frame.draw_string_advanced(
            8, 8, 16, "OpenCV Lines", color=(0, 255, 0))
        Display.show_image(self.frame, self.display_x, self.display_y,
                           self.DISPLAY_LAYER)
        return count

    def stop(self):
        Application.stop(self)
        sensor = self.sensor
        self.sensor = None
        self.frame = None
        # Disable the OSD layer before stopping the sensor: the layer still
        # points at the sensor snapshot buffer, so releasing the sensor first
        # would leave the display reading a freed buffer.
        try:
            Display.disable_layer(self.DISPLAY_LAYER)
        except Exception as e:
            print("OpenCVFindLinesApp: layer cleanup failed:", e)
        if sensor is not None:
            try:
                sensor.stop()
            except Exception as e:
                print("OpenCVFindLinesApp: sensor stop failed:", e)
