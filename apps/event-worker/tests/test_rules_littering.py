"""Unit tests for Rule 8: possible_littering."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from worker.rules.littering import LitteringTracker, evaluate_possible_littering

TZ = ZoneInfo("Asia/Bangkok")
T0 = datetime(2026, 7, 22, 12, 0, 0, tzinfo=TZ)


def _scene(**extra):
    d = {
        "camera_id": "cam-gate",
        "camera_name": "cam-gate",
        "label": "person",
        "score": 0.8,
        "zones": ["litter_watch"],
        "box": [0.3, 0.3, 0.5, 0.8],
        "track_id": "p1",
        "started_at": T0,
        "current_at": T0,
        "nearby_person_count": 1,
        "person_present": True,
        "objects": [
            {
                "label": "bottle",
                "box": [0.45, 0.4, 0.5, 0.5],
                "track_id": "b1",
                "zones": ["litter_watch"],
            }
        ],
    }
    d.update(extra)
    return d


def test_stateless_littering_happy_path():
    r = evaluate_possible_littering(
        _scene(drop_duration_s=5.0, downward_delta=0.1, in_litter_zone=True),
        T0 + timedelta(seconds=5),
    )
    assert r is not None
    assert r.event_type == "possible_littering"
    assert r.message_th.startswith("พบเหตุที่ควรตรวจสอบ:")
    assert r.severity == "low"
    assert r.zone == "litter_watch"


def test_stateless_no_proxy_objects_none():
    d = _scene(objects=[], drop_duration_s=5.0, downward_delta=0.1)
    d["label"] = "person"
    assert evaluate_possible_littering(d, T0) is None


def test_stateless_feature_flag_disabled():
    r = evaluate_possible_littering(
        _scene(drop_duration_s=5.0, downward_delta=0.1, in_litter_zone=True),
        T0,
        {"littering_enabled": False},
    )
    assert r is None


def test_stateless_duration_out_of_window():
    # too short
    assert (
        evaluate_possible_littering(
            _scene(drop_duration_s=2.0, downward_delta=0.1, in_litter_zone=True),
            T0,
        )
        is None
    )
    # too long
    assert (
        evaluate_possible_littering(
            _scene(drop_duration_s=9.0, downward_delta=0.1, in_litter_zone=True),
            T0,
        )
        is None
    )


def test_stateless_no_person_none():
    d = _scene(
        label="bottle",
        person_present=False,
        nearby_person_count=0,
        objects=[{"label": "bottle", "zones": ["litter_watch"], "box": [0.4, 0.5, 0.45, 0.6]}],
        drop_duration_s=5.0,
        downward_delta=0.1,
        in_litter_zone=True,
    )
    assert evaluate_possible_littering(d, T0) is None


def test_tracker_sequence_downward_in_zone():
    tracker = LitteringTracker()
    # t0: bottle high
    assert (
        tracker.update(
            {
                "camera_id": "cam-gate",
                "label": "person",
                "person_present": True,
                "nearby_person_count": 1,
                "current_at": T0,
                "objects": [
                    {
                        "label": "bottle",
                        "track_id": "b1",
                        "box": [0.45, 0.35, 0.5, 0.42],
                        "zones": ["litter_watch"],
                    }
                ],
            },
            T0,
        )
        is None
    )

    # t+4s: bottle lower (downward)
    r = tracker.update(
        {
            "camera_id": "cam-gate",
            "label": "person",
            "person_present": True,
            "nearby_person_count": 1,
            "current_at": T0 + timedelta(seconds=4),
            "objects": [
                {
                    "label": "bottle",
                    "track_id": "b1",
                    "box": [0.45, 0.55, 0.5, 0.62],
                    "zones": ["litter_watch"],
                }
            ],
        },
        T0 + timedelta(seconds=4),
    )
    assert r is not None
    assert r.event_type == "possible_littering"
    assert r.message_th.startswith("พบเหตุที่ควรตรวจสอบ:")


def test_tracker_person_only_model_returns_none():
    tracker = LitteringTracker()
    assert (
        tracker.update(
            {
                "camera_id": "cam-gate",
                "label": "person",
                "current_at": T0,
                "box": [0.3, 0.3, 0.5, 0.8],
                "zones": ["litter_watch"],
            },
            T0,
        )
        is None
    )
