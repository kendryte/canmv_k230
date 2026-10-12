import socket

from libs.Network import connect_network, load_network_config


CONFIG = load_network_config({
    "network_type": "wifi_sta",
    "wlan_device": "auto",
    "ssid": "TEST",
    "password": "12345678",
    "timeout": 20,
    "host": "www.baidu.com",
    "port": 80,
    "path": "/index.html",
})


def read_response(read):
    # Read headers a byte at a time: CanMV blocking socket reads may wait
    # for the entire requested buffer, even when a shorter reply is ready.
    response = bytearray()
    while not response.endswith(b"\r\n\r\n"):
        chunk = read(1)
        if not chunk:
            raise OSError("HTTP connection closed before completing the headers")
        response.extend(chunk)
        if len(response) > 16384:
            raise ValueError("HTTP response headers are too large")

    content_lengths = []
    transfer_encodings = []
    for line in bytes(response).split(b"\r\n")[1:]:
        if b":" in line:
            name, value = line.split(b":", 1)
            name = name.strip().lower()
            if name == b"content-length":
                for item in value.split(b","):
                    try:
                        length = int(item.strip())
                    except ValueError:
                        raise ValueError("invalid HTTP Content-Length")
                    if length < 0:
                        raise ValueError("invalid HTTP Content-Length")
                    content_lengths.append(length)
            elif name == b"transfer-encoding":
                transfer_encodings.extend(
                    item.strip().lower() for item in value.split(b",")
                )

    if len(set(content_lengths)) > 1:
        raise ValueError("conflicting HTTP Content-Length headers")
    unsupported_encodings = [
        item for item in transfer_encodings if item and item != b"identity"
    ]
    if unsupported_encodings:
        raise ValueError("unsupported HTTP Transfer-Encoding")
    content_length = content_lengths[0] if content_lengths else None

    if content_length is None:
        # HTTP/1.0 may frame the body by closing the connection instead.
        while True:
            chunk = read(1)
            if not chunk:
                break
            response.extend(chunk)
    else:
        # Stop at the declared body length, without an extra read after the
        # peer closes or a wait for a larger receive buffer to fill.
        remaining = content_length
        while remaining:
            chunk = read(min(remaining, 1024))
            if not chunk:
                raise OSError("HTTP connection closed before completing the body")
            response.extend(chunk)
            remaining -= len(chunk)
    return bytes(response)


def send_all(write, data):
    offset = 0
    while offset < len(data):
        sent = write(data[offset:])
        if not sent:
            raise OSError("HTTP connection closed while sending")
        offset += sent


def request(use_stream):
    address = socket.getaddrinfo(CONFIG["host"], CONFIG["port"])[0][-1]
    request_data = (
        "GET %s HTTP/1.0\r\nHost: %s\r\nConnection: close\r\n\r\n" %
        (CONFIG["path"], CONFIG["host"])
    ).encode()

    sock = socket.socket()
    try:
        sock.settimeout(CONFIG["timeout"])
        sock.connect(address)
        if use_stream:
            stream = sock.makefile("rwb", 0)
            send_all(stream.write, request_data)
            response = read_response(stream.read)
        else:
            send_all(sock.send, request_data)
            response = read_response(sock.recv)

        if not response.startswith(b"HTTP/"):
            raise RuntimeError("invalid HTTP response")
        print(response)
    finally:
        sock.close()


def main():
    netif, _ = connect_network(
        CONFIG["network_type"],
        ssid=CONFIG.get("ssid"),
        password=CONFIG.get("password"),
        wlan_device=CONFIG["wlan_device"],
        timeout=CONFIG["timeout"],
        ip_config=CONFIG.get("ip_config"),
    )
    try:
        request(use_stream=True)
        request(use_stream=False)
        print("HTTP client completed")
    finally:
        netif = None


if __name__ == "__main__":
    main()
