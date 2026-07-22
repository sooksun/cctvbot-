from datetime import datetime
from zoneinfo import ZoneInfo

from worker.schedules import is_school_closed

DEFAULT_CONFIG = {
    "school_closed": {
        "weekdays": [
            {"start": "18:00", "end": "06:00"},
        ],
        "weekends": "all_day",
    },
    "timezone": "Asia/Bangkok",
}

TZ = ZoneInfo("Asia/Bangkok")


def test_tuesday_2200_is_closed():
    # Tuesday 2026-07-21 22:00 Asia/Bangkok
    now = datetime(2026, 7, 21, 22, 0, tzinfo=TZ)
    assert is_school_closed(now, DEFAULT_CONFIG) is True


def test_tuesday_1000_is_open():
    now = datetime(2026, 7, 21, 10, 0, tzinfo=TZ)
    assert is_school_closed(now, DEFAULT_CONFIG) is False


def test_weekday_after_midnight_before_end_is_closed():
    # Wednesday 05:00 still in overnight window that started Tue 18:00
    now = datetime(2026, 7, 22, 5, 0, tzinfo=TZ)
    assert is_school_closed(now, DEFAULT_CONFIG) is True


def test_weekday_after_morning_open():
    now = datetime(2026, 7, 22, 7, 0, tzinfo=TZ)
    assert is_school_closed(now, DEFAULT_CONFIG) is False


def test_saturday_all_day_closed():
    # Saturday 2026-07-25
    now = datetime(2026, 7, 25, 14, 0, tzinfo=TZ)
    assert is_school_closed(now, DEFAULT_CONFIG) is True


def test_sunday_all_day_closed():
    now = datetime(2026, 7, 26, 9, 0, tzinfo=TZ)
    assert is_school_closed(now, DEFAULT_CONFIG) is True


def test_naive_datetime_uses_config_timezone():
    # naive treated as local Asia/Bangkok
    now = datetime(2026, 7, 21, 22, 0)
    assert is_school_closed(now, DEFAULT_CONFIG) is True
