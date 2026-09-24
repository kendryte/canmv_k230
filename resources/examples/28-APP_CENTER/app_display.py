# app_display.py - Shared Display facade exposed to independent applications

import image
from media.display import Display


class AppDisplay:
    """The only hardware service owned by the application center.

    LVGL uses the topmost OSD3. The active application uses OSD0 as its default
    application plane; OSD1 and OSD2 remain free for applications that need
    extra planes (for example future multi-camera applications). AI YUV camera
    streams are independently bound to a VIDEO layer below the OSD planes.
    """

    def __init__(self, x, y, width, height, layer=Display.LAYER_OSD0):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.layer = layer

    def create_canvas(self, pixel_format=image.ARGB8888):
        return image.Image(self.width, self.height, pixel_format)

    def show(self, img, x=None, y=None, layer=None):
        Display.show_image(img,
                           self.x if x is None else x,
                           self.y if y is None else y,
                           self.layer if layer is None else layer)

    def clear(self):
        # Disable instead of painting an ARGB frame. The next application can
        # configure OSD0 with its native RGB/ARGB format without a temporary
        # full-screen allocation or conversion.
        try:
            Display.disable_layer(self.layer)
        except Exception as e:
            print("AppDisplay.clear failed:", e)
