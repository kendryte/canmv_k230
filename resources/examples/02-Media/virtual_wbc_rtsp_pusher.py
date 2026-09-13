import time, os, urandom, sys

from media.display import *
from media.media import *
from libs.WBCRtspPusher import WBCRtspPusher
from libs.Network import connect_network

DISPLAY_WIDTH = ALIGN_UP(800, 16)
DISPLAY_HEIGHT = 480

# Select "default", "lan", "wifi_sta", or "wifi_ap".
NETWORK_TYPE = "wifi_sta"
WLAN_DEVICE = "auto"  # "auto", "usb", "sdio", or "spi"
NETWORK_TIMEOUT = 15
WIFI_SSID = "TEST"
WIFI_PASSWORD = "12345678"
RTSP_SERVER_URL = "rtsp://1.1.1.1:554/live"


def display_test():
    # create image for drawing
    img = image.Image(DISPLAY_WIDTH, DISPLAY_HEIGHT, image.ARGB8888)
    # use lcd as display output
    Display.init(Display.VIRT, width = DISPLAY_WIDTH, height = DISPLAY_HEIGHT, fps = 60,to_ide=False)
    # init wbc
    WBCRtspPusher.configure(rtsp_url=RTSP_SERVER_URL)
    # 启用wbc编码推流
    WBCRtspPusher.start()

    try:
        while True:
            img.clear()
            for i in range(10):
                x = (urandom.getrandbits(11) % img.width())
                y = (urandom.getrandbits(11) % img.height())
                r = (urandom.getrandbits(8))
                g = (urandom.getrandbits(8))
                b = (urandom.getrandbits(8))
                size = (urandom.getrandbits(30) % 64) + 32
                # If the first argument is a scaler then this method expects
                # to see x, y, and text. Otherwise, it expects a (x,y,text) tuple.
                # Character and string rotation can be done at 0, 90, 180, 270, and etc. degrees.
                img.draw_string_advanced(x,y,size, "Hello World!，你好世界！！！", color = (r, g, b),)

            # draw result to screen
            Display.show_image(img)

            time.sleep(1)
            os.exitpoint()
    except KeyboardInterrupt as e:
        print("user stop: ", e)
    except BaseException as e:
        import sys
        sys.print_exception(e)

    WBCRtspPusher.stop()  # stop wbc pusher
    # deinit display
    Display.deinit()
    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    time.sleep_ms(100)

if __name__ == "__main__":
    os.exitpoint(os.EXITPOINT_ENABLE)

    nic, network_ip = connect_network(
        NETWORK_TYPE,
        ssid=WIFI_SSID,
        password=WIFI_PASSWORD,
        wlan_device=WLAN_DEVICE,
        timeout=NETWORK_TIMEOUT,
    )
    display_test()
