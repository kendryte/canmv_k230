import time, os, urandom, sys

from media.display import *
from media.media import *
from libs.WBCRtspPusher import WBCRtspPusher
from libs.Network import connect_network, load_network_config

DISPLAY_WIDTH = ALIGN_UP(800, 16)
DISPLAY_HEIGHT = 480

NETWORK_CONFIG = load_network_config({
    "network_type": "wifi_sta",
    "wlan_device": "auto",
    "ssid": "TEST",
    "password": "12345678",
    "timeout": 20,
    "host": "192.168.1.100",
    "port": 8554,
    "path": "/live/test",
}, "/sdcard/examples/02-Media/network_config.json")
RTSP_SERVER_URL = "rtsp://%s:%d/%s" % (
    NETWORK_CONFIG["host"],
    int(NETWORK_CONFIG["port"]),
    NETWORK_CONFIG.get("path", "/live/test").strip("/"),
)


def display_test():
    # create image for drawing
    img = image.Image(DISPLAY_WIDTH, DISPLAY_HEIGHT, image.ARGB8888)
    display_inited = False
    pusher_started = False
    try:
        # use lcd as display output
        Display.init(Display.VIRT, width = DISPLAY_WIDTH, height = DISPLAY_HEIGHT, fps = 60,to_ide=False)
        display_inited = True
        # init wbc
        WBCRtspPusher.configure(rtsp_url=RTSP_SERVER_URL)
        # 启用wbc编码推流
        WBCRtspPusher.start()
        pusher_started = True
        print("Virtual WBC RTSP pusher started")

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
        raise
    finally:
        if pusher_started:
            WBCRtspPusher.stop()  # stop wbc pusher
        if display_inited:
            Display.deinit()
        os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
        time.sleep_ms(100)

if __name__ == "__main__":
    os.exitpoint(os.EXITPOINT_ENABLE)

    nic, network_ip = connect_network(
        NETWORK_CONFIG["network_type"],
        ssid=NETWORK_CONFIG.get("ssid"),
        password=NETWORK_CONFIG.get("password"),
        wlan_device=NETWORK_CONFIG.get("wlan_device", "auto"),
        timeout=NETWORK_CONFIG.get("timeout", 20),
        ip_config=NETWORK_CONFIG.get("ip_config"),
    )
    display_test()
