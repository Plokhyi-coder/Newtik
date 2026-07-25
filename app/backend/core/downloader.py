"""yt-dlp wrapper: metadata lookup and full-source download.

Always downloads the whole source video - deliberately does NOT use yt-dlp's
download_ranges/--download-sections. That looked like a nice bandwidth
optimization, but yt-dlp hardcodes routing ANY section-limited download
through its ffmpeg-based external downloader (see get_suitable_downloader in
yt_dlp/downloader/__init__.py: section_start/section_end always wins over the
native HTTP downloader, no config can override it), which invokes the
system's ffmpeg with the raw CDN URL and headers as command-line arguments.
That crashed outright on a real Windows install ("ffmpeg exited with code
<garbage>", instantly, every single time) - a known fragile combination
(very long signed CDN URLs / header passing over the OS command line).
task_queue.py does its own local trim (a plain, controlled ffmpeg -ss/-t
stream-copy, same shape as cutter.py's own cuts) right after this returns,
so the end result for the user is identical - it just costs extra bandwidth
for long sources instead of letting yt-dlp download only the needed range.
Also deliberately does NOT use force_keyframes_at_cuts for the same "no
naked ffmpeg re-encode of a long/high-res source" reasoning as before.
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from pathlib import Path
from typing import Callable

import yt_dlp

from backend.core.ffmpeg_utils import probe_resolution
from backend.models.schemas import VideoMetadata

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

# yt-dlp's CLI enables the "deno" JS runtime by default (used to solve the
# signature/"n"-parameter challenges YouTube's non-mobile clients require),
# but that default lives in the CLI's argument parser, not in YoutubeDL()
# itself - calling the Python API directly (as we do) with no js_runtimes
# entry means NO runtime is ever attempted, even if deno is installed and on
# PATH. That silently forced every download down yt-dlp's "no JS runtime"
# fallback path (a single, more limited client), regardless of what's
# actually available on the machine. start.bat installs a portable deno via
# winget; this just tells yt-dlp to look for it.
_JS_RUNTIMES = {"deno": {}}

# Hard ceiling on the whole download call. This used to guard a range-limited
# clip download, where 300s was already generous - but download_video() now
# always fetches the FULL source (see its docstring: section-limited download
# crashes ffmpeg on Windows), which for a long source at "detailed" (up to
# 2160p/4K) quality can legitimately be several GB and take well over 5
# minutes on an ordinary home connection. This exists to catch a genuinely
# stuck extraction (JS-runtime issues, YouTube-side weirdness, ...), not to
# second-guess a real, if slow, transfer - so it's set high enough that only
# an actual hang trips it.
_DOWNLOAD_TIMEOUT_SEC = 1800

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
        "js_runtimes": _JS_RUNTIMES,
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
    on_progress: ProgressCallback | None = None,
    quality: str | None = None,
) -> Path:
    """Downloads the full source video into dest_dir/{job_id}.mp4, capped to a
    resolution matching `quality` (fast/medium/detailed). Any time-range trim
    the user picked is applied afterward by task_queue.py, not here."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(dest_dir / f"{job_id}.%(ext)s")

    # Resolving the actual stream URL - signature/throttling challenges,
    # picking a format - happens before yt-dlp's progress_hooks ever fire, and
    # can legitimately take anywhere from a couple of seconds to a couple of
    # minutes depending on the network and YouTube's mood. Without some signal
    # during that window, the UI just sits frozen on "начало..." the whole
    # time, indistinguishable from being genuinely stuck - this heartbeat
    # gives the user something that visibly moves instead.
    hook_fired = threading.Event()
    last_logged_pct = -1

    def hook(d: dict) -> None:
        nonlocal last_logged_pct
        hook_fired.set()
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)
            pct = int(downloaded / total * 100) if total else 0
            # Throttled to every 10% - this is what future bad-quality/hang
            # reports need to tell "genuinely slow, real transfer, X% in Ys"
            # apart from "stuck at 0%", instead of relying on whatever the UI
            # happened to show at the moment of a screenshot.
            if pct >= last_logged_pct + 10 or (pct == 100 and last_logged_pct != 100):
                last_logged_pct = pct
                mb = f"{downloaded / 1_048_576:.0f}"
                total_mb = f"{total / 1_048_576:.0f}" if total else "?"
                logger.info("Download progress: %s%% (%s/%s MB)", pct, mb, total_mb)
            if on_progress:
                on_progress(pct, "видео...")
        elif d["status"] == "finished":
            if on_progress:
                on_progress(100, "завершено, объединение потоков...")

    def _heartbeat() -> None:
        waited = 0
        interval = 8
        while waited < _DOWNLOAD_TIMEOUT_SEC and not hook_fired.wait(timeout=interval):
            waited += interval
            if on_progress:
                on_progress(0, f"получение ссылки на видео... ({waited}с)")

    ydl_opts: dict = {
        "format": _format_selector(quality),
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
        "progress_hooks": [hook],
        "quiet": True,
        "no_warnings": True,
        "extractor_args": _EXTRACTOR_ARGS,
        "js_runtimes": _JS_RUNTIMES,
        "logger": _YtdlpLogger(),
        **_NETWORK_OPTS,
    }

    logger.info(
        "Starting yt-dlp download: quality=%s format=%s", quality, ydl_opts["format"],
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
    heartbeat_thread = threading.Thread(target=_heartbeat, daemon=True)
    heartbeat_thread.start()
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
    finally:
        hook_fired.set()  # let the heartbeat thread exit promptly either way

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
