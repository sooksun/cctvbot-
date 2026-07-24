"""Unit tests for Rule 7: abnormal_motion + abnormal_crowd."""

from datetime import datetime
from zoneinfo import ZoneInfo

from worker.rules.abnormal_motion import (
    evaluate_abnormal_crowd,
    evaluate_abnormal_motion,
)

TZ = ZoneInfo("Asia/Bangkok")
T0 = datetime(2026, 7, 22, 11, 0, 0, tzinfo=TZ)


def _det(**extra):
    d = {
        "camera_id": "cam-hall",
        "camera_name": "cam-hall",
        "label": "person",
        "score": 0.88,
        "zones": ["hall"],
        "box": [0.4, 0.2, 0.55, 0.7],
        "track_id": "t-run-1",
        "started_at": T0,
        "current_at": T0,
        "speed": 0.0,
        "nearby_person_count": 1,
    }
    d.update(extra)
    return d


def test_abnormal_motion_above_threshold():
    r = evaluate_abnormal_motion(_det(speed=0.2), T0)
    assert r is not None
    assert r.event_type == "abnormal_motion"
    assert r.message_th.startswith("พบเหตุที่ควรตรวจสอบ:")
    assert r.severity == "medium"
    assert r.params["speed"] == 0.2


def test_abnormal_motion_default_threshold_boundary():
    # default run_speed_threshold = 0.15 — must be strictly greater
    assert evaluate_abnormal_motion(_det(speed=0.15), T0) is None
    assert evaluate_abnormal_motion(_det(speed=0.151), T0) is not None


def test_abnormal_motion_custom_threshold():
    cfg = {"run_speed_threshold": 0.3}
    assert evaluate_abnormal_motion(_det(speed=0.25), T0, cfg) is None
    r = evaluate_abnormal_motion(_det(speed=0.35), T0, cfg)
    assert r is not None
    assert r.event_type == "abnormal_motion"


def test_abnormal_motion_no_speed_none():
    d = _det()
    d.pop("speed")
    assert evaluate_abnormal_motion(d, T0) is None


def test_abnormal_motion_non_person_none():
    assert evaluate_abnormal_motion(_det(label="dog", speed=0.5), T0) is None


def test_abnormal_crowd_five_or_more():
    r = evaluate_abnormal_crowd(_det(nearby_person_count=5), T0)
    assert r is not None
    assert r.event_type == "abnormal_crowd"
    assert r.message_th.startswith("พบเหตุที่ควรตรวจสอบ:")
    assert "5" in r.message_th
    assert r.objects[0]["count"] == 5


def test_abnormal_crowd_under_threshold_none():
    assert evaluate_abnormal_crowd(_det(nearby_person_count=4), T0) is None


def test_abnormal_crowd_custom_threshold():
    cfg = {"crowd_threshold": 3}
    assert evaluate_abnormal_crowd(_det(nearby_person_count=2), T0, cfg) is None
    r = evaluate_abnormal_crowd(_det(nearby_person_count=3), T0, cfg)
    assert r is not None
    assert r.event_type == "abnormal_crowd"


def test_abnormal_crowd_missing_count_none():
    d = _det()
    d.pop("nearby_person_count")
    assert evaluate_abnormal_crowd(d, T0) is None
