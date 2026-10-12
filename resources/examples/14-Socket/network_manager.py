from libs.Network import NetworkManager, get_default_device, load_network_config


# "default" reuses an interface that already has an IP address.
# "lan" uses DHCP, "wifi_sta" joins an AP, and "wifi_ap" creates an AP.
CONFIG = load_network_config({
    "network_type": "wifi_sta",
    "wlan_device": "auto",
    "ssid": "TEST",
    "password": "12345678",
    "timeout": 20,
})


def main():
    manager = NetworkManager(
        network_type=CONFIG["network_type"],
        ssid=CONFIG.get("ssid"),
        password=CONFIG.get("password"),
        wlan_device=CONFIG["wlan_device"],
        timeout=CONFIG["timeout"],
        ip_config=CONFIG.get("ip_config"),
        show=False,
    )

    # Inspect registered devices before choosing one. Netdev names are assigned
    # dynamically, so applications should not hard-code them.
    manager.show_devices()

    netif, ip = manager.connect()
    manager.show_info()
    print("Network ready:", ip)
    print("Default network device:", get_default_device() or "auto")

    # The manager keeps the interface for reuse by all application components.
    # manager.connect() reconnects when needed, manager.scan() scans Wi-Fi, and
    # manager.disconnect() stops Wi-Fi and restores automatic route selection.
    return netif


main()
