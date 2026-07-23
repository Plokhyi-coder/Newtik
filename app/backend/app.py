from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.api import routes_job, routes_project, routes_results, ws_progress
from backend.config.settings import APP_DIR, LOGS_DIR
from backend.core import task_queue

FRONTEND_DESKTOP_DIR = APP_DIR / "frontend" / "desktop"
FRONTEND_SHARED_DIR = APP_DIR / "frontend" / "shared"


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
    app = FastAPI(title="Newtik")

    @app.on_event("startup")
    async def _bind_loop() -> None:
        task_queue.bind_event_loop(asyncio.get_running_loop())

    app.include_router(routes_project.router)
    app.include_router(routes_job.router)
    app.include_router(routes_results.router)
    app.include_router(ws_progress.router)

    app.mount("/shared", StaticFiles(directory=str(FRONTEND_SHARED_DIR)), name="shared")
    app.mount("/", StaticFiles(directory=str(FRONTEND_DESKTOP_DIR), html=True), name="desktop")

    return app
