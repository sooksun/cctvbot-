# School CCTV Security System (cctvbot) — Design Spec

**Date:** 2026-07-23  
**Project:** `cctvbot`  
**Status:** Approved for implementation planning  
**Mode:** Local-first / on-premise (school server)

---

## 1. Purpose

Build an on-premise school security assistance system that:

1. Ingests video from mixed **IP cameras** and **Analog cameras (via DVR RTSP)**.
2. Detects **signals that warrant human review** (not automatic guilt judgments).
3. Emits events via **realtime API** and **evidence files** (JSON + image + clip).
4. Shows events on an **internal Web Dashboard**.
5. Sends **LINE text-only** alerts **only after a human confirms** an event.

Primary users: school director / security staff operating entirely on school LAN (no child imagery leaving the school, except optional short LINE text after confirmation).

---

## 2. Goals and Non-Goals

### Goals (MVP)

- Connect **2–4 pilot cameras** (IP and/or Analog via DVR RTSP).
- Detect event types: **1, 2, 5, 7, 8, 9** (see §5).
- Persist evidence under a school-controlled path.
- Human review workflow with audit log.
- LINE short text after `confirmed` only.

### Non-Goals (MVP)

- Face recognition / student identity matching.
- Classroom instructional observation / PLC reports (later phase).
- Animal, tree-fall, smoke/fire detection (later phase).
- Replacing the existing NVR/DVR recording system.
- Public internet exposure of cameras, Frigate, or evidence storage.
- Auto-punishment or automated disciplinary decisions.

---

## 3. Design Principles

1. **Local-first:** Video, snapshots, and clips stay on school servers.
2. **Human-in-the-loop:** AI proposes; humans confirm.
3. **Language of uncertainty:** UI/API copy uses “พบเหตุที่ควรตรวจสอบ”, never definitive blame.
4. **Dual output (Approach C):** Realtime API + durable evidence files so failures of one path do not lose proof.
5. **Camera-agnostic AI layer:** Worker and API only see RTSP-backed `camera_id` streams; IP vs Analog is handled at ingest.

---

## 4. Architecture

```
IP Camera ──RTSP/ONVIF──┐
                        ├──► Frigate (GPU: RTX 5070 Ti)
Analog ──► DVR ──RTSP───┘      detect / record / clips / health
                              │
                              ▼ MQTT / Webhook
                        event-worker (Python)
                              │  rules 1,2,5,7,8,9
                              │  debounce / zones / schedules
                              ├──► write /data/events/{id}/
                              └──► POST /api/events
                                        │
                                   API (FastAPI)
                                        ├──► MySQL
                                        └──► evidence paths
                                        │
                              Next.js Dashboard (LAN)
                                        │
                              review → confirmed
                                        │
                              LINE Messaging API (text only)
```

### Components

| Component | Tech | Responsibility |
|-----------|------|----------------|
| Frigate | Docker + YOLO + GPU | RTSP ingest, object detection, recording, clips, camera health |
| event-worker | Python | Map Frigate signals → school rules; write evidence files; POST events |
| api | FastAPI | Events, review, cameras, audit, LINE dispatch after confirm |
| web | Next.js + Tailwind | Internal dashboard, review UI, clip playback (auth) |
| db | MySQL | events, cameras, users, audit_logs |
| evidence store | Bind mount `/data/events` | `event.json`, `thumb.jpg`, `clip.mp4` |

### Network policy

- Cameras/NVR/DVR reachable only on school LAN/VLAN.
- No port-forward of cameras, Frigate UI, or raw RTSP to the public internet.
- Dashboard on school LAN (HTTPS preferred in production).
- External access (if any later) only via school VPN — not in MVP requirement.

---

## 5. Event Types (MVP)

| Rule code | `event_type` | Description |
|-----------|--------------|-------------|
| 1 | `person_after_hours` | Person detected during `school_closed` schedule |
| 1 | `person_restricted_zone` | Person inside restricted polygon zone |
| 2 | `person_fall_or_down` | Person fallen / lying still beyond threshold |
| 5 | `camera_offline` | Stream/camera unavailable beyond threshold |
| 5 | `camera_tamper` | Black/blurred/sudden scene change (possible cover/repoint) |
| 7 | `abnormal_motion` | High-speed / violent motion in monitored zones |
| 7 | `abnormal_crowd` | Dense group of people beyond threshold |
| 8 | `possible_littering` | Suspected littering (object leave-hand / ground near person) |
| 9 | `possible_fight` | Suspected fight / close-range aggressive multi-person motion |

All new events start as `status: pending_review`.

### Default rule thresholds (tunable via config)

| Rule | Initial threshold |
|------|-------------------|
| After hours | Config schedule e.g. weekdays 18:00–06:00, full weekend |
| Fall / still | Still ≥ **15** seconds |
| Camera offline | Offline ≥ **30** seconds |
| Crowd | ≥ **5** persons in proximity window |
| Fight | ≥ **2** persons, close range, aggressive motion ≥ **3** seconds |
| Littering | Person + small object trajectory to ground in `litter_watch` zone within **3–8** seconds |
| Debounce | Same type + same camera within **60** seconds → merge |
| Clip window | Before **30s**, after **30s** (fall/fight after may use **60s**) |

Rules 8 and 9 are higher false-positive risk; review UI must make confirm / false_positive fast.

---

## 6. Evidence Files + Realtime API

### Directory layout

```
/data/events/
  EVT-YYYYMMDD-####/
    event.json
    thumb.jpg
    clip.mp4
    detections.json    # optional
```

### `event.json` (schema v1.0)

Required conceptual fields:

- `event_id`, `schema_version`, `source` (`cctvbot`)
- `camera` (`camera_id`, `name`, `stream_type`, `zone`)
- `event_type`, `severity`, `status`, `confidence`
- `started_at`, `ended_at`, `detected_at` (ISO-8601 with offset)
- `rule` (`code`, `name`, `params`)
- `objects[]` (`label`, `count`, `track_ids`)
- `evidence` (relative file names + clip margins + `relative_path`)
- `review` (`reviewed_by`, `reviewed_at`, `decision`, `note`)
- `notifications` (`dashboard`, `line_sent`, `line_sent_at`)
- `message_th` (human-readable Thai summary without student names)

### Event status lifecycle

```
pending_review
  → confirmed | false_positive
  → action_taken   (optional operational step)
  → closed
```

### API (MVP)

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/events` | Create event (worker / system) |
| `GET` | `/api/events` | List/filter (`status`, camera, type, time) |
| `GET` | `/api/events/{id}` | Event detail |
| `PATCH` | `/api/events/{id}/review` | Human review decision |
| `GET` | `/api/events/{id}/evidence` | Evidence metadata + internal paths/URLs |
| `GET` | `/api/cameras` | Camera online/offline + labels |
| `POST` | `/api/auth/login` | Session/JWT for dashboard users |

On `decision = confirmed`, API enqueues LINE text-only notification and sets `notifications.line_sent`.

### Dual-write guarantee

1. Worker writes evidence directory first (or atomically as a temp dir then rename).
2. Worker POSTs event to API with `event_id` and relative evidence path.
3. If API is down, files remain consumable by a folder watcher or later replay import.

---

## 7. Notifications

| Channel | When | Content |
|---------|------|---------|
| Web Dashboard | Immediately on event create | Full event + evidence (auth required) |
| LINE | Only after human `confirmed` | Short Thai text: location, time, type, event_id. **No image, no clip, no student name** |

Example LINE body:

```
[ยืนยันแล้ว] พบเหตุที่ควรตรวจสอบ
จุด: ประตูหน้า | เวลา: 22:14
ประเภท: บุคคลนอกเวลา
รหัส: EVT-20260722-0014
เปิดดูภาพได้ที่ระบบภายในเท่านั้น
```

---

## 8. Auth, Roles, PDPA

### Roles

| Role | Capabilities |
|------|----------------|
| `admin` | View events, review, view clips, configure cameras/schedules, view audit |
| `viewer` | View event list and camera status only (no review, no clip download) |
| `system` | Worker service account: `POST /api/events` only |

No public self-registration.

### Audit log (mandatory)

Every sensitive action records: `who`, `action`, `event_id`, `at`, `ip`, optional `note`.

Actions include: `view_event`, `view_clip`, `download_clip`, `review_confirm`, `review_false_positive`, `send_line`.

### Data retention defaults

| Data | Default |
|------|---------|
| General Frigate recordings | 30 days (config) |
| Confirmed event evidence | Until `closed` or school policy config |
| Audit logs | Longer retention than media (config; do not auto-purge with clips) |

### Privacy constraints

- No AI cameras in toilets / changing rooms.
- No face recognition in MVP.
- Prefer processing entirely on school GPU server (RTX 5070 Ti).
- LINE is an explicit exception for **text after confirm only**.

---

## 9. Repository layout

```
cctvbot/
├── docker-compose.yml
├── frigate/
│   └── config.yml
├── apps/
│   ├── event-worker/
│   ├── api/
│   └── web/
├── data/
│   ├── events/
│   ├── frigate/
│   └── config/          # gitignored secrets & local schedules
├── docs/
│   └── superpowers/specs/
└── README.md
```

---

## 10. Implementation phases (within MVP delivery)

1. Docker Compose + Frigate with **1** RTSP camera smoke test.
2. FastAPI + MySQL schema + evidence path conventions.
3. event-worker: rules **1** and **5** (highest operational value, simpler signals).
4. Next.js dashboard: list + detail + review actions.
5. Rules **2** and **7**.
6. Rules **8** (`possible_littering`) and **9** (`possible_fight`).
7. LINE send on confirm + audit completeness pass.

Pilot camera count remains **2–4** until false-positive rates are acceptable.

---

## 11. Success criteria (MVP)

- At least 2 cameras stream into Frigate on school LAN.
- Creating a synthetic or real rule match produces both API row and `/data/events/{id}/event.json`.
- Admin can confirm/false-positive from dashboard; audit row written.
- Confirmed event triggers LINE text without media.
- Camera offline surfaces as `camera_offline` within configured threshold.
- No camera or evidence port is required to be publicly reachable for the system to function.

---

## 12. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| High false positives on litter/fight | Review-first UX; tunable thresholds; zone limits; debounce |
| Mixed Analog/IP quality | Normalize at DVR/NVR RTSP; per-camera sensitivity |
| GPU overload | Start 2–4 cameras; detect FPS limits in Frigate |
| LINE token leakage | env-only secrets; never log token; gitignore `.env` |
| Over-trust in AI | Copy + training: “ควรตรวจสอบ” only |

---

## 13. Decisions log

| Decision | Choice |
|----------|--------|
| Output mode | C — API realtime + evidence files |
| Camera plant | C — mixed IP + Analog |
| Pilot size | A — 2–4 cameras |
| MVP event set | 1, 2, 5, 7, **8, 9 in MVP** |
| Notifications | Dashboard immediate + LINE text after human confirm |
| Architecture | Frigate + Python event-worker + FastAPI + Next.js + MySQL |
| Hosting | 100% on-premise school server with GPU |

---

## 14. Next step

After stakeholder review of this spec:

1. Write implementation plan (`docs/superpowers/plans/...`).
2. Scaffold repo services and Frigate config for pilot cameras.
3. Implement in phase order (§10).
