"""Rules 7/9 gate + person-motion enrichment firing through the pipeline."""

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from worker.api_client import ApiClient
from worker.debounce import Debouncer
from worker.mqtt_consumer import EventPipeline

TZ = ZoneInfo("Asia/Bangkok")
T0 = datetime(2026, 7, 25, 12, 0, 0, tzinfo=TZ)  # Saturday-safe; school open below

# School always open so person_after_hours never fires and isolates rules 7/9.
_SCHEDULE = {"timezone": "Asia/Bangkok", "school_closed": {"weekdays": [], "weekends": []}}


def _pipeline(tmp_path, motion_on, posted, clock):
    def handler(request: httpx.Request) -> httpx.Response:
        posted.append(json.loads(request.content.decode())["event_type"])
        return httpx.Response(201, json={"ok": True})

    api = ApiClient(
        base_url="http://api:8000",
        system_token="t",
        transport=httpx.MockTransport(handler),
    )
    return EventPipeline(
        evidence_root=tmp_path,
        api_client=api,
        debouncer=Debouncer(window_seconds=0),
        schedule_config=_SCHEDULE,
        rules_config={
            "person_motion_enrichment": motion_on,
            "enrichment_available": False,
            "run_speed_threshold": 0.15,
            "crowd_threshold": 5,
            "fight_person_min": 2,
            "fight_motion_seconds": 3.0,
            "fight_speed_threshold": 0.12,
            "speed_ema_alpha": 0.5,
            "nearby_window_seconds": 5.0,
            "motion_track_ttl_seconds": 60.0,
        },
        now_fn=lambda: clock["t"],
    )


def _person_msg(track_id, box, camera="cam-yard"):
    return {
        "type": "update",
        "after": {
            "camera": camera,
            "label": "person",
            "id": track_id,
            "top_score": 0.9,
            "start_time": T0.timestamp(),
            "box": box,
        },
    }


def test_abnormal_motion_fires_when_enrichment_on(tmp_path):
    posted, clock = [], {"t": T0}
    p = _pipeline(tmp_path, True, posted, clock)
    p.handle_frigate_event(_person_msg("p1", [0.1, 0.2, 0.2, 0.5]))
    clock["t"] = T0 + timedelta(seconds=1)
    p.handle_frigate_event(_person_msg("p1", [0.6, 0.2, 0.7, 0.5]))  # moved 0.5 → ema 0.25>0.15
    assert "abnormal_motion" in posted


def test_abnormal_crowd_fires_with_five_persons(tmp_path):
    posted, clock = [], {"t": T0}
    p = _pipeline(tmp_path, True, posted, clock)
    for i in range(5):
        clock["t"] = T0 + timedelta(seconds=i * 0.1)
        p.handle_frigate_event(_person_msg(f"p{i}", [0.1, 0.1, 0.2, 0.2]))
    assert "abnormal_crowd" in posted


def test_possible_fight_fires(tmp_path):
    posted, clock = [], {"t": T0}
    p = _pipeline(tmp_path, True, posted, clock)

    def step(dt, tid, box):
        clock["t"] = T0 + timedelta(seconds=dt)
        p.handle_frigate_event(_person_msg(tid, box))

    step(0, "p1", [0.2, 0.2, 0.3, 0.5])   # p1 seed
    step(0, "p2", [0.6, 0.6, 0.7, 0.9])   # second person → nearby 2
    step(1, "p1", [0.5, 0.2, 0.6, 0.5])   # moved 0.3 → ema 0.15, high_since=t1
    step(2, "p1", [0.2, 0.2, 0.3, 0.5])   # ema 0.225
    step(3, "p1", [0.5, 0.2, 0.6, 0.5])   # dur=2 (<3)
    step(4, "p1", [0.2, 0.2, 0.3, 0.5])   # dur=3 → fight fires (nearby p1,p2 in 5s window)
    assert "possible_fight" in posted


def test_rules_79_gated_off(tmp_path):
    posted, clock = [], {"t": T0}
    p = _pipeline(tmp_path, False, posted, clock)
    p.handle_frigate_event(_person_msg("p1", [0.1, 0.2, 0.2, 0.5]))
    clock["t"] = T0 + timedelta(seconds=1)
    p.handle_frigate_event(_person_msg("p1", [0.6, 0.2, 0.7, 0.5]))
    assert "abnormal_motion" not in posted
    assert "abnormal_crowd" not in posted


def test_littering_stays_gated_by_enrichment_available(tmp_path):
    # person_motion on, but enrichment_available False → littering must not fire.
    posted, clock = [], {"t": T0}
    p = _pipeline(tmp_path, True, posted, clock)
    p.handle_frigate_event(_person_msg("p1", [0.1, 0.2, 0.2, 0.5]))
    assert "possible_littering" not in posted
