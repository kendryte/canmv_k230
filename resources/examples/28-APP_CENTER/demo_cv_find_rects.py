# demo_cv_find_rects.py - Independent OpenCV rectangle detection application

import time
import cv2
from media.sensor import Sensor
from media.display import Display
from app_contract import Application


class OpenCVFindRectsApp(Application):
    name = "OpenCV 矩形"
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
        binary = cv2.adaptiveThreshold(
            blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 11, 2)
        contours, _ = cv2.findContours(
            binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        count = 0
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < 300:
                continue
            perimeter = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.03 * perimeter, True)
            if len(approx) != 4:
                continue
            cv2.drawContours(frame_np, [approx], -1, (0, 255, 0), 3)
            x, y, w, h = cv2.boundingRect(contour)
            cv2.rectangle(frame_np, (x, y), (x + w, y + h),
                          (0, 0, 255), 2)
            cv2.putText(frame_np, "%dx%d" % (w, h), (x, y - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                        (255, 255, 0), 1)
            count += 1
        self.frame.draw_string_advanced(
            8, 8, 16, "OpenCV Rects", color=(0, 255, 0))
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
            print("OpenCVFindRectsApp: layer cleanup failed:", e)
        if sensor is not None:
            try:
                sensor.stop()
            except Exception as e:
                print("OpenCVFindRectsApp: sensor stop failed:", e)
