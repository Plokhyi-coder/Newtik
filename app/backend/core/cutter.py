"""Sequential time-based cutting of a source file into fixed-length clips.

This is the MVP cutting mode ("no smart cutting"): the source is split back to
back into clip_length_sec chunks. Stream-copy is used for speed since
overlay.py re-encodes anyway when it burns text/subtitles onto the clip.
Smart-cutting (stage 4) will call suggest_cut_points() from highlight_scorer
instead of this fixed grid and pass the resulting timings to cut_segment().
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from backend.config.settings import MIN_LAST_SEGMENT_SEC
from backend.core.ffmpeg_utils import run_ffmpeg, probe_duration

logger = logging.getLogger("newtik.cutter")

ProgressCallback = Callable[[int, str], None]


@dataclass
class CutSegment:
    clip_id: str
    start: float
    end: float
    file_path: Path


def cut_segment(source: Path, start: float, end: float, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg([
        "-ss", str(start), "-i", str(source), "-t", str(end - start),
        "-c", "copy", "-avoid_negative_ts", "make_zero",
        str(out_path),
    ])


def cut_by_time(
    source: Path,
    out_dir: Path,
    clip_length_sec: int,
    on_progress: ProgressCallback | None = None,
) -> list[CutSegment]:
    total_duration = probe_duration(source)
    out_dir.mkdir(parents=True, exist_ok=True)

    boundaries: list[tuple[float, float]] = []
    cursor = 0.0
    while cursor < total_duration:
        end = min(cursor + clip_length_sec, total_duration)
        if end - cursor < MIN_LAST_SEGMENT_SEC and boundaries:
            # tail too short to be its own clip - drop it rather than ship a near-empty clip
            break
        boundaries.append((cursor, end))
        cursor = end

    segments: list[CutSegment] = []
    for i, (start, end) in enumerate(boundaries):
        clip_id = f"clip_{i:03d}"
        out_path = out_dir / f"{clip_id}.mp4"
        cut_segment(source, start, end, out_path)
        segments.append(CutSegment(clip_id=clip_id, start=start, end=end, file_path=out_path))
        if on_progress:
            pct = int((i + 1) / len(boundaries) * 100) if boundaries else 100
            on_progress(pct, f"клип {i + 1}/{len(boundaries)}")

    return segments
