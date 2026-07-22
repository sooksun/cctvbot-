"""Per (camera_id, event_type) debounce window."""

from __future__ import annotations

from datetime import datetime, timedelta


class Debouncer:
    def __init__(self, window_seconds: int = 60) -> None:
        self.window_seconds = window_seconds
        self._last: dict[tuple[str, str], datetime] = {}

    def should_emit(self, camera_id: str, event_type: str, now: datetime) -> bool:
        key = (camera_id, event_type)
        last = self._last.get(key)
        if last is not None and (now - last) < timedelta(seconds=self.window_seconds):
            return False
        self._last[key] = now
        return True
