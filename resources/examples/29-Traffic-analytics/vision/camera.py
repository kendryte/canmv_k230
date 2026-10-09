import image
from media.display import Display
from media.media import ALIGN_UP, MediaManager
from media.sensor import CAM_CHN_ID_0, CAM_CHN_ID_1, CAM_CHN_ID_2, Sensor

import config

DISPLAY_TYPES = {
    "hdmi": "LT9611",
    "lcd": "ST7701",
    "virt": "VIRT",
}


def _display_type(mode):
    return getattr(Display, DISPLAY_TYPES.get(mode, "ST7701"))


class CameraPipeline:
    def __init__(self):
        self.sensor = None
        self.osd_img = None
        self.display_size = None
        self.stage = None
        self._frame = None          

    def open_display(self):
        # Initialize LCD/HDMI display.
        display_type = _display_type(config.DISPLAY_MODE)
        if config.DISPLAY_SIZE:
            Display.init(display_type, width=config.DISPLAY_SIZE[0],
                         height=config.DISPLAY_SIZE[1], osd_num=1, to_ide=True)
            self.display_size = (config.DISPLAY_SIZE[0], config.DISPLAY_SIZE[1])
        else:
            Display.init(display_type, osd_num=1, to_ide=True)
            self.display_size = (Display.width(), Display.height())
        self.osd_img = image.Image(self.display_size[0], self.display_size[1], image.ARGB8888)
        return self.display_size

    def start(self, stage):
        # Start camera and configure display/AI channels
        self.stage = stage
        width, height = self.display_size
        ai_w = ALIGN_UP(config.RGB888P_SIZE[0], 16)
        ai_h = config.RGB888P_SIZE[1]

        if config.SENSOR_ID is None:
            self.sensor = Sensor(fps=config.SENSOR_FPS)
        else:
            self.sensor = Sensor(id=config.SENSOR_ID, fps=config.SENSOR_FPS)
        self.sensor.reset()

        # CH0: YUV video directly bound to display
        self.sensor.set_framesize(w=stage[2], h=stage[3], chn=CAM_CHN_ID_0)
        self.sensor.set_pixformat(Sensor.YUV420SP, chn=CAM_CHN_ID_0)

        # CH1: full-res RGB used for report/scene snapshots
        self.sensor.set_framesize(w=width, h=height, chn=CAM_CHN_ID_1)
        self.sensor.set_pixformat(Sensor.RGB888, chn=CAM_CHN_ID_1)

        # CH2: RGBP image used as AI/YOLO input
        self.sensor.set_framesize(w=ai_w, h=ai_h, chn=CAM_CHN_ID_2)
        self.sensor.set_pixformat(Sensor.RGBP888, chn=CAM_CHN_ID_2)

        # Bind camera CH0 directly to the display video layer
        bind_info = self.sensor.bind_info(x=stage[0], y=stage[1], chn=CAM_CHN_ID_0)
        Display.bind_layer(**bind_info, layer=Display.LAYER_VIDEO1)

        # Must come after Display.init()/bind_layer() and before sensor.run() -
        # this allocates the media buffer pool. Skipping it is why frames
        # never reached HDMI even though the sensor was running fine.
        MediaManager.init()

        self.sensor.run()
        print("[camera] display", self.display_size, "stage", stage)

    def get_ai_frame(self):
        # Capture the latest AI frame for YOLO.
        self._frame = self.sensor.snapshot(chn=CAM_CHN_ID_2)
        return self._frame.to_numpy_ref()

    def capture_scene(self):
        # Gets a normal RGB image from CH1
        return self.sensor.snapshot(chn=CAM_CHN_ID_1)

    def show(self):
        # Displays the OSD
        Display.show_image(self.osd_img, 0, 0, Display.LAYER_OSD3)

    def destroy(self):
        # Stop camera and release display resources.
        self._frame = None
        if self.sensor is not None:
            try:
                self.sensor.stop()
            except Exception as err:
                print("[camera] sensor stop:", err)
            self.sensor = None
        try:
            Display.deinit()
        except Exception as err:
            print("[camera] display deinit:", err)
        try:
            MediaManager.deinit()
        except Exception as err:
            print("[camera] media deinit:", err)