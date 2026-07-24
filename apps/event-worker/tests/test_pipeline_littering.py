"""Rule 8 littering firing through the pipeline (camera-level person presence)."""

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from worker.api_client import ApiClient
from worker.debounce import Debouncer
from worker.mqtt_consumer import EventPipeline

TZ = ZoneInfo("Asia/Bangkok")
T0 = datetime(2026, 7, 25, 12, 0, 0, tzinfo=TZ)
_SCHEDULE = {"timezone": "Asia/Bangkok", "school_closed": {"weekdays": [], "weekends": []}}


def _pipeline(tmp_path, litter_on, posted, clock):
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
            "person_motion_enrichment": False,  # isolate littering
            "enrichment_available": litter_on,
            "littering_enabled": True,
            "litter_zone": "litter_watch",
            "litter_min_seconds": 3.0,
            "litter_max_seconds": 8.0,
            "litter_downward_delta": 0.05,
            "nearby_window_seconds": 5.0,
            "motion_track_ttl_seconds": 300.0,
        },
        now_fn=lambda: clock["t"],
    )


def _person_msg(track_id, box, camera="cam-yard"):
    return {
        "type": "update",
        "after": {"camera": camera, "label": "person", "id": track_id,
                  "top_score": 0.9, "start_time": T0.timestamp(), "box": box},
    }


def _bottle_msg(track_id, box, zones, camera="cam-yard"):
    return {
        "type": "update",
        "after": {"camera": camera, "label": "bottle", "id": track_id,
                  "top_score": 0.8, "start_time": T0.timestamp(), "box": box,
                  "current_zones": zones},
    }


def test_littering_fires_person_then_bottle_drop(tmp_path):
    posted, clock = [], {"t": T0}
    p = _pipeline(tmp_path, True, posted, clock)
    p.handle_frigate_event(_person_msg("pp", [0.4, 0.3, 0.5, 0.7]))          # person present
    p.handle_frigate_event(_bottle_msg("b1", [0.45, 0.38, 0.5, 0.42], ["litter_watch"]))  # cy 0.40
    clock["t"] = T0 + timedelta(seconds=4)
    p.handle_frigate_event(_bottle_msg("b1", [0.45, 0.48, 0.5, 0.52], ["litter_watch"]))  # cy 0.50, dy 0.10
    assert "possible_littering" in posted


def test_littering_no_person_no_fire(tmp_path):
    posted, clock = [], {"t": T0}
    p = _pipeline(tmp_path, True, posted, clock)
    p.handle_frigate_event(_bottle_msg("b1", [0.45, 0.38, 0.5, 0.42], ["litter_watch"]))
    clock["t"] = T0 + timedelta(seconds=4)
    p.handle_frigate_event(_bottle_msg("b1", [0.45, 0.48, 0.5, 0.52], ["litter_watch"]))
    assert "possible_littering" not in posted


def test_littering_gated_off(tmp_path):
    posted, clock = [], {"t": T0}
    p = _pipeline(tmp_path, False, posted, clock)
    p.handle_frigate_event(_person_msg("pp", [0.4, 0.3, 0.5, 0.7]))
    p.handle_frigate_event(_bottle_msg("b1", [0.45, 0.38, 0.5, 0.42], ["litter_watch"]))
    clock["t"] = T0 + timedelta(seconds=4)
    p.handle_frigate_event(_bottle_msg("b1", [0.45, 0.48, 0.5, 0.52], ["litter_watch"]))
    assert "possible_littering" not in posted
