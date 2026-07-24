from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend.api import (
    routes_channel,
    routes_gallery,
    routes_job,
    routes_network,
    routes_project,
    routes_results,
    routes_settings,
    ws_progress,
)
from backend.config.settings import APP_DIR, LOGS_DIR
from backend.core import task_queue
from backend.core.ffmpeg_utils import ensure_ffmpeg_on_path

FRONTEND_DESKTOP_DIR = APP_DIR / "frontend" / "desktop"
FRONTEND_SHARED_DIR = APP_DIR / "frontend" / "shared"
FRONTEND_MOBILE_DIR = APP_DIR / "frontend" / "mobile"


def setup_logging() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(LOGS_DIR / "app.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def create_app() -> FastAPI:
    setup_logging()
    ensure_ffmpeg_on_path()
    app = FastAPI(title="Newtik")

    @app.on_event("startup")
    async def _bind_loop() -> None:
        task_queue.bind_event_loop(asyncio.get_running_loop())

    app.include_router(routes_project.router)
    app.include_router(routes_job.router)
    app.include_router(routes_results.router)
    app.include_router(routes_network.router)
    app.include_router(routes_gallery.router)
    app.include_router(routes_settings.router)
    app.include_router(routes_channel.router)
    app.include_router(ws_progress.router)

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> RedirectResponse:
        # Browsers probe this path directly regardless of the <link rel="icon"> tag.
        return RedirectResponse(url="/assets/favicon.svg")

    @app.get("/mobile", include_in_schema=False)
    async def mobile_no_slash() -> RedirectResponse:
        # StaticFiles(html=True) only resolves index.html for paths ending in
        # "/", so a phone hitting the slash-less form (typed by hand, or
        # normalized away by a QR scanner) would otherwise get a bare 404.
        return RedirectResponse(url="/mobile/")

    app.mount("/shared", StaticFiles(directory=str(FRONTEND_SHARED_DIR)), name="shared")
    app.mount("/mobile", StaticFiles(directory=str(FRONTEND_MOBILE_DIR), html=True), name="mobile")
    app.mount("/", StaticFiles(directory=str(FRONTEND_DESKTOP_DIR), html=True), name="desktop")

    return app
