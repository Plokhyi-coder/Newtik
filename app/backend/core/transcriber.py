"""Speech-to-text via faster-whisper, used to burn auto-generated
subtitles into a clip. VAD filtering means stretches with no speech
produce no subtitle cue at all - silence stays silent instead of an
empty caption box sitting on screen, which is the whole point of doing
this with real transcription instead of a fixed on-screen timer.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
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
_model_device: str | None = None  # which device _model was actually built for
_gpu_disabled = False  # set once a CUDA failure proves the GPU path unusable

# Hard ceiling per clip. Whisper on CPU is slow but bounded; a transcription
# that blows past this is stuck (a half-initialized CUDA context wedging on
# the next call is the observed case) rather than merely slow, and without
# this the whole job hangs with no way out.
_TRANSCRIBE_TIMEOUT_SEC = 600


@dataclass
class SubtitleCue:
    start: float
    end: float
    text: str


class TranscriptionError(RuntimeError):
    pass


def _resolve_device() -> str:
    if _gpu_disabled:
        return "cpu"
    if WHISPER_DEVICE != "auto":
        return WHISPER_DEVICE
    try:
        import ctranslate2

        return "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
    except Exception:
        return "cpu"


def is_model_loaded() -> bool:
    return _model is not None


def _load_model(device: str):
    from faster_whisper import WhisperModel

    compute_type = WHISPER_COMPUTE_TYPE_CUDA if device == "cuda" else WHISPER_COMPUTE_TYPE_CPU
    logger.info(
        "Loading Whisper model %s on %s (%s) - if this isn't cached locally yet, "
        "it downloads now and can take a while depending on connection speed",
        WHISPER_MODEL, device, compute_type,
    )
    return WhisperModel(WHISPER_MODEL, device=device, compute_type=compute_type)


def _get_model(device: str):
    global _model, _model_device
    if _model is not None and _model_device == device:
        return _model
    _model = _load_model(device)
    _model_device = device
    return _model


def _run_transcribe(model, clip_path: Path) -> list[SubtitleCue]:
    segments, _info = model.transcribe(
        str(clip_path),
        vad_filter=True,
        word_timestamps=False,
    )
    # faster-whisper returns a lazy generator - the actual decoding (and so
    # any CUDA failure) happens while consuming it, which is why this is
    # materialized here inside the guarded call rather than by the caller.
    return [
        SubtitleCue(start=seg.start, end=seg.end, text=seg.text.strip())
        for seg in segments
        if seg.text.strip()
    ]


def _transcribe_on(device: str, clip_path: Path) -> list[SubtitleCue]:
    """Runs one transcription attempt on `device` under a hard timeout."""
    model = _get_model(device)
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="newtik-whisper")
    future = executor.submit(_run_transcribe, model, clip_path)
    try:
        return future.result(timeout=_TRANSCRIBE_TIMEOUT_SEC)
    except FutureTimeoutError as exc:
        raise TranscriptionError(
            f"Распознавание речи не завершилось за {_TRANSCRIBE_TIMEOUT_SEC} сек и было прервано"
        ) from exc
    finally:
        executor.shutdown(wait=False)


def transcribe(clip_path: Path) -> list[SubtitleCue]:
    """Transcribes clip_path. Timestamps are clip-relative (0 = the start
    of this clip), since each clip is transcribed independently rather than
    slicing a transcript of the full source video.

    Falls back from GPU to CPU permanently on the first CUDA failure: a
    machine can report a CUDA device while still missing the CUDA runtime
    DLLs faster-whisper needs (cublas/cudnn), which fails at the first
    decode rather than at model load. Retrying that same broken GPU model
    for every subsequent clip is what turned one clean error into an
    apparent hang, so the device choice is downgraded process-wide, not
    per-call.
    """
    global _model, _model_device, _gpu_disabled

    device = _resolve_device()
    try:
        return _transcribe_on(device, clip_path)
    except Exception as exc:
        if device != "cuda":
            if isinstance(exc, TranscriptionError):
                raise
            raise TranscriptionError(f"Не удалось распознать речь: {exc}") from exc

        logger.warning(
            "Whisper failed on GPU (%s) - falling back to CPU for this and all "
            "later clips. Install the CUDA runtime libraries (cuBLAS/cuDNN) "
            "to use the GPU instead.", exc,
        )
        _gpu_disabled = True
        _model = None
        _model_device = None

    try:
        return _transcribe_on("cpu", clip_path)
    except TranscriptionError:
        raise
    except Exception as cpu_exc:
        raise TranscriptionError(f"Не удалось распознать речь: {cpu_exc}") from cpu_exc


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
