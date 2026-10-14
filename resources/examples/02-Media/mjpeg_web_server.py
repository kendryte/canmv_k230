# MJPEG web server example
#
# Connect the board and the viewing device to the same network, then open the
# URL printed on the serial console. Select the network type below.

import gc
import os
import socket
import sys
import time

from media.mjpeg import MJPEGEncoder
from media.sensor import Sensor
from libs.Network import connect_network, load_network_config


NETWORK_CONFIG = load_network_config({
    "network_type": "wifi_sta",
    "wlan_device": "auto",
    "ssid": "TEST",
    "password": "12345678",
    "timeout": 20,
    "port": 8080,
}, "/sdcard/examples/02-Media/network_config.json")
SERVER_PORT = int(NETWORK_CONFIG["port"])
FRAME_WIDTH = 1920
FRAME_HEIGHT = 1080
FRAME_ALIGNMENT = 12
JPEG_QUALITY = 50
STREAM_FPS = 30
REQUEST_TIMEOUT_MS = 2000
MAX_REQUEST_BYTES = 4096
SEND_STALL_TIMEOUT_MS = 5000
SEND_CHUNK_BYTES = 16384

# Video-frame input is recommended for FHD/high-frame-rate streaming because it
# avoids copying each sensor frame through an image staging buffer. Set this to
# False to demonstrate image.Image input at lower resolutions.
USE_VIDEO_FRAME = True

INDEX_HTML = b"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>CanMV Camera</title>
<style>
*{box-sizing:border-box}
html,body{width:100%;height:100%;margin:0;background:#0a0a0a;color:#f5f5f5;font-family:Arial,sans-serif}
body{display:grid;grid-template-rows:48px 1fr;overflow:hidden}
header{display:flex;align-items:center;justify-content:space-between;padding:0 16px;
background:#151515;border-bottom:1px solid #2b2b2b}
h1{margin:0;font-size:16px;font-weight:600;letter-spacing:0}
.status{display:flex;align-items:center;gap:7px;font-size:12px;color:#d7d7d7}
.dot{width:8px;height:8px;border-radius:50%;background:#ef4444}
main{min-width:0;min-height:0;display:flex;align-items:center;justify-content:center}
img{display:block;width:100%;height:100%;object-fit:contain}
</style>
</head>
<body>
<header><h1>CanMV Camera</h1><div class="status"><span class="dot"></span><span>Live</span></div></header>
<main><img id="stream" alt="Live camera"></main>
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


def capture_jpeg(sensor, encoder):
    frame = sensor.snapshot(dump_frame=USE_VIDEO_FRAME)
    jpeg = encoder.encode(frame, timeout_ms=1000)
    del frame
    return jpeg


# RT-Smart caps a blocking socket's send timeout at 500 ms. Send incrementally
# in nonblocking mode so a large FHD JPEG can wait for TCP backpressure safely.
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

    # CanMV's blocking recv waits for the requested byte count. Read in
    # nonblocking mode until all headers arrive. Leaving unread headers when
    # closing a socket can make the TCP stack send a reset and lose the reply.
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


def stream_mjpeg(client, sensor, encoder):
    send_all(
        client,
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: multipart/x-mixed-replace; boundary=frame\r\n"
        b"Cache-Control: no-store, no-cache, must-revalidate\r\n"
        b"Pragma: no-cache\r\n"
        b"Connection: close\r\n\r\n"
    )

    frame_interval = 1000 // STREAM_FPS
    frame_count = 0
    while True:
        started = time.ticks_ms()
        jpeg = capture_jpeg(sensor, encoder)
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


def serve_client(client, sensor, encoder):
    path = read_path(client)

    if path == "/stream":
        stream_mjpeg(client, sensor, encoder)
    elif path == "/snapshot.jpg":
        jpeg = capture_jpeg(sensor, encoder)
        send_response(client, "200 OK", "image/jpeg", jpeg)
        del jpeg
    elif path == "/favicon.ico":
        send_response(client, "204 No Content", "text/plain", b"")
    else:
        send_response(client, "200 OK", "text/html; charset=utf-8", INDEX_HTML)


def main():
    netif = None
    sensor = None
    encoder = None
    server = None
    client = None

    try:
        netif, ip = connect_network(
            NETWORK_CONFIG["network_type"],
            ssid=NETWORK_CONFIG.get("ssid"),
            password=NETWORK_CONFIG.get("password"),
            wlan_device=NETWORK_CONFIG.get("wlan_device", "auto"),
            timeout=NETWORK_CONFIG.get("timeout", 20),
            ip_config=NETWORK_CONFIG.get("ip_config"),
        )

        sensor = Sensor()
        sensor.reset()
        sensor.set_framesize(width=FRAME_WIDTH, height=FRAME_HEIGHT, alignment=FRAME_ALIGNMENT)
        sensor.set_pixformat(Sensor.YUV420SP)
        sensor.run()

        encoder = MJPEGEncoder(quality=JPEG_QUALITY)

        # Let automatic exposure and white balance settle before serving frames.
        for _ in range(10):
            sensor.snapshot()

        first_jpeg = capture_jpeg(sensor, encoder)
        print("First JPEG size:", len(first_jpeg), "bytes")
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
                serve_client(client, sensor, encoder)
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
        if sensor is not None:
            sensor.stop()

        # Keep the network object referenced until all sockets are closed.
        netif = None
        os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
        time.sleep_ms(100)


if __name__ == "__main__":
    os.exitpoint(os.EXITPOINT_ENABLE)
    main()
