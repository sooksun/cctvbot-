# /monitor Live Video (MSE via Frigate go2rtc) — Design Spec

**Date:** 2026-07-26
**Project:** `cctvbot`
**Status:** Approved for implementation planning
**Mode:** Internal monitor (school LAN); every `/monitor` tile becomes a live MSE video.

---

## 1. Purpose

`/monitor` currently shows near-live **snapshot polling** (a JPEG per tile every 2s). This
spec upgrades every grid tile to a **live MSE video stream** (~1s latency) served by
Frigate's built-in **go2rtc**, while keeping the existing snapshot path as an automatic
**fallback**. Browsers cannot play RTSP directly, so go2rtc is the RTSP→MSE gateway; the
architecture already includes Frigate, so no new infrastructure is added.

## 2. Scope

### In scope
- Add a `go2rtc:` section to `frigate/config.yml` mapping each camera to its RTSP source.
- Frontend: replace the `<img>` snapshot in `MonitorTile` with a live MSE `<video>`;
  **all** grid tiles play live. Fullscreen reuses the same stream.
- **Fallback to snapshot polling** when MSE is unavailable (browser unsupported, stream
  down, WebSocket error) — the page never goes blank.
- **Pause/disconnect the stream when the tab is hidden** (visibilitychange), reconnect on
  show — mirrors the snapshot hook, bounds N-stream cost.
- Same-origin proxy for the go2rtc MSE WebSocket so **Frigate stays un-exposed** (prod:
  reverse proxy `/live/` → Frigate; dev: configurable WS base).
- Dev path to run/verify **without full Frigate** via standalone go2rtc.

### Out of scope
- WebRTC / two-way audio (MSE only this round; WebRTC is go2rtc's own fallback but we do
  not wire the UDP path).
- Recording/clip playback changes (unchanged).
- Removing snapshot code — it stays as the fallback and still powers `/cameras`.
- Multi-quality / adaptive bitrate, PTZ.

## 3. Architecture & data flow

```
Tapo RTSP ──► go2rtc (inside Frigate) ──MSE/WebSocket──► [proxy] ──► browser <video>
                                                                       │ on error
                                                                       ▼
                                          API snapshot proxy ──► <img> (fallback, existing)
```

- **Stream source:** go2rtc (embedded in Frigate). MSE endpoint:
  `ws://<host>/live/mse/api/ws?src=<camera_id>` (Frigate 0.14 proxies go2rtc; MSE is its
  default live mode).
- **Camera identity:** the go2rtc stream name **must equal** the `camera_id` used
  everywhere else (`gate_front`, …) so the same id drives list, snapshot, and live.
- **Latency:** MSE ~1s, no UDP required.

## 4. Frigate go2rtc config

Add to `frigate/config.yml` (top level):
```yaml
go2rtc:
  streams:
    gate_front:
      - rtsp://sooksun:{FRIGATE_RTSP_PASSWORD}@192.168.1.34:554/stream1
```
- Use the **main** stream (`stream1`, 1080p) for live viewing quality; detect keeps using
  the substream (unchanged in the `cameras:` block).
- One entry per enabled camera; the key is the `camera_id`.
- Password continues to come from `FRIGATE_RTSP_PASSWORD` (env), never committed.

## 5. Exposure / proxy (Frigate stays un-exposed)

The browser must reach the go2rtc WebSocket, but Frigate (port 5000) must not be public
(consistent with the snapshot spec's "browser never talks to Frigate directly" for the
public path). The frontend uses a **configurable, same-origin-preferred WS base**:

- Config: `NEXT_PUBLIC_LIVE_WS_BASE` — the **full WebSocket base up to `?src=`**. The tile
  builds `${base}?src=<camera_id>`. This single value absorbs the path difference between
  Frigate's proxied endpoint and standalone go2rtc, so the frontend never hard-codes a path.
- **Prod (Frigate via NPM):** base = same-origin `/live/mse/api/ws`. NPM proxies `/live/` →
  `frigate:5000` **with WebSocket upgrade**; browser uses same-origin `/live/...`. Frigate
  stays LAN-only behind the proxy.
- **Dev (standalone go2rtc):** base = `ws://<host>:1984/api/ws` (go2rtc's native MSE path),
  since there is no NPM in dev.

## 6. Frontend

`apps/web/src/components/LiveVideo.tsx` (new):
- A React wrapper around go2rtc's vendored `video-stream` web component (a pinned copy of
  `video-stream.js` committed to the repo) which plays MSE into a `<video>` element and
  handles reconnect. `LiveVideo` builds the WS URL from `NEXT_PUBLIC_LIVE_WS_BASE`, mounts
  the component, and surfaces its error event as the `onError` prop. Props: `cameraId`,
  `onError` (fires when the stream cannot play).
- Connects on mount / when visible; **disconnects on unmount and when `document.hidden`**;
  reconnects on visible. Autoplay muted, `playsInline`.

`apps/web/src/app/monitor/page.tsx`:
- `MonitorTile` renders `<LiveVideo cameraId=... onError={...}>`. On `onError`, the tile
  **falls back** to the existing `useCameraSnapshot` `<img>` (kept intact). So a tile shows
  live video when possible, else the 2s snapshot, else "ไม่มีภาพจากกล้อง".
- `FullscreenView` receives the same live element/stream (no second connection), matching
  the "single source per camera" rule established in the snapshot fix.
- Status dot, name, badges, and the "อัปเดตเมื่อ" freshness line remain (freshness for the
  fallback snapshot; for live, show a small "สด" indicator instead).

## 7. Testing (validation bar)

Frontend (vitest + RTL; the network/MSE layer is mocked):
- `LiveVideo` renders a `<video>` and attempts a connection to the expected WS URL
  (`.../live/mse/api/ws?src=<id>`) built from `NEXT_PUBLIC_LIVE_WS_BASE`.
- On a simulated stream error, `LiveVideo` calls `onError`, and `MonitorTile` falls back to
  the snapshot `<img>` (assert the fallback renders).
- Hidden-tab: on `visibilitychange` to hidden, the stream disconnects (no reconnect while
  hidden); resumes on visible.
- `npm run test`, `npm run lint`, `npx tsc --noEmit`, `npm run build` clean; existing
  suites stay green.

Manual (needs go2rtc/Frigate): open `/monitor`, confirm the gate_front tile plays live
video ~1s latency, fullscreen keeps playing, and killing the stream falls back to snapshot.

## 8. Dev / testing without full Frigate

Run **standalone go2rtc** (single binary) with a minimal config whose stream name equals
the `camera_id` and points at the Tapo RTSP; it serves MSE at `/api/ws?src=<camera_id>`.
Set `NEXT_PUBLIC_LIVE_WS_BASE=ws://localhost:1984/api/ws` so the frontend builds
`ws://localhost:1984/api/ws?src=<camera_id>`. This verifies the whole frontend live path
(connect, play, fallback, hidden-tab) without Docker/Frigate. Production still uses
Frigate's embedded go2rtc.

## 9. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| N live streams overwhelm CPU/bandwidth as cameras grow | Pause/disconnect on hidden tab; MSE (no per-tile UDP); document a soft cap and revisit adaptive/again-snapshot for large walls. |
| MSE unsupported / stream drops → blank wall | Automatic per-tile fallback to the existing snapshot polling; page never blanks. |
| Exposing Frigate to the browser | Same-origin proxy (`/live/`) with WS upgrade; Frigate stays LAN-only, un-exposed publicly. |
| Vendored go2rtc player drift / CSP | Pin the vendored file; keep the adapter thin and behind `LiveVideo` so it can be swapped without touching tiles. |
| Live path unverifiable without go2rtc | Frontend unit-tested with a mocked MSE layer; real playback verified with standalone go2rtc (dev) / Frigate (prod). |
| Stream name ≠ camera_id mismatch | go2rtc stream key MUST equal `camera_id`; called out in §3/§4 and checked in review. |
