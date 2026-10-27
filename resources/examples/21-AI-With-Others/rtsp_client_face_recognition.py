# RTSP 人脸检测
#
# 文件名是 rtsp_client_face_recognition.py，实际做的是检测，不是识别。
# 模型是 face_detection_320.kmodel，检测和画框与 rtsp_client_face_detect.py 相同。
# 差别只有屏幕：这里用 DISPLAY_MODE 选面板，并把窗口宽高传给 Display.init。
# rtsp_client_face_detect.py 写死 ST7701，init 不传宽高。
#
# 拉流、解码和显示都用 multimedia.RtspClient。
# bind_info 交给 Display.bind_layer，检测框画在 OSD 上。
# 构造时的 width/height 让 VDEC 把解码图缩到屏幕大小。get_frame 是这个尺寸的 RGB，
# letterbox 到 320 由检测自己完成。
# URL 支持 rtsp://user:pass@host:port/path，账号也可以用 username/password 传入。
#
# 依赖固件中的 multimedia.RtspClient。源码已经在 CanMV 里，烧录新固件后才能跑。

import os
import gc
import nncase_runtime as nn
import ulab.numpy as np
import aidemo
import image
from media.display import *
from multimedia import RtspClient
from media.media import ALIGN_UP
from libs.AIBase import AIBase
from libs.AI2D import Ai2d
from libs.Utils import *
from libs.Network import connect_network, load_network_config
from libs.DisplayConfig import get_display_type

# 占位地址。可用 network_config.json 中的 rtsp_url 覆盖。
RTSP_URL = "rtsp://user:pass@192.168.2.115:8554/auth"
# "lcd" 对应 ST7701。需要其它屏幕时改成 "hdmi" / "st7701" / "nt35516" 等。
DISPLAY_MODE = "lcd"
# 屏幕上的位置和大小，对应 bind_info 的 x, y, width, height。
# 宽高必须是正偶数，并且不能大于码流分辨率。
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

FACE_DET_KMODEL = "/sdcard/examples/kmodel/face_detection_320.kmodel"
ANCHORS_PATH = "/sdcard/examples/utils/prior_data_320.bin"
FACE_DET_INPUT_SIZE = [320, 320]
CONFIDENCE_THRESHOLD = 0.5
NMS_THRESHOLD = 0.2
ANCHOR_LEN = 4200
DET_DIM = 4


class FaceDetApp(AIBase):
    def __init__(self, kmodel_path, model_input_size, anchors,
                 confidence_threshold=0.5, nms_threshold=0.2,
                 rgb888p_size=[1920, 1080]):
        super().__init__(kmodel_path, model_input_size, rgb888p_size, 0)
        self.confidence_threshold = confidence_threshold
        self.nms_threshold = nms_threshold
        self.anchors = anchors
        self.rgb888p_size = [ALIGN_UP(rgb888p_size[0], 16), rgb888p_size[1]]
        self.ai2d = Ai2d(0)
        self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT, nn.ai2d_format.NCHW_FMT,
                                 np.uint8, np.uint8)

    def config_preprocess(self, input_image_size=None):
        ai2d_input_size = input_image_size if input_image_size else self.rgb888p_size
        top, bottom, left, right, _ = letterbox_pad_param(self.rgb888p_size, self.model_input_size)
        self.ai2d.pad([0, 0, 0, 0, top, bottom, left, right], 0, [104, 117, 123])
        self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
        self.ai2d.build([1, 3, ai2d_input_size[1], ai2d_input_size[0]],
                        [1, 3, self.model_input_size[1], self.model_input_size[0]])

    def postprocess(self, results):
        res = aidemo.face_det_post_process(
            self.confidence_threshold, self.nms_threshold,
            self.model_input_size[0], self.anchors, self.rgb888p_size, results)
        if len(res) == 0:
            return res, res
        return res[0], res[1]


def draw_detections(img, dets, src_size, display_size):
    if not dets:
        return
    for det in dets:
        x1, y1, w, h = det[:4]
        x1 = int(round(x1)) * display_size[0] // src_size[0]
        y1 = int(round(y1)) * display_size[1] // src_size[1]
        w = int(round(w)) * display_size[0] // src_size[0]
        h = int(round(h)) * display_size[1] // src_size[1]
        if w <= 0 or h <= 0:
            continue
        img.draw_rectangle(x1, y1, w, h, color=(255, 0, 0, 255), thickness=4)


def _check(ret, what):
    if ret != 0:
        raise OSError("%s failed: %s" % (what, ret))


def run():
    os.exitpoint(os.EXITPOINT_ENABLE)
    client = None
    face_det = None
    osd = None
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
        if video_w == 0 or video_h == 0:
            raise OSError("rtsp video size unknown")
        print("video: %dx%d, output: %dx%d" % (video_w, video_h, DISPLAY_W, DISPLAY_H))

        Display.bind_layer(**client.bind_info(
            x=DISPLAY_X, y=DISPLAY_Y, width=DISPLAY_W, height=DISPLAY_H),
            layer=Display.LAYER_VIDEO1)
        Display.init(get_display_type(DISPLAY_MODE), width=DISPLAY_W, height=DISPLAY_H,
                     to_ide=True, osd_num=1)
        display_inited = True
        osd = image.Image(DISPLAY_W, DISPLAY_H, image.ARGB8888)

        anchors = np.fromfile(ANCHORS_PATH, dtype=np.float)
        anchors = anchors.reshape((ANCHOR_LEN, DET_DIM))
        face_det = FaceDetApp(
            FACE_DET_KMODEL, FACE_DET_INPUT_SIZE, anchors,
            CONFIDENCE_THRESHOLD, NMS_THRESHOLD,
            rgb888p_size=[DISPLAY_W, DISPLAY_H])
        face_det.config_preprocess()
        print("model ready")

        _check(client.start(), "rtsp start")
        started = True
        print("rtsp play:", RTSP_URL)

        processed_frames = 0
        while True:
            os.exitpoint()
            frame = client.get_frame(timeout_ms=100)
            if frame is None:
                continue
            img_np = frame.to_numpy_ref()
            shape = img_np.shape
            nchw = img_np.reshape((1, shape[0], shape[1], shape[2]))
            dets, _landms = face_det.run(nchw)
            osd.clear()
            draw_detections(osd, dets, (DISPLAY_W, DISPLAY_H), (DISPLAY_W, DISPLAY_H))
            Display.show_image(osd, x=DISPLAY_X, y=DISPLAY_Y, layer=Display.LAYER_OSD0)
            processed_frames += 1
            if processed_frames == 3:
                print("RTSP face detection ready: 3 frames processed")
            gc.collect()
    except KeyboardInterrupt as exc:
        print("user stop:", exc)
    except OSError as exc:
        print("rtsp failed:", exc)
    finally:
        if client is not None and started:
            try:
                client.stop()
            except Exception as exc:
                print("rtsp stop:", exc)
        if display_inited:
            try:
                Display.disable_layer(Display.LAYER_VIDEO1)
            except Exception as exc:
                print("display unbind:", exc)
        if client is not None:
            try:
                client.deinit()
            except Exception as exc:
                print("rtsp deinit:", exc)
        if display_inited:
            try:
                Display.deinit()
            except Exception as exc:
                print("display deinit:", exc)
        if face_det is not None:
            try:
                face_det.deinit()
            except Exception as exc:
                print("face deinit:", exc)
        print("release end")


if __name__ == "__main__":
    run()
