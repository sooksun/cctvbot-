# Camera Monitor Page (Live-ish Snapshot Grid) — Design Spec

**Date:** 2026-07-26
**Project:** `cctvbot`
**Status:** Approved for implementation planning
**Mode:** Internal monitor (school LAN); read-only live-ish view for `viewer` + `admin`.

---

## 1. Purpose

Staff (teachers / guards — role `viewer`) have no way to watch cameras. The only camera
view is `/cameras`, an **admin-only** management page that mixes preview with edit
controls. This spec adds `/monitor`: a read-only, auto-refreshing snapshot grid that both
`viewer` and `admin` can open, with click-to-fullscreen.

This is **part A** of a 3-part camera-management effort. Part B (add/remove cameras via
Frigate config API) and part C (per-camera rule config) are separate specs, planned and
built after A.

## 2. Scope

### In scope
- New page `apps/web/src/app/monitor/page.tsx` — read-only snapshot grid, `viewer`+`admin`.
- Widen `GET /api/cameras/{id}/snapshot` from admin-only to `admin` + `viewer`.
- Reusable `useCameraSnapshot(cameraId, intervalMs)` hook: periodic snapshot fetch,
  object-URL cleanup, and **pause polling while the tab is hidden**. Refactored from the
  inline snapshot logic currently in `CameraCard` so both `/cameras` and `/monitor` share it.
- Responsive grid (1 / 2 / 3 columns by viewport) + click-to-fullscreen overlay.
- Show **all** cameras including offline / `enabled=false`, each with a status badge.
- AppHeader "จอมอนิเตอร์" link, visible to `viewer` + `admin`.

### Out of scope
- Live video (WebRTC / HLS / go2rtc) — snapshot polling only this round.
- Any camera mutation (add / remove / edit / enable) — stays on `/cameras` (parts B/C).
- Multi-grid presets (1×1 / 2×2 / 3×3 chooser) — responsive auto-grid only.
- Per-tile event overlays / last-event badges — deferred.

## 3. Security & privacy

- Snapshots stay **server-side proxied**: the API fetches
  `{FRIGATE_BASE_URL}/api/{id}/latest.jpg` and returns the bytes (JWT-gated). The browser
  never talks to Frigate → Frigate stays LAN-only, un-exposed. Unchanged from the camera
  dashboard spec.
- **Deliberate policy change:** the camera-dashboard spec restricted snapshots to
  admin-only ("preview shows people"). This spec **widens snapshot + the monitor page to
  `viewer`** on purpose — staff monitoring is the whole point of `/monitor`. Accepted
  trade-off: `viewer` accounts are trusted school staff on the LAN, and every route stays
  login-gated. No anonymous access.
- `/monitor` requires authentication (`AuthGate`) but **not** admin; `viewer` is allowed.

## 4. Data model

No schema change. Uses existing `Camera` rows and the existing snapshot proxy.

## 5. Endpoints

### `GET /api/cameras/{camera_id}/snapshot` — widen to `admin` + `viewer`
Change the dependency from `require_roles("admin")` to `require_roles("admin", "viewer")`
in `apps/api/app/routers/cameras.py`. Behavior otherwise unchanged: 404 unknown camera,
502 when Frigate is unreachable/non-200, else the JPEG.

`GET /api/cameras` (list) already allows `admin` + `viewer` — no change.

**No new endpoints.**

## 6. Frontend

`apps/web/src/hooks/useCameraSnapshot.ts` (new):
- Signature `useCameraSnapshot(cameraId: string, intervalMs: number)` →
  `{ url: string | null, error: boolean, refresh: () => void }`.
- Fetches via the existing `fetchCameraSnapshotUrl` (authed blob → object URL).
- Revokes the previous object URL on each update and on unmount (no leaks — mirrors the
  current `CameraCard` cleanup).
- Pauses the interval when `document.hidden` (listen to `visibilitychange`); resumes +
  immediate refresh on becoming visible.
- `/cameras` `CameraCard` is refactored to consume this hook (keeps its 5s cadence);
  `/monitor` uses 2s. Shared logic, no duplication.

`apps/web/src/app/monitor/page.tsx` (new, behind `AuthGate`, no admin gate):
- `MonitorContent` — loads `listCameras()`, handles loading / error / empty states.
- `MonitorGrid` — responsive grid `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3`.
- `MonitorTile` — snapshot (2s via the hook) + camera name + online/offline dot +
  "อัปเดตเมื่อ ..." timestamp + badge for `!enabled` ("ปิดเฝ้าระวัง") / offline. Snapshot
  failure → "ไม่มีภาพจากกล้อง" placeholder. Click → fullscreen.
- `FullscreenView` — fixed overlay showing one camera large, snapshot polling continues
  (2s); close via ESC key or backdrop click. Body scroll locked while open.

`apps/web/src/components/AppHeader.tsx`:
- Add "จอมอนิเตอร์" → `/monitor`, shown to `viewer` + `admin` (unlike the admin-only
  "จัดการกล้อง").

Refresh cadence: **2s** for `/monitor`. All visible tiles poll; hidden-tab pause keeps
idle cost near zero. Fullscreen polls only the one open camera plus the grid behind it.

## 7. Testing (validation bar)

API (`apps/api/tests/`):
- snapshot endpoint: `viewer` JWT now returns 200 `image/jpeg` (mocked Frigate); still
  404 unknown camera and 502 on Frigate failure.

Frontend (`apps/web`, vitest + RTL harness already present):
- `/monitor` renders a tile per camera from a mocked `listCameras`.
- offline / disabled camera renders its badge (not hidden).
- click a tile → `FullscreenView` opens; ESC closes it.
- `useCameraSnapshot`: sets an interval, refreshes, and clears the interval + revokes the
  URL on unmount (fake timers + mocked fetch).
- `npm run build`, `eslint`, `tsc --noEmit` clean.

All existing suites stay green (API + worker + web).

## 8. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Snapshot polling load on Frigate/API with many cameras | 2s interval + pause on hidden tab; small pilot (1 real camera now). Revisit rate if the grid grows large. |
| Widening snapshots to `viewer` exposes live people to more accounts | Deliberate, documented decision (§3); LAN-only, login-gated, trusted staff. |
| Refactoring `CameraCard` onto the shared hook regresses `/cameras` | Keep `CameraCard`'s 5s cadence + manual refresh; covered by existing `/cameras` behavior and new hook tests. |
| Live snapshot path unverifiable without a running Frigate | Hook/endpoint unit-tested with mocks; real image is a deployment check (needs `docker compose up frigate`). |
| Object-URL leaks from fast polling | Hook revokes on every update + unmount (explicit test). |
