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

from backend.core.ffmpeg_utils import probe_resolution
from backend.models.schemas import TimeRange, VideoMetadata

logger = logging.getLogger("newtik.downloader")

ProgressCallback = Callable[[int, str], None]

# Historically this forced player_client=[android,ios,tv,web] to dodge a
# JS-interpreter dependency in yt-dlp's default ("web") client. That's now
# actively counter-productive: YouTube has since restricted android (SABR-only,
# no direct URL), ios (requires a PO token we don't provide) and tv (DRM) to the
# point where none of those 4 clients reliably yield usable formats any more -
# which silently starved every quality preset down to whatever scraps of a
# low-res format survived, regardless of the resolution cap below.
# yt-dlp itself now auto-selects a client set tailored to whether a JS runtime
# is available (falling back to 'android_vr' alone when it isn't - see
# _DEFAULT_JSLESS_CLIENTS in yt_dlp's youtube extractor) and that selection is
# actively updated by yt-dlp's maintainers as YouTube's restrictions change.
# Leaving extractor_args empty lets that logic run instead of freezing our own
# guess in place, which would only get more wrong over time.
_EXTRACTOR_ARGS: dict = {}

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


# The final export is a 1080x1920 vertical crop of the source (see overlay.py),
# NOT a plain resize - and cropping a 16:9 frame down to a 9:16 slice keeps
# only `source_height * 9/16` px of width. A 1080p (1920x1080) source is
# therefore cropped to a strip just ~607px wide, which then has to be
# *upscaled* ~1.8x to fill the 1080px-wide output - producing exactly the
# soft/blocky look users report even on the "highest" setting. Avoiding any
# upscale in that crop needs source_height >= 1920 (i.e. true 4K/2160p,
# since 1920*9/16 = 1080), which is why "detailed" caps at 2160 and not some
# lower "good enough" number - anything less always upscales in the crop
# regardless of encode CRF. "fast"/"medium" intentionally still cap lower as
# a real speed/size trade-off, accepting that softness.
_DOWNLOAD_HEIGHT_CAP = {
    "fast": 720,
    "medium": 1440,
    "detailed": 2160,
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

    # Confirms what actually landed on disk, independent of what we asked
    # for - the deciding evidence if a user reports bad quality again: this
    # line tells us whether yt-dlp really fetched a high-res stream or
    # quietly fell back to something lower (e.g. the source has no format
    # above 720p at all, which no setting here can work around).
    resolution = probe_resolution(result)
    logger.info("Download finished: %s (resolution=%s)", result.name, resolution or "unknown")
    return result
