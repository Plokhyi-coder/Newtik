"""Vertical (9:16) export + fixed text overlay burn-in via ffmpeg filters.

Pure ffmpeg instead of moviepy: measured ~15x faster for clips with text
in testing (moviepy's per-frame Python compositing was the dominant cost,
not the final x264 preset), and it means the speed/quality mode selection
actually matters, since crop+scale+text+encode now happens in one native
ffmpeg pass instead of a Python frame-processing pass followed by encoding.

Every clip is center-cropped and scaled to 1080x1920 regardless of whether
a text overlay is set, since the target platforms (TikTok/Shorts/Reels)
all expect vertical video - a horizontal YouTube source needs this on
every run, not just when the user adds text.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from backend.config.settings import DEFAULT_FONT_PATH, OVERLAY_FONT_SIZE
from backend.core.ffmpeg_utils import run_ffmpeg
from backend.models.schemas import TextOverlayConfig

logger = logging.getLogger("newtik.overlay")

TARGET_W, TARGET_H = 1080, 1920  # 9:16 - TikTok/Shorts/Reels standard


@dataclass(frozen=True)
class VariationSpec:
    """One "duplicate" recipe: a combination of crop offset, speed, and color
    grade distinct enough that the variant doesn't read as an exact copy of
    the original clip, without being jarring to watch."""

    label: str
    crop_shift_frac: float  # -1..1, fraction of the available horizontal crop slack
    speed: float  # 1.0 = unchanged; passed to setpts (video) and atempo (audio)
    eq: str  # ffmpeg eq= filter argument string ("contrast=..:saturation=..")


# Cycled by index when variations_count > len(VARIATION_RECIPES) is disallowed
# by the schema (max 5), so every requested variant maps to exactly one recipe.
VARIATION_RECIPES: list[VariationSpec] = [
    VariationSpec("смещение влево, тёплые тона", -0.6, 1.05, "contrast=1.05:brightness=0.02:saturation=1.15"),
    VariationSpec("смещение вправо, холодные тона", 0.6, 0.96, "contrast=1.05:saturation=0.9"),
    VariationSpec("яркие цвета, ускорение", 0.0, 1.08, "contrast=1.15:saturation=1.4"),
    VariationSpec("выше контраст, лёгкое смещение", -0.3, 1.0, "contrast=1.2:brightness=-0.02"),
    VariationSpec("приглушённые тона, замедление", 0.3, 0.94, "contrast=0.95:saturation=0.75"),
]

# Speed vs. quality tradeoff, picked by the user on screen 2 ("Быстрый/Средний/Детальный").
# ultrafast/high-CRF trades noticeably worse compression efficiency for much faster
# encodes - the right call for "I need this NOW", less so if only a couple of clips.
QUALITY_PRESETS: dict[str, dict[str, str | int]] = {
    "fast": {"preset": "ultrafast", "crf": 30},
    "medium": {"preset": "veryfast", "crf": 23},
    "detailed": {"preset": "slow", "crf": 18},
}

_POSITION_X_EXPR = {"left": "40", "center": "(w-text_w)/2", "right": "w-text_w-40"}
_POSITION_Y_EXPR = {"top": "40", "center": "(h-text_h)/2", "bottom": "h-text_h-100"}


class OverlayError(RuntimeError):
    pass


def _escape_ffmpeg_path(path: str) -> str:
    """Escapes a filesystem path for use inside an ffmpeg filter option value
    (fontfile=/textfile=). Colons are the filter-argument separator, so a
    Windows drive letter like "C:" needs escaping; backslashes are normalized
    to forward slashes first since ffmpeg accepts those on Windows too."""
    return path.replace("\\", "/").replace(":", "\\:")


def apply_text_overlay(
    clip_path: Path,
    out_path: Path,
    config: TextOverlayConfig,
    quality: str = "medium",
    variation: VariationSpec | None = None,
) -> None:
    """Writes clip_path center-cropped to 9:16, with `config.text` burned in if set.

    `variation`, when given, nudges the crop window off-center, re-grades
    color via an eq filter, and retimes the clip (video setpts + audio
    atempo) - enough visual difference between "duplicate" variants that
    they don't look like the exact same export five times over.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    preset = QUALITY_PRESETS.get(quality, QUALITY_PRESETS["medium"])

    # crop dimensions are expressions ffmpeg evaluates itself (iw/ih = input size),
    # so this works for any source resolution without probing it in Python first.
    crop_w = r"min(iw\,ih*9/16)"
    crop_h = r"min(ih\,iw*16/9)"
    shift = variation.crop_shift_frac if variation else 0.0
    # (iw-crop_w)/2 is the centered offset; the *(1+shift) term nudges it
    # toward one edge without ever exceeding the available slack.
    crop_x_expr = f"(iw-{crop_w})/2*(1+({shift}))" if shift else f"(iw-{crop_w})/2"
    filters = [
        f"crop='{crop_w}':'{crop_h}':x='{crop_x_expr}':y='(ih-{crop_h})/2'",
        f"scale={TARGET_W}:{TARGET_H}",
    ]
    if variation and variation.eq:
        filters.append(f"eq={variation.eq}")

    textfile_path: Path | None = None
    try:
        if config.text.strip():
            if DEFAULT_FONT_PATH is None:
                raise OverlayError(
                    "Не найден системный шрифт для наложения текста. "
                    "Укажите путь к .ttf в settings.DEFAULT_FONT_PATH."
                )
            # textfile= (rather than text=) sidesteps most escaping headaches for
            # arbitrary user-entered text - only the path itself needs escaping.
            textfile_path = out_path.with_suffix(".overlaytext.txt")
            textfile_path.write_text(config.text, encoding="utf-8")

            start = max(0.0, config.start_sec)
            end = start + max(0.0, config.duration_sec)
            x_expr = _POSITION_X_EXPR.get(config.position_x, _POSITION_X_EXPR["center"])
            y_expr = _POSITION_Y_EXPR.get(config.position_y, _POSITION_Y_EXPR["bottom"])
            filters.append(
                "drawtext="
                f"fontfile='{_escape_ffmpeg_path(DEFAULT_FONT_PATH)}':"
                f"textfile='{_escape_ffmpeg_path(str(textfile_path))}':"
                f"fontsize={OVERLAY_FONT_SIZE}:fontcolor=white:bordercolor=black:borderw=2:"
                f"x={x_expr}:y={y_expr}:"
                rf"enable='between(t\,{start}\,{end})'"
            )

        # setpts is appended last (after drawtext) so drawtext's between(t,..)
        # window still refers to the original timeline, not the sped-up one.
        if variation and variation.speed != 1.0:
            filters.append(f"setpts=PTS/{variation.speed}")

        args = ["-i", str(clip_path), "-vf", ",".join(filters)]
        if variation and variation.speed != 1.0:
            args += ["-af", f"atempo={variation.speed}"]
        args += [
            "-c:v", "libx264", "-preset", str(preset["preset"]), "-crf", str(preset["crf"]),
            "-c:a", "aac", "-movflags", "+faststart",
            str(out_path),
        ]
        run_ffmpeg(args)
    finally:
        if textfile_path is not None:
            textfile_path.unlink(missing_ok=True)
