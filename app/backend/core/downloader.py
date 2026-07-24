"""yt-dlp wrapper: metadata lookup and range-limited download.

Only downloads the requested time range when one is given, via yt-dlp's
download_ranges (equivalent of --download-sections). Deliberately does NOT
use force_keyframes_at_cuts: that flag makes yt-dlp re-encode the section
locally via ffmpeg to land exactly on the requested boundary, which for a
long/high-res source can mean several GB of RAM and 100% CPU for a very
long time with zero progress feedback (yt-dlp's progress_hooks only cover
the actual network download, not this postprocessing step) - indistinguishable
from a hang. cutter.py already re-cuts precisely from whatever we download
here, so a download boundary that's merely "close" (snapped to the nearest
keyframe, typically within a couple of seconds) costs nothing - the final
clip timing is unaffected.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from pathlib import Path
from typing import Callable

import yt_dlp
from yt_dlp.utils import download_range_func

from backend.models.schemas import TimeRange, VideoMetadata

logger = logging.getLogger("newtik.downloader")

ProgressCallback = Callable[[int, str], None]

# YouTube's default ("web") player client needs a JS interpreter to solve its
# signature/throttling obfuscation, which most machines don't have installed
# (yt-dlp logs a warning about it and can hang indefinitely resolving actual
# stream URLs rather than erroring out cleanly). android/ios/tv clients use
# unobfuscated or differently-handled URLs that don't need JS at all - listing
# them first means yt-dlp tries those before ever falling back to the
# JS-dependent web client.
_EXTRACTOR_ARGS = {"youtube": {"player_client": ["android", "ios", "tv", "web"]}}

# Hard ceiling on the whole download call. A range-limited, resolution-capped
# clip should never legitimately take this long - this exists purely so a
# stuck extraction (JS-runtime issues, YouTube-side weirdness, ...) fails
# loudly with a clear, actionable error instead of hanging the job forever
# with no way to recover short of restarting the app.
_DOWNLOAD_TIMEOUT_SEC = 300

# yt-dlp's own retry/warning messages otherwise vanish entirely under quiet=True,
# which made a real network stall look like a silent, undiagnosable hang - this
# routes them into app.log instead so a stuck job leaves a trail to look at.
class _YtdlpLogger:
    def debug(self, msg: str) -> None:
        logger.debug("[yt-dlp] %s", msg)

    def info(self, msg: str) -> None:
        logger.info("[yt-dlp] %s", msg)

    def warning(self, msg: str) -> None:
        logger.warning("[yt-dlp] %s", msg)

    def error(self, msg: str) -> None:
        logger.error("[yt-dlp] %s", msg)


# Bounds how long a stalled connection can hang for before yt-dlp gives up and
# raises, instead of retrying (near-)indefinitely with zero visible progress.
_NETWORK_OPTS = {
    "socket_timeout": 30,
    "retries": 5,
    "fragment_retries": 5,
}


class DownloadError(RuntimeError):
    """Raised for user-facing download failures (private/unavailable video, no network, ...)."""


# The final export is always scaled to a fixed 1080x1920 canvas (see
# overlay.py), so downloading source resolution above what that needs is
# pure waste - it slows the download and buys zero visible quality in the
# output. Capping this is also the main lever for the "Быстрый" quality
# preset to actually mean "faster" - previously it only changed the final
# encode preset/CRF, not what got downloaded in the first place.
_DOWNLOAD_HEIGHT_CAP = {
    "fast": 720,
    "medium": 1080,
    "detailed": 1440,
}


def _format_selector(quality: str | None) -> str:
    # Deliberately no [ext=mp4]/[ext=m4a] filters: YouTube very often serves
    # anything above ~480p only as VP9/AV1 in a webm container, with mp4/avc1
    # capped much lower (sometimes 360-480p) or absent above that. Requiring
    # mp4 here silently forced every quality preset down to that same
    # low-res mp4-only stream - "fast/medium/detailed" all produced identical,
    # visibly worse-than-source output no matter what the user picked.
    # download_video() already sets merge_output_format="mp4", which remuxes
    # (or, for incompatible codecs, transcodes) the final file to .mp4 - and
    # overlay.py always re-encodes to libx264 regardless of the source codec -
    # so the downloaded container/codec never reaches the user; only the
    # resolution cap below matters.
    cap = _DOWNLOAD_HEIGHT_CAP.get(quality or "")
    if cap is None:
        return "bv*+ba/b/best"
    return f"bv*[height<={cap}]+ba/b[height<={cap}]/best[height<={cap}]/best"


def fetch_metadata(url: str) -> VideoMetadata:
    ydl_opts = {
        "quiet": True, "no_warnings": True, "skip_download": True,
        "extractor_args": _EXTRACTOR_ARGS,
        "logger": _YtdlpLogger(), **_NETWORK_OPTS,
    }
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
    quality: str | None = None,
) -> Path:
    """Downloads `url` into dest_dir/{job_id}.mp4, optionally limited to time_range
    and capped to a resolution matching `quality` (fast/medium/detailed)."""
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
        "format": _format_selector(quality),
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
        "progress_hooks": [hook],
        "quiet": True,
        "no_warnings": True,
        "extractor_args": _EXTRACTOR_ARGS,
        "logger": _YtdlpLogger(),
        **_NETWORK_OPTS,
    }

    has_range = time_range and (time_range.start_sec is not None or time_range.end_sec is not None)
    if has_range:
        start = time_range.start_sec or 0
        end = time_range.end_sec  # None means "to the end" - yt-dlp accepts that
        ydl_opts["download_ranges"] = download_range_func(None, [(start, end)])
        # No force_keyframes_at_cuts here on purpose - see the module
        # docstring. The section boundary lands on the nearest keyframe
        # instead of exactly on start/end, which cutter.py's own re-cut
        # absorbs without any visible effect on the final clip.

    logger.info(
        "Starting yt-dlp download: quality=%s range=%s format=%s",
        quality, (time_range.start_sec, time_range.end_sec) if has_range else "full video",
        ydl_opts["format"],
    )

    def _do_download() -> None:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

    # Run on a throwaway thread so a hang can be turned into a clean error
    # after _DOWNLOAD_TIMEOUT_SEC - yt-dlp gives no way to cancel an
    # in-progress call, so a genuinely stuck extraction keeps running in the
    # background even after this raises, but the job itself stops blocking
    # the user instead of sitting frozen indefinitely.
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="newtik-ytdlp")
    future = executor.submit(_do_download)
    try:
        future.result(timeout=_DOWNLOAD_TIMEOUT_SEC)
    except FutureTimeoutError as exc:
        executor.shutdown(wait=False)
        logger.error("yt-dlp download exceeded %ss - treating as failed", _DOWNLOAD_TIMEOUT_SEC)
        raise DownloadError(
            "Скачивание видео заняло слишком много времени и было прервано. "
            "Проверьте интернет-соединение или попробуйте другое видео."
        ) from exc
    except yt_dlp.utils.DownloadError as exc:
        executor.shutdown(wait=False)
        raise DownloadError(f"Не удалось скачать видео (недоступно/приватное?): {exc}") from exc
    else:
        executor.shutdown(wait=False)

    result = dest_dir / f"{job_id}.mp4"
    if not result.exists():
        candidates = list(dest_dir.glob(f"{job_id}.*"))
        if not candidates:
            raise DownloadError("Файл после скачивания не найден на диске.")
        result = candidates[0]
    return result
