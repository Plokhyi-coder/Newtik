from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from backend.core import notifications

router = APIRouter(prefix="/api/settings", tags=["settings"])


class NotificationSettings(BaseModel):
    enabled: bool


@router.get("/notifications", response_model=NotificationSettings)
def get_notifications() -> NotificationSettings:
    return NotificationSettings(enabled=notifications.is_enabled())


@router.put("/notifications", response_model=NotificationSettings)
def set_notifications(payload: NotificationSettings) -> NotificationSettings:
    notifications.set_enabled(payload.enabled)
    return payload
