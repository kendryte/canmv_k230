"""Common network selection and connection helpers for CanMV examples."""

import network as _network
import os
import time


TYPE_DEFAULT = "default"
TYPE_LAN = "lan"
TYPE_WIFI_STA = "wifi_sta"
TYPE_WIFI_AP = "wifi_ap"

NETWORK_TYPES = (TYPE_DEFAULT, TYPE_LAN, TYPE_WIFI_STA, TYPE_WIFI_AP)
NETWORK_TIMEOUT = 20

WLAN_AUTO = getattr(_network, "WLAN_AUTO", 0)
WLAN_USB = getattr(_network, "WLAN_USB", 1)
WLAN_SDIO = getattr(_network, "WLAN_SDIO", 2)
WLAN_SPI = getattr(_network, "WLAN_SPI", 3)

WLAN_DEVICES = {
    "auto": WLAN_AUTO,
    "usb": WLAN_USB,
    "sdio": WLAN_SDIO,
    "spi": WLAN_SPI,
}

_TYPE_ALIASES = {
    None: TYPE_DEFAULT,
    "auto": TYPE_DEFAULT,
    "ethernet": TYPE_LAN,
    "usb_eth": TYPE_LAN,
    "wifi": TYPE_WIFI_STA,
    "sta": TYPE_WIFI_STA,
    "ap": TYPE_WIFI_AP,
}


def _normalise_type(network_type):
    network_type = _TYPE_ALIASES.get(network_type, network_type)
    if network_type not in NETWORK_TYPES:
        raise ValueError("network type must be one of: %s" %
                         ", ".join(NETWORK_TYPES))
    return network_type


def _normalise_wlan_device(wlan_device):
    if wlan_device is None:
        return WLAN_AUTO
    if isinstance(wlan_device, str):
        key = wlan_device.lower()
        if key not in WLAN_DEVICES:
            raise ValueError("WLAN device must be auto, usb, sdio, or spi")
        return WLAN_DEVICES[key]
    if wlan_device not in WLAN_DEVICES.values():
        raise ValueError("unsupported WLAN device")
    return wlan_device

def _sleep_ms(milliseconds):
    try:
        time.sleep_ms(milliseconds)
    except AttributeError:
        time.sleep(milliseconds / 1000.0)


def _ifconfig(netif):
    try:
        return netif.ifconfig()
    except Exception:
        return None


def _raw_device_name(netif):
    try:
        return netif.netdev_name()
    except Exception:
        return None


def network_device_name(netif):
    """Return the current netdev name selected by netmgmt."""
    return _raw_device_name(netif) or "unavailable"


def get_devices():
    """Return every netdev currently registered with netmgmt."""
    if not hasattr(_network, "get_dev_list"):
        return []
    devices = _network.get_dev_list()
    return list(devices) if devices else []


def get_default_device():
    """Return the active default netdev name, or None when no route is ready."""
    if not hasattr(_network, "get_default_dev"):
        return None
    return _network.get_default_dev()


def set_default_device(device=None):
    """Prefer a NIC/name, or pass None to restore automatic route selection."""
    if not hasattr(_network, "set_default_dev"):
        raise RuntimeError("default network selection is not supported")
    if _network.set_default_dev(device) is False:
        raise RuntimeError("failed to set default network device")
    return get_default_device()


def show_devices():
    """Print and return registered netdevs and the active default route."""
    devices = get_devices()
    default_device = get_default_device()
    print("Network devices:", devices)
    print("Default network device:", default_device or "auto")
    return devices


def has_ip(netif):
    config = _ifconfig(netif)
    return bool(config and config[0] not in (None, "", "0.0.0.0"))


def isconnected(netif):
    """Return link state; interfaces without isconnected() use active state."""
    try:
        return bool(netif.isconnected())
    except Exception:
        try:
            return bool(netif.active())
        except Exception:
            return True


def wait_for_ip(netif, timeout=NETWORK_TIMEOUT, require_connection=True):
    """Wait for a non-zero IPv4 address and return it."""
    start = time.time()
    while time.time() - start < timeout:
        config = _ifconfig(netif)
        if (config and config[0] not in (None, "", "0.0.0.0") and
                (not require_connection or isconnected(netif))):
            return config[0]
        _sleep_ms(100)
    raise RuntimeError("network address timeout on %s" % network_device_name(netif))


def configure_ip(netif, ip_config="dhcp", timeout=NETWORK_TIMEOUT,
                 require_connection=True):
    """Apply DHCP or a static ifconfig tuple, then wait for the address."""
    if netif.ifconfig(ip_config) is False:
        raise RuntimeError("network IP configuration failed")
    return wait_for_ip(netif, timeout=timeout,
                       require_connection=require_connection)


def mac_address(netif):
    """Return an interface MAC in lower-case colon notation."""
    try:
        mac = netif.config("mac")
    except Exception as error:
        raise RuntimeError("cannot read MAC address from %s: %s" %
                           (network_device_name(netif), error))
    if mac is None or len(mac) != 6:
        raise ValueError("invalid MAC address length")
    return ":".join("%02x" % value for value in mac)


def network_info(netif):
    """Return the useful runtime state for one network interface."""
    info = {
        "device": network_device_name(netif),
        "default": get_default_device(),
        "active": None,
        "connected": isconnected(netif),
        "ifconfig": _ifconfig(netif),
        "mac": None,
        "status": None,
    }
    try:
        info["active"] = netif.active()
    except Exception:
        pass
    try:
        info["mac"] = mac_address(netif)
    except Exception:
        pass
    try:
        info["status"] = netif.status()
    except Exception:
        pass
    return info


def show_network_info(netif):
    """Print and return the state of the selected interface."""
    info = network_info(netif)
    print("Selected network device:", info["device"])
    print("Network active:", info["active"])
    print("Network connected:", info["connected"])
    print("Network config:", info["ifconfig"])
    if info["mac"] is not None:
        print("Network MAC:", info["mac"])
    return info


def _new_interface(network_type, wlan_device=WLAN_AUTO):
    if network_type == TYPE_LAN:
        if not hasattr(_network, "LAN"):
            raise RuntimeError("LAN is not supported by this firmware")
        return _network.LAN()
    if not hasattr(_network, "WLAN"):
        raise RuntimeError("Wi-Fi is not supported by this firmware")
    role = _network.STA_IF if network_type == TYPE_WIFI_STA else _network.AP_IF
    return _network.WLAN(role, _normalise_wlan_device(wlan_device))


def _default_interface():
    default_name = get_default_device()

    candidates = []
    if hasattr(_network, "LAN"):
        candidates.append((_network.LAN(), TYPE_LAN))
    if hasattr(_network, "WLAN"):
        candidates.append((_network.WLAN(_network.STA_IF, WLAN_AUTO), TYPE_WIFI_STA))
        candidates.append((_network.WLAN(_network.AP_IF, WLAN_AUTO), TYPE_WIFI_AP))

    if default_name is not None:
        for netif, network_type in candidates:
            if _raw_device_name(netif) == default_name:
                return netif, network_type

        # An explicit USB/SDIO/SPI Wi-Fi default may not be the auto choice.
        if hasattr(_network, "WLAN"):
            for wlan_device in (WLAN_USB, WLAN_SDIO, WLAN_SPI):
                for role, network_type in (
                        (_network.STA_IF, TYPE_WIFI_STA),
                        (_network.AP_IF, TYPE_WIFI_AP)):
                    netif = _network.WLAN(role, wlan_device)
                    if _raw_device_name(netif) == default_name:
                        return netif, network_type

    for netif, network_type in candidates:
        require_connection = network_type != TYPE_WIFI_AP
        if has_ip(netif) and (not require_connection or isconnected(netif)):
            return netif, network_type

    raise RuntimeError(
        "no connected default interface; select lan, wifi_sta, or wifi_ap"
    )


def get_interface(network_type=TYPE_DEFAULT, wlan_device="auto"):
    """Return the interface for a type without connecting or changing routes."""
    network_type = _normalise_type(network_type)
    if network_type == TYPE_DEFAULT:
        return _default_interface()[0]
    return _new_interface(network_type, wlan_device)


def _activate(netif, network_type):
    if network_type in (TYPE_WIFI_STA, TYPE_WIFI_AP):
        if netif.active(True) is False:
            raise RuntimeError("Wi-Fi interface is unavailable")
        return
    try:
        active = netif.active()
    except Exception:
        active = True
    if active is False:
        try:
            result = netif.active(True)
        except Exception as error:
            raise RuntimeError("LAN interface is not active: %s" % error)
        if result is False:
            raise RuntimeError("LAN interface is not active")


def _configure_lan(netif, ip_config):
    if ip_config is None:
        ip_config = "dhcp"
    if ip_config == "dhcp" and has_ip(netif):
        return
    if netif.ifconfig(ip_config) is False:
        raise RuntimeError("LAN IP configuration failed")


def _configure_ap(netif, ssid, password, channel, band):
    if ssid is None:
        raise ValueError("Wi-Fi AP requires an ssid")
    kwargs = {"ssid": ssid}
    if password is not None:
        kwargs["key"] = password
    if channel is not None:
        kwargs["channel"] = channel
    if band is not None:
        kwargs["band"] = band
    try:
        result = netif.config(**kwargs)
    except TypeError:
        kwargs.pop("channel", None)
        kwargs.pop("band", None)
        result = netif.config(**kwargs)
    if result is False:
        raise RuntimeError("Wi-Fi AP start failed")


def connect_network(network_type=TYPE_DEFAULT, ssid=None, password=None,
                    timeout=NETWORK_TIMEOUT, wlan_device="auto", netif=None,
                    ip_config=None, channel=None, band=None, set_default=True,
                    show=True):
    """Connect one interface and return ``(netif, ip)``.

    ``network_type`` may be ``default``, ``lan``, ``wifi_sta`` or
    ``wifi_ap``.  ``default`` reuses an already connected default/automatic
    interface.  ``wlan_device`` may be ``auto``, ``usb``, ``sdio`` or ``spi``.
    No netdev name is hard-coded.
    """
    network_type = _normalise_type(network_type)
    if show:
        show_devices()

    if network_type == TYPE_DEFAULT:
        if netif is None:
            netif, resolved_type = _default_interface()
        else:
            resolved_type = TYPE_DEFAULT
        ip = wait_for_ip(netif, timeout=timeout,
                         require_connection=resolved_type != TYPE_WIFI_AP)
        if show:
            show_network_info(netif)
        return netif, ip

    if netif is None:
        netif = _new_interface(network_type, wlan_device)
    _activate(netif, network_type)

    if network_type == TYPE_LAN:
        _configure_lan(netif, ip_config)
        require_connection = True
    elif network_type == TYPE_WIFI_STA:
        if ssid is not None:
            if netif.connect(ssid, password) is False:
                raise RuntimeError("Wi-Fi connection failed")
        elif not isconnected(netif):
            raise ValueError("Wi-Fi STA requires an ssid")
        require_connection = True
    else:
        _configure_ap(netif, ssid, password, channel, band)
        require_connection = False

    ip = wait_for_ip(netif, timeout=timeout,
                     require_connection=require_connection)
    if set_default and network_type != TYPE_WIFI_AP:
        set_default_device(netif)
    if show:
        show_network_info(netif)
    return netif, ip


def disconnect_network(netif, network_type=TYPE_WIFI_STA,
                       restore_default=True):
    """Stop a Wi-Fi interface and optionally restore automatic routing."""
    network_type = _normalise_type(network_type)
    result = True
    if network_type == TYPE_WIFI_STA:
        result = netif.disconnect()
    elif network_type == TYPE_WIFI_AP:
        result = netif.stop()
    if restore_default and network_type != TYPE_WIFI_AP:
        set_default_device(None)
    return result is not False


def scan_wifi(wlan_device="auto"):
    """Scan using the selected Wi-Fi card and return the firmware results."""
    netif = _new_interface(TYPE_WIFI_STA, wlan_device)
    _activate(netif, TYPE_WIFI_STA)
    return netif.scan()


class NetworkManager:
    """Own and reuse one interface across all components in an application."""

    def __init__(self, network_type=TYPE_DEFAULT, ssid=None, password=None,
                 timeout=NETWORK_TIMEOUT, wlan_device="auto",
                 set_default=True, show=True):
        self.network_type = network_type
        self.ssid = ssid
        self.password = password
        self.timeout = timeout
        self.wlan_device = wlan_device
        self.set_as_default = set_default
        self.show = show
        self.netif = None
        self.ip = None

    def connect(self, **kwargs):
        if not kwargs and self.netif is not None and has_ip(self.netif):
            network_type = _normalise_type(self.network_type)
            if network_type == TYPE_WIFI_AP or isconnected(self.netif):
                self.ip = _ifconfig(self.netif)[0]
                if (self.set_as_default and
                        network_type not in (TYPE_DEFAULT, TYPE_WIFI_AP)):
                    set_default_device(self.netif)
                return self.netif, self.ip
        options = {
            "network_type": self.network_type,
            "ssid": self.ssid,
            "password": self.password,
            "timeout": self.timeout,
            "wlan_device": self.wlan_device,
            "netif": self.netif,
            "set_default": self.set_as_default,
            "show": self.show,
        }
        options.update(kwargs)

        current_type = _normalise_type(self.network_type)
        requested_type = _normalise_type(options["network_type"])
        selection_changed = requested_type != current_type
        if (not selection_changed and
                requested_type in (TYPE_WIFI_STA, TYPE_WIFI_AP)):
            selection_changed = (
                _normalise_wlan_device(options["wlan_device"]) !=
                _normalise_wlan_device(self.wlan_device)
            )
        if selection_changed and "netif" not in kwargs:
            options["netif"] = None

        netif, ip = connect_network(**options)
        self.network_type = requested_type
        self.ssid = options["ssid"]
        self.password = options["password"]
        self.timeout = options["timeout"]
        self.wlan_device = options["wlan_device"]
        self.set_as_default = options["set_default"]
        self.show = options["show"]
        self.netif, self.ip = netif, ip
        return self.netif, self.ip

    def disconnect(self, restore_default=True):
        if self.netif is None:
            return True
        result = disconnect_network(self.netif, self.network_type,
                                    restore_default)
        if result:
            self.netif = None
            self.ip = None
        return result

    def info(self):
        return network_info(self.netif) if self.netif is not None else None

    def show_info(self):
        return show_network_info(self.netif) if self.netif is not None else None

    def show_devices(self):
        return show_devices()

    def wait_for_ip(self, require_connection=True):
        if self.netif is None:
            raise RuntimeError("network interface is not initialized")
        self.ip = wait_for_ip(self.netif, self.timeout, require_connection)
        return self.ip

    def set_default(self):
        if self.netif is None:
            raise RuntimeError("network interface is not initialized")
        return set_default_device(self.netif)

    def scan(self):
        return scan_wifi(self.wlan_device)
