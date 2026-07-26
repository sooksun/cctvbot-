import os

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ["API_SECRET_KEY"] = "test-secret-key-at-least-32-characters"
os.environ["SYSTEM_API_TOKEN"] = "test-system-token"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "admin123!"

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session", autouse=True)
def _ensure_schema():
    from app.config import settings
    from app.db import Base, engine
    import app.models  # noqa: F401  (register tables on Base.metadata)

    is_sqlite = settings.database_url.startswith("sqlite")
    if not is_sqlite:
        Base.metadata.create_all(bind=engine)
    yield
    if not is_sqlite:
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _reset_login_limiter():
    # login_limiter is module-level; reset so per-test logins don't accumulate
    # toward the rate limit across the shared in-memory DB session.
    from app.routers.auth_router import login_limiter

    login_limiter.reset()
    yield


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def admin_headers(client: TestClient) -> dict:
    r = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123!"},
    )
    assert r.status_code == 200
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sample_event(client: TestClient) -> str:
    import uuid

    event_id = f"EVT-TEST-{uuid.uuid4().hex[:8].upper()}"
    payload = {
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
        "confidence": 0.9,
        "started_at": "2026-07-23T15:00:00+07:00",
        "ended_at": None,
        "detected_at": "2026-07-23T15:00:05+07:00",
        "rule": {"code": "person_after_hours", "name": "บุคคลนอกเวลา", "params": {}},
        "objects": [],
        "evidence": {
            "thumb": "thumb.jpg",
            "clip": "clip.mp4",
            "clip_before_seconds": 30,
            "clip_after_seconds": 30,
            "relative_path": f"events/{event_id}/",
        },
        "message_th": "พบเหตุที่ควรตรวจสอบ",
    }
    r = client.post(
        "/api/events",
        json=payload,
        headers={"X-System-Token": "test-system-token"},
    )
    assert r.status_code == 201
    return event_id
