"""Unit tests for Rule 9: possible_fight."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from worker.rules.fight import FightTracker, evaluate_possible_fight

TZ = ZoneInfo("Asia/Bangkok")
T0 = datetime(2026, 7, 22, 13, 0, 0, tzinfo=TZ)


def _det(**extra):
    d = {
        "camera_id": "cam-yard",
        "camera_name": "cam-yard",
        "label": "person",
        "score": 0.85,
        "zones": ["yard"],
        "box": [0.4, 0.2, 0.55, 0.7],
        "track_id": "t1",
        "started_at": T0,
        "current_at": T0,
        "nearby_person_count": 2,
        "speed": 0.2,
        "high_motion_duration_s": 3.0,
    }
    d.update(extra)
    return d


def test_stateless_fight_happy_path():
    r = evaluate_possible_fight(_det(), T0)
    assert r is not None
    assert r.event_type == "possible_fight"
    assert r.message_th.startswith("พบเหตุที่ควรตรวจสอบ:")
    assert r.severity == "high"
    assert r.objects[0]["count"] == 2


def test_stateless_single_person_none():
    assert (
        evaluate_possible_fight(
            _det(nearby_person_count=1, high_motion_duration_s=5.0),
            T0,
        )
        is None
    )


def test_stateless_short_motion_none():
    assert (
        evaluate_possible_fight(
            _det(nearby_person_count=3, high_motion_duration_s=2.0),
            T0,
        )
        is None
    )


def test_stateless_low_speed_when_provided_none():
    assert (
        evaluate_possible_fight(
            _det(speed=0.01, high_motion_duration_s=5.0),
            T0,
        )
        is None
    )


def test_tracker_sequence_high_motion_3s():
    tracker = FightTracker(motion_seconds=3.0, speed_threshold=0.12)
    # t0 seed
    assert (
        tracker.update(
            _det(nearby_person_count=2, speed=0.2, current_at=T0),
            T0,
        )
        is None
    )
    # t+2s still under threshold
    assert (
        tracker.update(
            _det(
                nearby_person_count=2,
                speed=0.25,
                current_at=T0 + timedelta(seconds=2),
            ),
            T0 + timedelta(seconds=2),
        )
        is None
    )
    # t+3s emit
    r = tracker.update(
        _det(
            nearby_person_count=3,
            speed=0.22,
            current_at=T0 + timedelta(seconds=3),
        ),
        T0 + timedelta(seconds=3),
    )
    assert r is not None
    assert r.event_type == "possible_fight"
    assert r.message_th.startswith("พบเหตุที่ควรตรวจสอบ:")
    assert r.params["nearby_person_count"] >= 2

    # no re-emit
    assert (
        tracker.update(
            _det(
                nearby_person_count=3,
                speed=0.3,
                current_at=T0 + timedelta(seconds=4),
            ),
            T0 + timedelta(seconds=4),
        )
        is None
    )


def test_tracker_resets_when_count_drops():
    tracker = FightTracker(motion_seconds=3.0)
    tracker.update(_det(nearby_person_count=2, speed=0.2, current_at=T0), T0)
    # count drops
    tracker.update(
        _det(nearby_person_count=1, speed=0.2, current_at=T0 + timedelta(seconds=2)),
        T0 + timedelta(seconds=2),
    )
    # restart — only 1s of high motion with 2 persons
    assert (
        tracker.update(
            _det(
                nearby_person_count=2,
                speed=0.2,
                current_at=T0 + timedelta(seconds=3),
            ),
            T0 + timedelta(seconds=3),
        )
        is None
    )


def test_tracker_flag_high_relative_motion():
    tracker = FightTracker(motion_seconds=3.0)
    tracker.update(
        _det(
            nearby_person_count=2,
            speed=None,
            high_relative_motion=True,
            current_at=T0,
        ),
        T0,
    )
    r = tracker.update(
        _det(
            nearby_person_count=2,
            speed=None,
            high_relative_motion=True,
            current_at=T0 + timedelta(seconds=3),
        ),
        T0 + timedelta(seconds=3),
    )
    assert r is not None
    assert r.event_type == "possible_fight"
