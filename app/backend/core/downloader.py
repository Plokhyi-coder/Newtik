"""yt-dlp wrapper: metadata lookup and range-limited download.

Only downloads the requested time range when one is given, via yt-dlp's
download_ranges/force_keyframes_at_cuts (equivalent of --download-sections).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

import yt_dlp
from yt_dlp.utils import download_range_func

from backend.models.schemas import TimeRange, VideoMetadata

logger = logging.getLogger("newtik.downloader")

ProgressCallback = Callable[[int, str], None]


class DownloadError(RuntimeError):
    """Raised for user-facing download failures (private/unavailable video, no network, ...)."""


def fetch_metadata(url: str) -> VideoMetadata:
    ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        raise DownloadError(f"Не удалось получить информацию о видео: {exc}") from exc

    return VideoMetadata(
        source_url=url,
        title=info.get("title", "Без названия"),
        duration_sec=float(info.get("duration") or 0),
        thumbnail_url=info.get("thumbnail"),
    )


def download_video(
    url: str,
    dest_dir: Path,
    job_id: str,
    time_range: TimeRange | None = None,
    on_progress: ProgressCallback | None = None,
) -> Path:
    """Downloads `url` into dest_dir/{job_id}.mp4, optionally limited to time_range."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(dest_dir / f"{job_id}.%(ext)s")

    def hook(d: dict) -> None:
        if not on_progress:
            return
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)
            pct = int(downloaded / total * 100) if total else 0
            on_progress(pct, "видео...")
        elif d["status"] == "finished":
            on_progress(100, "завершено, объединение потоков...")

    ydl_opts: dict = {
        "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best",
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
        "progress_hooks": [hook],
        "quiet": True,
        "no_warnings": True,
    }

    has_range = time_range and (time_range.start_sec is not None or time_range.end_sec is not None)
    if has_range:
        start = time_range.start_sec or 0
        end = time_range.end_sec  # None means "to the end" - yt-dlp accepts that
        ydl_opts["download_ranges"] = download_range_func(None, [(start, end)])
        ydl_opts["force_keyframes_at_cuts"] = True

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except yt_dlp.utils.DownloadError as exc:
        raise DownloadError(f"Не удалось скачать видео (недоступно/приватное?): {exc}") from exc

    result = dest_dir / f"{job_id}.mp4"
    if not result.exists():
        candidates = list(dest_dir.glob(f"{job_id}.*"))
        if not candidates:
            raise DownloadError("Файл после скачивания не найден на диске.")
        result = candidates[0]
    return result
