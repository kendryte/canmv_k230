# AI MJPEG web server example
#
# This example runs face detection, draws the detections over the camera image,
# and serves the composited display through an MJPEG stream. Connect the board
# and the viewing device to the same network, then open the URL printed on the
# serial console. Select the network type below.

import gc
import os
import socket
import sys
import time

import aidemo
import nncase_runtime as nn
import ulab.numpy as np

from libs.AI2D import Ai2d
from libs.AIBase import AIBase
from libs.PipeLine import PipeLine
from libs.Utils import *
from libs.Network import connect_network, load_network_config
from media.display import Display
from media.media import *
from media.mjpeg import MJPEGEncoder


NETWORK_CONFIG = load_network_config({
    "network_type": "wifi_sta",
    "wlan_device": "auto",
    "ssid": "TEST",
    "password": "12345678",
    "timeout": 20,
    "port": 8080,
}, "/sdcard/examples/02-Media/network_config.json")
SERVER_PORT = int(NETWORK_CONFIG["port"])
STREAM_FPS = 15
JPEG_QUALITY = 50
REQUEST_TIMEOUT_MS = 2000
MAX_REQUEST_BYTES = 4096
SEND_STALL_TIMEOUT_MS = 5000
SEND_CHUNK_BYTES = 16384

# A virtual display is used as the compositing surface. Display writeback then
# captures both the camera layer and the AI overlay for JPEG encoding.
DISPLAY_MODE = "virt"
DISPLAY_SIZE = [1280, 720]
RGB888P_SIZE = [1280, 720]

KMODEL_PATH = "/sdcard/examples/kmodel/face_detection_320.kmodel"
ANCHORS_PATH = "/sdcard/examples/utils/prior_data_320.bin"
MODEL_INPUT_SIZE = [320, 320]
ANCHOR_LENGTH = 4200
ANCHOR_DIMENSION = 4
CONFIDENCE_THRESHOLD = 0.5
NMS_THRESHOLD = 0.2

INDEX_HTML = b"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>CanMV AI Camera</title>
<style>
*{box-sizing:border-box}
html,body{width:100%;height:100%;margin:0;background:#0a0a0a;color:#f5f5f5;font-family:Arial,sans-serif}
body{display:grid;grid-template-rows:48px 1fr;overflow:hidden}
header{display:flex;align-items:center;justify-content:space-between;padding:0 16px;
background:#151515;border-bottom:1px solid #2b2b2b}
h1{margin:0;font-size:16px;font-weight:600;letter-spacing:0}
.status{display:flex;align-items:center;gap:7px;font-size:12px;color:#d7d7d7}
.dot{width:8px;height:8px;border-radius:50%;background:#22c55e}
main{min-width:0;min-height:0;display:flex;align-items:center;justify-content:center}
img{display:block;width:100%;height:100%;object-fit:contain}
</style>
</head>
<body>
<header><h1>CanMV Face Detection</h1><div class="status"><span class="dot"></span><span>Live</span></div></header>
<main><img id="stream" alt="Live face detection"></main>
<script>
const stream=document.getElementById("stream");
let retryTimer=null;
function connectStream(){
retryTimer=null;
stream.src="/stream?_="+Date.now();
}
stream.onerror=function(){
stream.removeAttribute("src");
if(retryTimer===null){retryTimer=setTimeout(connectStream,1000)}
};
connectStream();
</script>
</body>
</html>
"""


class FaceDetectionApp(AIBase):
    def __init__(self, kmodel_path, model_input_size, anchors,
                 confidence_threshold=0.5, nms_threshold=0.2,
                 rgb888p_size=[224, 224], display_size=[1920, 1080],
                 debug_mode=0):
        super().__init__(kmodel_path, model_input_size, rgb888p_size, debug_mode)
        self.model_input_size = model_input_size
        self.confidence_threshold = confidence_threshold
        self.nms_threshold = nms_threshold
        self.anchors = anchors
        self.rgb888p_size = [ALIGN_UP(rgb888p_size[0], 16), rgb888p_size[1]]
        self.display_size = [ALIGN_UP(display_size[0], 16), display_size[1]]
        self.debug_mode = debug_mode
        self.ai2d = Ai2d(debug_mode)
        self.ai2d.set_ai2d_dtype(
            nn.ai2d_format.NCHW_FMT,
            nn.ai2d_format.NCHW_FMT,
            np.uint8,
            np.uint8,
        )

    def config_preprocess(self, input_image_size=None):
        with ScopedTiming("set preprocess config", self.debug_mode > 0):
            ai2d_input_size = input_image_size if input_image_size else self.rgb888p_size
            top, bottom, left, right, _ = letterbox_pad_param(
                self.rgb888p_size, self.model_input_size
            )
            self.ai2d.pad(
                [0, 0, 0, 0, top, bottom, left, right],
                0,
                [104, 117, 123],
            )
            self.ai2d.resize(
                nn.interp_method.tf_bilinear,
                nn.interp_mode.half_pixel,
            )
            self.ai2d.build(
                [1, 3, ai2d_input_size[1], ai2d_input_size[0]],
                [1, 3, self.model_input_size[1], self.model_input_size[0]],
            )

    def postprocess(self, results):
        with ScopedTiming("postprocess", self.debug_mode > 0):
            post_result = aidemo.face_det_post_process(
                self.confidence_threshold,
                self.nms_threshold,
                self.model_input_size[1],
                self.anchors,
                self.rgb888p_size,
                results,
            )
            if len(post_result) == 0:
                return post_result
            return post_result[0]

    def draw_result(self, osd_img, detections):
        with ScopedTiming("display_draw", self.debug_mode > 0):
            osd_img.clear()
            if not detections:
                return

            for detection in detections:
                x, y, width, height = map(
                    lambda value: int(round(value, 0)), detection[:4]
                )
                x = x * self.display_size[0] // self.rgb888p_size[0]
                y = y * self.display_size[1] // self.rgb888p_size[1]
                width = width * self.display_size[0] // self.rgb888p_size[0]
                height = height * self.display_size[1] // self.rgb888p_size[1]
                osd_img.draw_rectangle(
                    x,
                    y,
                    width,
                    height,
                    color=(255, 255, 0, 255),
                    thickness=3,
                )


def capture_jpeg(pipeline, face_detector, encoder):
    ai_frame = pipeline.get_frame()
    detections = face_detector.run(ai_frame)
    face_detector.draw_result(pipeline.osd_img, detections)
    pipeline.show_image()

    display_frame = Display.writeback_dump(1000)
    if display_frame is None:
        raise RuntimeError("display writeback timeout")

    jpeg = encoder.encode(display_frame, timeout_ms=1000)
    del display_frame
    return jpeg


# RT-Smart caps a blocking socket's send timeout at 500 ms. Send incrementally
# in nonblocking mode so a large JPEG can wait for TCP backpressure safely.
def send_all(client, data):
    view = memoryview(data)
    offset = 0
    deadline = time.ticks_add(time.ticks_ms(), SEND_STALL_TIMEOUT_MS)

    while offset < len(view):
        try:
            end = min(offset + SEND_CHUNK_BYTES, len(view))
            sent = client.send(view[offset:end])
            if sent:
                offset += sent
                deadline = time.ticks_add(time.ticks_ms(), SEND_STALL_TIMEOUT_MS)
                continue
        except OSError as error:
            if error.errno not in (11, 110):
                raise

        if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
            raise OSError(110)
        os.exitpoint()
        time.sleep_ms(1)


def send_response(client, status, content_type, body):
    header = (
        "HTTP/1.1 %s\r\n"
        "Content-Type: %s\r\n"
        "Content-Length: %d\r\n"
        "Cache-Control: no-store\r\n"
        "Connection: close\r\n\r\n"
    ) % (status, content_type, len(body))
    send_all(client, header.encode())
    if body:
        send_all(client, body)


def read_path(client):
    request = bytearray()
    deadline = time.ticks_add(time.ticks_ms(), REQUEST_TIMEOUT_MS)

    client.setblocking(False)
    while len(request) < MAX_REQUEST_BYTES:
        chunk = client.recv(min(256, MAX_REQUEST_BYTES - len(request)))
        if chunk:
            request.extend(chunk)
            if request.find(b"\r\n\r\n") >= 0 or request.find(b"\n\n") >= 0:
                break
        elif time.ticks_diff(deadline, time.ticks_ms()) <= 0:
            raise OSError(110)
        else:
            os.exitpoint()
            time.sleep_ms(10)

    request_line = bytes(request).split(b"\r\n", 1)[0].split()
    if len(request_line) < 2:
        return "/"
    return request_line[1].decode().split("?", 1)[0]


def stream_mjpeg(client, pipeline, face_detector, encoder):
    send_all(
        client,
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: multipart/x-mixed-replace; boundary=frame\r\n"
        b"Cache-Control: no-store, no-cache, must-revalidate\r\n"
        b"Pragma: no-cache\r\n"
        b"Connection: close\r\n\r\n",
    )

    frame_interval = 1000 // STREAM_FPS
    frame_count = 0
    while True:
        started = time.ticks_ms()
        jpeg = capture_jpeg(pipeline, face_detector, encoder)
        part_header = (
            "--frame\r\n"
            "Content-Type: image/jpeg\r\n"
            "Content-Length: %d\r\n\r\n"
        ) % len(jpeg)
        send_all(client, part_header.encode())
        send_all(client, jpeg)
        send_all(client, b"\r\n")
        del jpeg

        frame_count += 1
        if frame_count % 10 == 0:
            gc.collect()

        delay = frame_interval - time.ticks_diff(time.ticks_ms(), started)
        if delay > 0:
            time.sleep_ms(delay)
        os.exitpoint()


def serve_client(client, pipeline, face_detector, encoder):
    path = read_path(client)

    if path == "/stream":
        stream_mjpeg(client, pipeline, face_detector, encoder)
    elif path == "/snapshot.jpg":
        jpeg = capture_jpeg(pipeline, face_detector, encoder)
        send_response(client, "200 OK", "image/jpeg", jpeg)
        del jpeg
    elif path == "/favicon.ico":
        send_response(client, "204 No Content", "text/plain", b"")
    else:
        send_response(client, "200 OK", "text/html; charset=utf-8", INDEX_HTML)


def main():
    netif = None
    pipeline = None
    face_detector = None
    encoder = None
    server = None
    client = None
    writeback_enabled = False

    try:
        netif, ip = connect_network(
            NETWORK_CONFIG["network_type"],
            ssid=NETWORK_CONFIG.get("ssid"),
            password=NETWORK_CONFIG.get("password"),
            wlan_device=NETWORK_CONFIG.get("wlan_device", "auto"),
            timeout=NETWORK_CONFIG.get("timeout", 20),
            ip_config=NETWORK_CONFIG.get("ip_config"),
        )

        anchors = np.fromfile(ANCHORS_PATH, dtype=np.float)
        anchors = anchors.reshape((ANCHOR_LENGTH, ANCHOR_DIMENSION))

        pipeline = PipeLine(
            rgb888p_size=RGB888P_SIZE,
            display_mode=DISPLAY_MODE,
            display_size=DISPLAY_SIZE,
        )
        pipeline.create(to_ide=False)

        face_detector = FaceDetectionApp(
            KMODEL_PATH,
            model_input_size=MODEL_INPUT_SIZE,
            anchors=anchors,
            confidence_threshold=CONFIDENCE_THRESHOLD,
            nms_threshold=NMS_THRESHOLD,
            rgb888p_size=RGB888P_SIZE,
            display_size=pipeline.get_display_size(),
            debug_mode=0,
        )
        face_detector.config_preprocess()

        encoder = MJPEGEncoder(quality=JPEG_QUALITY)
        if not Display.writeback(True):
            raise RuntimeError("start display writeback failed")
        writeback_enabled = True

        # Let automatic exposure and white balance settle before serving frames.
        for _ in range(10):
            pipeline.get_frame()

        first_jpeg = capture_jpeg(pipeline, face_detector, encoder)
        print("First AI JPEG size:", len(first_jpeg), "bytes")
        del first_jpeg
        gc.collect()

        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(socket.getaddrinfo("0.0.0.0", SERVER_PORT)[0][-1])
        server.listen(2)
        server.setblocking(False)

        print("Open http://%s:%d/ in a browser" % (ip, SERVER_PORT))

        while True:
            try:
                client, address = server.accept()
            except OSError as error:
                if error.errno != 11:
                    raise
                os.exitpoint()
                time.sleep_ms(20)
                continue

            print("Client:", address)
            try:
                serve_client(client, pipeline, face_detector, encoder)
            except OSError:
                # A stream ends when the browser closes or reloads the page.
                pass
            finally:
                client.close()
                client = None
                gc.collect()

    except KeyboardInterrupt:
        print("Stopped by user")
    except BaseException as error:
        import sys
        sys.print_exception(error)
        raise
    finally:
        if client is not None:
            client.close()
        if server is not None:
            server.close()
        if encoder is not None:
            encoder.close()
        if writeback_enabled and not Display.writeback(False):
            print("stop display writeback failed")
        if face_detector is not None:
            face_detector.deinit()
        if pipeline is not None:
            pipeline.destroy()

        # Keep the network object referenced until all sockets are closed.
        netif = None
        os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
        time.sleep_ms(100)


if __name__ == "__main__":
    os.exitpoint(os.EXITPOINT_ENABLE)
    main()
