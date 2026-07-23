"""Entry point: runs the FastAPI backend in a background thread and opens the
pywebview desktop window pointed at it. The same backend also serves the
mobile transfer page (stage 8), so there is only ever one server process.
"""
from __future__ import annotations

import logging
import threading
import time

import uvicorn
import webview

from backend.app import create_app
from backend.config.settings import HOST, API_PORT

logger = logging.getLogger("newtik.main")


def _run_server() -> None:
    app = create_app()
    uvicorn.run(app, host=HOST, port=API_PORT, log_level="info")


def _wait_for_server(url: str, timeout: float = 15.0) -> None:
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return
        except Exception:
            time.sleep(0.3)


def main() -> None:
    server_thread = threading.Thread(target=_run_server, daemon=True)
    server_thread.start()

    url = f"http://{HOST}:{API_PORT}/"
    _wait_for_server(url)

    webview.create_window("Newtik", url, width=1280, height=800, min_size=(1024, 700))
    webview.start()


if __name__ == "__main__":
    main()
