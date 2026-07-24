"""Audio-energy based "potential" scoring and smart cut-point suggestion.

This is a first pass at the algorithm described in the spec: an RMS loudness
curve over the whole video, normalized 0-100 relative to that same video,
used both to score clips (average curve value in range) and to nudge fixed
grid cut boundaries toward locally quiet points so a cut doesn't land
mid-sentence/mid-hit.

Keyword-trigger weighting and pause-after-emphasis detection (the rest of
the spec's algorithm) need word-level transcript timestamps, which the
project no longer produces - so those factors are simply absent from the
curve rather than faked. Everything here is a relative, heuristic
"priority" score, not a prediction of algorithmic reach - the UI already
frames it that way.
"""
from __future__ import annotations

import logging
import subprocess
import wave
from pathlib import Path

import numpy as np

from backend.core.ffmpeg_utils import check_ffmpeg_available

logger = logging.getLogger("newtik.highlight_scorer")

WINDOW_SEC = 1.0


def _extract_mono_wav(source: Path, out_wav: Path) -> None:
    check_ffmpeg_available()
    proc = subprocess.run(
        ["ffmpeg", "-y", "-i", str(source), "-ac", "1", "-ar", "16000", "-vn", str(out_wav)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Не удалось извлечь аудио для анализа: {proc.stderr[-2000:]}")


def build_score_curve(source: Path, tmp_dir: Path) -> np.ndarray:
    """RMS loudness per WINDOW_SEC-second window, normalized 0-100 relative to this video."""
    tmp_dir.mkdir(parents=True, exist_ok=True)
    wav_path = tmp_dir / "_audio_analysis.wav"
    _extract_mono_wav(source, wav_path)
    try:
        with wave.open(str(wav_path), "rb") as wf:
            sample_rate = wf.getframerate()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)
    finally:
        wav_path.unlink(missing_ok=True)

    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float64)
    if samples.size == 0:
        return np.zeros(1)

    window_size = int(WINDOW_SEC * sample_rate)
    n_windows = max(1, int(np.ceil(samples.size / window_size)))
    curve = np.zeros(n_windows)
    for i in range(n_windows):
        chunk = samples[i * window_size:(i + 1) * window_size]
        if chunk.size:
            curve[i] = np.sqrt(np.mean(chunk ** 2))

    curve_min, curve_max = float(curve.min()), float(curve.max())
    if curve_max - curve_min < 1e-6:
        return np.full(n_windows, 50.0)
    return (curve - curve_min) / (curve_max - curve_min) * 100


def score_clip(curve: np.ndarray, start_sec: float, end_sec: float) -> float:
    start_idx = max(0, int(start_sec / WINDOW_SEC))
    end_idx = min(len(curve), max(start_idx + 1, int(end_sec / WINDOW_SEC)))
    segment = curve[start_idx:end_idx]
    if segment.size == 0:
        return 0.0
    return round(float(np.mean(segment)), 1)


def _find_quiet_point_near(curve: np.ndarray, target_sec: float, tolerance_sec: float) -> float:
    """Searches +/- tolerance_sec around target_sec for the quietest instant."""
    center_idx = int(target_sec / WINDOW_SEC)
    span = max(1, int(tolerance_sec / WINDOW_SEC))
    lo = max(0, center_idx - span)
    hi = min(len(curve), center_idx + span + 1)
    if hi <= lo:
        return target_sec
    window = curve[lo:hi]
    best_idx = lo + int(np.argmin(window))
    return best_idx * WINDOW_SEC


def suggest_cut_points(
    curve: np.ndarray,
    total_duration: float,
    clip_length_sec: float,
    tolerance_sec: float = 3.0,
    min_segment_sec: float = 5.0,
) -> list[tuple[float, float]]:
    """"Whole video, sequentially" coverage mode: walks the timeline in
    clip_length_sec steps, nudging each interior boundary to the quietest
    point within tolerance_sec of it so a cut doesn't land mid-sentence.
    ("Only the best moments" peak-picking mode is not implemented yet.)
    """
    if total_duration <= 0:
        return []

    boundaries = [0.0]
    cursor = clip_length_sec
    while cursor < total_duration:
        boundaries.append(_find_quiet_point_near(curve, cursor, tolerance_sec))
        cursor += clip_length_sec
    boundaries.append(total_duration)

    # Nudging can make boundaries non-monotonic or produce a too-short tail segment.
    boundaries = sorted(set(boundaries))
    segments: list[tuple[float, float]] = []
    for start, end in zip(boundaries, boundaries[1:]):
        if end - start >= min_segment_sec:
            segments.append((start, end))
    return segments
