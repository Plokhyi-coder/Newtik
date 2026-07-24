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
