# MySQL Integration Testing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Run the API suite against MySQL + add one explicit end-to-end integration test.

**Architecture:** conftest respects `DATABASE_URL` + creates/drops schema for non-sqlite; a skip-on-sqlite lifecycle test.

**Tech Stack:** pytest, SQLAlchemy, pymysql, MySQL 8.

## Global Constraints

- Default `pytest` behavior unchanged (sqlite in-memory, integration test skipped).
- Do not change application code unless a real MySQL incompatibility is found.
- MySQL test DB is `utf8mb4`; created fresh + dropped around the run.
- Keep green: sqlite suite (60), worker (95).

---

### Task 1: conftest respects DATABASE_URL + schema fixture

**Files:**
- Modify: `apps/api/tests/conftest.py`

- [ ] **Step 1: Respect an external DATABASE_URL**

Change the top of `conftest.py`:
```python
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
```
to:
```python
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
```
(Leave `API_SECRET_KEY` / `SYSTEM_API_TOKEN` / `ADMIN_*` hard-set.)

- [ ] **Step 2: Add a session-autouse schema fixture** (after the imports / before `client`):

```python
@pytest.fixture(scope="session", autouse=True)
def _ensure_schema():
    from app.config import settings
    from app.db import Base, engine
    import app.models  # noqa: F401  (register tables)

    is_sqlite = settings.database_url.startswith("sqlite")
    if not is_sqlite:
        Base.metadata.create_all(bind=engine)
    yield
    if not is_sqlite:
        Base.metadata.drop_all(bind=engine)
```

- [ ] **Step 3: Confirm sqlite suite unchanged**

Run: `cd apps/api && ./.venv/Scripts/python.exe -m pytest -q`
Expected: 60 passed (integration test not yet added).

- [ ] **Step 4: Commit**

```bash
git add apps/api/tests/conftest.py
git commit -m "test(api): conftest respects DATABASE_URL + schema fixture for non-sqlite"
```

---

### Task 2: Integration test + run on MySQL

**Files:**
- Create: `apps/api/tests/test_mysql_integration.py`

- [ ] **Step 1: Write the integration test**

```python
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
```

- [ ] **Step 2: Run the FULL suite on MySQL**

```bash
cd apps/api
# create fresh utf8mb4 DB
./.venv/Scripts/python.exe -c "import pymysql; c=pymysql.connect(host='127.0.0.1',port=3306,user='root',password=''); cur=c.cursor(); cur.execute('DROP DATABASE IF EXISTS cctvbot_it'); cur.execute('CREATE DATABASE cctvbot_it CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci'); c.close()"
DATABASE_URL="mysql+pymysql://root@127.0.0.1:3306/cctvbot_it" ./.venv/Scripts/python.exe -m pytest -q
```
Expected: all pass on MySQL (60 existing + 1 integration = 61). **If any fail due to a
MySQL incompatibility, fix the root cause** (app or test) and re-run until green.

- [ ] **Step 3: Drop the MySQL test DB**

```bash
cd apps/api && ./.venv/Scripts/python.exe -c "import pymysql; c=pymysql.connect(host='127.0.0.1',port=3306,user='root',password=''); c.cursor().execute('DROP DATABASE IF EXISTS cctvbot_it'); c.close()"
```

- [ ] **Step 4: Confirm the default sqlite run is unchanged**

Run: `cd apps/api && ./.venv/Scripts/python.exe -m pytest -q`
Expected: 60 passed (integration test skipped).

- [ ] **Step 5: Commit**

```bash
git add apps/api/tests/test_mysql_integration.py
git commit -m "test(api): MySQL end-to-end integration test (skip on sqlite)"
```

---

## Self-Review

**Spec coverage:** §3 conftest + schema fixture → Task 1; integration test → Task 2 Step 1;
§4 running → Task 2 Steps 2–4; §5 verification → Task 2. ✓

**Placeholder scan:** full code in each step. ✓

**Consistency:** `_ensure_schema` uses the app engine (MySQL when `DATABASE_URL` targets it);
`skipif` matches the sqlite default; the integration payload mirrors the API schema
(camera/rule/evidence). Default `pytest` stays sqlite (`setdefault`). ✓
