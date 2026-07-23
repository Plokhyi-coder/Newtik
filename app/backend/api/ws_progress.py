from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.core import task_queue
from backend.models.schemas import JobStage

logger = logging.getLogger("newtik.ws")

router = APIRouter()


@router.websocket("/ws/jobs/{job_id}")
async def job_progress(websocket: WebSocket, job_id: str) -> None:
    await websocket.accept()
    state = task_queue.get_job(job_id)
    if state is None:
        await websocket.send_json({"error": "Задача не найдена"})
        await websocket.close()
        return

    queue: asyncio.Queue = asyncio.Queue()
    state.subscribers.append(queue)
    try:
        # Send current state immediately so late-connecting clients aren't stuck at 0%.
        await websocket.send_json(state.progress.model_dump())
        if state.progress.stage in (JobStage.DONE, JobStage.ERROR):
            return

        while True:
            progress = await queue.get()
            await websocket.send_json(progress.model_dump())
            if progress.stage in (JobStage.DONE, JobStage.ERROR):
                break
    except WebSocketDisconnect:
        pass
    finally:
        if queue in state.subscribers:
            state.subscribers.remove(queue)
