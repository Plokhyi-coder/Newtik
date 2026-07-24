"""Pydantic models shared by API routes, task_queue and the results manifest.

Fields for later stages (scoring, variations, transcript) are already present
with neutral defaults so the manifest format does not change shape once those
stages land - the frontend can read the same JSON from day one.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class TimeRange(BaseModel):
    start_sec: float | None = None
    end_sec: float | None = None


class TextOverlayConfig(BaseModel):
    text: str = ""
    position_x: str = "center"  # "left" | "center" | "right"
    position_y: str = "bottom"  # "top" | "center" | "bottom"
    start_sec: float = 0.0
    duration_sec: float = 5.0


class VideoMetadata(BaseModel):
    source_url: str
    title: str
    duration_sec: float
    thumbnail_url: str | None = None


class QualityMode(str, Enum):
    FAST = "fast"
    MEDIUM = "medium"
    DETAILED = "detailed"


class JobCreateRequest(BaseModel):
    source_url: str
    time_range: TimeRange = Field(default_factory=TimeRange)
    clip_length_sec: int = 30
    smart_cut_enabled: bool = False
    variations_count: int = Field(default=0, ge=0, le=5)
    subtitles_enabled: bool = False  # reserved, stage 3/6
    quality: QualityMode = QualityMode.MEDIUM
    text_overlay: TextOverlayConfig = Field(default_factory=TextOverlayConfig)


class JobStage(str, Enum):
    QUEUED = "queued"
    DOWNLOAD = "download"
    CUT = "cut_or_analyze"
    TRANSCRIBE = "transcribe"
    OVERLAY = "subtitles_overlay"
    VARIATIONS = "variations"
    DONE = "done"
    ERROR = "error"


class JobProgress(BaseModel):
    stage: JobStage
    progress: int = 0  # 0-100 within the current stage
    message: str = ""


class ClipMeta(BaseModel):
    clip_id: str
    source_start: float
    source_end: float
    file_path: str  # relative to storage/jobs/{job_id}/clips
    thumbnail_path: str | None = None
    potential_score: float | None = None  # reserved, stage 4/5
    variation_index: int = 0  # 0 = original, 1..N = variation
    variation_techniques: list[str] = Field(default_factory=list)  # reserved, stage 7


class JobManifest(BaseModel):
    job_id: str
    source_url: str
    title: str
    created_at: str
    clips: list[ClipMeta] = Field(default_factory=list)


class JobSummary(BaseModel):
    """Lightweight per-job record for the "Задачи" list - written to
    job_meta.json on creation and refreshed on every progress update, so the
    task list survives an app restart even mid-job (the last-known progress
    just won't move again until this process re-runs it)."""

    job_id: str
    source_url: str
    title: str
    thumbnail_url: str | None = None
    created_at: str
    status: str = "queued"  # queued | running | done | error
    progress: JobProgress = Field(default_factory=lambda: JobProgress(stage=JobStage.QUEUED))
    finished_at: str | None = None
    error: str | None = None
