import socket
import time

from libs.Network import connect_network, load_network_config


CONFIG = load_network_config({
    "network_type": "wifi_sta",
    "wlan_device": "auto",
    "ssid": "TEST",
    "password": "12345678",
    "timeout": 20,
    "host": "192.168.1.110",
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


def receive_line(sock):
    # A blocking CanMV recv(256) can wait for all 256 bytes. The server's
    # greeting is a short line, so read only through its newline.
    data = bytearray()
    while not data.endswith(b"\n"):
        chunk = sock.recv(1)
        if not chunk:
            raise OSError("TCP server closed before completing its greeting")
        data.extend(chunk)
    return bytes(data)


def receive_exactly(sock, length):
    data = bytearray()
    while len(data) < length:
        chunk = sock.recv(min(256, length - len(data)))
        if not chunk:
            raise OSError("TCP server closed before completing its response")
        data.extend(chunk)
    return bytes(data)


def main():
    netif, _ = connect_network(
        CONFIG["network_type"],
        ssid=CONFIG.get("ssid"),
        password=CONFIG.get("password"),
        wlan_device=CONFIG["wlan_device"],
        timeout=CONFIG["timeout"],
        ip_config=CONFIG.get("ip_config"),
    )

    address = socket.getaddrinfo(CONFIG["host"], CONFIG["port"])[0][-1]
    print("TCP connect address:", address)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(CONFIG["timeout"])
        sock.connect(address)
        greeting = receive_line(sock)
        print("TCP greeting:", greeting)
        request = bytearray()
        for index in range(CONFIG["message_count"]):
            payload = "K230 tcp client message %d\n" % index
            encoded = payload.encode()
            send_all(sock, encoded)
            request.extend(encoded)
            print(payload, end="")
            time.sleep_ms(50)
        send_all(sock, b"end\n")
        request.extend(b"end\n")
        expected = b"recv: " + bytes(request)
        response = receive_exactly(sock, len(expected))
        if response != expected:
            raise OSError("invalid TCP server response")
        print("TCP response:", response)
        print("TCP client completed")
    finally:
        sock.close()
        netif = None


if __name__ == "__main__":
    main()
