from libs.Network import connect_network, load_network_config, network_device_name


CONFIG = load_network_config({
    "timeout": 20,
    "ip_config": "dhcp",
})


def main():
    lan, ip = connect_network(
        "lan",
        timeout=CONFIG["timeout"],
        ip_config=CONFIG["ip_config"],
    )
    print("LAN active:", lan.active())
    print("LAN config:", lan.ifconfig())
    print("LAN device:", network_device_name(lan))
    print("LAN address:", ip)
    print("LAN MAC:", lan.config("mac"))


if __name__ == "__main__":
    main()
