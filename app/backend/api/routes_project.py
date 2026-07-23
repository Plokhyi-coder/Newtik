from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.downloader import DownloadError, fetch_metadata
from backend.models.schemas import VideoMetadata

router = APIRouter(prefix="/api", tags=["project"])


class AnalyzeRequest(BaseModel):
    url: str


@router.post("/analyze", response_model=VideoMetadata)
def analyze(request: AnalyzeRequest) -> VideoMetadata:
    try:
        return fetch_metadata(request.url)
    except DownloadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
