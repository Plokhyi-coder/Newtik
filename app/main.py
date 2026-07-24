"""Entry point: runs the FastAPI backend in a background thread and opens the
pywebview desktop window pointed at it. The same backend also serves the
mobile transfer page (stage 8), so there is only ever one server process.
"""
from __future__ import annotations

import logging
import os
import threading
import time

import uvicorn
import webview

from backend.app import create_app
from backend.config.settings import BIND_HOST, HOST, API_PORT

logger = logging.getLogger("newtik.main")


def _run_server() -> None:
    app = create_app()
    # Binds on all interfaces (not just loopback) so a phone on the same
    # Wi-Fi can reach the QR-transfer page - the desktop window itself still
    # talks to 127.0.0.1 below, that's unaffected by what the server binds to.
    uvicorn.run(app, host=BIND_HOST, port=API_PORT, log_level="info")


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

    # webview.start() only returns once the window is closed (or its native
    # WebView2/GTK process crashes) - at that point force a hard, total
    # process exit instead of falling through to Python's normal interpreter
    # finalization. That normal path runs atexit hooks (including the one
    # that tears down every ThreadPoolExecutor process-wide) on the main
    # thread while the background server thread - a daemon thread - can keep
    # running for a while afterward, since it's usually parked in an
    # OS-level wait (epoll/select) that doesn't get torn down immediately.
    # The result in practice: the server keeps answering GET requests, but
    # every "start a new job" request fails with "cannot schedule new
    # futures after interpreter shutdown" until the process is killed
    # manually - os._exit(0) here removes that half-dead window entirely.
    os._exit(0)


if __name__ == "__main__":
    main()
