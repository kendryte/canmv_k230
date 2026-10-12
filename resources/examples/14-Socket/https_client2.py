import requests
from libs.Network import connect_network, load_network_config

CONFIG = load_network_config({
    "network_type": "wifi_sta",
    "wlan_device": "auto",
    "ssid": "TEST",
    "password": "12345678",
    "timeout": 20,
})

# Use urequests to make HTTPS request
def test_https_baidu():
    print("\n[TEST] HTTPS GET using urequests")
    try:
        response = requests.get("https://www.baidu.com")
        print(response.text)
        response.close()
        print("[✓] HTTPS request completed")
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
    print("HTTPS requests client completed")


if __name__ == "__main__":
    main()
