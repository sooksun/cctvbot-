# School CCTV Security (cctvbot) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver an on-premise school CCTV security MVP: Frigate ingest (2–4 cameras), rule-based events (1/2/5/7/8/9), dual API + evidence files, internal dashboard review, LINE text after human confirm.

**Architecture:** Frigate (GPU) detects and records → Python event-worker applies school rules, writes `/data/events/{id}/`, POSTs to FastAPI → MySQL stores events/audit → Next.js dashboard for review → LINE text-only on `confirmed`.

**Tech Stack:** Docker Compose, Frigate, Python 3.11+, FastAPI, SQLAlchemy, MySQL 8, Next.js (App Router), Tailwind CSS, MQTT (Eclipse Mosquitto), LINE Messaging API.

**Spec:** `docs/superpowers/specs/2026-07-23-school-cctv-security-design.md`

## Global Constraints

- Local-first: video/clips/snapshots stay on school server; no public port-forward of cameras/Frigate/evidence.
- UI/API Thai copy uses “พบเหตุที่ควรตรวจสอบ” only — never definitive blame or student names.
- LINE only after human `confirmed`; text only; no media.
- MVP event types: `person_after_hours`, `person_restricted_zone`, `person_fall_or_down`, `camera_offline`, `camera_tamper`, `abnormal_motion`, `abnormal_crowd`, `possible_littering`, `possible_fight`.
- Status lifecycle: `pending_review` → `confirmed` | `false_positive` → `action_taken` → `closed`.
- Dual output: evidence files first, then API POST; files must survive API outage.
- No face recognition; no AI on toilets/changing rooms.
- Pilot: 2–4 cameras; roles: `admin`, `viewer`, `system`.
- Evidence path root: `/data/events` (bind-mounted; Windows dev may use `./data/events`).
- Secrets only in `.env` (gitignored).

## File map (create)

```
cctvbot/
├── .env.example
├── .gitignore
├── docker-compose.yml
├── README.md
├── frigate/
│   └── config.yml
├── data/
│   ├── events/.gitkeep
│   ├── frigate/.gitkeep
│   └── config/.gitkeep
├── apps/
│   ├── api/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── pyproject.toml          # optional; requirements.txt is enough
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── config.py
│   │   │   ├── db.py
│   │   │   ├── models.py
│   │   │   ├── schemas.py
│   │   │   ├── auth.py
│   │   │   ├── audit.py
│   │   │   ├── line_notify.py
│   │   │   └── routers/
│   │   │       ├── auth_router.py
│   │   │       ├── events.py
│   │   │       └── cameras.py
│   │   └── tests/
│   │       ├── conftest.py
│   │       ├── test_events.py
│   │       ├── test_review_line.py
│   │       └── test_auth.py
│   ├── event-worker/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── worker/
│   │   │   ├── main.py
│   │   │   ├── config.py
│   │   │   ├── evidence.py
│   │   │   ├── api_client.py
│   │   │   ├── debounce.py
│   │   │   ├── schedules.py
│   │   │   ├── rules/
│   │   │   │   ├── base.py
│   │   │   │   ├── person_after_hours.py
│   │   │   │   ├── person_restricted.py
│   │   │   │   ├── person_fall.py
│   │   │   │   ├── camera_health.py
│   │   │   │   ├── abnormal_motion.py
│   │   │   │   ├── littering.py
│   │   │   │   └── fight.py
│   │   │   └── mqtt_consumer.py
│   │   └── tests/
│   │       ├── test_evidence.py
│   │       ├── test_debounce.py
│   │       ├── test_schedules.py
│   │       └── test_rules_*.py
│   └── web/
│       ├── package.json
│       ├── next.config.ts
│       ├── tailwind.config.ts
│       ├── src/app/...
│       └── ...
└── docs/...
```

---

### Task 1: Repository scaffold and secrets layout

**Files:**
- Create: `.gitignore`, `.env.example`, `README.md`, `data/events/.gitkeep`, `data/frigate/.gitkeep`, `data/config/.gitkeep`, `docker-compose.yml` (stub services comments OK until later tasks fill images)

**Interfaces:**
- Produces: local folder layout; env var names used by all later services

- [ ] **Step 1: Create `.gitignore`**

```gitignore
.env
.env.*
!.env.example
data/events/*
!data/events/.gitkeep
data/frigate/*
!data/frigate/.gitkeep
data/config/*
!data/config/.gitkeep
**/__pycache__/
**/.venv/
**/node_modules/
**/.next/
*.pyc
.DS_Store
```

- [ ] **Step 2: Create `.env.example`**

```env
# MySQL
MYSQL_ROOT_PASSWORD=change_me_root
MYSQL_DATABASE=cctvbot
MYSQL_USER=cctvbot
MYSQL_PASSWORD=change_me_db
DATABASE_URL=mysql+pymysql://cctvbot:change_me_db@db:3306/cctvbot

# API
API_SECRET_KEY=change_me_jwt_secret_min_32_chars_long
SYSTEM_API_TOKEN=change_me_system_token_for_worker
EVIDENCE_ROOT=/data/events
CORS_ORIGINS=http://localhost:3000

# Seed admin (created on first boot)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change_me_admin

# LINE (optional until Task 8)
LINE_CHANNEL_ACCESS_TOKEN=
LINE_USER_ID=

# Worker
API_BASE_URL=http://api:8000
MQTT_HOST=mosquitto
MQTT_PORT=1883
FRIGATE_BASE_URL=http://frigate:5000
SCHOOL_TZ=Asia/Bangkok

# Frigate
FRIGATE_RTSP_PASSWORD=
```

- [ ] **Step 3: Create stub `docker-compose.yml` networks and volumes only + placeholder comments**

```yaml
services: {}
networks:
  cctvbot:
    driver: bridge
volumes:
  mysql_data:
```

Full service blocks are added in Tasks 2, 3, 5, 9 (do not start empty compose as production yet).

- [ ] **Step 4: Write `README.md` with purpose, local-first warning, link to spec/plan, copy `.env.example` → `.env`**

- [ ] **Step 5: Commit**

```bash
git add .gitignore .env.example README.md data docker-compose.yml
git commit -m "chore: scaffold cctvbot repo layout and env template"
```

---

### Task 2: MySQL schema + FastAPI core (models, config, health)

**Files:**
- Create: `apps/api/requirements.txt`, `apps/api/Dockerfile`, `apps/api/app/config.py`, `apps/api/app/db.py`, `apps/api/app/models.py`, `apps/api/app/main.py`, `apps/api/tests/conftest.py`, `apps/api/tests/test_health.py`
- Modify: `docker-compose.yml` — add `db` and `api` services

**Interfaces:**
- Produces: SQLAlchemy models `User`, `Camera`, `Event`, `AuditLog`; `get_db()`; `GET /health` → `{"status":"ok"}`

- [ ] **Step 1: Write `apps/api/requirements.txt`**

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
sqlalchemy==2.0.36
pymysql==1.1.1
cryptography==44.0.0
pydantic==2.10.4
pydantic-settings==2.7.0
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
bcrypt==4.2.1
httpx==0.28.1
pytest==8.3.4
pytest-asyncio==0.25.0
```

- [ ] **Step 2: Implement `app/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "mysql+pymysql://cctvbot:cctvbot@127.0.0.1:3306/cctvbot"
    api_secret_key: str = "dev-secret-change-me-32chars-min"
    system_api_token: str = "dev-system-token"
    evidence_root: str = "./data/events"
    cors_origins: str = "http://localhost:3000"
    admin_username: str = "admin"
    admin_password: str = "admin123!"
    line_channel_access_token: str = ""
    line_user_id: str = ""

settings = Settings()
```

- [ ] **Step 3: Implement `app/models.py` with tables**

```python
# Columns (exact names for later tasks):
# users: id, username, password_hash, role (admin|viewer|system), created_at
# cameras: id, camera_id (unique str), name, stream_type, zone, is_online, last_seen_at, created_at
# events: id, event_id (unique), camera_id, event_type, severity, status, confidence,
#         started_at, ended_at, detected_at, rule_json, objects_json, evidence_json,
#         review_json, notifications_json, message_th, created_at, updated_at
# audit_logs: id, who, action, event_id (nullable), ip, note, created_at
```

Use JSON columns for `rule_json`, `objects_json`, `evidence_json`, `review_json`, `notifications_json` (MySQL JSON type).

- [ ] **Step 4: Implement `app/db.py` engine + `SessionLocal` + `get_db` + `init_db()` creating tables**

- [ ] **Step 5: Implement `app/main.py` with FastAPI app, CORS from settings, lifespan `init_db()`, `GET /health`**

- [ ] **Step 6: Write failing test `tests/test_health.py`**

```python
from fastapi.testclient import TestClient
from app.main import app

def test_health():
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
```

- [ ] **Step 7: Run test**

```bash
cd apps/api
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest tests/test_health.py -v
```

Expected: PASS (health does not need DB if init is tolerant; if init requires MySQL, use sqlite for tests in `conftest.py` by setting `DATABASE_URL=sqlite+pysqlite:///:memory:` and installing `aiosqlite` OR use pymysql against Laragon MySQL `cctvbot`).

**Test DB strategy (required):** In `conftest.py`, set env `DATABASE_URL=sqlite+pysqlite:///:memory:` before importing app, add `sqlalchemy` sqlite support (`pip install pysqlite3-binary` not needed on Python 3; use built-in). Change URL scheme handling: for tests only, allow `sqlite+pysqlite:///:memory:` by adding dependency nothing extra on 3.11+.

```python
# conftest.py
import os
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["API_SECRET_KEY"] = "test-secret-key-at-least-32-characters"
os.environ["SYSTEM_API_TOKEN"] = "test-system-token"
```

If SQLAlchemy 2 needs `from sqlalchemy import create_engine` with sqlite, ensure `models` use generic types (JSON works on sqlite).

- [ ] **Step 8: Add `db` + `api` to `docker-compose.yml`**

```yaml
services:
  db:
    image: mysql:8.4
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD}
      MYSQL_DATABASE: ${MYSQL_DATABASE}
      MYSQL_USER: ${MYSQL_USER}
      MYSQL_PASSWORD: ${MYSQL_PASSWORD}
    volumes:
      - mysql_data:/var/lib/mysql
    ports:
      - "3307:3306"
    networks: [cctvbot]
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "127.0.0.1"]
      interval: 5s
      timeout: 5s
      retries: 20

  api:
    build: ./apps/api
    env_file: .env
    environment:
      DATABASE_URL: ${DATABASE_URL}
      EVIDENCE_ROOT: /data/events
    volumes:
      - ./data/events:/data/events
    ports:
      - "8000:8000"
    depends_on:
      db:
        condition: service_healthy
    networks: [cctvbot]
```

Dockerfile:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 9: Commit**

```bash
git add apps/api docker-compose.yml
git commit -m "feat(api): add FastAPI core, models, health, and MySQL service"
```

---

### Task 3: Auth (login JWT) + seed admin + system token

**Files:**
- Create: `apps/api/app/auth.py`, `apps/api/app/routers/auth_router.py`, `apps/api/tests/test_auth.py`
- Modify: `apps/api/app/main.py` — include router; seed admin + system user on startup

**Interfaces:**
- Produces:
  - `POST /api/auth/login` body `{username, password}` → `{access_token, token_type, role}`
  - `get_current_user(credentials)` dependency
  - `require_roles(*roles)` dependency
  - Header `X-System-Token: <SYSTEM_API_TOKEN>` for worker `POST /api/events`

- [ ] **Step 1: Write failing tests in `test_auth.py`**

```python
def test_login_admin_ok(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123!"})
    assert r.status_code == 200
    assert "access_token" in r.json()
    assert r.json()["role"] == "admin"

def test_login_bad_password(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401
```

Use fixtures that seed admin with known password hash.

- [ ] **Step 2: Implement passlib hashing + JWT encode/decode in `auth.py`**

- [ ] **Step 3: Implement login router + seed on lifespan**

- [ ] **Step 4: Run tests**

```bash
cd apps/api
pytest tests/test_auth.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api
git commit -m "feat(api): add JWT login, roles, and system token auth"
```

---

### Task 4: Events API + evidence metadata + audit on review

**Files:**
- Create: `apps/api/app/schemas.py`, `apps/api/app/audit.py`, `apps/api/app/routers/events.py`, `apps/api/app/routers/cameras.py`, `apps/api/tests/test_events.py`
- Modify: `apps/api/app/main.py`

**Interfaces:**
- Consumes: auth deps from Task 3; models from Task 2
- Produces:
  - `POST /api/events` (system token) — create from worker payload matching `event.json` schema v1.0
  - `GET /api/events` (admin|viewer) — filters: `status`, `camera_id`, `event_type`
  - `GET /api/events/{event_id}` (admin|viewer) — audit `view_event`
  - `PATCH /api/events/{event_id}/review` (admin only) body `{decision: confirmed|false_positive, note?: str}`
  - `GET /api/events/{event_id}/evidence` (admin) — paths under evidence root; audit `view_clip` if clip requested via query later
  - `GET /api/cameras` (admin|viewer)
  - `PUT /api/cameras/{camera_id}` (system) — upsert online status

**Event create body (Pydantic) — field names must match worker:**

```python
class CameraInfo(BaseModel):
    camera_id: str
    name: str
    stream_type: str = "ip_rtsp"
    zone: str | None = None

class EvidenceInfo(BaseModel):
    thumb: str | None = None
    clip: str | None = None
    clip_before_seconds: int = 30
    clip_after_seconds: int = 30
    relative_path: str

class EventCreate(BaseModel):
    event_id: str
    schema_version: str = "1.0"
    source: str = "cctvbot"
    camera: CameraInfo
    event_type: str
    severity: str
    status: str = "pending_review"
    confidence: float
    started_at: datetime
    ended_at: datetime | None = None
    detected_at: datetime
    rule: dict
    objects: list[dict] = []
    evidence: EvidenceInfo
    message_th: str
```

- [ ] **Step 1: Write tests**

```python
def test_create_event_with_system_token(client):
    payload = { ... minimal valid EventCreate ... }
    r = client.post("/api/events", json=payload, headers={"X-System-Token": "test-system-token"})
    assert r.status_code == 201
    assert r.json()["event_id"] == payload["event_id"]
    assert r.json()["status"] == "pending_review"

def test_create_event_unauthorized(client):
    r = client.post("/api/events", json={})
    assert r.status_code in (401, 403)

def test_list_pending(client, admin_headers, sample_event):
    r = client.get("/api/events?status=pending_review", headers=admin_headers)
    assert r.status_code == 200
    assert len(r.json()) >= 1

def test_review_confirm(client, admin_headers, sample_event):
    r = client.patch(
        f"/api/events/{sample_event}/review",
        json={"decision": "confirmed", "note": "ตรวจแล้ว"},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "confirmed"
```

- [ ] **Step 2: Implement routers + audit helper `write_audit(db, who, action, event_id, ip, note)`**

- [ ] **Step 3: On create, also upsert `Camera` row from `camera.camera_id`**

- [ ] **Step 4: Run pytest**

```bash
pytest apps/api/tests/test_events.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api
git commit -m "feat(api): events CRUD, review, cameras, audit log"
```

---

### Task 5: event-worker evidence writer + debounce + API client

**Files:**
- Create: `apps/event-worker/requirements.txt`, `apps/event-worker/Dockerfile`, `apps/event-worker/worker/config.py`, `apps/event-worker/worker/evidence.py`, `apps/event-worker/worker/api_client.py`, `apps/event-worker/worker/debounce.py`, `apps/event-worker/worker/schedules.py`, `apps/event-worker/tests/test_evidence.py`, `apps/event-worker/tests/test_debounce.py`, `apps/event-worker/tests/test_schedules.py`

**Interfaces:**
- Produces:
  - `build_event_id(now: datetime) -> str` format `EVT-YYYYMMDD-####` (#### sequence per day in memory or from file counter under evidence root)
  - `write_evidence(root, event_dict, thumb_bytes=None, clip_path=None) -> Path` creates dir, writes `event.json`, optional files, atomic rename from `.tmp-*`
  - `Debouncer.should_emit(camera_id, event_type, now) -> bool` (60s window)
  - `is_school_closed(now, schedule_config) -> bool`
  - `ApiClient.post_event(payload: dict) -> None` with `X-System-Token`

- [ ] **Step 1: Write tests for evidence atomic write**

```python
def test_write_evidence_creates_event_json(tmp_path):
    event = {
        "event_id": "EVT-20260722-0001",
        "schema_version": "1.0",
        "message_th": "พบเหตุที่ควรตรวจสอบ: ทดสอบ",
        # ... minimal fields
    }
    path = write_evidence(tmp_path, event)
    assert (path / "event.json").exists()
    data = json.loads((path / "event.json").read_text(encoding="utf-8"))
    assert data["event_id"] == "EVT-20260722-0001"
```

- [ ] **Step 2: Write debounce test — second event within 60s returns False**

- [ ] **Step 3: Write schedule test — Tuesday 22:00 closed if config weekdays 18:00-06:00**

```yaml
# default schedule structure used by schedules.py
school_closed:
  weekdays:
    - start: "18:00"
      end: "06:00"   # spans midnight
  weekends: "all_day"
timezone: "Asia/Bangkok"
```

- [ ] **Step 4: Implement modules until tests pass**

```bash
cd apps/event-worker
pip install -r requirements.txt
pytest -v
```

- [ ] **Step 5: Commit**

```bash
git add apps/event-worker
git commit -m "feat(worker): evidence writer, debounce, schedules, API client"
```

---

### Task 6: Worker rules 1 + 5 + MQTT consumer skeleton

**Files:**
- Create: `apps/event-worker/worker/rules/base.py`, `person_after_hours.py`, `person_restricted.py`, `camera_health.py`, `mqtt_consumer.py`, `main.py`, `tests/test_rules_after_hours.py`, `tests/test_rules_camera.py`
- Modify: `docker-compose.yml` — add `mosquitto`, `event-worker`

**Interfaces:**
- Consumes: evidence/debounce/api from Task 5
- Produces: `RuleResult | None` from each rule; `handle_frigate_event(msg: dict) -> list[str]` event_ids created
- Frigate MQTT topics to subscribe: `frigate/events`, `frigate/available`, and per-camera stats if needed (`frigate/<cam>/status` varies by version — implement adapter that reads Frigate HTTP `/api/stats` every 30s as fallback for offline)

**Rule 1 after hours:** if Frigate event label `person` and `is_school_closed(now)` → `person_after_hours`.

**Rule 1 restricted:** if `person` and zone name in current_zones intersects config `restricted_zones` for camera → `person_restricted_zone`.

**Rule 5 offline:** if camera missing from Frigate stats or `camera_fps == 0` for ≥ 30s → `camera_offline`.

**Rule 5 tamper (MVP heuristic):** if event type is motion and Frigate `stationary`/`false_positive` not set — optional stub: function `maybe_tamper(frame_score)` can return None until snapshot analysis; implement minimal: if MQTT payload has `type == "end"` and label is None and duration long — skip. **Minimum for Task 6:** implement `camera_offline` fully; implement `camera_tamper` as callable that emits when worker receives explicit internal signal `{"signal":"tamper","camera_id":...}` OR when Frigate records `black` detection if configured — document in code. Prefer: poll snapshot brightness via Frigate API snapshot; if mean luminance < 10 for 3 consecutive checks → tamper.

- [ ] **Step 1: Unit tests for after_hours rule with fixed datetime**

- [ ] **Step 2: Unit tests for offline tracker**

- [ ] **Step 3: Implement rules + `main.py` loop (MQTT + HTTP poll)**

- [ ] **Step 4: Compose services**

```yaml
  mosquitto:
    image: eclipse-mosquitto:2
    ports: ["1883:1883"]
    networks: [cctvbot]

  event-worker:
    build: ./apps/event-worker
    env_file: .env
    volumes:
      - ./data/events:/data/events
      - ./data/config:/config
    depends_on: [api, mosquitto]
    networks: [cctvbot]
```

- [ ] **Step 5: Commit**

```bash
git add apps/event-worker docker-compose.yml
git commit -m "feat(worker): rules 1 and 5 with MQTT consumer"
```

---

### Task 7: Worker rules 2, 7, 8, 9

**Files:**
- Create: `apps/event-worker/worker/rules/person_fall.py`, `abnormal_motion.py`, `littering.py`, `fight.py`, corresponding tests

**Interfaces:**
- Same `RuleResult` as Task 6
- Input event shape (normalized from Frigate):

```python
class NormalizedDetection(TypedDict):
    camera_id: str
    label: str
    score: float
    zones: list[str]
    box: list[float]  # [x1,y1,x2,y2] normalized 0-1
    track_id: str | None
    started_at: datetime
    current_at: datetime
    speed: float | None  # optional from track history
    nearby_person_count: int
```

**Rule 2:** label person AND (aspect ratio width/height > 1.2 OR external pose flag) AND still duration ≥ 15s → `person_fall_or_down`. MVP without pose model: use horizontal box aspect ratio + centroid movement < threshold for 15s.

**Rule 7 motion:** person track speed > config `run_speed_threshold` (default 0.15 norm-units/s) → `abnormal_motion`.

**Rule 7 crowd:** `nearby_person_count >= 5` → `abnormal_crowd`.

**Rule 8 littering:** labels include person AND (bottle|cup|bag|umbrella as proxy objects if model supports COCO) with object centroid moving downward toward ground zone `litter_watch` within 3–8s → `possible_littering`. If model only has `person`, implement rule that requires Frigate object list and returns None when no object labels (feature-flagged).

**Rule 9 fight:** `nearby_person_count >= 2` and high relative motion ≥ 3s → `possible_fight`.

All message_th must start with `พบเหตุที่ควรตรวจสอบ:`.

- [ ] **Step 1: Write unit tests per rule with synthetic NormalizedDetection sequences**

- [ ] **Step 2: Implement rules**

- [ ] **Step 3: pytest all worker tests**

```bash
cd apps/event-worker && pytest -v
```

- [ ] **Step 4: Commit**

```bash
git add apps/event-worker
git commit -m "feat(worker): rules 2, 7, 8, 9 for MVP detections"
```

---

### Task 8: LINE notify on confirmed review

**Files:**
- Create: `apps/api/app/line_notify.py`, `apps/api/tests/test_review_line.py`
- Modify: `apps/api/app/routers/events.py` review handler

**Interfaces:**
- Produces: `send_line_text(token: str, user_id: str, text: str) -> None` using `https://api.line.me/v2/bot/message/push`
- On review `confirmed`: build text template from event; call send; set `notifications.line_sent=true`; audit `send_line`
- If token empty: skip send, leave `line_sent=false`, still confirm status (log warning)

Template:

```
[ยืนยันแล้ว] พบเหตุที่ควรตรวจสอบ
จุด: {camera_name} | เวลา: {time_local}
ประเภท: {event_type_th}
รหัส: {event_id}
เปิดดูภาพได้ที่ระบบภายในเท่านั้น
```

- [ ] **Step 1: Test with httpx mock — confirm triggers push JSON without image keys**

- [ ] **Step 2: Implement + wire review endpoint**

- [ ] **Step 3: pytest**

- [ ] **Step 4: Commit**

```bash
git add apps/api
git commit -m "feat(api): LINE text notify after human confirm"
```

---

### Task 9: Frigate config for 2–4 pilot cameras

**Files:**
- Create: `frigate/config.yml`, `data/config/cameras.example.yml`
- Modify: `docker-compose.yml` — add `frigate` service with GPU notes

**Interfaces:**
- Produces: working Frigate config template; cameras use env RTSP URLs

```yaml
# frigate/config.yml — template; replace host/user/pass per school
mqtt:
  host: mosquitto
  port: 1883

ffmpeg:
  hwaccel_args: preset-nvidia-h264   # adjust if no NVIDIA on dev machine

detectors:
  onnx:
    type: onnx  # or tensorrt/openvino per Frigate docs for GPU box

cameras:
  gate_front:
    ffmpeg:
      inputs:
        - path: rtsp://user:pass@192.168.1.21:554/stream1
          roles: [detect, record]
    detect:
      width: 1280
      height: 720
      fps: 5
    zones:
      restricted:
        coordinates: 0.1,0.1,0.9,0.1,0.9,0.9,0.1,0.9
      litter_watch:
        coordinates: 0.2,0.4,0.8,0.4,0.8,0.95,0.2,0.95
    record:
      enabled: true
      retain:
        days: 30

  # yard_1, building_a, hall_1 — same pattern for up to 4

objects:
  track: [person, bottle, cup, backpack, handbag, umbrella]
```

**Windows/Laragon dev without GPU:** set detector to `cpu` and comment `hwaccel_args`.

- [ ] **Step 1: Add frigate service to compose with `/config`, media volume, port 5000 internal only (optional publish 5000 for LAN admin)**

- [ ] **Step 2: Document in README how to set RTSP for IP vs DVR channel**

- [ ] **Step 3: Commit**

```bash
git add frigate docker-compose.yml data/config README.md
git commit -m "feat(frigate): pilot camera config template and compose service"
```

---

### Task 10: Next.js dashboard — auth + event list + review

**Files:**
- Create: `apps/web/*` (Next.js App Router + Tailwind)
- Modify: `docker-compose.yml` — `web` service port 3000

**Interfaces:**
- Consumes: `POST /api/auth/login`, `GET /api/events`, `GET /api/events/{id}`, `PATCH /api/events/{id}/review`, `GET /api/cameras`
- Produces: pages `/login`, `/` (dashboard), `/events/[eventId]`

**UI requirements:**
- Thai labels; event banners use “พบเหตุที่ควรตรวจสอบ”
- Filters: status, camera, type
- Admin buttons: ยืนยันเหตุ / ไม่ใช่เหตุ (+ note field)
- Viewer: no review buttons
- Evidence: show thumb via API static mount or proxied `/api/events/{id}/evidence/thumb` (add route if needed serving file only for admin JWT)

- [ ] **Step 1: Scaffold Next.js**

```bash
cd apps
npx create-next-app@15 web --typescript --tailwind --eslint --app --src-dir --import-alias "@/*" --use-npm
```

- [ ] **Step 2: Add `src/lib/api.ts` fetch wrappers with token in memory/localStorage**

- [ ] **Step 3: Login page + auth gate**

- [ ] **Step 4: Dashboard table of events + cameras status strip**

- [ ] **Step 5: Event detail + review actions**

- [ ] **Step 6: Manual smoke**

```bash
# API running on :8000
cd apps/web && npm run dev
# login admin → see empty list → create event via curl with system token → appears → confirm
```

- [ ] **Step 7: Dockerfile for web + compose service**

```dockerfile
FROM node:22-alpine AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build
CMD ["npm", "start"]
```

Env: `NEXT_PUBLIC_API_URL=http://localhost:8000` for browser calls to API on LAN.

- [ ] **Step 8: Commit**

```bash
git add apps/web docker-compose.yml
git commit -m "feat(web): internal dashboard login, events list, and review"
```

---

### Task 11: End-to-end wiring + seed script + final README

**Files:**
- Create: `scripts/smoke_create_event.py`, `data/config/schedule.yml`, `data/config/rules.yml`
- Modify: `README.md`, `.env.example` if gaps

**Interfaces:**
- Smoke script uses `SYSTEM_API_TOKEN` to POST a synthetic `person_after_hours` event and writes matching evidence folder for dashboard demo without Frigate.

- [ ] **Step 1: Implement `scripts/smoke_create_event.py`**

```python
# writes ./data/events/EVT-.../event.json + posts to API
```

- [ ] **Step 2: Run smoke against local API; confirm dashboard + review + (optional) LINE**

- [ ] **Step 3: README sections: architecture diagram (text), quick start, RTSP notes, PDPA notes, ports (3000 web, 8000 api, 3307 mysql, 5000 frigate optional, 1883 mqtt)**

- [ ] **Step 4: Commit**

```bash
git add scripts data/config README.md
git commit -m "docs: E2E smoke script and operator quick start"
```

---

### Task 12: Verification checklist (definition of done)

- [ ] **Step 1: API unit tests green**

```bash
cd apps/api && pytest -v
```

- [ ] **Step 2: Worker unit tests green**

```bash
cd apps/event-worker && pytest -v
```

- [ ] **Step 3: Smoke event visible in DB and `/data/events`**

- [ ] **Step 4: Review confirm updates status; audit_logs has `review_confirm` (and `send_line` if LINE configured)**

- [ ] **Step 5: Confirm no evidence file is sent to LINE payload (inspect mock/logs)**

- [ ] **Step 6: Final commit if fixes needed**

```bash
git add -A
git commit -m "test: MVP verification fixes"
```

---

## Spec coverage checklist (self-review)

| Spec requirement | Task |
|------------------|------|
| Mixed IP + Analog via RTSP | 9 |
| Frigate + GPU server | 9 |
| event-worker rules 1,2,5,7,8,9 | 6, 7 |
| Dual API + files | 4, 5 |
| Dashboard review | 10 |
| LINE after confirm text-only | 8 |
| Auth roles admin/viewer/system | 3 |
| Audit log | 4 |
| Local-first / no face ID | Global + 9, 10 |
| 2–4 pilot cameras | 9 |
| Schedules / zones | 5, 6, 9 |
| Retention 30 days Frigate | 9 config |
| Smoke / success criteria | 11, 12 |

## Placeholder scan

No TBD/TODO steps; thresholds use numeric defaults from spec.

## Type consistency

- `event_id` string format `EVT-YYYYMMDD-####` shared worker ↔ API ↔ web
- Review decision enum: `confirmed` | `false_positive`
- System auth header: `X-System-Token`
- Evidence relative_path: `events/EVT-.../` under `EVIDENCE_ROOT`

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-23-school-cctv-security.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — execute tasks in this session with checkpoints  

Which approach?
