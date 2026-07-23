from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.core import task_queue
from backend.core.downloader import DownloadError, fetch_metadata
from backend.models.schemas import JobCreateRequest

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("")
def create_job(request: JobCreateRequest) -> dict:
    try:
        metadata = fetch_metadata(request.source_url)
    except DownloadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    state = task_queue.create_job(request, metadata.title)
    return {"job_id": state.job_id}


@router.get("/{job_id}")
def get_job_status(job_id: str) -> dict:
    state = task_queue.get_job(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return {
        "job_id": state.job_id,
        "status": state.status,
        "progress": state.progress.model_dump(),
        "error": state.error,
    }
