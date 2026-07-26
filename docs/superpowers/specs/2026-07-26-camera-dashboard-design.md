# Camera Dashboard (Preview + Config + Control) — Design Spec

**Date:** 2026-07-26
**Project:** `cctvbot`
**Status:** Approved for implementation planning
**Mode:** Internal dashboard (school LAN); admin-only camera management.

---

## 1. Purpose

There is no admin-facing way to preview, configure, or control cameras. Cameras are
only listed (`GET /api/cameras`) and updated by the worker (`PUT`, system token). This
spec adds an admin camera dashboard: live-ish preview (Frigate snapshot proxied through
the authenticated API — Frigate stays un-exposed), editable metadata (name/zone), and
enable/disable monitoring that actually suppresses events.

## 2. Scope

### In scope
- `GET /api/cameras/{id}/snapshot` (admin) — proxy Frigate `latest.jpg`.
- `PATCH /api/cameras/{id}` (admin) — edit `name`, `zone`, `enabled`.
- `Camera.enabled` column; `create_event` drops events from disabled cameras.
- `/cameras` admin page: preview (auto-refresh) + inline edit + enable toggle.
- API `frigate_base_url` config; AppHeader admin link.

### Out of scope
- Editing `frigate/config.yml` (RTSP/detect/zones).
- PTZ / ONVIF control.
- Viewer access to preview (admin-only; preview shows people).

## 3. Security & constraints

- Preview is **server-side proxied**: the API fetches `{FRIGATE_BASE_URL}/api/{id}/latest.jpg`
  and returns the bytes. The browser never talks to Frigate → Frigate stays LAN-only,
  un-exposed (per the local-first spec).
- All new endpoints + the `/cameras` page are `admin`-only.
- No live Frigate in the dev environment → the proxy is unit-tested with a mocked
  Frigate fetch; the real image path requires a live Frigate (deployment verification).

## 4. Data model

Add to `Camera` (`apps/api/app/models.py`):
```
enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
```
Created via `Base.metadata.create_all` like the rest of the schema (the project uses no
Alembic). **Existing deployed databases need a one-time**
`ALTER TABLE cameras ADD COLUMN enabled TINYINT(1) NOT NULL DEFAULT 1;` — documented in
DEPLOY.md. Worker-created cameras (via `PUT`) default to `enabled=True`.

`CameraResponse` gains `enabled: bool`.

## 5. Endpoints

### `PATCH /api/cameras/{camera_id}` — admin
Body `CameraConfigUpdate` (all optional): `name`, `zone`, `enabled`. Partial update:
only provided fields change. 404 if the camera does not exist. Returns `CameraResponse`.
Distinct from the existing system-token `PUT` (worker status upserts).

### `GET /api/cameras/{camera_id}/snapshot` — admin
404 if the camera is unknown. Otherwise fetch `{frigate_base_url}/api/{camera_id}/latest.jpg`
server-side (10s timeout). Frigate 200 → return the JPEG as `image/jpeg`. Frigate
unreachable or non-200 → **502** "snapshot unavailable". The Frigate fetch lives in a
small module function so tests can monkeypatch it.

### `POST /api/events` (existing) — respect `enabled`
Before creating: if the target camera exists and `enabled is False`, do **not** create
the event; return **202** `{"detail": "camera monitoring disabled", "event_id": ...}`.
Unknown camera (first event) proceeds normally (created enabled by default). This gives
disable a real effect — no alerts from disabled cameras.

## 6. Config

`apps/api/app/config.py`: add `frigate_base_url: str = "http://frigate:5000"`.
`.env.example`: add `FRIGATE_BASE_URL=http://frigate:5000` under the API section.

## 7. Frontend

`apps/web/src/lib/api.ts`:
- extend `Camera` with `enabled: boolean`.
- `updateCamera(id, { name?, zone?, enabled? }) -> Camera`.
- `cameraSnapshotUrl(id)` helper + reuse the authed-blob fetch pattern for the image
  (snapshot needs the JWT, so fetch as blob → object URL, like evidence thumbnails).

`apps/web/src/app/cameras/page.tsx` (admin, behind `AuthGate`): a grid of camera cards,
each showing the proxied snapshot (auto-refresh ~5s + manual refresh), an inline
name/zone edit, and an enable/disable toggle. Non-admins are redirected/notified.

`apps/web/src/components/AppHeader.tsx`: add a "จัดการกล้อง" link to `/cameras`
(admin only).

## 8. Testing (validation bar)

API (`apps/api/tests/`):
- `PATCH` edits name/zone/enabled (partial); 404 unknown camera; viewer → 403.
- snapshot: mocked Frigate → 200 `image/jpeg` + bytes; unknown camera → 404; Frigate
  failure → 502.
- `create_event` drops events from a disabled camera (202, no row) and creates for an
  enabled/unknown camera.
- `CameraResponse` includes `enabled`.

Frontend: `npm run build`, `eslint`, `tsc --noEmit` clean.

All existing suites stay green: API 52 (before new tests), worker 90.

## 9. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Adding `enabled` breaks an already-deployed DB (no migrations) | Documented one-time `ALTER TABLE` in DEPLOY.md; consistent with the project's create_all approach. |
| Snapshot polling load on Frigate/API | ~5s interval, admin-only, small pilot; manual refresh otherwise. |
| Frigate exposure | Server-side proxy only; browser never reaches Frigate. |
| Live preview unverifiable without Frigate | Proxy unit-tested with mock; real image is a deployment check (documented). |
| Disabled camera still writes evidence to disk (worker dual-write) | Acceptable; the API drop prevents the alert/event row. Note for later worker-side gating. |
