# RTSP 显示
#
# 把画面送到屏幕，启动时检查三帧确认解码成功，不做检测。
# init 的 width/height 让 VDEC 把解码图缩到屏幕大小，bind_info 用同一个窗口。
#
# 依赖固件中的 multimedia.RtspClient。源码已经在 CanMV 里，烧录新固件后才能跑。

import time
from media.display import Display
from multimedia import RtspClient
from libs.Network import connect_network, load_network_config

# 占位地址。可用 network_config.json 中的 rtsp_url 覆盖。
RTSP_URL = "rtsp://user:pass@192.168.2.115:8554/auth"
DISPLAY_X = 0
DISPLAY_Y = 0
DISPLAY_W = 800
DISPLAY_H = 480

# 占位网络参数。可用 /sdcard/network_config.json 覆盖，不要把真实密码提交到仓库。
CONFIG = load_network_config({
    "network_type": "wifi_sta",
    "wlan_device": "auto",
    "ssid": "TEST",
    "password": "12345678",
    "timeout": 20,
})
RTSP_URL = CONFIG.get("rtsp_url", RTSP_URL)


def run():
    client = None
    started = False
    display_inited = False
    try:
        _, network_ip = connect_network(
            CONFIG["network_type"],
            ssid=CONFIG.get("ssid"),
            password=CONFIG.get("password"),
            wlan_device=CONFIG["wlan_device"],
            timeout=CONFIG["timeout"],
            ip_config=CONFIG.get("ip_config"),
        )
        print("network:", network_ip)

        client = RtspClient(RTSP_URL, cache_count=60, buffer_count=6,
                            width=DISPLAY_W, height=DISPLAY_H)
        video_w, video_h = client.video_size()
        print("video: %dx%d, output: %dx%d" % (video_w, video_h, DISPLAY_W, DISPLAY_H))

        Display.bind_layer(**client.bind_info(
            x=DISPLAY_X, y=DISPLAY_Y, width=DISPLAY_W, height=DISPLAY_H),
            layer=Display.LAYER_VIDEO1)
        Display.init(Display.ST7701, width=DISPLAY_W, height=DISPLAY_H, to_ide=False, osd_num=1)
        display_inited = True

        client.start()
        print("start", 0)
        started = True
        decoded_frames = 0
        deadline = time.time() + 15
        while decoded_frames < 3:
            client.check()
            if time.time() >= deadline:
                raise OSError("RTSP decoded frame timeout")
            frame = client.get_frame(timeout_ms=1000)
            if frame is not None:
                decoded_frames += 1
                del frame
        print("RTSP display ready: 3 frames decoded")
        while True:
            time.sleep(1)
            client.check()
    except OSError as exc:
        print("rtsp failed:", exc)
    finally:
        if client is not None and started:
            client.stop()
        if display_inited:
            Display.disable_layer(Display.LAYER_VIDEO1)
        if client is not None:
            client.deinit()
        if display_inited:
            Display.deinit()
        print("stopped")


if __name__ == "__main__":
    run()
