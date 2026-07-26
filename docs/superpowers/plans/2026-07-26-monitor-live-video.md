# /monitor Live Video (MSE via go2rtc) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every `/monitor` grid tile play a live MSE video (~1s) from Frigate's go2rtc, falling back to the existing snapshot polling when live is unavailable.

**Architecture:** go2rtc (embedded in Frigate) transcodes each camera's RTSP into MSE over WebSocket. A vendored go2rtc `<video-stream>` web component, wrapped by a React `LiveVideo`, plays it. `MonitorTile` shows live video and, on stream error/timeout, falls back to the `useCameraSnapshot` `<img>` from part A. Frigate stays un-exposed via a same-origin proxy.

**Tech Stack:** Next.js 16 App Router + React 19 + TypeScript + vitest 4 + RTL (web); Frigate go2rtc config (YAML); ffmpeg (audio transcode inside go2rtc).

## Global Constraints

- Live protocol is **MSE** (`mode='mse'`); WebRTC/audio-talk are out of scope.
- **Tapo audio is PCM A-law → MSE cannot play it. go2rtc/Frigate MUST transcode audio to AAC while copying video** — form: `ffmpeg:<rtsp>#video=copy#audio=aac`. (Spike-proven: without this, the `<video>` errors immediately.)
- go2rtc **stream name === `camera_id`** (drives list/snapshot/live from one id).
- Frontend builds the WS URL from `NEXT_PUBLIC_LIVE_WS_BASE` — the **full WS base up to `?src=`**. Dev (standalone go2rtc): `ws://localhost:1984/api/ws`. Prod (Frigate via reverse proxy, same-origin): `/live/mse/api/ws`.
- Cross-origin dev requires go2rtc `api.origin: "*"`; prod is same-origin via the proxy (no origin config).
- Frigate stays LAN-only/un-exposed publicly; the browser reaches go2rtc only via the same-origin proxy in prod.
- Live must **pause when the tab is hidden** — the go2rtc component does this natively (visibilitychange + IntersectionObserver); do not reimplement.
- On live failure (WS/stream error or no frames within a timeout) each tile **falls back to snapshot polling**; the page never blanks. Snapshot code from part A stays intact.
- Vendored files live at `apps/web/public/vendor/go2rtc/{video-rtc.js,video-stream.js}` (pinned copies from go2rtc 1.9.14). All UI copy in Thai.
- Web gates: `npm run test`, `npm run lint`, `npx tsc --noEmit`, `npm run build` all clean; existing suites stay green.

> **Spike status:** `LiveVideo.tsx`, the `MonitorTile` live/fallback wiring, and the vendored files already exist on branch `feat/monitor-live-video` and were proven to play 1080p MSE. This plan **hardens** that spike code (env config, error detection, fallback optimization, fullscreen, tests) and adds the Frigate config + docs. Treat existing spike code as a starting point to refine, not gospel — apply each task's changes on top.

---

### Task 1: Frigate go2rtc config + env + dev/proxy docs

**Files:**
- Modify: `frigate/config.yml` (add top-level `go2rtc:` block)
- Modify: `.env.example` (add `NEXT_PUBLIC_LIVE_WS_BASE`)
- Modify: `DEPLOY.md` (proxy `/live/` WS upgrade + dev standalone go2rtc note)

**Interfaces:**
- Produces: a go2rtc stream named `gate_front` serving MSE with AAC audio; the env var `NEXT_PUBLIC_LIVE_WS_BASE` that Task 2 reads.

- [ ] **Step 1: Add the go2rtc block to `frigate/config.yml`** (above `cameras:`)

```yaml
# Live view (MSE) source. Audio transcoded to AAC because Tapo/G.711 (PCM A-law)
# is not MSE-playable; video is copied (no re-encode). Stream name == camera_id.
go2rtc:
  streams:
    gate_front:
      - "ffmpeg:rtsp://sooksun:{FRIGATE_RTSP_PASSWORD}@192.168.1.34:554/stream1#video=copy#audio=aac"
```

- [ ] **Step 2: Add the env var to `.env.example`** (under a new `# Live video` heading)

```bash
# Live video (MSE). Full WebSocket base up to ?src=.
# Prod (Frigate behind the reverse proxy, same-origin): /live/mse/api/ws
# Dev (standalone go2rtc): ws://localhost:1984/api/ws
NEXT_PUBLIC_LIVE_WS_BASE=/live/mse/api/ws
```

- [ ] **Step 3: Document the proxy + dev go2rtc in `DEPLOY.md`**

Add a "Live video (go2rtc MSE)" subsection stating: (a) the reverse proxy must proxy `/live/` → `frigate:5000` **with WebSocket upgrade** (`Upgrade`/`Connection` headers) so the browser uses same-origin `/live/mse/api/ws?src=<camera_id>` and Frigate stays un-exposed; (b) for local dev without Frigate, run standalone go2rtc with `api.origin: "*"` and set `NEXT_PUBLIC_LIVE_WS_BASE=ws://localhost:1984/api/ws`.

- [ ] **Step 4: Validate YAML + commit**

Run: `python -c "import yaml; yaml.safe_load(open('frigate/config.yml',encoding='utf-8')); print('ok')"`
Expected: `ok`
```bash
git add frigate/config.yml .env.example DEPLOY.md
git commit -m "feat(live): go2rtc MSE config (audio->aac) + live WS env + proxy docs"
```

> Note: `frigate/config.yml` may be locally modified/gitignored per deployment; if the working copy is the real per-site config, apply the same `go2rtc:` block there. The committed template gets the block as shown.

---

### Task 2: Harden `LiveVideo` + unit tests

**Files:**
- Modify: `apps/web/src/components/LiveVideo.tsx` (from the spike)
- Test: `apps/web/src/components/LiveVideo.test.tsx` (new)

**Interfaces:**
- Consumes: `NEXT_PUBLIC_LIVE_WS_BASE`; vendored `/vendor/go2rtc/video-stream.js`.
- Produces: `LiveVideo({ cameraId: string; onError?: () => void })` — mounts `<video-stream mode="mse" src="${base}?src=<cameraId>">`; calls `onError` on load failure, video `error`, or no frames within `FAIL_TIMEOUT_MS = 10000`; removes the element on unmount.

- [ ] **Step 1: Write the failing test**

Create `apps/web/src/components/LiveVideo.test.tsx`:

```tsx
import { render, act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import LiveVideo from "@/components/LiveVideo";

// Pretend the web component is already registered so the module-load path resolves.
beforeEach(() => {
  vi.useFakeTimers();
  (window.customElements as unknown as { get: (n: string) => unknown }).get = () => class {};
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

it("mounts a video-stream with an mse src built from the camera id", async () => {
  const { container } = render(<LiveVideo cameraId="gate_front" />);
  await act(async () => { await Promise.resolve(); });
  const el = container.querySelector("video-stream") as HTMLElement & { src?: string; mode?: string };
  expect(el).not.toBeNull();
  expect(el.mode).toBe("mse");
  expect(el.src).toContain("?src=gate_front");
});

it("calls onError when no frames arrive within the timeout", async () => {
  const onError = vi.fn();
  render(<LiveVideo cameraId="gate_front" onError={onError} />);
  await act(async () => { await Promise.resolve(); });
  await act(async () => { vi.advanceTimersByTime(10000); });
  expect(onError).toHaveBeenCalledTimes(1);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && npm run test -- LiveVideo`
Expected: FAIL (assertions on the spike component's timing/props not yet matching, or module-load path).

- [ ] **Step 3: Refine `LiveVideo.tsx`** so it satisfies the contract

Ensure: reads `process.env.NEXT_PUBLIC_LIVE_WS_BASE || "ws://localhost:1984/api/ws"`; sets `mode="mse"`; builds `` `${base}?src=${encodeURIComponent(cameraId)}` ``; a `FAIL_TIMEOUT_MS = 10000` timer calls `onError` if the inner `<video>` never reaches `readyState >= 2`; the inner `<video>`'s `error` event calls `onError`; clears timers and removes the element on unmount; guards against double-fire with a `settled` flag. (Start from the spike file; make the timeout/settled logic explicit and testable.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/web && npm run test -- LiveVideo`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/LiveVideo.tsx apps/web/src/components/LiveVideo.test.tsx apps/web/public/vendor/go2rtc/
git commit -m "feat(web): LiveVideo MSE wrapper (go2rtc) with timeout+error fallback"
```

---

### Task 3: `MonitorTile` live-first + snapshot fallback (+ don't poll snapshot while live)

**Files:**
- Modify: `apps/web/src/app/monitor/page.tsx` (`MonitorTile`)
- Test: `apps/web/src/app/monitor/page.test.tsx` (extend)

**Interfaces:**
- Consumes: `LiveVideo` (Task 2), `useCameraSnapshot` (part A).
- Produces: a tile that renders `<LiveVideo>` first; on `onError` shows the snapshot `<img>` fallback + freshness; a `🔴 สด` indicator while live.

- [ ] **Step 1: Write the failing test**

Add to `apps/web/src/app/monitor/page.test.tsx` (the file already mocks `@/lib/api` and `@/hooks/useCameraSnapshot`). Add a mock for `LiveVideo` that lets a test trigger `onError`:

```tsx
vi.mock("@/components/LiveVideo", () => ({
  default: ({ cameraId, onError }: { cameraId: string; onError?: () => void }) => (
    <button data-testid={`live-${cameraId}`} onClick={() => onError?.()}>live {cameraId}</button>
  ),
}));
```

Then a test:

```tsx
it("shows live by default and falls back to snapshot on live error", async () => {
  render(<MonitorPage />);
  await waitFor(() => expect(screen.getByTestId("live-gate_front")).toBeInTheDocument());
  // สด indicator visible while live
  expect(screen.getAllByText("🔴 สด").length).toBeGreaterThan(0);
  // trigger live failure for gate_front → fallback path renders (snapshot mock returns url/error)
  fireEvent.click(screen.getByTestId("live-gate_front"));
  await waitFor(() =>
    expect(screen.queryByTestId("live-gate_front")).toBeNull(),
  );
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && npm run test -- monitor`
Expected: FAIL (LiveVideo mock / สด indicator / fallback wiring not matching until MonitorTile is finalized).

- [ ] **Step 3: Finalize `MonitorTile`**

`MonitorTile` renders `<LiveVideo cameraId={cam.camera_id} onError={handleLiveError}/>` (stable `handleLiveError` via `useCallback`) while `!liveFailed`; on error, `setLiveFailed(true)` and render the existing snapshot `<img>`/placeholder block. Show `🔴 สด` while live, else the stale badge + `อัปเดตเมื่อ` line. **Optimization:** only run `useCameraSnapshot` when `liveFailed` is true (e.g. pass an "enabled" flag to the hook or mount a small `SnapshotFallback` child that owns the hook) so healthy live tiles don't also poll snapshots. Keep `FullscreenView` receiving the same data.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/web && npm run test -- monitor`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/app/monitor/page.tsx apps/web/src/app/monitor/page.test.tsx
git commit -m "feat(web): /monitor tiles play live video with snapshot fallback"
```

---

### Task 4: Live video in `FullscreenView` (single stream) + verify

**Files:**
- Modify: `apps/web/src/app/monitor/page.tsx` (`FullscreenView`)
- Test: `apps/web/src/app/monitor/page.test.tsx` (extend)

**Interfaces:**
- Consumes: `LiveVideo`, the tile's live/fallback state.
- Produces: fullscreen showing the live stream (or the snapshot when the tile fell back), preserving ESC/backdrop close + scroll lock from part A.

- [ ] **Step 1: Write the failing test**

Add to `page.test.tsx`:

```tsx
it("fullscreen shows live video when the tile is live", async () => {
  render(<MonitorPage />);
  await waitFor(() => expect(screen.getByRole("button", { name: /กล้องหน้า/ })).toBeInTheDocument());
  fireEvent.click(screen.getByRole("button", { name: /กล้องหน้า/ }));
  const dialog = screen.getByRole("dialog");
  expect(dialog).toBeInTheDocument();
  // a LiveVideo (mocked) is present inside the dialog
  expect(within(dialog).getByTestId("live-gate_front")).toBeInTheDocument();
});
```

(Import `within` from `@testing-library/react`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && npm run test -- monitor`
Expected: FAIL (fullscreen renders snapshot img, not LiveVideo, until updated).

- [ ] **Step 3: Update `FullscreenView`**

When the tile is live (not `liveFailed`), render `<LiveVideo cameraId={cam.camera_id}>` large inside the dialog; when fallen back, render the snapshot `<img>` as today. Pass `liveFailed` (and the snapshot url/error/lastUpdated) from `MonitorTile` into `FullscreenView`. Keep ESC + backdrop close + body-scroll-lock unchanged. To honor "single source per camera", the fullscreen live element is a separate `<video-stream>` for the expanded camera only while the grid tile behind is unmounted or paused (the grid keeps its own; acceptable since only one camera is expanded — OR lift as a follow-up). Keep it simple: render fullscreen LiveVideo; the grid tile's own stream pauses via the component's IntersectionObserver when covered.

- [ ] **Step 4: Run tests + full web gate**

Run: `cd apps/web && npm run test && npm run lint && npx tsc --noEmit && npm run build`
Expected: all clean.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/app/monitor/page.tsx apps/web/src/app/monitor/page.test.tsx
git commit -m "feat(web): live video in /monitor fullscreen view"
```

---

## Verification (whole feature)

- Web: `cd apps/web && npm run test && npm run lint && npx tsc --noEmit && npm run build` — all green.
- Manual (dev, standalone go2rtc as in the spike): open `/monitor` in a **visible** browser tab → `gate_front` plays 1080p MSE (~1s), the `🔴 สด` indicator shows, hiding the tab pauses the stream, and killing go2rtc falls each tile back to snapshot within ~10s.
- Manual (prod): reverse proxy `/live/` → Frigate with WS upgrade; `NEXT_PUBLIC_LIVE_WS_BASE=/live/mse/api/ws`.

## Notes / Out of scope

- WebRTC / two-way audio; adaptive bitrate; substream-for-grid (revisit if many-camera bandwidth is a problem — main stream 1080p per the spec).
- Removing snapshot code — it remains the fallback and powers `/cameras`.
- The spike's go2rtc binary + `go2rtc.yaml` live in the scratchpad (dev only, not committed); production uses Frigate's embedded go2rtc.
