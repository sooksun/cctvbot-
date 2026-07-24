"""Unit tests for person_after_hours and person_restricted rules."""

from datetime import datetime
from zoneinfo import ZoneInfo

from worker.rules.person_after_hours import evaluate_person_after_hours
from worker.rules.person_restricted import evaluate_person_restricted

TZ = ZoneInfo("Asia/Bangkok")

SCHEDULE = {
    "school_closed": {
        "weekdays": [{"start": "18:00", "end": "06:00"}],
        "weekends": "all_day",
    },
    "timezone": "Asia/Bangkok",
}

RULES = {
    "restricted_zones": {
        "cam-front": ["restricted", "roof"],
        "cam-back": ["server_room"],
    }
}


def _person(camera_id: str = "cam-front", zones: list[str] | None = None, **extra):
    d = {
        "camera_id": camera_id,
        "camera_name": camera_id,
        "label": "person",
        "score": 0.92,
        "zones": zones or [],
        "track_id": "t1",
    }
    d.update(extra)
    return d


def test_person_after_hours_tuesday_2200():
    now = datetime(2026, 7, 21, 22, 0, tzinfo=TZ)  # Tuesday closed
    result = evaluate_person_after_hours(_person(), now, SCHEDULE)
    assert result is not None
    assert result.event_type == "person_after_hours"
    assert result.message_th.startswith("พบเหตุที่ควรตรวจสอบ:")
    assert result.rule["code"] == "person_after_hours"
    assert result.severity == "high"
    assert result.camera_id == "cam-front"


def test_person_after_hours_open_daytime_none():
    now = datetime(2026, 7, 21, 10, 0, tzinfo=TZ)  # Tuesday open
    result = evaluate_person_after_hours(_person(), now, SCHEDULE)
    assert result is None


def test_person_after_hours_ignores_non_person():
    now = datetime(2026, 7, 21, 22, 0, tzinfo=TZ)
    result = evaluate_person_after_hours(
        _person(label="car"), now, SCHEDULE
    )
    assert result is None


def test_person_after_hours_weekend_afternoon():
    now = datetime(2026, 7, 25, 14, 0, tzinfo=TZ)  # Saturday
    result = evaluate_person_after_hours(_person(), now, SCHEDULE)
    assert result is not None
    assert result.event_type == "person_after_hours"


def test_person_restricted_zone_hit():
    now = datetime(2026, 7, 21, 10, 0, tzinfo=TZ)
    result = evaluate_person_restricted(
        _person(zones=["driveway", "restricted"]), now, RULES
    )
    assert result is not None
    assert result.event_type == "person_restricted_zone"
    assert result.message_th.startswith("พบเหตุที่ควรตรวจสอบ:")
    assert "restricted" in result.params["matched_zones"]


def test_person_restricted_no_intersection():
    now = datetime(2026, 7, 21, 10, 0, tzinfo=TZ)
    result = evaluate_person_restricted(
        _person(zones=["driveway"]), now, RULES
    )
    assert result is None


def test_person_restricted_wrong_camera_zone_map():
    now = datetime(2026, 7, 21, 10, 0, tzinfo=TZ)
    # restricted is only on cam-front, not cam-back
    result = evaluate_person_restricted(
        _person(camera_id="cam-back", zones=["restricted"]), now, RULES
    )
    assert result is None


def test_person_restricted_server_room_on_back():
    now = datetime(2026, 7, 21, 10, 0, tzinfo=TZ)
    result = evaluate_person_restricted(
        _person(camera_id="cam-back", zones=["server_room"]), now, RULES
    )
    assert result is not None
    assert result.event_type == "person_restricted_zone"
