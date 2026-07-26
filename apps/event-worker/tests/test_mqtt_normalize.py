"""Frigate box is pixels at detect resolution; must normalize to 0-1 at ingest."""

from zoneinfo import ZoneInfo

from worker.mqtt_consumer import _normalize_box, normalize_frigate_event

TZ = ZoneInfo("Asia/Bangkok")


def test_normalize_box_pixels():
    b = _normalize_box([415, 489, 528, 700], 1280, 720)
    assert abs(b[0] - 415 / 1280) < 1e-9
    assert abs(b[1] - 489 / 720) < 1e-9
    assert abs(b[2] - 528 / 1280) < 1e-9
    assert abs(b[3] - 700 / 720) < 1e-9
    assert all(0.0 <= v <= 1.0 for v in b)


def test_normalize_box_already_normalized_untouched():
    b = _normalize_box([0.4, 0.2, 0.55, 0.7], 1280, 720)
    assert b == [0.4, 0.2, 0.55, 0.7]


def test_normalize_box_invalid_passthrough():
    assert _normalize_box(None, 1280, 720) is None
    assert _normalize_box([1, 2], 1280, 720) == [1, 2]


def test_normalize_frigate_event_normalizes_pixel_box():
    msg = {
        "type": "update",
        "after": {
            "camera": "cam-yard",
            "label": "person",
            "id": "t1",
            "top_score": 0.9,
            "box": [415, 489, 528, 700],
        },
    }
    det = normalize_frigate_event(msg, TZ, detect_width=1280, detect_height=720)
    assert det is not None
    assert all(0.0 <= v <= 1.0 for v in det["box"])
    assert abs(det["box"][0] - 415 / 1280) < 1e-9
