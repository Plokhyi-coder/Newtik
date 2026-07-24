"""Read-only "Explorer" view over storage/jobs/*/clips - one folder per
finished job, files inside are its clips. Delete goes through send2trash
(the OS recycle bin), not a permanent unlink, and "reveal" shells out to
the OS's own file manager - both match how a normal desktop file explorer
behaves, which is the whole point of this view.
"""
from __future__ import annotations

import platform
import subprocess
from pathlib import Path

from send2trash import send2trash

from backend.config.settings import JOBS_DIR
from backend.core import task_queue
from backend.models.schemas import JobManifest


class GalleryError(RuntimeError):
    pass


def _job_dir(job_id: str) -> Path:
    """Resolves job_id to its storage directory, rejecting any path-traversal
    attempt (a job_id containing "../" etc.) rather than silently escaping
    JOBS_DIR - job_id ultimately comes from the URL, so it's untrusted."""
    base = JOBS_DIR.resolve()
    path = (JOBS_DIR / job_id).resolve()
    if path != base and base not in path.parents:
        raise GalleryError("Некорректный идентификатор задачи")
    return path


def _load_manifest(job_id: str) -> tuple[Path, JobManifest]:
    job_dir = _job_dir(job_id)
    manifest_path = job_dir / "manifest.json"
    if not manifest_path.exists():
        raise GalleryError("Папка не найдена")
    return job_dir, JobManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))


def list_folders() -> list[dict]:
    folders = []
    for summary in task_queue.list_jobs():
        if summary.status != "done":
            continue
        job_dir = JOBS_DIR / summary.job_id
        manifest_path = job_dir / "manifest.json"
        if not manifest_path.exists():
            continue
        manifest = JobManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        # A clip can be individually trashed via delete_file() without the
        # manifest being rewritten - skip anything that no longer exists on
        # disk rather than showing a ghost 0-byte entry.
        existing_clips = [c for c in manifest.clips if (job_dir / c.file_path).exists()]
        total_size = sum((job_dir / c.file_path).stat().st_size for c in existing_clips)
        folders.append({
            "job_id": summary.job_id,
            "name": summary.title,
            "created_at": summary.created_at,
            "item_count": len(existing_clips),
            "total_size_bytes": total_size,
            "thumbnail_url": (
                f"/api/jobs/{summary.job_id}/thumbnail/{existing_clips[0].clip_id}"
                if existing_clips else None
            ),
        })
    return folders


def list_files(job_id: str) -> dict:
    job_dir, manifest = _load_manifest(job_id)
    files = []
    for clip in manifest.clips:
        p = job_dir / clip.file_path
        if not p.exists():
            continue  # individually trashed via delete_file() - manifest wasn't rewritten
        files.append({
            "clip_id": clip.clip_id,
            "name": f"{clip.clip_id}.mp4",
            "size_bytes": p.stat().st_size,
            "created_at": manifest.created_at,
            "variation_index": clip.variation_index,
        })
    return {"job_id": job_id, "name": manifest.title, "files": files}


def _clip_path(job_id: str, clip_id: str) -> Path:
    job_dir, manifest = _load_manifest(job_id)
    clip = next((c for c in manifest.clips if c.clip_id == clip_id), None)
    if clip is None:
        raise GalleryError("Файл не найден")
    return job_dir / clip.file_path


def delete_folder(job_id: str) -> None:
    job_dir = _job_dir(job_id)
    if not job_dir.exists():
        raise GalleryError("Папка не найдена")
    send2trash(str(job_dir))
    task_queue.delete_job(job_id)  # also drop it out of the Задачи list


def delete_file(job_id: str, clip_id: str) -> None:
    path = _clip_path(job_id, clip_id)
    if not path.exists():
        raise GalleryError("Файл не найден")
    send2trash(str(path))


def _run_reveal(args: list[str]) -> None:
    try:
        subprocess.run(args)
    except OSError as exc:
        # Missing file manager binary (e.g. no xdg-open on a headless/minimal
        # Linux box) - surface it as a normal API error, not a 500 crash.
        raise GalleryError(f"Не удалось открыть системный проводник: {exc}") from exc


def reveal_folder(job_id: str) -> None:
    job_dir, _manifest = _load_manifest(job_id)
    clips_dir = job_dir / "clips"
    system = platform.system()
    if system == "Windows":
        _run_reveal(["explorer", str(clips_dir)])
    elif system == "Darwin":
        _run_reveal(["open", str(clips_dir)])
    else:
        _run_reveal(["xdg-open", str(clips_dir)])


def reveal_file(job_id: str, clip_id: str) -> None:
    path = _clip_path(job_id, clip_id)
    system = platform.system()
    if system == "Windows":
        _run_reveal(["explorer", "/select,", str(path)])
    elif system == "Darwin":
        _run_reveal(["open", "-R", str(path)])
    else:
        _run_reveal(["xdg-open", str(path.parent)])
