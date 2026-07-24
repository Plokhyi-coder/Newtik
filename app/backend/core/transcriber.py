"""Speech-to-text via faster-whisper, used to burn auto-generated
subtitles into a clip. VAD filtering means stretches with no speech
produce no subtitle cue at all - silence stays silent instead of an
empty caption box sitting on screen, which is the whole point of doing
this with real transcription instead of a fixed on-screen timer.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from backend.config.settings import (
    WHISPER_COMPUTE_TYPE_CPU,
    WHISPER_COMPUTE_TYPE_CUDA,
    WHISPER_DEVICE,
    WHISPER_MODEL,
)

logger = logging.getLogger("newtik.transcriber")

_model = None  # loaded once on first use and reused across clips/jobs


@dataclass
class SubtitleCue:
    start: float
    end: float
    text: str


class TranscriptionError(RuntimeError):
    pass


def _resolve_device() -> str:
    if WHISPER_DEVICE != "auto":
        return WHISPER_DEVICE
    try:
        import ctranslate2

        return "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
    except Exception:
        return "cpu"


def is_model_loaded() -> bool:
    return _model is not None


def _get_model():
    global _model
    if _model is not None:
        return _model

    from faster_whisper import WhisperModel

    device = _resolve_device()
    compute_type = WHISPER_COMPUTE_TYPE_CUDA if device == "cuda" else WHISPER_COMPUTE_TYPE_CPU
    logger.info(
        "Loading Whisper model %s on %s (%s) - if this isn't cached locally yet, "
        "it downloads now and can take a while depending on connection speed",
        WHISPER_MODEL, device, compute_type,
    )
    _model = WhisperModel(WHISPER_MODEL, device=device, compute_type=compute_type)
    return _model


def transcribe(clip_path: Path) -> list[SubtitleCue]:
    """Transcribes clip_path. Timestamps are clip-relative (0 = the start
    of this clip), since each clip is transcribed independently rather than
    slicing a transcript of the full source video."""
    try:
        model = _get_model()
        segments, _info = model.transcribe(
            str(clip_path),
            vad_filter=True,
            word_timestamps=False,
        )
        return [
            SubtitleCue(start=seg.start, end=seg.end, text=seg.text.strip())
            for seg in segments
            if seg.text.strip()
        ]
    except Exception as exc:
        raise TranscriptionError(f"Не удалось распознать речь: {exc}") from exc


def _srt_timestamp(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def write_srt(cues: list[SubtitleCue], out_path: Path) -> None:
    lines: list[str] = []
    for i, cue in enumerate(cues, start=1):
        lines.append(str(i))
        lines.append(f"{_srt_timestamp(cue.start)} --> {_srt_timestamp(cue.end)}")
        lines.append(cue.text)
        lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")
