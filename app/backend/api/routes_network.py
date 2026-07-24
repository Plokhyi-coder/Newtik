from __future__ import annotations

import io
import socket

import qrcode
from fastapi import APIRouter
from fastapi.responses import Response

from backend.config.settings import API_PORT
from backend.core.network import get_lan_ip

router = APIRouter(prefix="/api", tags=["network"])


def _mobile_url() -> str:
    # Trailing slash matters: StaticFiles(html=True) only resolves index.html
    # for paths under the mount that end in "/" - "/mobile" with no slash 404s.
    return f"http://{get_lan_ip()}:{API_PORT}/mobile/"


@router.get("/network-info")
def network_info() -> dict:
    lan_ip = get_lan_ip()

    # Connect to our own LAN address the way a phone would. This passes even
    # when Windows Firewall blocks the port (loopback-ish traffic from the
    # same host is generally allowed), so it can't prove a phone will get
    # through - but a failure here does prove the server isn't listening on
    # the LAN interface at all, which is a different problem worth splitting
    # out from "firewall is blocking you".
    listening = False
    try:
        with socket.create_connection((lan_ip, API_PORT), timeout=2):
            listening = True
    except OSError:
        listening = False

    return {
        "lan_ip": lan_ip,
        "port": API_PORT,
        "mobile_url": _mobile_url(),
        "listening_on_lan": listening,
        "has_lan_ip": not lan_ip.startswith("127."),
    }


@router.get("/qr.png")
def qr_png() -> Response:
    img = qrcode.make(_mobile_url(), box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")
