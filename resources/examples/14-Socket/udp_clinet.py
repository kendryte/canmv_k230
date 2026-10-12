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
    print("UDP destination:", address)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        for index in range(CONFIG["message_count"]):
            payload = ("K230 udp client message %d\n" % index).encode()
            sent = sock.sendto(payload, address)
            if sent != len(payload):
                raise OSError("short UDP send: %d/%d" % (sent, len(payload)))
            print(payload)
            time.sleep_ms(50)
        print("UDP client completed")
    finally:
        sock.close()
        netif = None


if __name__ == "__main__":
    main()
