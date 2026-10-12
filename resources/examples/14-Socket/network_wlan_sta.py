from libs.Network import connect_network, load_network_config

CONFIG = load_network_config({
    "wlan_device": "auto",
    "ssid": "TEST",
    "password": "12345678",
    "timeout": 10,
})

def main():
    sta, _ = connect_network("wifi_sta", ssid=CONFIG["ssid"],
                             password=CONFIG.get("password"),
                             wlan_device=CONFIG["wlan_device"],
                             timeout=CONFIG["timeout"])
    print(sta.ifconfig())

    print(sta.status())

    # 这里的断开网络，只是一个测试。实际应用可不断开
    sta.disconnect()
    print("断开连接")
    print(sta.status())
    print("WLAN STA completed")


if __name__ == "__main__":
    main()
