"""Small shared wrappers around the ffmpeg/ffprobe CLI (subprocess-based, no ffmpeg-python dependency)."""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger("newtik.ffmpeg")


class FfmpegNotFoundError(RuntimeError):
    """Raised when ffmpeg/ffprobe are not on PATH."""


def check_ffmpeg_available() -> None:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise FfmpegNotFoundError(
            "ffmpeg/ffprobe не найдены в PATH. Установите ffmpeg и перезапустите приложение."
        )


def probe_duration(path: Path) -> float:
    check_ffmpeg_available()
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json", str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def run_ffmpeg(args: list[str]) -> None:
    check_ffmpeg_available()
    cmd = ["ffmpeg", "-y", *args]
    logger.debug("ffmpeg command: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg завершился с ошибкой: {proc.stderr[-2000:]}")


def extract_thumbnail(video_path: Path, thumbnail_path: Path, at_sec: float = 0.5) -> None:
    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg([
        "-ss", str(at_sec), "-i", str(video_path),
        "-frames:v", "1", "-vf", "scale=320:-1",
        str(thumbnail_path),
    ])
