from pathlib import Path

from fastapi.testclient import TestClient


def _minimal_event_payload(event_id: str = "EVT-20260723-0001") -> dict:
    return {
        "event_id": event_id,
        "schema_version": "1.0",
        "source": "cctvbot",
        "camera": {
            "camera_id": "cam_front_gate",
            "name": "ประตูหน้า",
            "stream_type": "ip_rtsp",
            "zone": "entrance",
        },
        "event_type": "person_after_hours",
        "severity": "medium",
        "status": "pending_review",
        "confidence": 0.87,
        "started_at": "2026-07-23T15:00:00+07:00",
        "ended_at": "2026-07-23T15:00:12+07:00",
        "detected_at": "2026-07-23T15:00:05+07:00",
        "rule": {
            "code": "person_after_hours",
            "name": "บุคคลนอกเวลา",
            "params": {"after": "18:00"},
        },
        "objects": [{"label": "person", "count": 1, "track_ids": ["1"]}],
        "evidence": {
            "thumb": "thumb.jpg",
            "clip": "clip.mp4",
            "clip_before_seconds": 30,
            "clip_after_seconds": 30,
            "relative_path": f"events/{event_id}/",
        },
        "message_th": "พบเหตุที่ควรตรวจสอบ ที่ประตูหน้า",
    }


def test_create_event_with_system_token(client: TestClient):
    payload = _minimal_event_payload()
    r = client.post(
        "/api/events",
        json=payload,
        headers={"X-System-Token": "test-system-token"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["event_id"] == payload["event_id"]
    assert body["status"] == "pending_review"
    assert body["message_th"] == payload["message_th"]
    assert body["camera_id"] == "cam_front_gate"


def test_create_event_unauthorized(client: TestClient):
    r = client.post("/api/events", json={})
    assert r.status_code in (401, 403)


def test_list_pending(client: TestClient, admin_headers: dict, sample_event: str):
    r = client.get("/api/events?status=pending_review", headers=admin_headers)
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 1
    assert any(e["event_id"] == sample_event for e in data)


def test_review_confirm(client: TestClient, admin_headers: dict, sample_event: str):
    r = client.patch(
        f"/api/events/{sample_event}/review",
        json={"decision": "confirmed", "note": "ตรวจแล้ว"},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "confirmed"
    assert r.json()["review"]["decision"] == "confirmed"
    assert r.json()["review"]["note"] == "ตรวจแล้ว"


def test_get_event_audits_view(client: TestClient, admin_headers: dict, sample_event: str):
    r = client.get(f"/api/events/{sample_event}", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["event_id"] == sample_event


def test_evidence_admin_only(client: TestClient, admin_headers: dict, sample_event: str):
    r = client.get(f"/api/events/{sample_event}/evidence", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["event_id"] == sample_event
    assert "paths" in body
    assert body["thumb"] == "thumb.jpg"


def test_list_cameras_after_event(
    client: TestClient, admin_headers: dict, sample_event: str
):
    del sample_event
    r = client.get("/api/cameras", headers=admin_headers)
    assert r.status_code == 200
    cams = r.json()
    assert any(c["camera_id"] == "cam_front_gate" for c in cams)


def test_upsert_camera_system(client: TestClient):
    r = client.put(
        "/api/cameras/cam_lab",
        json={"name": "ห้องแล็บ", "is_online": True, "zone": "lab"},
        headers={"X-System-Token": "test-system-token"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["camera_id"] == "cam_lab"
    assert body["is_online"] is True
    assert body["name"] == "ห้องแล็บ"


def test_review_false_positive(
    client: TestClient, admin_headers: dict, sample_event: str
):
    r = client.patch(
        f"/api/events/{sample_event}/review",
        json={"decision": "false_positive"},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "false_positive"


def test_create_camera_offline_sets_is_online_false(
    client: TestClient, admin_headers: dict
):
    payload = _minimal_event_payload("EVT-OFFLINE-0001")
    payload["event_type"] = "camera_offline"
    payload["severity"] = "critical"
    payload["rule"] = {
        "code": "camera_offline",
        "name": "กล้องออฟไลน์",
        "params": {},
    }
    payload["camera"] = {
        "camera_id": "cam_offline_1",
        "name": "กล้องออฟไลน์",
        "stream_type": "ip_rtsp",
        "zone": "yard",
    }
    r = client.post(
        "/api/events",
        json=payload,
        headers={"X-System-Token": "test-system-token"},
    )
    assert r.status_code == 201

    cams = client.get("/api/cameras", headers=admin_headers)
    assert cams.status_code == 200
    cam = next(c for c in cams.json() if c["camera_id"] == "cam_offline_1")
    assert cam["is_online"] is False


def test_create_rejects_path_traversal_relative_path(client: TestClient):
    payload = _minimal_event_payload("EVT-TRAVERSAL-0001")
    payload["evidence"]["relative_path"] = "../../etc/passwd"
    r = client.post(
        "/api/events",
        json=payload,
        headers={"X-System-Token": "test-system-token"},
    )
    assert r.status_code == 400


def test_evidence_rejects_path_traversal_on_get(
    client: TestClient, admin_headers: dict, sample_event: str, monkeypatch
):
    """get_evidence rejects stored relative_path that escapes evidence_root."""
    from app.db import SessionLocal
    from app.models import Event

    db = SessionLocal()
    try:
        event = db.query(Event).filter(Event.event_id == sample_event).first()
        assert event is not None
        evidence = dict(event.evidence_json or {})
        evidence["relative_path"] = "../../../Windows/System32"
        event.evidence_json = evidence
        db.commit()
    finally:
        db.close()

    r = client.get(f"/api/events/{sample_event}/evidence", headers=admin_headers)
    assert r.status_code == 400


def test_evidence_file_serves_thumb(
    client: TestClient, admin_headers: dict, sample_event: str, tmp_path: Path, monkeypatch
):
    from app.config import settings
    from app.db import SessionLocal
    from app.models import Event

    monkeypatch.setattr(settings, "evidence_root", str(tmp_path))
    event_dir = tmp_path / sample_event
    event_dir.mkdir(parents=True)
    thumb = event_dir / "thumb.jpg"
    thumb.write_bytes(b"\xff\xd8\xfffakejpeg")

    db = SessionLocal()
    try:
        event = db.query(Event).filter(Event.event_id == sample_event).first()
        assert event is not None
        evidence = dict(event.evidence_json or {})
        evidence["relative_path"] = sample_event
        evidence["thumb"] = "thumb.jpg"
        event.evidence_json = evidence
        db.commit()
    finally:
        db.close()

    r = client.get(
        f"/api/events/{sample_event}/evidence/file?name=thumb.jpg",
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.content == b"\xff\xd8\xfffakejpeg"
    assert "image/jpeg" in r.headers.get("content-type", "")


def test_evidence_file_rejects_bad_name(
    client: TestClient, admin_headers: dict, sample_event: str
):
    r = client.get(
        f"/api/events/{sample_event}/evidence/file?name=../../secret.txt",
        headers=admin_headers,
    )
    assert r.status_code == 400


def test_list_events_pagination(client: TestClient, admin_headers: dict):
    # Scope by a dedicated camera_id so the assertion is isolated from rows
    # created by other tests sharing the in-memory DB.
    cam = "cam_pagination_test"
    for i in range(3):
        payload = _minimal_event_payload(f"EVT-PAGE-{i:04d}")
        payload["camera"]["camera_id"] = cam
        r = client.post(
            "/api/events",
            json=payload,
            headers={"X-System-Token": "test-system-token"},
        )
        assert r.status_code == 201

    page1 = client.get(
        f"/api/events?camera_id={cam}&limit=2", headers=admin_headers
    )
    assert page1.status_code == 200
    assert len(page1.json()) == 2

    page2 = client.get(
        f"/api/events?camera_id={cam}&limit=2&offset=2", headers=admin_headers
    )
    assert page2.status_code == 200
    assert len(page2.json()) == 1

    # no overlap between pages
    ids1 = {e["event_id"] for e in page1.json()}
    ids2 = {e["event_id"] for e in page2.json()}
    assert ids1.isdisjoint(ids2)


def test_list_events_rejects_invalid_limit(client: TestClient, admin_headers: dict):
    assert client.get("/api/events?limit=0", headers=admin_headers).status_code == 422
    assert client.get("/api/events?limit=999", headers=admin_headers).status_code == 422
    assert client.get("/api/events?offset=-1", headers=admin_headers).status_code == 422


def test_events_composite_index_declared():
    from app.models import Event

    names = {ix.name for ix in Event.__table__.indexes}
    assert "ix_events_status_created_at" in names
