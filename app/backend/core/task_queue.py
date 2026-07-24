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
from pathlib import Path

from backend.config.settings import DOWNLOADS_DIR, JOBS_DIR
from backend.core import cutter, downloader, highlight_scorer, notifications, overlay
from backend.core.ffmpeg_utils import extract_thumbnail, probe_duration
from backend.models.schemas import (
    ClipMeta,
    JobCreateRequest,
    JobManifest,
    JobProgress,
    JobStage,
    JobSummary,
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
    source_url: str = ""
    title: str = ""
    thumbnail_url: str | None = None
    created_at: str = ""
    status: str = "queued"  # queued | running | done | error
    progress: JobProgress = field(default_factory=lambda: JobProgress(stage=JobStage.QUEUED))
    manifest: JobManifest | None = None
    error: str | None = None
    finished_at: str | None = None
    archived: bool = False
    subscribers: list[asyncio.Queue] = field(default_factory=list)


def get_job(job_id: str) -> JobState | None:
    return _jobs.get(job_id)


def _to_summary(state: JobState) -> JobSummary:
    return JobSummary(
        job_id=state.job_id,
        source_url=state.source_url,
        title=state.title,
        thumbnail_url=state.thumbnail_url,
        created_at=state.created_at,
        status=state.status,
        progress=state.progress,
        finished_at=state.finished_at,
        error=state.error,
    )


def _meta_path(job_id: str) -> Path:
    return JOBS_DIR / job_id / "job_meta.json"


def _persist_meta(state: JobState) -> None:
    path = _meta_path(state.job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_to_summary(state).model_dump_json(indent=2), encoding="utf-8")


def list_jobs() -> list[JobSummary]:
    """Merges this process's in-memory jobs with any job_meta.json left on
    disk by a previous run (app restarted mid-job or after finishing) -
    in-memory always wins since it's the freshest, live-updating copy."""
    summaries: dict[str, JobSummary] = {jid: _to_summary(s) for jid, s in _jobs.items() if not s.archived}

    if JOBS_DIR.exists():
        for meta_path in JOBS_DIR.glob("*/job_meta.json"):
            job_id = meta_path.parent.name
            if job_id in summaries:
                continue
            try:
                summary = JobSummary.model_validate_json(meta_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not _is_archived_on_disk(job_id):
                summaries[job_id] = summary

    return sorted(summaries.values(), key=lambda s: s.created_at, reverse=True)


def _archived_marker_path(job_id: str) -> Path:
    return JOBS_DIR / job_id / ".archived"


def _is_archived_on_disk(job_id: str) -> bool:
    return _archived_marker_path(job_id).exists()


def delete_job(job_id: str) -> bool:
    """Dismisses a job from the "Задачи" list. Does not touch clip files or
    the manifest - those stay on disk for the Gallery to show separately."""
    state = _jobs.get(job_id)
    found = state is not None
    if state is not None:
        state.archived = True
        _persist_meta(state)
    if (JOBS_DIR / job_id).exists():
        found = True
        _archived_marker_path(job_id).touch()
    return found


def create_job(request: JobCreateRequest, title: str, thumbnail_url: str | None = None) -> JobState:
    job_id = uuid.uuid4().hex[:12]
    state = JobState(
        job_id=job_id,
        source_url=request.source_url,
        title=title,
        thumbnail_url=thumbnail_url,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    _jobs[job_id] = state
    _persist_meta(state)
    _executor.submit(_run_job, state, request, title)
    return state


def _push_progress(state: JobState, stage: JobStage, progress: int, message: str) -> None:
    state.progress = JobProgress(stage=stage, progress=progress, message=message)
    if stage in (JobStage.DONE, JobStage.ERROR):
        state.finished_at = datetime.now(timezone.utc).isoformat()
    _persist_meta(state)
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

        scores: dict[str, float] = {}
        if request.smart_cut_enabled:
            _push_progress(state, JobStage.CUT, 0, "анализ моментов...")
            curve = highlight_scorer.build_score_curve(source_path, job_dir)
            total_duration = probe_duration(source_path)
            boundaries = highlight_scorer.suggest_cut_points(curve, total_duration, request.clip_length_sec)

            segments: list[cutter.CutSegment] = []
            for i, (start, end) in enumerate(boundaries):
                clip_id = f"clip_{i:03d}"
                out_path = clips_dir / f"{clip_id}.mp4"
                cutter.cut_segment(source_path, start, end, out_path)
                segments.append(cutter.CutSegment(clip_id=clip_id, start=start, end=end, file_path=out_path))
                scores[clip_id] = highlight_scorer.score_clip(curve, start, end)
                _push_progress(
                    state, JobStage.CUT, int((i + 1) / len(boundaries) * 100) if boundaries else 100,
                    f"клип {i + 1}/{len(boundaries)}",
                )
        else:
            segments = cutter.cut_by_time(
                source_path,
                clips_dir,
                request.clip_length_sec,
                on_progress=lambda pct, msg: _push_progress(state, JobStage.CUT, pct, msg),
            )

        clips: list[ClipMeta] = []
        total = len(segments) or 1
        variations_count = request.variations_count
        for i, seg in enumerate(segments):
            _push_progress(
                state, JobStage.OVERLAY, int(i / total * 100),
                f"клип {i + 1}/{total} (кодирование...)",
            )
            final_path = clips_dir / f"{seg.clip_id}_final.mp4"
            overlay.apply_text_overlay(seg.file_path, final_path, request.text_overlay, request.quality.value)

            thumb_path = thumbs_dir / f"{seg.clip_id}.jpg"
            extract_thumbnail(final_path, thumb_path)

            clips.append(ClipMeta(
                clip_id=seg.clip_id,
                source_start=seg.start,
                source_end=seg.end,
                file_path=str(final_path.relative_to(job_dir)),
                thumbnail_path=str(thumb_path.relative_to(job_dir)),
                potential_score=scores.get(seg.clip_id),
                variation_index=0,
            ))
            _push_progress(
                state, JobStage.OVERLAY, int((i + 1) / total * 100),
                f"клип {i + 1}/{total}",
            )

            # Variants are cut from the same pre-overlay segment as the original,
            # not the finished file - each gets its own crop/speed/color recipe
            # independently rather than compounding on top of one another.
            for v in range(1, variations_count + 1):
                recipe = overlay.VARIATION_RECIPES[(v - 1) % len(overlay.VARIATION_RECIPES)]
                _push_progress(
                    state, JobStage.VARIATIONS,
                    int(((i * variations_count) + v) / (total * max(variations_count, 1)) * 100),
                    f"клип {i + 1}/{total}, вариант {v}/{variations_count}",
                )
                variant_id = f"{seg.clip_id}_var{v}"
                variant_path = clips_dir / f"{variant_id}_final.mp4"
                overlay.apply_text_overlay(
                    seg.file_path, variant_path, request.text_overlay, request.quality.value, variation=recipe,
                )
                variant_thumb = thumbs_dir / f"{variant_id}.jpg"
                extract_thumbnail(variant_path, variant_thumb)
                clips.append(ClipMeta(
                    clip_id=variant_id,
                    source_start=seg.start,
                    source_end=seg.end,
                    file_path=str(variant_path.relative_to(job_dir)),
                    thumbnail_path=str(variant_thumb.relative_to(job_dir)),
                    potential_score=scores.get(seg.clip_id),
                    variation_index=v,
                    variation_techniques=[recipe.label],
                ))

            if seg.file_path != final_path and seg.file_path.exists():
                seg.file_path.unlink()

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
        notifications.notify("Newtik", f"Нарезка успешно готова: {title}")
    except Exception as exc:  # noqa: BLE001 - surfaced to the UI as a job error, not a crash
        logger.exception("Job %s failed", job_id)
        state.status = "error"
        state.error = str(exc)
        _push_progress(state, JobStage.ERROR, 0, str(exc))
        notifications.notify("Newtik — ошибка", f"Не удалось обработать «{title}»: {exc}")
