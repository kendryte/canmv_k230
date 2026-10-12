import socket
import struct
import time
from libs.Network import connect_network, load_network_config

CONFIG = load_network_config({
    "network_type": "wifi_sta",
    "wlan_device": "auto",
    "ssid": "TEST",
    "password": "12345678",
    "timeout": 20,
    "host": "239.255.0.1",
    "port": 5007,
    "message_count": 0,
    "multicast_sender": False,
})

MULTICAST_GROUP = CONFIG["host"]
MULTICAST_PORT = CONFIG["port"]

def inet_aton(ip_str):
    """Convert dotted string to 4-byte IP (like socket.inet_aton)."""
    return bytes(map(int, ip_str.split('.')))

def multicast_sender(ip):
    """Send UDP multicast messages every 2 seconds."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        ttl = struct.pack('b', 1)
        sock.setsockopt(0, 33, ttl)  # IPPROTO_IP = 0, IP_MULTICAST_TTL = 33

        count = 0
        print(f"[SENDER] Sending to {MULTICAST_GROUP}:{MULTICAST_PORT}")
        while not CONFIG["message_count"] or count < CONFIG["message_count"]:
            msg = f"[{ip}] Multicast message {count}"
            sock.sendto(msg.encode(), (MULTICAST_GROUP, MULTICAST_PORT))
            print(f"[SENDER] Sent: {msg}")
            count += 1
            time.sleep(2)
    finally:
        sock.close()
    print("Multicast sender completed")

def multicast_receiver():
    """Listen to UDP multicast messages."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('0.0.0.0', MULTICAST_PORT))

        mreq = struct.pack("4s4s",
                           inet_aton(MULTICAST_GROUP),
                           inet_aton('0.0.0.0'))  # Use 'network_ip' for stricter binding

        sock.setsockopt(0, 35, mreq)  # IPPROTO_IP = 0, IP_ADD_MEMBERSHIP = 35

        print(f"[RECEIVER] Listening on {MULTICAST_GROUP}:{MULTICAST_PORT} ...")

        count = 0
        while not CONFIG["message_count"] or count < CONFIG["message_count"]:
            data, addr = sock.recvfrom(1024)
            if data:
                try:
                    print(f"[RECEIVER] From {addr}: {data.decode()}")
                except UnicodeError:
                    print(f"[RECEIVER] From {addr}: <binary data>")
            else:
                print(f"[RECEIVER] From {addr}: <empty packet>")
            count += 1
    finally:
        sock.close()
    print("Multicast receiver completed")

def main():
    netif, ip = connect_network(
        CONFIG["network_type"],
        ssid=CONFIG.get("ssid"),
        password=CONFIG.get("password"),
        wlan_device=CONFIG["wlan_device"],
        timeout=CONFIG["timeout"],
        ip_config=CONFIG.get("ip_config"),
    )
    if CONFIG["multicast_sender"]:
        multicast_sender(ip)
    else:
        multicast_receiver()

if __name__ == "__main__":
    main()
