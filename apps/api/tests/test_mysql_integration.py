"""End-to-end lifecycle on a real MySQL engine.

Skipped unless DATABASE_URL points at MySQL. Run:
  (create a fresh utf8mb4 DB, then)
  DATABASE_URL="mysql+pymysql://root@127.0.0.1:3306/<db>" \
    ./.venv/Scripts/python.exe -m pytest tests/test_mysql_integration.py -q
"""

import pytest
from fastapi.testclient import TestClient

from app.config import settings

pytestmark = pytest.mark.skipif(
    settings.database_url.startswith("sqlite"),
    reason="MySQL integration test — set DATABASE_URL to a MySQL URL to run",
)


def _payload(event_id: str, camera_id: str) -> dict:
    return {
        "event_id": event_id,
        "schema_version": "1.0",
        "source": "cctvbot",
        "camera": {
            "camera_id": camera_id,
            "name": "ประตูหน้า",
            "stream_type": "ip_rtsp",
            "zone": "ทางเข้า",
        },
        "event_type": "person_after_hours",
        "severity": "high",
        "status": "pending_review",
        "confidence": 0.9,
        "started_at": "2026-07-26T20:00:00+07:00",
        "ended_at": None,
        "detected_at": "2026-07-26T20:00:05+07:00",
        "rule": {"code": "person_after_hours", "name": "บุคคลนอกเวลา", "params": {}},
        "objects": [{"label": "person", "count": 1, "track_ids": ["1"]}],
        "evidence": {
            "thumb": "thumb.jpg",
            "clip": "clip.mp4",
            "clip_before_seconds": 30,
            "clip_after_seconds": 30,
            "relative_path": event_id,
        },
        "message_th": "พบเหตุที่ควรตรวจสอบ: ตรวจพบบุคคลนอกเวลาทำการ ที่กล้อง ประตูหน้า",
    }


def test_full_lifecycle_on_mysql(client: TestClient, admin_headers: dict):
    sys_h = {"X-System-Token": "test-system-token"}
    eid = "EVT-MYSQLIT-0001"
    cam = "cam_mysql_it"

    payload = _payload(eid, cam)
    r = client.post("/api/events", json=payload, headers=sys_h)
    assert r.status_code == 201
    # Thai text round-trips through MySQL (utf8mb4) + JSON columns
    assert r.json()["message_th"] == payload["message_th"]
    assert r.json()["rule"]["name"] == "บุคคลนอกเวลา"

    assert client.patch(
        f"/api/events/{eid}/review",
        json={"decision": "confirmed", "note": "ตรวจแล้ว"},
        headers=admin_headers,
    ).status_code == 200
    assert client.patch(
        f"/api/events/{eid}/status", json={"status": "action_taken"}, headers=admin_headers
    ).status_code == 200
    assert client.patch(
        f"/api/events/{eid}/status", json={"status": "closed"}, headers=admin_headers
    ).status_code == 200

    # disable the camera → next event is dropped (202)
    assert client.patch(
        f"/api/cameras/{cam}", json={"enabled": False}, headers=admin_headers
    ).status_code == 200
    r2 = client.post("/api/events", json=_payload("EVT-MYSQLIT-0002", cam), headers=sys_h)
    assert r2.status_code == 202

    # persisted lifecycle + JSON review survive on MySQL
    got = client.get(f"/api/events/{eid}", headers=admin_headers).json()
    assert got["status"] == "closed"
    assert got["review"]["decision"] == "confirmed"
    assert got["review"]["note"] == "ตรวจแล้ว"
