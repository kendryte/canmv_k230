import gc
import os
import socket
import time

from libs.Network import (connect_network, get_devices, load_network_config,
                          network_info)


CONFIG = load_network_config({
    "network_type": "wifi_sta",
    "wlan_device": "auto",
    "ssid": "TEST",
    "password": "12345678",
    "timeout": 20,
    "port": 8081,
    "message_count": 1,
})

SERVER_PORT = CONFIG["port"]
REQUEST_TIMEOUT_MS = 2000
MAX_REQUEST_BYTES = 4096


def error_code(error):
    return getattr(error, "errno", error.args[0] if error.args else None)


def read_request(client):
    request = bytearray()
    deadline = time.ticks_add(time.ticks_ms(), REQUEST_TIMEOUT_MS)

    # CanMV's blocking recv waits for the requested byte count. Accumulate the
    # request in nonblocking mode until the complete HTTP header is available.
    # On this port b"" can also mean "no data yet", so only the deadline can
    # distinguish an idle client from one that has disconnected.
    client.setblocking(False)
    while len(request) < MAX_REQUEST_BYTES:
        try:
            chunk = client.recv(min(256, MAX_REQUEST_BYTES - len(request)))
        except OSError as error:
            if error_code(error) != 11:
                raise
            chunk = None
        if chunk:
            request.extend(chunk)
            if request.find(b"\r\n\r\n") >= 0 or request.find(b"\n\n") >= 0:
                return bytes(request)
        if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
            raise OSError(110)

        os.exitpoint()
        time.sleep_ms(10)

    raise ValueError("HTTP request header is too large")


def html_escape(value):
    return (str(value).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def build_status_page(netif, client_address, counter):
    info = network_info(netif)
    config = info["ifconfig"] or ("unavailable",) * 4
    system = os.uname()
    connected = "Online" if info["connected"] else "Offline"
    client = "%s:%s" % client_address
    devices = ", ".join(get_devices()) or "none"
    uptime = time.ticks_ms() // 1000

    return ("""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CanMV Device Status</title>
<style>
*{box-sizing:border-box}
:root{color-scheme:light;--ink:#18202a;--muted:#657080;--line:#d9dee5;--panel:#fff;--wash:#f3f5f7;--accent:#087f5b}
body{margin:0;background:var(--wash);color:var(--ink);font:14px/1.5 Arial,sans-serif;letter-spacing:0}
header{background:#17212b;color:#fff;border-bottom:4px solid var(--accent)}
.bar,main,footer{width:min(920px,calc(100%% - 32px));margin:auto}
.bar{min-height:112px;display:flex;align-items:center;justify-content:space-between;gap:24px}
.product{margin:0 0 4px;color:#9daab7;font-size:13px;text-transform:uppercase}
h1{margin:0;font-size:30px;font-weight:650;letter-spacing:0}
.state{display:flex;align-items:center;gap:9px;font-weight:600;white-space:nowrap}
.dot{width:10px;height:10px;border-radius:50%%;background:#20c997;box-shadow:0 0 0 4px rgba(32,201,151,.16)}
main{padding:28px 0;display:grid;grid-template-columns:1fr 1fr;gap:18px}
section{background:var(--panel);border:1px solid var(--line);border-radius:6px;overflow:hidden}
section.wide{grid-column:1/-1}
h2{margin:0;padding:13px 16px;border-bottom:1px solid var(--line);font-size:15px;background:#f8f9fa;letter-spacing:0}
dl{margin:0}
.row{display:grid;grid-template-columns:150px minmax(0,1fr);gap:16px;padding:11px 16px;border-bottom:1px solid #edf0f3}
.row:last-child{border-bottom:0}
dt{color:var(--muted)}
dd{margin:0;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;overflow-wrap:anywhere}
footer{padding:0 0 28px;color:var(--muted);font-size:12px}
@media(max-width:680px){.bar{min-height:96px}.bar,main,footer{width:min(100%% - 24px,920px)}h1{font-size:24px}main{grid-template-columns:1fr;padding:18px 0}.row{grid-template-columns:1fr;gap:2px}section.wide{grid-column:auto}}
</style>
</head>
<body>
<header><div class="bar"><div><p class="product">CanMV K230</p><h1>Device Status</h1></div><div class="state"><span class="dot"></span>%s</div></div></header>
<main>
<section><h2>System</h2><dl>
<div class="row"><dt>Board</dt><dd>%s</dd></div>
<div class="row"><dt>Firmware</dt><dd>%s</dd></div>
<div class="row"><dt>MicroPython build</dt><dd>%s</dd></div>
<div class="row"><dt>Uptime</dt><dd>%d seconds</dd></div>
<div class="row"><dt>Free heap</dt><dd>%d bytes</dd></div>
</dl></section>
<section><h2>Request</h2><dl>
<div class="row"><dt>Request number</dt><dd>%d</dd></div>
<div class="row"><dt>Client</dt><dd>%s</dd></div>
<div class="row"><dt>Server port</dt><dd>%d</dd></div>
<div class="row"><dt>Registered devices</dt><dd>%s</dd></div>
</dl></section>
<section class="wide"><h2>Network</h2><dl>
<div class="row"><dt>Selected interface</dt><dd>%s</dd></div>
<div class="row"><dt>Default interface</dt><dd>%s</dd></div>
<div class="row"><dt>IPv4 address</dt><dd>%s</dd></div>
<div class="row"><dt>Subnet mask</dt><dd>%s</dd></div>
<div class="row"><dt>Gateway</dt><dd>%s</dd></div>
<div class="row"><dt>DNS server</dt><dd>%s</dd></div>
<div class="row"><dt>MAC address</dt><dd>%s</dd></div>
</dl></section>
</main>
<footer>Generated by /sdcard/examples/14-Socket/http_server.py</footer>
</body>
</html>
""" % (
        connected,
        html_escape(system.machine),
        html_escape(system.release),
        html_escape(system.version),
        uptime,
        gc.mem_free(),
        counter + 1,
        html_escape(client),
        SERVER_PORT,
        html_escape(devices),
        html_escape(info["device"]),
        html_escape(info["default"] or "automatic"),
        html_escape(config[0]),
        html_escape(config[1]),
        html_escape(config[2]),
        html_escape(config[3]),
        html_escape(info["mac"] or "unavailable"),
    )).encode()


def send_response(client, netif, client_address, counter):
    body = build_status_page(netif, client_address, counter)
    header = (
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: text/html; charset=utf-8\r\n"
        "Content-Length: %d\r\n"
        "Connection: close\r\n"
        "Cache-Control: no-store\r\n"
        "\r\n"
    ) % len(body)

    # The response is small. Blocking sendall() guarantees that it is queued
    # completely before close() releases the client socket.
    client.setblocking(True)
    client.sendall(header.encode() + body)


def accept_client(server):
    while True:
        try:
            return server.accept()
        except OSError as error:
            if error_code(error) != 11:
                raise
        os.exitpoint()
        time.sleep_ms(10)


def main():
    netif, ip = connect_network(
        CONFIG["network_type"],
        ssid=CONFIG.get("ssid"),
        password=CONFIG.get("password"),
        wlan_device=CONFIG["wlan_device"],
        timeout=CONFIG["timeout"],
        ip_config=CONFIG.get("ip_config"),
    )

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        address = socket.getaddrinfo("0.0.0.0", SERVER_PORT)[0][-1]
        server.bind(address)
        server.listen(5)
        print("Listening, connect your browser to http://%s:%d/" %
              (ip, SERVER_PORT))
        print("HTTP server ready: %s:%d" % (ip, SERVER_PORT))

        counter = 0
        while counter < CONFIG["message_count"]:
            client, client_address = accept_client(server)
            print("Client address:", client_address)
            try:
                request = read_request(client)
                print(request)
                send_response(client, netif, client_address, counter)
                counter += 1
            except (OSError, ValueError) as error:
                print("HTTP client error:", error)
            finally:
                client.close()

        print("HTTP server completed")
    finally:
        server.close()
        # Keep the selected interface referenced until all sockets are closed.
        netif = None


if __name__ == "__main__":
    main()
