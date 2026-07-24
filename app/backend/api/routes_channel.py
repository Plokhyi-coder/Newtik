from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core import channel_parser

router = APIRouter(prefix="/api", tags=["channel"])


class ParseChannelRequest(BaseModel):
    url: str


@router.post("/parse-channel")
def parse_channel(request: ParseChannelRequest) -> dict:
    try:
        return channel_parser.parse_channel(request.url)
    except channel_parser.ChannelParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
