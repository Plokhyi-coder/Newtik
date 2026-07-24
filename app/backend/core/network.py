"""LAN IP detection for the QR phone-transfer feature."""
from __future__ import annotations

import socket


def get_lan_ip() -> str:
    """Best-effort LAN IP address of this machine, so a phone on the same
    Wi-Fi network can reach the server. The UDP "connect" below never
    actually sends a packet - it just asks the OS which local address it
    would route through to reach that target, which is the LAN IP on any
    normal home/office network."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        pass
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return "127.0.0.1"


def get_all_lan_ips() -> list[str]:
    """Every non-loopback IPv4 address bound to this machine, primary guess first.

    A machine with more than one active adapter (Wi-Fi + Ethernet, a VPN, a
    virtualization bridge like Docker/VirtualBox/Hyper-V, ...) can have
    get_lan_ip()'s single UDP-route guess land on the wrong one - a phone on
    the same Wi-Fi needs the Wi-Fi adapter's address specifically, not a VPN
    tunnel or virtual-bridge IP that never actually leaves this machine.
    Surfacing every candidate lets the QR panel offer alternatives to try.
    """
    primary = get_lan_ip()
    ips: list[str] = [] if primary.startswith("127.") else [primary]
    try:
        _, _, addrs = socket.gethostbyname_ex(socket.gethostname())
        for ip in addrs:
            if not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except OSError:
        pass
    return ips
