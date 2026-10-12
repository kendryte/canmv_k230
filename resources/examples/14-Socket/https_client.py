import usocket
import ussl
from libs.Network import connect_network, load_network_config

CONFIG = load_network_config({
    "network_type": "wifi_sta",
    "wlan_device": "auto",
    "ssid": "TEST",
    "password": "12345678",
    "timeout": 20,
})

# HTTPS GET to www.baidu.com
def test_https_baidu():
    try:
        print("\n[TEST] HTTPS GET https://www.baidu.com")
        addr = usocket.getaddrinfo("www.baidu.com", 443)[0][-1]
        sock = usocket.socket()
        sock.connect(addr)

        # Wrap with TLS — SNI is required by Baidu
        ssl_sock = ussl.wrap_socket(sock, server_hostname="www.baidu.com")

        # Send HTTPS GET request
        ssl_sock.write(b"GET / HTTP/1.1\r\nHost: www.baidu.com\r\nConnection: close\r\n\r\n")

        # Read and print the response
        while True:
            data = ssl_sock.read()
            if not data:
                break
            print(data.decode(), end='')

        ssl_sock.close()
        print("\n[✓] HTTPS request to Baidu completed")
    except Exception as e:
        print("HTTPS request failed:", e)
        raise

def main():
    netif, _ = connect_network(
        CONFIG["network_type"],
        ssid=CONFIG.get("ssid"),
        password=CONFIG.get("password"),
        wlan_device=CONFIG["wlan_device"],
        timeout=CONFIG["timeout"],
        ip_config=CONFIG.get("ip_config"),
    )
    test_https_baidu()
    print("HTTPS client completed")


if __name__ == "__main__":
    main()
