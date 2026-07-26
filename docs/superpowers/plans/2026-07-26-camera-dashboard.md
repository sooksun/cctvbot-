# Camera Dashboard (Preview + Config + Control) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Admin camera dashboard — proxied Frigate snapshot preview, editable name/zone, enable/disable monitoring that suppresses events.

**Architecture:** New admin endpoints on the cameras router (PATCH config, GET snapshot proxy), a `Camera.enabled` column that `create_event` honors, and a `/cameras` admin page. Frigate stays server-side (browser never reaches it).

**Tech Stack:** FastAPI, SQLAlchemy, httpx (Frigate proxy), pytest; Next 16 + React 19 + TS.

## Global Constraints

- All new endpoints + `/cameras` page are `admin`-only.
- Frigate is proxied server-side; the browser never talks to Frigate directly.
- `Camera.enabled` is added via `create_all` (project uses no Alembic); document the one-time `ALTER TABLE` for existing DBs in DEPLOY.md.
- No live Frigate here → the snapshot proxy is unit-tested with a monkeypatched fetch.
- Run API from `apps/api/` via `./.venv/Scripts/python.exe -m pytest`; web from `apps/web/`.
- Keep green: API 52 (before new tests), worker 90.

---

### Task 1: `enabled` column + admin PATCH + event suppression

**Files:**
- Modify: `apps/api/app/models.py` (Camera.enabled)
- Modify: `apps/api/app/schemas.py` (CameraResponse.enabled, CameraConfigUpdate)
- Modify: `apps/api/app/routers/cameras.py` (enabled in responses, PATCH endpoint)
- Modify: `apps/api/app/routers/events.py` (create_event drops disabled)
- Modify: `DEPLOY.md` (ALTER TABLE note)
- Test: `apps/api/tests/test_events.py`

**Interfaces:**
- Produces: `PATCH /api/cameras/{id}` body `{name?, zone?, enabled?}` → CameraResponse; `CameraResponse.enabled: bool`.

- [ ] **Step 1: Write failing tests** — append to `apps/api/tests/test_events.py`:

```python
def test_camera_response_has_enabled(client: TestClient, admin_headers: dict, sample_event: str):
    del sample_event
    r = client.get("/api/cameras", headers=admin_headers)
    assert r.status_code == 200
    assert all("enabled" in c for c in r.json())


def test_patch_camera_config_admin(client: TestClient, admin_headers: dict, sample_event: str):
    del sample_event  # sample_event created camera cam_front_gate
    r = client.patch(
        "/api/cameras/cam_front_gate",
        json={"name": "ประตูหน้าใหม่", "zone": "gate2", "enabled": False},
        headers=admin_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "ประตูหน้าใหม่"
    assert body["zone"] == "gate2"
    assert body["enabled"] is False


def test_patch_camera_unknown_404(client: TestClient, admin_headers: dict):
    r = client.patch("/api/cameras/nope", json={"name": "x"}, headers=admin_headers)
    assert r.status_code == 404


def test_patch_camera_viewer_forbidden(client: TestClient, sample_event: str):
    del sample_event
    from app.auth import create_access_token, hash_password
    from app.db import SessionLocal
    from app.models import User

    db = SessionLocal()
    try:
        if not db.query(User).filter(User.username == "viewer_cam").first():
            db.add(User(username="viewer_cam", password_hash=hash_password("x"), role="viewer"))
            db.commit()
    finally:
        db.close()
    token = create_access_token({"sub": "viewer_cam", "role": "viewer"})
    r = client.patch(
        "/api/cameras/cam_front_gate",
        json={"name": "x"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


def test_create_event_dropped_when_camera_disabled(client: TestClient, admin_headers: dict):
    # create a camera via an event, then disable it, then a new event is dropped (202).
    from tests.test_events import _minimal_event_payload

    p1 = _minimal_event_payload("EVT-DIS-0001")
    p1["camera"]["camera_id"] = "cam_disable_test"
    assert client.post("/api/events", json=p1, headers={"X-System-Token": "test-system-token"}).status_code == 201

    assert client.patch(
        "/api/cameras/cam_disable_test",
        json={"enabled": False},
        headers=admin_headers,
    ).status_code == 200

    p2 = _minimal_event_payload("EVT-DIS-0002")
    p2["camera"]["camera_id"] = "cam_disable_test"
    r = client.post("/api/events", json=p2, headers={"X-System-Token": "test-system-token"})
    assert r.status_code == 202
    # the dropped event must not exist
    got = client.get("/api/events/EVT-DIS-0002", headers=admin_headers)
    assert got.status_code == 404
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd apps/api && ./.venv/Scripts/python.exe -m pytest tests/test_events.py -q -k "camera or disabled"`
Expected: FAIL (no `enabled`, no PATCH route, event not dropped).

- [ ] **Step 3: Add `enabled` to the Camera model** (`apps/api/app/models.py`), after `is_online`:

```python
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
```

- [ ] **Step 4: Update schemas** (`apps/api/app/schemas.py`)

Add `enabled` to `CameraResponse` (after `is_online`):

```python
    is_online: bool
    enabled: bool = True
```

Add a new model:

```python
class CameraConfigUpdate(BaseModel):
    name: Optional[str] = None
    zone: Optional[str] = None
    enabled: Optional[bool] = None
```

- [ ] **Step 5: Update `cameras.py`** — imports, `enabled` in responses, PATCH endpoint

Imports:

```python
from fastapi import APIRouter, Depends, HTTPException, status
```
```python
from app.schemas import CameraConfigUpdate, CameraResponse, CameraUpsert
```

Add `enabled=c.enabled` to the `CameraResponse(...)` in `list_cameras`, and `enabled=camera.enabled` to the `CameraResponse(...)` returned by `upsert_camera`.

Add the PATCH endpoint (after `upsert_camera`):

```python
@router.patch("/{camera_id}", response_model=CameraResponse)
def update_camera_config(
    camera_id: str,
    body: CameraConfigUpdate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_roles("admin"))],
) -> CameraResponse:
    del user
    camera = db.query(Camera).filter(Camera.camera_id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
    if body.name is not None:
        camera.name = body.name
    if body.zone is not None:
        camera.zone = body.zone
    if body.enabled is not None:
        camera.enabled = body.enabled
    db.commit()
    db.refresh(camera)
    return CameraResponse(
        camera_id=camera.camera_id,
        name=camera.name,
        stream_type=camera.stream_type,
        zone=camera.zone,
        is_online=camera.is_online,
        enabled=camera.enabled,
        last_seen_at=camera.last_seen_at,
        created_at=camera.created_at,
    )
```

- [ ] **Step 6: Suppress events for disabled cameras** (`apps/api/app/routers/events.py`)

Add `JSONResponse` to the responses import:

```python
from fastapi.responses import FileResponse, JSONResponse
```

In `create_event`, right after the duplicate-check `raise` block and before `_upsert_camera`:

```python
    camera = (
        db.query(Camera).filter(Camera.camera_id == body.camera.camera_id).first()
    )
    if camera is not None and camera.enabled is False:
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"detail": "camera monitoring disabled", "event_id": body.event_id},
        )
```

- [ ] **Step 7: DEPLOY.md — one-time ALTER note**

In DEPLOY.md section 2 (database), add after the auto-create note:

```markdown
> อัปเกรดจากเวอร์ชันก่อนมี camera enable/disable: รันครั้งเดียวบน DB เดิม —
> `ALTER TABLE cameras ADD COLUMN enabled TINYINT(1) NOT NULL DEFAULT 1;`
> (DB สร้างใหม่ไม่ต้องทำ — `create_all` ใส่คอลัมน์ให้แล้ว)
```

- [ ] **Step 8: Run the API suite**

Run: `cd apps/api && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS — 52 + 5 = 57 green.

- [ ] **Step 9: Commit**

```bash
git add apps/api/app/models.py apps/api/app/schemas.py apps/api/app/routers/cameras.py apps/api/app/routers/events.py apps/api/tests/test_events.py DEPLOY.md
git commit -m "feat(api): camera enable/disable + admin config PATCH; drop events from disabled cams"
```

---

### Task 2: Snapshot proxy endpoint

**Files:**
- Modify: `apps/api/app/config.py` (frigate_base_url)
- Modify: `.env.example` (FRIGATE_BASE_URL)
- Modify: `apps/api/app/routers/cameras.py` (snapshot endpoint + fetch helper)
- Test: `apps/api/tests/test_events.py`

**Interfaces:**
- Produces: `GET /api/cameras/{id}/snapshot` (admin) → `image/jpeg` | 404 | 502.
- `_fetch_frigate_snapshot(camera_id) -> bytes | None` (monkeypatchable).

- [ ] **Step 1: Write failing tests** — append to `apps/api/tests/test_events.py`:

```python
def test_snapshot_proxies_frigate(client: TestClient, admin_headers: dict, sample_event: str, monkeypatch):
    del sample_event  # camera cam_front_gate exists
    from app.routers import cameras

    monkeypatch.setattr(cameras, "_fetch_frigate_snapshot", lambda cid: b"\xff\xd8\xfffakejpeg")
    r = client.get("/api/cameras/cam_front_gate/snapshot", headers=admin_headers)
    assert r.status_code == 200
    assert "image/jpeg" in r.headers.get("content-type", "")
    assert r.content == b"\xff\xd8\xfffakejpeg"


def test_snapshot_unknown_camera_404(client: TestClient, admin_headers: dict):
    r = client.get("/api/cameras/nope/snapshot", headers=admin_headers)
    assert r.status_code == 404


def test_snapshot_frigate_down_502(client: TestClient, admin_headers: dict, sample_event: str, monkeypatch):
    del sample_event
    from app.routers import cameras

    monkeypatch.setattr(cameras, "_fetch_frigate_snapshot", lambda cid: None)
    r = client.get("/api/cameras/cam_front_gate/snapshot", headers=admin_headers)
    assert r.status_code == 502
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd apps/api && ./.venv/Scripts/python.exe -m pytest tests/test_events.py -q -k snapshot`
Expected: FAIL (route not defined).

- [ ] **Step 3: Add `frigate_base_url` to API config** (`apps/api/app/config.py`), after `evidence_root`:

```python
    frigate_base_url: str = "http://frigate:5000"
```

- [ ] **Step 4: Add `FRIGATE_BASE_URL` to `.env.example`** under the `# API` section:

```
FRIGATE_BASE_URL=http://frigate:5000
```

- [ ] **Step 5: Add the fetch helper + snapshot endpoint** (`apps/api/app/routers/cameras.py`)

Imports (extend):

```python
import httpx
from fastapi import APIRouter, Depends, HTTPException, Response, status
from app.config import settings
```

Add the helper (module level, after the router定义):

```python
def _fetch_frigate_snapshot(camera_id: str) -> bytes | None:
    """Fetch a camera's latest JPEG from Frigate server-side. None on failure."""
    base = settings.frigate_base_url.rstrip("/")
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{base}/api/{camera_id}/latest.jpg")
            if resp.status_code == 200:
                return resp.content
    except httpx.HTTPError:
        return None
    return None
```

Add the endpoint (after `update_camera_config`):

```python
@router.get("/{camera_id}/snapshot")
def get_camera_snapshot(
    camera_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_roles("admin"))],
) -> Response:
    del user
    camera = db.query(Camera).filter(Camera.camera_id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
    data = _fetch_frigate_snapshot(camera_id)
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="snapshot unavailable"
        )
    return Response(content=data, media_type="image/jpeg")
```

- [ ] **Step 6: Run the API suite**

Run: `cd apps/api && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS — 57 + 3 = 60 green.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/config.py .env.example apps/api/app/routers/cameras.py apps/api/tests/test_events.py
git commit -m "feat(api): admin camera snapshot proxy from Frigate"
```

---

### Task 3: Camera dashboard page (frontend)

**Files:**
- Modify: `apps/web/src/lib/api.ts` (Camera.enabled, updateCamera, snapshot blob fetch)
- Create: `apps/web/src/app/cameras/page.tsx`
- Modify: `apps/web/src/components/AppHeader.tsx` (admin link)

**Interfaces:**
- Consumes: PATCH `/api/cameras/{id}`, GET `/api/cameras/{id}/snapshot` from Tasks 1–2.

- [ ] **Step 1: Extend `api.ts`**

Add `enabled: boolean;` to the `Camera` interface (after `is_online`).

Add helpers (after `listCameras`):

```typescript
export async function updateCamera(
  cameraId: string,
  patch: { name?: string; zone?: string | null; enabled?: boolean },
): Promise<Camera> {
  return request<Camera>(`/api/cameras/${encodeURIComponent(cameraId)}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

/** Fetch a camera snapshot (admin JWT) as an object URL for <img>. */
export async function fetchCameraSnapshotUrl(cameraId: string): Promise<string> {
  const token = getToken();
  const headers = new Headers();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(
    `${API_URL}/api/cameras/${encodeURIComponent(cameraId)}/snapshot`,
    { headers },
  );
  if (!res.ok) throw new ApiError(res.status, "snapshot unavailable");
  return URL.createObjectURL(await res.blob());
}
```

- [ ] **Step 2: Create `apps/web/src/app/cameras/page.tsx`**

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import AuthGate from "@/components/AuthGate";
import AppHeader from "@/components/AppHeader";
import {
  Camera,
  fetchCameraSnapshotUrl,
  isAdmin,
  listCameras,
  updateCamera,
} from "@/lib/api";

function CameraCard({ cam, onSaved }: { cam: Camera; onSaved: () => void }) {
  const [snap, setSnap] = useState<string | null>(null);
  const [name, setName] = useState(cam.name);
  const [zone, setZone] = useState(cam.zone ?? "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const loadSnap = useCallback(async () => {
    setErr(null);
    try {
      const url = await fetchCameraSnapshotUrl(cam.camera_id);
      setSnap((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return url;
      });
    } catch {
      setSnap((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
      setErr("ไม่มีภาพจากกล้อง");
    }
  }, [cam.camera_id]);

  useEffect(() => {
    void loadSnap();
    const t = setInterval(() => void loadSnap(), 5000);
    return () => {
      clearInterval(t);
      setSnap((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
    };
  }, [loadSnap]);

  async function save(patch: { name?: string; zone?: string | null; enabled?: boolean }) {
    setBusy(true);
    setErr(null);
    try {
      await updateCamera(cam.camera_id, patch);
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "บันทึกไม่สำเร็จ");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-3 aspect-video overflow-hidden rounded-lg bg-slate-100">
        {snap ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={snap} alt={`ภาพ ${cam.name}`} className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-slate-400">
            {err ?? "กำลังโหลด..."}
          </div>
        )}
      </div>
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-2 text-sm">
          <span
            className={`h-2.5 w-2.5 rounded-full ${cam.is_online ? "bg-green-500" : "bg-red-500"}`}
          />
          <code className="text-xs text-slate-500">{cam.camera_id}</code>
        </span>
        <button
          type="button"
          onClick={() => void loadSnap()}
          className="rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-700 hover:bg-slate-50"
        >
          รีเฟรชภาพ
        </button>
      </div>
      <div className="mt-3 space-y-2">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900"
          placeholder="ชื่อกล้อง"
        />
        <input
          value={zone}
          onChange={(e) => setZone(e.target.value)}
          className="w-full rounded-md border border-slate-300 px-2 py-1 text-sm text-slate-900"
          placeholder="โซน"
        />
        <div className="flex items-center justify-between">
          <button
            type="button"
            disabled={busy}
            onClick={() => void save({ name, zone: zone || null })}
            className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60"
          >
            บันทึก
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void save({ enabled: !cam.enabled })}
            className={`rounded-md px-3 py-1.5 text-sm font-medium ${
              cam.enabled
                ? "border border-slate-300 text-slate-700 hover:bg-slate-50"
                : "bg-green-600 text-white hover:bg-green-700"
            }`}
          >
            {cam.enabled ? "ปิดเฝ้าระวัง" : "เปิดเฝ้าระวัง"}
          </button>
        </div>
        {err ? <p className="text-xs text-red-600">{err}</p> : null}
      </div>
    </div>
  );
}

function CamerasContent() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const admin = isAdmin();

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
        <h1 className="text-lg font-semibold text-slate-900">จัดการกล้อง</h1>
        {!admin ? (
          <p className="text-sm text-slate-500">เฉพาะแอดมินเท่านั้น</p>
        ) : error ? (
          <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
        ) : loading ? (
          <p className="text-sm text-slate-500">กำลังโหลด...</p>
        ) : cameras.length === 0 ? (
          <p className="text-sm text-slate-500">ยังไม่มีกล้องในระบบ</p>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {cameras.map((cam) => (
              <CameraCard key={cam.camera_id} cam={cam} onSaved={() => void load()} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

export default function CamerasPage() {
  return (
    <AuthGate>
      <CamerasContent />
    </AuthGate>
  );
}
```

- [ ] **Step 3: AppHeader admin link** (`apps/web/src/components/AppHeader.tsx`)

`getRole` is already imported (`role` is read). Add a cameras link before the change-password link, shown only for admin:

```tsx
          {role === "admin" ? (
            <Link
              href="/cameras"
              className="hidden text-slate-600 hover:text-slate-900 sm:inline"
            >
              จัดการกล้อง
            </Link>
          ) : null}
```

- [ ] **Step 4: Verify build, lint, typecheck**

Run: `cd apps/web && npx tsc --noEmit` → rc 0
Run: `cd apps/web && npm run lint` → exit 0 (existing 3 warnings)
Run: `cd apps/web && npm run build` → Compiled successfully (route `/cameras` listed)

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib/api.ts apps/web/src/app/cameras/page.tsx apps/web/src/components/AppHeader.tsx
git commit -m "feat(web): admin camera dashboard (preview + config + enable toggle)"
```

---

## Self-Review

**Spec coverage:** §4 model+enabled → Task 1; §5 PATCH/snapshot/event-suppression → Tasks 1–2; §6 config → Task 2; §7 frontend → Task 3; §8 tests → Tasks 1–3. ✓

**Placeholder scan:** No TBD/TODO; full code in each step. ✓

**Type consistency:** `CameraResponse.enabled` added and set in all three constructions (list, upsert, patch); `updateCamera` body maps to `CameraConfigUpdate`; `_fetch_frigate_snapshot` name identical in impl + test monkeypatch. Frontend `Camera.enabled` matches API. ✓

**Route safety:** `GET /{id}/snapshot`, `PATCH /{id}`, `GET ""` (list), `PUT /{id}` (system) — distinct method/path combos, no collision. ✓
