# Camera Monitor Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only `/monitor` page where `viewer` + `admin` watch all cameras as an auto-refreshing snapshot grid with click-to-fullscreen.

**Architecture:** Reuse the existing authenticated snapshot proxy (`GET /api/cameras/{id}/snapshot`) — widen it to `viewer`. Extract snapshot polling into a shared `useCameraSnapshot` hook (refresh + object-URL cleanup + pause on hidden tab), consumed by both the existing `CameraCard` and the new monitor page. No new endpoints, no schema change.

**Tech Stack:** FastAPI + pytest (API); Next.js 16 App Router + React 19 + TypeScript + Tailwind + vitest 4 + React Testing Library (web).

## Global Constraints

- `/monitor` + the snapshot endpoint allow `admin` + `viewer`; every route stays login-gated (no anonymous access).
- Snapshots stay server-side proxied — the browser never calls Frigate directly.
- Refresh cadence: `/monitor` = 2000ms; existing `/cameras` `CameraCard` keeps 5000ms.
- No DB schema change; no new API endpoints.
- All UI copy in Thai.
- All existing suites stay green (API, worker, web). Web gates: `npm run test`, `npm run build`, `npm run lint` all clean.

---

### Task 1: Widen snapshot endpoint to `viewer`

**Files:**
- Modify: `apps/api/app/routers/cameras.py` (the `get_camera_snapshot` dependency, ~line 136)
- Test: `apps/api/tests/test_events.py` (add one test beside the existing snapshot tests ~line 493)

**Interfaces:**
- Consumes: existing `require_roles`, `_fetch_frigate_snapshot`, `admin_headers`/`client`/`sample_event` fixtures.
- Produces: `GET /api/cameras/{id}/snapshot` reachable by `viewer` JWT (still 404 unknown, 502 Frigate-down).

- [ ] **Step 1: Write the failing test**

Add to `apps/api/tests/test_events.py`:

```python
def test_snapshot_allowed_for_viewer(client, sample_event, monkeypatch):
    del sample_event
    from app.auth import hash_password
    from app.db import SessionLocal
    from app.models import User
    from app.routers import cameras

    db = SessionLocal()
    try:
        if not db.query(User).filter(User.username == "viewer_snap").first():
            db.add(
                User(
                    username="viewer_snap",
                    password_hash=hash_password("viewpass123"),
                    role="viewer",
                )
            )
            db.commit()
    finally:
        db.close()
    token = client.post(
        "/api/auth/login",
        json={"username": "viewer_snap", "password": "viewpass123"},
    ).json()["access_token"]

    monkeypatch.setattr(
        cameras, "_fetch_frigate_snapshot", lambda cid: b"\xff\xd8\xfffakejpeg"
    )
    r = client.get(
        "/api/cameras/cam_front_gate/snapshot",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert "image/jpeg" in r.headers.get("content-type", "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && python -m pytest tests/test_events.py::test_snapshot_allowed_for_viewer -v`
Expected: FAIL with 403 (viewer currently forbidden).

- [ ] **Step 3: Widen the role**

In `apps/api/app/routers/cameras.py`, in `get_camera_snapshot`, change:

```python
    user: Annotated[User, Depends(require_roles("admin"))],
```
to:
```python
    user: Annotated[User, Depends(require_roles("admin", "viewer"))],
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/api && python -m pytest tests/test_events.py -k snapshot -v`
Expected: PASS — `test_snapshot_allowed_for_viewer`, `test_snapshot_proxies_frigate`, `test_snapshot_unknown_camera_404`, `test_snapshot_frigate_down_502`.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/routers/cameras.py apps/api/tests/test_events.py
git commit -m "feat(api): allow viewer role to read camera snapshots"
```

---

### Task 2: Shared `useCameraSnapshot` hook + refactor `CameraCard`

**Files:**
- Create: `apps/web/src/hooks/useCameraSnapshot.ts`
- Create: `apps/web/src/hooks/useCameraSnapshot.test.tsx`
- Modify: `apps/web/src/app/cameras/page.tsx` (`CameraCard`: replace inline snapshot state/effect with the hook)

**Interfaces:**
- Consumes: `fetchCameraSnapshotUrl(cameraId: string): Promise<string>` from `@/lib/api`.
- Produces: `useCameraSnapshot(cameraId: string, intervalMs: number): { url: string | null; error: boolean; refresh: () => void }`.

- [ ] **Step 1: Write the failing test**

Create `apps/web/src/hooks/useCameraSnapshot.test.tsx`:

```tsx
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const fetchSnapshot = vi.fn();
vi.mock("@/lib/api", () => ({
  fetchCameraSnapshotUrl: (id: string) => fetchSnapshot(id),
}));

import { useCameraSnapshot } from "@/hooks/useCameraSnapshot";

describe("useCameraSnapshot", () => {
  beforeEach(() => {
    fetchSnapshot.mockReset();
    fetchSnapshot.mockResolvedValue("blob:fake-url");
    vi.stubGlobal("URL", {
      ...URL,
      revokeObjectURL: vi.fn(),
    });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("fetches a snapshot on mount and exposes the url", async () => {
    const { result } = renderHook(() => useCameraSnapshot("cam1", 2000));
    await waitFor(() => expect(result.current.url).toBe("blob:fake-url"));
    expect(fetchSnapshot).toHaveBeenCalledWith("cam1");
  });

  it("sets error=true when the fetch rejects", async () => {
    fetchSnapshot.mockRejectedValueOnce(new Error("boom"));
    const { result } = renderHook(() => useCameraSnapshot("cam2", 2000));
    await waitFor(() => expect(result.current.error).toBe(true));
  });

  it("revokes the object URL on unmount", async () => {
    const { result, unmount } = renderHook(() => useCameraSnapshot("cam3", 2000));
    await waitFor(() => expect(result.current.url).toBe("blob:fake-url"));
    unmount();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:fake-url");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && npm run test -- useCameraSnapshot`
Expected: FAIL — module `@/hooks/useCameraSnapshot` not found.

- [ ] **Step 3: Create the hook**

Create `apps/web/src/hooks/useCameraSnapshot.ts`:

```ts
import { useCallback, useEffect, useRef, useState } from "react";
import { fetchCameraSnapshotUrl } from "@/lib/api";

/**
 * Poll a camera's snapshot on an interval. Revokes prior object URLs, and
 * pauses polling while the browser tab is hidden (resumes + refreshes on show).
 */
export function useCameraSnapshot(
  cameraId: string,
  intervalMs: number,
): { url: string | null; error: boolean; refresh: () => void } {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const urlRef = useRef<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const next = await fetchCameraSnapshotUrl(cameraId);
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
      urlRef.current = next;
      setUrl(next);
      setError(false);
    } catch {
      setError(true);
    }
  }, [cameraId]);

  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | null = null;

    const start = () => {
      if (timer) return;
      void refresh();
      timer = setInterval(() => void refresh(), intervalMs);
    };
    const stop = () => {
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
    };
    const onVisibility = () => {
      if (document.hidden) stop();
      else start();
    };

    start();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
      if (urlRef.current) {
        URL.revokeObjectURL(urlRef.current);
        urlRef.current = null;
      }
    };
  }, [refresh, intervalMs]);

  return { url, error, refresh };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/web && npm run test -- useCameraSnapshot`
Expected: PASS (3 tests).

- [ ] **Step 5: Refactor `CameraCard` onto the hook**

In `apps/web/src/app/cameras/page.tsx`, inside `CameraCard`:

Add the import near the top of the file (with the other imports):
```ts
import { useCameraSnapshot } from "@/hooks/useCameraSnapshot";
```

Replace the snapshot state + `loadSnap` + its `useEffect` (the `snap`/`setSnap` `useState`, the `loadSnap` `useCallback`, and the `useEffect` that sets the 5s interval) with:

```tsx
  const { url: snap, error: snapErr, refresh: loadSnap } = useCameraSnapshot(
    cam.camera_id,
    5000,
  );
```

Then in the JSX, the image block uses `snap` as before, and the error placeholder shows when `snapErr` is true:

```tsx
        {snap ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={snap}
            alt={`ภาพ ${cam.name}`}
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-slate-400">
            {snapErr ? "ไม่มีภาพจากกล้อง" : "กำลังโหลด..."}
          </div>
        )}
```

The manual "รีเฟรชภาพ" button keeps calling `loadSnap` (now the hook's `refresh`). Remove the now-unused `err`-for-snapshot local wiring if it only served the snapshot; keep the `err` state used by `save()`.

- [ ] **Step 6: Verify `/cameras` still builds + lints + type-checks**

Run: `cd apps/web && npm run test && npm run lint && npx tsc --noEmit`
Expected: all clean; existing web tests still pass.

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/hooks/useCameraSnapshot.ts apps/web/src/hooks/useCameraSnapshot.test.tsx apps/web/src/app/cameras/page.tsx
git commit -m "refactor(web): extract useCameraSnapshot hook, reuse in CameraCard"
```

---

### Task 3: `/monitor` page (grid + tile + fullscreen)

**Files:**
- Create: `apps/web/src/app/monitor/page.tsx`
- Create: `apps/web/src/app/monitor/page.test.tsx`

**Interfaces:**
- Consumes: `listCameras(): Promise<Camera[]>`, `Camera` from `@/lib/api`; `useCameraSnapshot` from Task 2; `AuthGate`, `AppHeader` components.
- Produces: default-export `MonitorPage` React component at route `/monitor`.

- [ ] **Step 1: Write the failing test**

Create `apps/web/src/app/monitor/page.test.tsx`:

```tsx
import type { ReactNode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const listCameras = vi.fn();
vi.mock("@/lib/api", () => ({
  listCameras: () => listCameras(),
  isAdmin: () => false,
}));
vi.mock("@/hooks/useCameraSnapshot", () => ({
  useCameraSnapshot: () => ({ url: null, error: true, refresh: vi.fn() }),
}));
vi.mock("@/components/AuthGate", () => ({
  default: ({ children }: { children: ReactNode }) => <>{children}</>,
}));
vi.mock("@/components/AppHeader", () => ({ default: () => <div /> }));

import MonitorPage from "@/app/monitor/page";

const CAMS = [
  {
    camera_id: "gate_front",
    name: "กล้องหน้า",
    stream_type: "ip",
    zone: "gate",
    is_online: true,
    enabled: true,
    last_seen_at: null,
    created_at: null,
  },
  {
    camera_id: "yard_1",
    name: "สนาม",
    stream_type: "ip",
    zone: "yard",
    is_online: false,
    enabled: false,
    last_seen_at: null,
    created_at: null,
  },
];

describe("MonitorPage", () => {
  beforeEach(() => {
    listCameras.mockReset();
    listCameras.mockResolvedValue(CAMS);
  });

  it("renders a tile per camera including offline/disabled", async () => {
    render(<MonitorPage />);
    await waitFor(() => expect(screen.getByText("กล้องหน้า")).toBeInTheDocument());
    expect(screen.getByText("สนาม")).toBeInTheDocument();
    expect(screen.getByText("ปิดเฝ้าระวัง")).toBeInTheDocument();
  });

  it("opens fullscreen on tile click and closes on Escape", async () => {
    render(<MonitorPage />);
    await waitFor(() => expect(screen.getByText("กล้องหน้า")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /กล้องหน้า/ }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && npm run test -- monitor`
Expected: FAIL — module `@/app/monitor/page` not found.

- [ ] **Step 3: Create the page**

Create `apps/web/src/app/monitor/page.tsx`:

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import AppHeader from "@/components/AppHeader";
import AuthGate from "@/components/AuthGate";
import { Camera, listCameras } from "@/lib/api";
import { useCameraSnapshot } from "@/hooks/useCameraSnapshot";

const REFRESH_MS = 2000;

function StatusBadges({ cam }: { cam: Camera }) {
  return (
    <span className="flex items-center gap-1.5">
      <span
        className={`h-2.5 w-2.5 rounded-full ${
          cam.is_online ? "bg-green-500" : "bg-red-500"
        }`}
      />
      <span className="text-sm text-slate-800">{cam.name}</span>
      {!cam.enabled ? (
        <span className="rounded bg-slate-200 px-1.5 text-xs text-slate-600">
          ปิดเฝ้าระวัง
        </span>
      ) : null}
      {!cam.is_online ? (
        <span className="rounded bg-red-100 px-1.5 text-xs text-red-700">
          ออฟไลน์
        </span>
      ) : null}
    </span>
  );
}

function MonitorTile({ cam, onExpand }: { cam: Camera; onExpand: () => void }) {
  const { url, error } = useCameraSnapshot(cam.camera_id, REFRESH_MS);
  return (
    <button
      type="button"
      onClick={onExpand}
      aria-label={cam.name}
      className="overflow-hidden rounded-xl border border-slate-200 bg-white text-left shadow-sm hover:border-slate-300"
    >
      <div className="aspect-video overflow-hidden bg-slate-100">
        {url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={url} alt={`ภาพ ${cam.name}`} className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-slate-400">
            {error ? "ไม่มีภาพจากกล้อง" : "กำลังโหลด..."}
          </div>
        )}
      </div>
      <div className="p-3">
        <StatusBadges cam={cam} />
      </div>
    </button>
  );
}

function FullscreenView({ cam, onClose }: { cam: Camera; onClose: () => void }) {
  const { url, error } = useCameraSnapshot(cam.camera_id, REFRESH_MS);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [onClose]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`ภาพเต็มจอ ${cam.name}`}
      onClick={onClose}
      className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-black/90 p-4"
    >
      <div className="mb-2 text-sm text-white">{cam.name} — กด ESC เพื่อปิด</div>
      {url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={url}
          alt={`ภาพเต็มจอ ${cam.name}`}
          className="max-h-[85vh] max-w-full rounded-lg object-contain"
        />
      ) : (
        <div className="text-slate-300">
          {error ? "ไม่มีภาพจากกล้อง" : "กำลังโหลด..."}
        </div>
      )}
    </div>
  );
}

function MonitorContent() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Camera | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setCameras(await listCameras());
    } catch (e) {
      setError(e instanceof Error ? e.message : "โหลดกล้องไม่สำเร็จ");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader />
      <main className="mx-auto max-w-6xl space-y-4 px-4 py-6">
        <h1 className="text-lg font-semibold text-slate-900">จอมอนิเตอร์</h1>
        {error ? (
          <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
        ) : loading ? (
          <p className="text-sm text-slate-500">กำลังโหลด...</p>
        ) : cameras.length === 0 ? (
          <p className="text-sm text-slate-500">ยังไม่มีกล้องในระบบ</p>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {cameras.map((cam) => (
              <MonitorTile
                key={cam.camera_id}
                cam={cam}
                onExpand={() => setExpanded(cam)}
              />
            ))}
          </div>
        )}
      </main>
      {expanded ? (
        <FullscreenView cam={expanded} onClose={() => setExpanded(null)} />
      ) : null}
    </div>
  );
}

export default function MonitorPage() {
  return (
    <AuthGate>
      <MonitorContent />
    </AuthGate>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/web && npm run test -- monitor`
Expected: PASS (2 tests).

- [ ] **Step 5: Verify build + lint + types**

Run: `cd apps/web && npm run build && npm run lint && npx tsc --noEmit`
Expected: all clean.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/app/monitor/page.tsx apps/web/src/app/monitor/page.test.tsx
git commit -m "feat(web): read-only /monitor snapshot grid with fullscreen"
```

---

### Task 4: AppHeader "จอมอนิเตอร์" link (viewer + admin)

**Files:**
- Modify: `apps/web/src/components/AppHeader.tsx`
- Modify: `apps/web/src/components/AppHeader.test.tsx`

**Interfaces:**
- Consumes: existing `getRole`, `getUsername`, `Link`.
- Produces: a `/monitor` link visible to any authenticated role; the admin-only `/cameras` link is unchanged.

- [ ] **Step 1: Write the failing test**

In `apps/web/src/components/AppHeader.test.tsx`, add to the `describe`:

```tsx
  it("shows the monitor link for a viewer", () => {
    localStorage.setItem("cctvbot_role", "viewer");
    render(<AppHeader />);
    expect(screen.getByText("จอมอนิเตอร์")).toBeInTheDocument();
    expect(screen.queryByText("จัดการกล้อง")).toBeNull();
  });

  it("shows the monitor link for an admin too", () => {
    localStorage.setItem("cctvbot_role", "admin");
    render(<AppHeader />);
    expect(screen.getByText("จอมอนิเตอร์")).toBeInTheDocument();
    expect(screen.getByText("จัดการกล้อง")).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && npm run test -- AppHeader`
Expected: FAIL — "จอมอนิเตอร์" not found.

- [ ] **Step 3: Add the link**

In `apps/web/src/components/AppHeader.tsx`, immediately before the admin-only `จัดการกล้อง` block, add:

```tsx
          <Link
            href="/monitor"
            className="hidden text-slate-600 hover:text-slate-900 sm:inline"
          >
            จอมอนิเตอร์
          </Link>
```

(Placed inside the same `<div className="flex items-center gap-3 text-sm">`, before the `{role === "admin" ? (...) : null}` camera link.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/web && npm run test -- AppHeader`
Expected: PASS — new viewer/admin tests plus the two existing ones.

- [ ] **Step 5: Full web gate**

Run: `cd apps/web && npm run test && npm run lint && npx tsc --noEmit && npm run build`
Expected: all clean.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/components/AppHeader.tsx apps/web/src/components/AppHeader.test.tsx
git commit -m "feat(web): add จอมอนิเตอร์ nav link for viewer + admin"
```

---

## Verification (whole feature)

- API: `cd apps/api && python -m pytest -q` — all green, including the new viewer snapshot test.
- Web: `cd apps/web && npm run test && npm run lint && npx tsc --noEmit && npm run build` — all green.
- Manual (needs a running Frigate + `docker compose up`): log in as a `viewer`, open `/monitor`, confirm the gate_front tile refreshes ~2s, offline/disabled cameras show badges, click opens fullscreen, ESC closes.

## Notes / Out of scope

- Live video (WebRTC/HLS) — deferred; snapshot polling only.
- Camera add/remove (part B) and per-camera rules (part C) — separate specs.
- Manual verification of the real image path requires a live Frigate; unit tests use mocks.
