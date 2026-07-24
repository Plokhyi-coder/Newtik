"""Desktop OS notifications on job completion/error, gated by a small
on-disk toggle so the setting survives restarts and the settings popup
and the backend always agree on the same state without a live connection
between them.
"""
from __future__ import annotations

import json
import logging

from backend.config.settings import STORAGE_DIR

logger = logging.getLogger("newtik.notifications")

_SETTINGS_PATH = STORAGE_DIR / "notification_settings.json"


def is_enabled() -> bool:
    try:
        data = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
        return bool(data.get("enabled", True))
    except (OSError, ValueError):
        return True  # on by default until the user turns it off


def set_enabled(enabled: bool) -> None:
    _SETTINGS_PATH.write_text(json.dumps({"enabled": enabled}), encoding="utf-8")


def notify(title: str, message: str) -> None:
    if not is_enabled():
        return
    try:
        # Imported lazily - plyer pulls in a platform-specific backend
        # (win10toast/pyobjus/notify2) that isn't guaranteed to be usable
        # everywhere (e.g. a headless Linux box with no notification
        # daemon), and a failure here must never take down a job.
        from plyer import notification

        notification.notify(title=title, message=message, app_name="Newtik", timeout=6)
    except Exception:
        logger.warning("Desktop notification failed (non-fatal)", exc_info=True)
