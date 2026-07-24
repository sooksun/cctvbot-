"""Unit tests for PersonMotionEnricher (rules 7 + 9 enrichment)."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from worker.enrichment import PersonMotionEnricher

TZ = ZoneInfo("Asia/Bangkok")
T0 = datetime(2026, 7, 25, 12, 0, 0, tzinfo=TZ)


def _person(track_id, box, camera_id="cam-yard"):
    return {"label": "person", "camera_id": camera_id, "track_id": track_id, "box": box}


def test_speed_zero_on_first_observation():
    enr = PersonMotionEnricher()
    d = _person("t1", [0.2, 0.2, 0.3, 0.4])
    enr.enrich(d, T0)
    assert d["speed"] == 0.0
    assert d["high_motion_duration_s"] == 0.0
    assert d["nearby_person_count"] == 1


def test_speed_computed_on_second_observation():
    enr = PersonMotionEnricher(speed_ema_alpha=0.5)
    enr.enrich(_person("t1", [0.2, 0.2, 0.3, 0.4]), T0)  # centroid x=0.25
    d2 = _person("t1", [0.5, 0.2, 0.6, 0.4])              # centroid x=0.55, moved 0.3
    enr.enrich(d2, T0 + timedelta(seconds=1))             # inst=0.3, ema=0.5*0.3=0.15
    assert abs(d2["speed"] - 0.15) < 1e-9


def test_high_motion_duration_accumulates_then_resets():
    enr = PersonMotionEnricher(speed_ema_alpha=1.0, high_motion_speed=0.12)
    enr.enrich(_person("t1", [0.2, 0.2, 0.3, 0.5]), T0)               # first obs, speed 0
    d1 = _person("t1", [0.5, 0.2, 0.6, 0.5])
    enr.enrich(d1, T0 + timedelta(seconds=1))                        # inst 0.3, high_since=t1
    assert d1["high_motion_duration_s"] == 0.0
    d2 = _person("t1", [0.2, 0.2, 0.3, 0.5])
    enr.enrich(d2, T0 + timedelta(seconds=3))                        # still fast, dur=3-1=2
    assert d2["high_motion_duration_s"] == 2.0
    d3 = _person("t1", [0.21, 0.2, 0.31, 0.5])                       # barely moves → slow
    enr.enrich(d3, T0 + timedelta(seconds=4))
    assert d3["high_motion_duration_s"] == 0.0


def test_nearby_counts_concurrent_persons():
    enr = PersonMotionEnricher(nearby_window_seconds=3.0)
    enr.enrich(_person("p1", [0.1, 0.1, 0.2, 0.2]), T0)
    d2 = _person("p2", [0.5, 0.5, 0.6, 0.6])
    enr.enrich(d2, T0 + timedelta(seconds=1))
    assert d2["nearby_person_count"] == 2


def test_end_event_decrements_nearby():
    enr = PersonMotionEnricher(nearby_window_seconds=10.0)
    enr.enrich(_person("p1", [0.1, 0.1, 0.2, 0.2]), T0)
    enr.enrich(_person("p2", [0.5, 0.5, 0.6, 0.6]), T0 + timedelta(seconds=1))
    enr.observe_end({"camera_id": "cam-yard", "track_id": "p2"}, T0 + timedelta(seconds=2))
    d = _person("p1", [0.1, 0.1, 0.2, 0.2])
    enr.enrich(d, T0 + timedelta(seconds=3))
    assert d["nearby_person_count"] == 1


def test_ttl_evicts_idle_tracks():
    enr = PersonMotionEnricher(track_ttl_seconds=60.0, nearby_window_seconds=300.0)
    enr.enrich(_person("p1", [0.1, 0.1, 0.2, 0.2]), T0)
    d = _person("p2", [0.5, 0.5, 0.6, 0.6])
    enr.enrich(d, T0 + timedelta(seconds=120))  # p1 idle > ttl → evicted
    assert d["nearby_person_count"] == 1
    assert len(enr._tracks) == 1


def test_non_person_is_noop():
    enr = PersonMotionEnricher()
    d = {"label": "bottle", "camera_id": "cam-yard", "track_id": "b1", "box": [0, 0, 1, 1]}
    enr.enrich(d, T0)
    assert "speed" not in d
    assert "nearby_person_count" not in d


def test_person_present_within_window():
    enr = PersonMotionEnricher(nearby_window_seconds=3.0)
    enr.enrich(_person("p1", [0.1, 0.1, 0.2, 0.2], camera_id="cam-a"), T0)
    assert enr.person_present("cam-a", T0 + timedelta(seconds=2)) is True
    assert enr.person_present("cam-a", T0 + timedelta(seconds=5)) is False
    assert enr.person_present("cam-b", T0) is False
    assert enr.person_present(None, T0) is False
