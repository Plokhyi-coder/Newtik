from __future__ import annotations

import io

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
    return {"lan_ip": get_lan_ip(), "port": API_PORT, "mobile_url": _mobile_url()}


@router.get("/qr.png")
def qr_png() -> Response:
    img = qrcode.make(_mobile_url(), box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")
