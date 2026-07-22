import json
from unittest.mock import MagicMock, patch

import httpx
from fastapi.testclient import TestClient

from app.line_notify import LINE_PUSH_URL, build_confirm_line_text, send_line_text


def test_send_line_text_push_json_text_only_no_image_keys():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_client = MagicMock()
    mock_client.post.return_value = mock_response

    with patch("app.line_notify.httpx.Client") as mock_cls:
        mock_cls.return_value.__enter__.return_value = mock_client
        mock_cls.return_value.__exit__.return_value = None
        send_line_text("test-token", "Uuser123", "hello line")

    mock_client.post.assert_called_once()
    args, kwargs = mock_client.post.call_args
    assert args[0] == LINE_PUSH_URL
    assert kwargs["headers"]["Authorization"] == "Bearer test-token"
    body = kwargs["json"]
    assert body["to"] == "Uuser123"
    assert len(body["messages"]) == 1
    msg = body["messages"][0]
    assert msg == {"type": "text", "text": "hello line"}
    assert "originalContentUrl" not in msg
    assert "previewImageUrl" not in msg
    assert "imageUrl" not in msg
    assert "image" not in msg
    dumped = json.dumps(body)
    assert "originalContentUrl" not in dumped
    assert "previewImageUrl" not in dumped


def test_build_confirm_line_text_template():
    text = build_confirm_line_text(
        camera_name="ประตูหน้า",
        time_local="22:14",
        event_type_label="บุคคลนอกเวลา",
        event_id="EVT-20260722-0014",
    )
    assert text.startswith("[ยืนยันแล้ว] พบเหตุที่ควรตรวจสอบ")
    assert "จุด: ประตูหน้า | เวลา: 22:14" in text
    assert "ประเภท: บุคคลนอกเวลา" in text
    assert "รหัส: EVT-20260722-0014" in text
    assert "เปิดดูภาพได้ที่ระบบภายในเท่านั้น" in text
    assert "http" not in text
    assert "image" not in text.lower()


def test_review_confirm_sends_line(
    client: TestClient, admin_headers: dict, sample_event: str, monkeypatch
):
    from app.config import settings

    monkeypatch.setattr(settings, "line_channel_access_token", "test-line-token")
    monkeypatch.setattr(settings, "line_user_id", "Ulineuser")

    with patch("app.routers.events.send_line_text") as mock_send:
        r = client.patch(
            f"/api/events/{sample_event}/review",
            json={"decision": "confirmed", "note": "ok"},
            headers=admin_headers,
        )

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "confirmed"
    assert body["notifications"]["line_sent"] is True
    assert body["notifications"]["line_sent_at"] is not None

    mock_send.assert_called_once()
    token, user_id, text = mock_send.call_args[0]
    assert token == "test-line-token"
    assert user_id == "Ulineuser"
    assert sample_event in text
    assert "ประตูหน้า" in text
    assert "บุคคลนอกเวลา" in text
    assert "http" not in text


def test_review_confirm_skips_line_when_token_empty(
    client: TestClient, admin_headers: dict, sample_event: str, monkeypatch
):
    from app.config import settings

    monkeypatch.setattr(settings, "line_channel_access_token", "")
    monkeypatch.setattr(settings, "line_user_id", "Ulineuser")

    with patch("app.routers.events.send_line_text") as mock_send:
        r = client.patch(
            f"/api/events/{sample_event}/review",
            json={"decision": "confirmed"},
            headers=admin_headers,
        )

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "confirmed"
    assert body["notifications"]["line_sent"] is False
    mock_send.assert_not_called()


def test_review_false_positive_no_line(
    client: TestClient, admin_headers: dict, sample_event: str, monkeypatch
):
    from app.config import settings

    monkeypatch.setattr(settings, "line_channel_access_token", "test-line-token")
    monkeypatch.setattr(settings, "line_user_id", "Ulineuser")

    with patch("app.routers.events.send_line_text") as mock_send:
        r = client.patch(
            f"/api/events/{sample_event}/review",
            json={"decision": "false_positive"},
            headers=admin_headers,
        )

    assert r.status_code == 200
    assert r.json()["status"] == "false_positive"
    assert r.json()["notifications"]["line_sent"] is False
    mock_send.assert_not_called()


def test_review_confirm_audits_send_line(
    client: TestClient, admin_headers: dict, sample_event: str, monkeypatch
):
    from app.config import settings
    from app.db import SessionLocal
    from app.models import AuditLog

    monkeypatch.setattr(settings, "line_channel_access_token", "tok")
    monkeypatch.setattr(settings, "line_user_id", "uid")

    with patch("app.routers.events.send_line_text"):
        r = client.patch(
            f"/api/events/{sample_event}/review",
            json={"decision": "confirmed"},
            headers=admin_headers,
        )
    assert r.status_code == 200

    db = SessionLocal()
    try:
        actions = [
            a.action
            for a in db.query(AuditLog)
            .filter(AuditLog.event_id == sample_event)
            .all()
        ]
    finally:
        db.close()

    assert "review_confirm" in actions
    assert "send_line" in actions
