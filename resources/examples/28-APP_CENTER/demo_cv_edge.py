# demo_cv_edge.py - Independent OpenCV edge application

import time
import image
import cv2
from media.sensor import Sensor
from media.display import Display
from app_contract import Application


class OpenCVEdgeApp(Application):
    """A resource-independent app adapted from 25-Compare/opencv_edge.py."""

    name = "OpenCV 边缘"
    model_path = ""
    required_files = []
    is_audio_only = False

    INPUT_WIDTH = 1280
    INPUT_HEIGHT = 960
    OUTPUT_WIDTH = 320
    OUTPUT_HEIGHT = 240
    SENSOR_ID = 2
    SENSOR_FPS = 90
    DISPLAY_LAYER = Display.LAYER_OSD0

    def __init__(self):
        Application.__init__(self)
        self.sensor = None
        self.output_data = None
        self.output_img = None
        self.display_x = 0
        self.display_y = 0

    def open(self):
        if self._opened or self.stop_req:
            return
        sensor = Sensor(id=self.SENSOR_ID,
                        width=self.INPUT_WIDTH,
                        height=self.INPUT_HEIGHT,
                        fps=self.SENSOR_FPS)
        # Transfer ownership immediately so close() can recover from any later
        # reset/config/run failure.
        self.sensor = sensor
        sensor.reset()
        sensor.set_framesize(width=self.OUTPUT_WIDTH,
                             height=self.OUTPUT_HEIGHT)
        sensor.set_pixformat(Sensor.GRAYSCALE)
        sensor.run()
        time.sleep_ms(500)
        if self.stop_req:
            return
        # OSD0 belongs to the active application. Its 320x240 grayscale attributes
        # stay fixed for the whole run and it is disabled again in stop().
        self.display_x = self.display.x + \
            (self.display.width - self.OUTPUT_WIDTH) // 2
        self.display_y = self.display.y + \
            (self.display.height - self.OUTPUT_HEIGHT) // 2
        self.start()
        self._opened = True

    def run_once(self):
        frame = self.sensor.snapshot()
        frame_np = frame.to_numpy_ref()
        blurred = cv2.GaussianBlur(frame_np, (3, 3), 0)
        self.output_data = cv2.Canny(blurred, 50, 80)
        self.output_img = image.Image(
            self.OUTPUT_WIDTH, self.OUTPUT_HEIGHT,
            image.GRAYSCALE, alloc=image.ALLOC_REF,
            data=self.output_data)
        self.output_img.draw_string_advanced(
            8, 8, 16, "OpenCV Canny")

        Display.show_image(self.output_img, self.display_x, self.display_y,
                           self.DISPLAY_LAYER)
        return 0

    def stop(self):
        Application.stop(self)
        sensor = self.sensor
        self.sensor = None
        # Disable the OSD layer before stopping the sensor: the layer may still
        # reference sensor-backed buffers, so releasing the sensor first would
        # leave the display reading a freed buffer.
        try:
            Display.disable_layer(self.DISPLAY_LAYER)
        except Exception as e:
            print("OpenCVEdgeApp: display layer cleanup failed:", e)
        if sensor is not None:
            try:
                sensor.stop()
            except Exception as e:
                print("OpenCVEdgeApp: sensor stop failed:", e)

    def deinit(self):
        self.output_img = None
        self.output_data = None
