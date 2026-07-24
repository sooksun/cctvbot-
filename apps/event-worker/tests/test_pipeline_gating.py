"""Rules 7/8/9 must be gated off until enrichment fields are available."""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from worker.api_client import ApiClient
from worker.debounce import Debouncer
from worker.mqtt_consumer import EventPipeline

TZ = ZoneInfo("Asia/Bangkok")
# Saturday midday; with school open (no closed windows) after-hours never fires,
# isolating the abnormal_motion/crowd rules.
T0 = datetime(2026, 7, 25, 12, 0, 0, tzinfo=TZ)

# School always open so person_after_hours does not fire.
_SCHEDULE = {
    "timezone": "Asia/Bangkok",
    "school_closed": {"weekdays": [], "weekends": []},
}


def _pipeline(tmp_path, enrichment: bool, posted: list[str]) -> EventPipeline:
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
            "enrichment_available": enrichment,
            "run_speed_threshold": 0.15,
            "crowd_threshold": 5,
        },
        now_fn=lambda: T0,
    )


def _enriched_person_msg() -> dict:
    return {
        "type": "update",
        "after": {
            "camera": "cam-yard",
            "label": "person",
            "top_score": 0.9,
            "start_time": T0.timestamp(),
            "speed": 0.9,  # > run_speed_threshold → motion
            "nearby_person_count": 8,  # >= crowd_threshold → crowd
        },
    }


def test_rules_789_gated_off_by_default(tmp_path):
    posted: list[str] = []
    pipeline = _pipeline(tmp_path, enrichment=False, posted=posted)
    pipeline.handle_frigate_event(_enriched_person_msg())
    assert "abnormal_motion" not in posted
    assert "abnormal_crowd" not in posted


def test_rules_789_fire_when_enrichment_available(tmp_path):
    posted: list[str] = []
    pipeline = _pipeline(tmp_path, enrichment=True, posted=posted)
    pipeline.handle_frigate_event(_enriched_person_msg())
    assert "abnormal_motion" in posted
    assert "abnormal_crowd" in posted
