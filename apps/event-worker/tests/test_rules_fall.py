"""Unit tests for Rule 2: person_fall_or_down."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from worker.rules.person_fall import FallTracker, evaluate_person_fall

TZ = ZoneInfo("Asia/Bangkok")
T0 = datetime(2026, 7, 22, 10, 0, 0, tzinfo=TZ)

# Horizontal box: width 0.4, height 0.2 → aspect 2.0
HORIZONTAL_BOX = [0.3, 0.6, 0.7, 0.8]
# Vertical standing person: width 0.15, height 0.45 → aspect ~0.33
VERTICAL_BOX = [0.4, 0.2, 0.55, 0.65]


def _det(**extra):
    d = {
        "camera_id": "cam-yard",
        "camera_name": "cam-yard",
        "label": "person",
        "score": 0.9,
        "zones": ["yard"],
        "box": list(HORIZONTAL_BOX),
        "track_id": "t-fall-1",
        "started_at": T0,
        "current_at": T0,
        "nearby_person_count": 1,
        "speed": 0.0,
    }
    d.update(extra)
    return d


def test_stateless_fall_after_15s_horizontal():
    result = evaluate_person_fall(
        _det(still_duration_s=15.0, aspect_ratio=2.0),
        T0 + timedelta(seconds=15),
    )
    assert result is not None
    assert result.event_type == "person_fall_or_down"
    assert result.message_th.startswith("พบเหตุที่ควรตรวจสอบ:")
    assert result.severity == "high"
    assert result.rule["code"] == "person_fall_or_down"


def test_stateless_fall_under_15s_none():
    assert (
        evaluate_person_fall(
            _det(still_duration_s=10.0, box=HORIZONTAL_BOX),
            T0 + timedelta(seconds=10),
        )
        is None
    )


def test_stateless_vertical_box_none():
    assert (
        evaluate_person_fall(
            _det(still_duration_s=20.0, box=VERTICAL_BOX),
            T0 + timedelta(seconds=20),
        )
        is None
    )


def test_stateless_pose_flag_overrides_box():
    result = evaluate_person_fall(
        _det(still_duration_s=15.0, box=VERTICAL_BOX, pose_fallen=True),
        T0 + timedelta(seconds=15),
    )
    assert result is not None
    assert result.event_type == "person_fall_or_down"


def test_stateless_non_person_none():
    assert (
        evaluate_person_fall(
            _det(label="car", still_duration_s=20.0),
            T0,
        )
        is None
    )


def test_tracker_sequence_horizontal_still_15s():
    tracker = FallTracker(still_seconds=15.0, move_threshold=0.02)
    # t=0 first frame — seed
    assert tracker.update(_det(box=HORIZONTAL_BOX, current_at=T0), T0) is None

    # small jitter under move threshold
    box_still = [0.301, 0.601, 0.701, 0.801]
    assert (
        tracker.update(
            _det(box=box_still, current_at=T0 + timedelta(seconds=10)),
            T0 + timedelta(seconds=10),
        )
        is None
    )

    # at 15s still → emit
    r = tracker.update(
        _det(box=box_still, current_at=T0 + timedelta(seconds=15)),
        T0 + timedelta(seconds=15),
    )
    assert r is not None
    assert r.event_type == "person_fall_or_down"
    assert r.message_th.startswith("พบเหตุที่ควรตรวจสอบ:")

    # no re-emit while still down
    assert (
        tracker.update(
            _det(box=box_still, current_at=T0 + timedelta(seconds=20)),
            T0 + timedelta(seconds=20),
        )
        is None
    )


def test_tracker_resets_on_large_move():
    tracker = FallTracker(still_seconds=15.0, move_threshold=0.02)
    tracker.update(_det(box=HORIZONTAL_BOX, current_at=T0), T0)
    # jump centroid far
    moved = [0.5, 0.6, 0.9, 0.8]
    tracker.update(_det(box=moved, current_at=T0 + timedelta(seconds=10)), T0 + timedelta(seconds=10))
    # only 10s after reset → none
    assert (
        tracker.update(
            _det(box=moved, current_at=T0 + timedelta(seconds=20)),
            T0 + timedelta(seconds=20),
        )
        is None
    )
