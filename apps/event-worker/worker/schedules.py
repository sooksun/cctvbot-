"""School closed schedule checks (weekdays overnight + weekend all-day)."""

from __future__ import annotations

from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo


def _parse_hhmm(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def _in_window(now_t: time, start: time, end: time) -> bool:
    """True if now_t is within [start, end), supporting midnight-spanning windows."""
    if start == end:
        return True
    if start < end:
        return start <= now_t < end
    # spans midnight e.g. 18:00 -> 06:00
    return now_t >= start or now_t < end


def is_school_closed(now: datetime, schedule_config: dict[str, Any]) -> bool:
    """
    Return True when the school is closed per schedule_config.

    Expected shape:
      {
        "school_closed": {
          "weekdays": [{"start": "18:00", "end": "06:00"}],
          "weekends": "all_day"
        },
        "timezone": "Asia/Bangkok"
      }
    """
    tz_name = schedule_config.get("timezone", "Asia/Bangkok")
    tz = ZoneInfo(tz_name)
    if now.tzinfo is None:
        local = now.replace(tzinfo=tz)
    else:
        local = now.astimezone(tz)

    closed = schedule_config.get("school_closed") or {}
    weekends = closed.get("weekends", "all_day")
    weekday = local.weekday()  # Mon=0 .. Sun=6

    if weekday >= 5:  # Sat/Sun
        if weekends == "all_day":
            return True
        if isinstance(weekends, list):
            t = local.time().replace(tzinfo=None)
            for window in weekends:
                if _in_window(t, _parse_hhmm(window["start"]), _parse_hhmm(window["end"])):
                    return True
            return False
        return False

    windows = closed.get("weekdays") or []
    t = local.time().replace(second=0, microsecond=0)
    # compare without tz on time objects
    t = time(t.hour, t.minute, t.second)
    for window in windows:
        start = _parse_hhmm(window["start"])
        end = _parse_hhmm(window["end"])
        if _in_window(t, start, end):
            return True
    return False
