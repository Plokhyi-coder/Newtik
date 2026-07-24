"""Channel/profile parsing for the "Парсинг канала" tab.

Uses yt-dlp's flat playlist extraction to list a channel's recent uploads
without downloading anything. Per-video like/comment counts are NOT part of
that flat listing (YouTube only exposes them on the individual watch page),
so the videos the UI cares most about are enriched with a second, bounded
pass - deliberately capped, since each enrichment is its own network round
trip and a channel can have thousands of uploads.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime, timedelta, timezone

import yt_dlp

from backend.core.downloader import _EXTRACTOR_ARGS, _NETWORK_OPTS, _YtdlpLogger

logger = logging.getLogger("newtik.channel_parser")

# How many videos to list, and how many of those to enrich with full
# like/comment counts. Enrichment is one network request per video, so this
# is the main cost knob for how long a parse takes.
MAX_VIDEOS = 30
MAX_ENRICHED = 12

_PARSE_TIMEOUT_SEC = 180


class ChannelParseError(RuntimeError):
    pass


def _flat_opts() -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "playlistend": MAX_VIDEOS,
        "extractor_args": _EXTRACTOR_ARGS,
        "logger": _YtdlpLogger(),
        **_NETWORK_OPTS,
    }


def _video_opts() -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extractor_args": _EXTRACTOR_ARGS,
        "logger": _YtdlpLogger(),
        **_NETWORK_OPTS,
    }


def _pick_thumbnail(entry: dict) -> str | None:
    if entry.get("thumbnail"):
        return entry["thumbnail"]
    thumbs = entry.get("thumbnails") or []
    return thumbs[-1].get("url") if thumbs else None


def _parse_upload_date(entry: dict) -> str | None:
    # yt-dlp gives either a YYYYMMDD string or a unix timestamp, depending on
    # extractor and whether this came from a flat listing or a full extract.
    raw = entry.get("upload_date")
    if raw and len(str(raw)) == 8:
        try:
            return datetime.strptime(str(raw), "%Y%m%d").replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass
    ts = entry.get("timestamp")
    if ts:
        try:
            return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
        except (ValueError, OSError):
            pass
    return None


def _enrich(url: str) -> dict | None:
    """Full (non-flat) extract for one video, for like/comment counts."""
    try:
        with yt_dlp.YoutubeDL(_video_opts()) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception:
        logger.debug("Enrichment failed for %s", url, exc_info=True)
        return None


def _do_parse(url: str) -> dict:
    with yt_dlp.YoutubeDL(_flat_opts()) as ydl:
        info = ydl.extract_info(url, download=False)

    entries = [e for e in (info.get("entries") or []) if e]
    # A channel URL can resolve to a playlist-of-playlists (the channel's
    # tabs) rather than straight to videos - step one level down if so.
    if entries and entries[0].get("_type") == "playlist":
        nested = entries[0].get("entries") or []
        if nested:
            entries = [e for e in nested if e]

    videos: list[dict] = []
    for entry in entries[:MAX_VIDEOS]:
        video_url = entry.get("url") or entry.get("webpage_url")
        if entry.get("id") and (not video_url or not str(video_url).startswith("http")):
            video_url = f"https://www.youtube.com/watch?v={entry['id']}"
        videos.append({
            "id": entry.get("id"),
            "title": entry.get("title") or "Без названия",
            "url": video_url,
            "thumbnail": _pick_thumbnail(entry),
            "views": entry.get("view_count"),
            "likes": entry.get("like_count"),
            "comments": entry.get("comment_count"),
            "duration_sec": entry.get("duration"),
            "published_at": _parse_upload_date(entry),
        })

    # Enrich the newest few with the counts the flat listing can't provide.
    to_enrich = [v for v in videos[:MAX_ENRICHED] if v["url"]]
    if to_enrich:
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="newtik-parse") as pool:
            for video, full in zip(to_enrich, pool.map(lambda v: _enrich(v["url"]), to_enrich)):
                if not full:
                    continue
                video["views"] = full.get("view_count", video["views"])
                video["likes"] = full.get("like_count", video["likes"])
                video["comments"] = full.get("comment_count", video["comments"])
                video["duration_sec"] = full.get("duration", video["duration_sec"])
                video["published_at"] = _parse_upload_date(full) or video["published_at"]
                if not video["thumbnail"]:
                    video["thumbnail"] = _pick_thumbnail(full)

    channel = {
        "name": info.get("channel") or info.get("uploader") or info.get("title") or "Канал",
        "avatar": _channel_avatar(info),
        "subscribers": info.get("channel_follower_count"),
        "url": info.get("channel_url") or info.get("webpage_url") or url,
    }
    return {"channel": channel, "videos": videos, "totals": _totals(videos)}


def _channel_avatar(info: dict) -> str | None:
    for thumb in info.get("thumbnails") or []:
        # Channel avatars are square-ish; banners are very wide. Preferring a
        # roughly-square thumbnail avoids picking the banner by accident.
        w, h = thumb.get("width"), thumb.get("height")
        if w and h and 0.8 <= w / h <= 1.25:
            return thumb.get("url")
    return info.get("thumbnail")


def _totals(videos: list[dict]) -> dict:
    """Sums views/likes/comments over the videos published within the last
    day / week / month. Only covers the videos actually fetched (and, for
    likes/comments, only the enriched subset), so it's a recent-activity
    snapshot rather than lifetime channel totals - the UI labels it as such."""
    now = datetime.now(timezone.utc)
    windows = {"day": timedelta(days=1), "week": timedelta(days=7), "month": timedelta(days=30)}
    out: dict[str, dict] = {}

    for key, delta in windows.items():
        cutoff = now - delta
        bucket = {"views": 0, "likes": 0, "comments": 0, "videos": 0}
        for v in videos:
            if not v["published_at"]:
                continue
            try:
                published = datetime.fromisoformat(v["published_at"])
            except ValueError:
                continue
            if published < cutoff:
                continue
            bucket["videos"] += 1
            bucket["views"] += v["views"] or 0
            bucket["likes"] += v["likes"] or 0
            bucket["comments"] += v["comments"] or 0
        out[key] = bucket
    return out


def parse_channel(url: str) -> dict:
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="newtik-channel")
    future = executor.submit(_do_parse, url)
    try:
        return future.result(timeout=_PARSE_TIMEOUT_SEC)
    except FutureTimeoutError as exc:
        raise ChannelParseError(
            "Анализ канала занял слишком много времени и был прерван."
        ) from exc
    except Exception as exc:
        raise ChannelParseError(f"Не удалось проанализировать канал: {exc}") from exc
    finally:
        executor.shutdown(wait=False)
