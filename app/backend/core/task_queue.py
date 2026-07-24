"""In-memory job registry + background execution.

MVP runs each job's steps (download -> cut -> overlay) sequentially on a
worker thread from a ThreadPoolExecutor - subprocess calls (ffmpeg, yt-dlp)
release the GIL while waiting, which is enough to keep the FastAPI/pywebview
UI thread responsive without the extra complexity of a process pool. Stage 3
(faster-whisper) is CPU/GPU-bound *inside* the Python process, so it will
move onto a ProcessPoolExecutor when it's introduced.

Progress crosses the thread -> asyncio boundary via `loop.call_soon_threadsafe`
into a per-subscriber asyncio.Queue, consumed by the websocket route.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.config.settings import DOWNLOADS_DIR, JOBS_DIR
from backend.core import cutter, downloader, overlay
from backend.core.ffmpeg_utils import extract_thumbnail
from backend.models.schemas import (
    ClipMeta,
    JobCreateRequest,
    JobManifest,
    JobProgress,
    JobStage,
)

logger = logging.getLogger("newtik.task_queue")

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="newtik-job")
_jobs: dict[str, "JobState"] = {}
_loop: asyncio.AbstractEventLoop | None = None


def bind_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Called once at FastAPI startup so job threads can push updates back to the loop."""
    global _loop
    _loop = loop


@dataclass
class JobState:
    job_id: str
    status: str = "queued"  # queued | running | done | error
    progress: JobProgress = field(default_factory=lambda: JobProgress(stage=JobStage.QUEUED))
    manifest: JobManifest | None = None
    error: str | None = None
    subscribers: list[asyncio.Queue] = field(default_factory=list)


def get_job(job_id: str) -> JobState | None:
    return _jobs.get(job_id)


def create_job(request: JobCreateRequest, title: str) -> JobState:
    job_id = uuid.uuid4().hex[:12]
    state = JobState(job_id=job_id)
    _jobs[job_id] = state
    _executor.submit(_run_job, state, request, title)
    return state


def _push_progress(state: JobState, stage: JobStage, progress: int, message: str) -> None:
    state.progress = JobProgress(stage=stage, progress=progress, message=message)
    if _loop is None:
        return
    for q in list(state.subscribers):
        _loop.call_soon_threadsafe(q.put_nowait, state.progress)


def _run_job(state: JobState, request: JobCreateRequest, title: str) -> None:
    job_id = state.job_id
    state.status = "running"
    try:
        job_dir = JOBS_DIR / job_id
        clips_dir = job_dir / "clips"
        thumbs_dir = job_dir / "thumbnails"

        _push_progress(state, JobStage.DOWNLOAD, 0, "начало...")
        source_path = downloader.download_video(
            request.source_url,
            DOWNLOADS_DIR,
            job_id,
            request.time_range,
            on_progress=lambda pct, msg: _push_progress(state, JobStage.DOWNLOAD, pct, msg),
        )

        segments = cutter.cut_by_time(
            source_path,
            clips_dir,
            request.clip_length_sec,
            on_progress=lambda pct, msg: _push_progress(state, JobStage.CUT, pct, msg),
        )

        clips: list[ClipMeta] = []
        total = len(segments) or 1
        for i, seg in enumerate(segments):
            _push_progress(
                state, JobStage.OVERLAY, int(i / total * 100),
                f"клип {i + 1}/{total} (кодирование...)",
            )
            final_path = clips_dir / f"{seg.clip_id}_final.mp4"
            overlay.apply_text_overlay(seg.file_path, final_path, request.text_overlay)
            if seg.file_path != final_path and seg.file_path.exists():
                seg.file_path.unlink()

            thumb_path = thumbs_dir / f"{seg.clip_id}.jpg"
            extract_thumbnail(final_path, thumb_path)

            clips.append(ClipMeta(
                clip_id=seg.clip_id,
                source_start=seg.start,
                source_end=seg.end,
                file_path=str(final_path.relative_to(job_dir)),
                thumbnail_path=str(thumb_path.relative_to(job_dir)),
            ))
            _push_progress(
                state, JobStage.OVERLAY, int((i + 1) / total * 100),
                f"клип {i + 1}/{total}",
            )

        manifest = JobManifest(
            job_id=job_id,
            source_url=request.source_url,
            title=title,
            created_at=datetime.now(timezone.utc).isoformat(),
            clips=clips,
        )
        (job_dir / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        state.manifest = manifest
        state.status = "done"
        _push_progress(state, JobStage.DONE, 100, "Готово")
    except Exception as exc:  # noqa: BLE001 - surfaced to the UI as a job error, not a crash
        logger.exception("Job %s failed", job_id)
        state.status = "error"
        state.error = str(exc)
        _push_progress(state, JobStage.ERROR, 0, str(exc))
