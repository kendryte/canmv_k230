from libs.Network import connect_network, load_network_config

CONFIG = load_network_config({
    "wlan_device": "auto",
    "ssid": "k230_ap_wjx",
    "password": "12345678",
})

def ap_test():
    ap, _ = connect_network("wifi_ap", ssid=CONFIG["ssid"],
                            password=CONFIG.get("password"),
                            wlan_device=CONFIG["wlan_device"])
    #查看ap信息
    print(ap.info())
    #查看ap的状态
    print(ap.status())
    print("WLAN AP completed")

if __name__ == "__main__":
    ap_test()
