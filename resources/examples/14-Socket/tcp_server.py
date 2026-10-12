import os
import socket
import time

from libs.Network import connect_network, load_network_config


CONFIG = load_network_config({
    "network_type": "wifi_sta",
    "wlan_device": "auto",
    "ssid": "TEST",
    "password": "12345678",
    "timeout": 20,
    "port": 8080,
    "message_count": 10,
})


def send_all(sock, data):
    offset = 0
    while offset < len(data):
        sent = sock.send(data[offset:])
        if not sent:
            raise OSError("TCP connection closed while sending")
        offset += sent


def accept_client(server):
    while True:
        try:
            return server.accept()
        except OSError as error:
            if getattr(error, "errno", error.args[0] if error.args else None) != 11:
                raise
        os.exitpoint()
        time.sleep_ms(10)


def receive_until_end(client):
    data = bytearray()
    # CanMV may return b"" from a nonblocking socket when no data is ready,
    # which is indistinguishable from a peer disconnect. Read one byte at a
    # time so blocking recv does not wait for a full multi-byte buffer.
    client.settimeout(CONFIG["timeout"])
    while data.find(b"end\n") < 0:
        chunk = client.recv(1)
        if not chunk:
            return bytes(data), False
        data.extend(chunk)
    return bytes(data), True


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
        server.bind(socket.getaddrinfo("0.0.0.0", CONFIG["port"])[0][-1])
        server.listen(5)
        server.setblocking(False)
        print("TCP server ready: %s:%d" % (ip, CONFIG["port"]))

        for index in range(CONFIG["message_count"]):
            client, client_address = accept_client(server)
            try:
                client.setblocking(True)
                send_all(client, b"Hello #%d from CanMV\n" % (index + 1))
                request, complete = receive_until_end(client)
                print("TCP request from", client_address, request)
                if complete:
                    client.setblocking(True)
                    send_all(client, b"recv: " + request)
                else:
                    print("TCP client closed before the end marker")
            finally:
                client.close()
        print("TCP server completed")
    finally:
        server.close()
        netif = None


if __name__ == "__main__":
    main()
