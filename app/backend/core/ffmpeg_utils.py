"""Small shared wrappers around the ffmpeg/ffprobe CLI (subprocess-based, no ffmpeg-python dependency)."""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger("newtik.ffmpeg")


class FfmpegNotFoundError(RuntimeError):
    """Raised when ffmpeg/ffprobe are not on PATH."""


def ensure_ffmpeg_on_path() -> None:
    """Best-effort auto-repair for the common Windows situation where ffmpeg was
    installed (e.g. via winget) after this process's PATH snapshot was taken -
    a plain `pip install`/`python main.py` launched from an old shell session
    never sees a PATH change made afterwards, even though the binary is on disk.
    Called once at app startup so the app self-heals regardless of how it was
    launched, instead of requiring the user to fix their shell's PATH by hand.
    """
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return

    candidate_dirs: list[Path] = []
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        winget_packages = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        if winget_packages.is_dir():
            try:
                candidate_dirs += [p.parent for p in winget_packages.rglob("ffmpeg.exe")]
            except OSError:
                pass
    candidate_dirs += [Path("C:/ffmpeg/bin"), Path("C:/Program Files/ffmpeg/bin")]

    for bin_dir in candidate_dirs:
        if (bin_dir / "ffmpeg.exe").exists() or (bin_dir / "ffmpeg").exists():
            os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
            logger.info("Auto-detected ffmpeg at %s, added to this process's PATH", bin_dir)
            return


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
