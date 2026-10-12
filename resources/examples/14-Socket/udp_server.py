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


def receive_datagram(sock):
    while True:
        try:
            data, address = sock.recvfrom(800)
            # CanMV may report no pending datagram as (b'', ('0.0.0.0', 0))
            # instead of EAGAIN. A real empty datagram still has a peer port.
            if address[1] != 0:
                return data, address
        except OSError as error:
            if getattr(error, "errno", error.args[0] if error.args else None) != 11:
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

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(socket.getaddrinfo("0.0.0.0", CONFIG["port"])[0][-1])
        sock.setblocking(False)
        print("UDP server ready: %s:%d" % (ip, CONFIG["port"]))

        for index in range(CONFIG["message_count"]):
            data, address = receive_datagram(sock)
            print("UDP request", index, data, address)
            sock.sendto(b"recv: " + data, address)
        print("UDP server completed")
    finally:
        sock.close()
        netif = None


if __name__ == "__main__":
    main()
