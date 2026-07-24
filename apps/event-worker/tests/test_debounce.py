from datetime import datetime, timedelta, timezone

from worker.debounce import Debouncer


def test_should_emit_first_event_true():
    deb = Debouncer(window_seconds=60)
    now = datetime(2026, 7, 22, 22, 0, 0, tzinfo=timezone.utc)
    assert deb.should_emit("cam-front", "person_after_hours", now) is True


def test_second_event_within_60s_returns_false():
    deb = Debouncer(window_seconds=60)
    now = datetime(2026, 7, 22, 22, 0, 0, tzinfo=timezone.utc)
    assert deb.should_emit("cam-front", "person_after_hours", now) is True
    later = now + timedelta(seconds=30)
    assert deb.should_emit("cam-front", "person_after_hours", later) is False


def test_event_after_window_returns_true():
    deb = Debouncer(window_seconds=60)
    now = datetime(2026, 7, 22, 22, 0, 0, tzinfo=timezone.utc)
    assert deb.should_emit("cam-front", "person_after_hours", now) is True
    later = now + timedelta(seconds=61)
    assert deb.should_emit("cam-front", "person_after_hours", later) is True


def test_different_camera_or_type_not_debounced():
    deb = Debouncer(window_seconds=60)
    now = datetime(2026, 7, 22, 22, 0, 0, tzinfo=timezone.utc)
    assert deb.should_emit("cam-front", "person_after_hours", now) is True
    assert deb.should_emit("cam-back", "person_after_hours", now) is True
    assert deb.should_emit("cam-front", "camera_offline", now) is True
