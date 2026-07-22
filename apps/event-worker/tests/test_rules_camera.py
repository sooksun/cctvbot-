"""Unit tests for OfflineTracker and tamper signals."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from worker.rules.camera_health import (
    LuminanceTamperTracker,
    OfflineTracker,
    evaluate_tamper_signal,
    maybe_tamper,
)

TZ = ZoneInfo("Asia/Bangkok")
T0 = datetime(2026, 7, 22, 12, 0, 0, tzinfo=TZ)


def test_offline_not_yet_under_threshold():
    tracker = OfflineTracker(threshold_seconds=30)
    stats = {"cameras": {"cam-front": {"camera_fps": 0.0}}}
    assert tracker.update(stats, T0) == []
    assert tracker.update(stats, T0 + timedelta(seconds=29)) == []


def test_offline_emits_after_30s():
    tracker = OfflineTracker(threshold_seconds=30)
    stats = {"cameras": {"cam-front": {"camera_fps": 0.0}}}
    tracker.update(stats, T0)
    results = tracker.update(stats, T0 + timedelta(seconds=30))
    assert len(results) == 1
    r = results[0]
    assert r.event_type == "camera_offline"
    assert r.camera_id == "cam-front"
    assert r.message_th.startswith("พบเหตุที่ควรตรวจสอบ:")
    assert r.severity == "critical"


def test_offline_missing_from_stats_with_known():
    tracker = OfflineTracker(threshold_seconds=30)
    # first see camera healthy so it becomes known
    tracker.update({"cameras": {"cam-a": {"camera_fps": 5.0}}}, T0)
    # then disappear
    empty = {"cameras": {}}
    tracker.update(empty, T0 + timedelta(seconds=1), known_cameras=["cam-a"])
    results = tracker.update(
        empty, T0 + timedelta(seconds=31), known_cameras=["cam-a"]
    )
    assert len(results) == 1
    assert results[0].event_type == "camera_offline"
    assert results[0].camera_id == "cam-a"


def test_offline_emits_once_until_recovery():
    tracker = OfflineTracker(threshold_seconds=30)
    stats = {"cameras": {"cam-front": {"camera_fps": 0.0}}}
    tracker.update(stats, T0)
    r1 = tracker.update(stats, T0 + timedelta(seconds=30))
    r2 = tracker.update(stats, T0 + timedelta(seconds=60))
    assert len(r1) == 1
    assert r2 == []


def test_offline_recovery_allows_reemit():
    tracker = OfflineTracker(threshold_seconds=30)
    down = {"cameras": {"cam-front": {"camera_fps": 0.0}}}
    up = {"cameras": {"cam-front": {"camera_fps": 8.0}}}
    tracker.update(down, T0)
    assert len(tracker.update(down, T0 + timedelta(seconds=30))) == 1
    # recover
    assert tracker.update(up, T0 + timedelta(seconds=40)) == []
    # down again
    tracker.update(down, T0 + timedelta(seconds=41))
    r = tracker.update(down, T0 + timedelta(seconds=71))
    assert len(r) == 1
    assert r[0].event_type == "camera_offline"


def test_healthy_fps_no_emit():
    tracker = OfflineTracker(threshold_seconds=30)
    stats = {"cameras": {"cam-front": {"camera_fps": 5.2}}}
    assert tracker.update(stats, T0) == []
    assert tracker.update(stats, T0 + timedelta(seconds=60)) == []


def test_tamper_explicit_signal():
    r = evaluate_tamper_signal({"signal": "tamper", "camera_id": "cam-x"}, T0)
    assert r is not None
    assert r.event_type == "camera_tamper"
    assert r.camera_id == "cam-x"
    assert r.message_th.startswith("พบเหตุที่ควรตรวจสอบ:")


def test_tamper_black_label():
    r = evaluate_tamper_signal(
        {"label": "black", "camera_id": "cam-y", "score": 0.95}, T0
    )
    assert r is not None
    assert r.event_type == "camera_tamper"


def test_tamper_no_signal():
    assert evaluate_tamper_signal({"label": "person", "camera_id": "c"}, T0) is None
    assert evaluate_tamper_signal({"signal": "tamper"}, T0) is None  # no camera


def test_maybe_tamper_stub_returns_none():
    assert maybe_tamper(None) is None
    assert maybe_tamper(0.01) is None


def test_luminance_streak_three():
    tracker = LuminanceTamperTracker(luminance_threshold=10.0, streak_required=3)
    assert tracker.update_luminance("cam-z", 5.0, T0) is None
    assert tracker.update_luminance("cam-z", 4.0, T0 + timedelta(seconds=30)) is None
    r = tracker.update_luminance("cam-z", 3.0, T0 + timedelta(seconds=60))
    assert r is not None
    assert r.event_type == "camera_tamper"
    # no re-emit while still dark
    assert tracker.update_luminance("cam-z", 2.0, T0 + timedelta(seconds=90)) is None


def test_luminance_reset_on_bright():
    tracker = LuminanceTamperTracker(luminance_threshold=10.0, streak_required=3)
    tracker.update_luminance("cam-z", 5.0, T0)
    tracker.update_luminance("cam-z", 5.0, T0 + timedelta(seconds=1))
    tracker.update_luminance("cam-z", 50.0, T0 + timedelta(seconds=2))  # reset
    assert tracker.update_luminance("cam-z", 5.0, T0 + timedelta(seconds=3)) is None
    assert tracker.update_luminance("cam-z", 5.0, T0 + timedelta(seconds=4)) is None
    r = tracker.update_luminance("cam-z", 5.0, T0 + timedelta(seconds=5))
    assert r is not None
