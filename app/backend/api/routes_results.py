from __future__ import annotations

import io
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from backend.config.settings import JOBS_DIR
from backend.core import task_queue
from backend.models.schemas import JobManifest

router = APIRouter(prefix="/api/jobs", tags=["results"])


def _load_manifest(job_id: str) -> JobManifest:
    state = task_queue.get_job(job_id)
    if state is not None and state.manifest is not None:
        return state.manifest

    manifest_path = JOBS_DIR / job_id / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="Результаты задачи не найдены")
    return JobManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))


def _find_clip_path(job_id: str, clip_id: str) -> Path:
    manifest = _load_manifest(job_id)
    clip = next((c for c in manifest.clips if c.clip_id == clip_id), None)
    if clip is None:
        raise HTTPException(status_code=404, detail="Клип не найден")
    return JOBS_DIR / job_id / clip.file_path


@router.get("/{job_id}/clips", response_model=JobManifest)
def get_clips(job_id: str) -> JobManifest:
    return _load_manifest(job_id)


@router.get("/{job_id}/download/{clip_id}")
def download_clip(job_id: str, clip_id: str) -> FileResponse:
    path = _find_clip_path(job_id, clip_id)
    return FileResponse(path, filename=path.name, media_type="video/mp4")


@router.get("/{job_id}/thumbnail/{clip_id}")
def get_thumbnail(job_id: str, clip_id: str) -> FileResponse:
    manifest = _load_manifest(job_id)
    clip = next((c for c in manifest.clips if c.clip_id == clip_id), None)
    if clip is None or clip.thumbnail_path is None:
        raise HTTPException(status_code=404, detail="Превью не найдено")
    return FileResponse(JOBS_DIR / job_id / clip.thumbnail_path, media_type="image/jpeg")


@router.get("/{job_id}/download-all")
def download_all(job_id: str) -> StreamingResponse:
    manifest = _load_manifest(job_id)
    job_dir = JOBS_DIR / job_id

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for clip in manifest.clips:
            file_path = job_dir / clip.file_path
            if file_path.exists():
                zf.write(file_path, arcname=file_path.name)
    buffer.seek(0)

    headers = {"Content-Disposition": f'attachment; filename="{job_id}_clips.zip"'}
    return StreamingResponse(buffer, media_type="application/zip", headers=headers)
