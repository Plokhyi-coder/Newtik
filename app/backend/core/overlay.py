"""Fixed text overlay burn-in via moviepy.

Stage 3+ (subtitles, karaoke highlighting) will render ASS subtitles through
ffmpeg's subtitles filter instead, but the free-text overlay handled here
(screen 4 of the spec) stays a moviepy composite regardless, since it needs
draggable-grid positioning rather than word-level timing.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from moviepy import VideoFileClip, TextClip, CompositeVideoClip

from backend.config.settings import DEFAULT_FONT_PATH, OVERLAY_FONT_SIZE
from backend.models.schemas import TextOverlayConfig

logger = logging.getLogger("newtik.overlay")


class OverlayError(RuntimeError):
    pass


def apply_text_overlay(clip_path: Path, out_path: Path, config: TextOverlayConfig) -> None:
    """Writes clip_path with `config.text` burned in to out_path.

    If config.text is empty, the clip is copied through unchanged (no re-encode).
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not config.text.strip():
        shutil.copyfile(clip_path, out_path)
        return

    if DEFAULT_FONT_PATH is None:
        raise OverlayError(
            "Не найден системный шрифт для наложения текста. "
            "Укажите путь к .ttf в settings.DEFAULT_FONT_PATH."
        )

    video = VideoFileClip(str(clip_path))
    try:
        start = max(0.0, min(config.start_sec, video.duration))
        duration = max(0.0, min(config.duration_sec, video.duration - start))
        if duration <= 0:
            shutil.copyfile(clip_path, out_path)
            return

        text_clip = (
            TextClip(
                font=DEFAULT_FONT_PATH,
                text=config.text,
                font_size=OVERLAY_FONT_SIZE,
                color="white",
                stroke_color="black",
                stroke_width=2,
            )
            .with_position((config.position_x, config.position_y))
            .with_start(start)
            .with_duration(duration)
        )

        composite = CompositeVideoClip([video, text_clip]).with_duration(video.duration)
        composite.write_videofile(
            str(out_path), codec="libx264", audio_codec="aac", logger=None,
        )
        composite.close()
        text_clip.close()
    finally:
        video.close()
