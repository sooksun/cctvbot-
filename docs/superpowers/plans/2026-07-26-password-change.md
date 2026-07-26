# Password Change (self-service) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Let any logged-in user change their own password via `POST /api/auth/change-password` and a dashboard form.

**Architecture:** Authenticated endpoint verifies the current password, enforces a minimum length + difference, re-hashes with the existing bcrypt helpers, writes an audit row. Frontend adds an `/account` page and an AppHeader link.

**Tech Stack:** FastAPI, pydantic (`Field(min_length=8)`), bcrypt 5; Next 16 + React 19 + TS.

## Global Constraints

- Endpoint auth: `Depends(get_current_user)` (self-service — user changes own password).
- Use existing `hash_password` / `verify_password` (bcrypt 5, 72-byte truncation) from `app.auth`.
- No schema change; audit via existing `write_audit` (action `change_password`).
- Tests: sqlite in-memory PERSISTS across the session (StaticPool) — each test must use its OWN throwaway user, never mutate the shared `admin` password.
- Run API from `apps/api/` via `./.venv/Scripts/python.exe -m pytest`; web from `apps/web/` via npm.
- Keep green: API 47 (before new tests), worker 90.

---

### Task 1: change-password endpoint (backend)

**Files:**
- Modify: `apps/api/app/routers/auth_router.py`
- Test: `apps/api/tests/test_auth.py`

**Interfaces:**
- Produces: `POST /api/auth/change-password` body `{current_password, new_password}` → `{"ok": true}`.

- [ ] **Step 1: Write failing tests** — append to `apps/api/tests/test_auth.py`:

```python
def _make_login(client, username, password, role="viewer"):
    from app.auth import hash_password
    from app.db import SessionLocal
    from app.models import User

    db = SessionLocal()
    try:
        u = db.query(User).filter(User.username == username).first()
        if u:
            u.password_hash = hash_password(password)
        else:
            db.add(User(username=username, password_hash=hash_password(password), role=role))
        db.commit()
    finally:
        db.close()
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200
    return r.json()["access_token"]


def test_change_password_success(client: TestClient):
    token = _make_login(client, "pwuser", "oldpass123")
    h = {"Authorization": f"Bearer {token}"}
    r = client.post(
        "/api/auth/change-password",
        json={"current_password": "oldpass123", "new_password": "newpass456"},
        headers=h,
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert client.post(
        "/api/auth/login", json={"username": "pwuser", "password": "newpass456"}
    ).status_code == 200
    assert client.post(
        "/api/auth/login", json={"username": "pwuser", "password": "oldpass123"}
    ).status_code == 401


def test_change_password_wrong_current(client: TestClient):
    token = _make_login(client, "pwuser2", "oldpass123")
    r = client.post(
        "/api/auth/change-password",
        json={"current_password": "WRONG", "new_password": "newpass456"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400


def test_change_password_same_as_current(client: TestClient):
    token = _make_login(client, "pwuser3", "oldpass123")
    r = client.post(
        "/api/auth/change-password",
        json={"current_password": "oldpass123", "new_password": "oldpass123"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400


def test_change_password_too_short(client: TestClient):
    token = _make_login(client, "pwuser4", "oldpass123")
    r = client.post(
        "/api/auth/change-password",
        json={"current_password": "oldpass123", "new_password": "short"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


def test_change_password_unauthenticated(client: TestClient):
    r = client.post(
        "/api/auth/change-password",
        json={"current_password": "x", "new_password": "newpass456"},
    )
    assert r.status_code == 401
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd apps/api && ./.venv/Scripts/python.exe -m pytest tests/test_auth.py -q -k change_password`
Expected: FAIL — route not defined (404/405).

- [ ] **Step 3: Implement the endpoint in `auth_router.py`**

Update the pydantic import and the app.auth / app.audit imports:

```python
from pydantic import BaseModel, Field
```
```python
from app.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
    verify_system_token,
)
from app.audit import write_audit
```

Add the request model next to `LoginRequest`:

```python
class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)
```

Add the endpoint after `me`:

```python
@router.post("/change-password")
def change_password(
    body: ChangePasswordRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="รหัสผ่านปัจจุบันไม่ถูกต้อง",
        )
    if body.new_password == body.current_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="รหัสใหม่ต้องต่างจากรหัสเดิม",
        )
    user.password_hash = hash_password(body.new_password)
    write_audit(
        db,
        who=user.username,
        action="change_password",
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return {"ok": True}
```

- [ ] **Step 4: Run the API suite**

Run: `cd apps/api && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS — 47 + 5 = 52 green.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/routers/auth_router.py apps/api/tests/test_auth.py
git commit -m "feat(api): self-service change-password endpoint"
```

---

### Task 2: change-password page (frontend)

**Files:**
- Modify: `apps/web/src/lib/api.ts`
- Create: `apps/web/src/app/account/page.tsx`
- Modify: `apps/web/src/components/AppHeader.tsx`

**Interfaces:**
- Consumes: `POST /api/auth/change-password` from Task 1.

- [ ] **Step 1: Add the client helper in `api.ts`**

After `login(...)`:

```typescript
export async function changePassword(
  currentPassword: string,
  newPassword: string,
): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>("/api/auth/change-password", {
    method: "POST",
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  });
}
```

- [ ] **Step 2: Create `apps/web/src/app/account/page.tsx`**

```tsx
"use client";

import { FormEvent, useState } from "react";
import AuthGate from "@/components/AuthGate";
import AppHeader from "@/components/AppHeader";
import { changePassword } from "@/lib/api";

function AccountContent() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setMessage(null);
    if (next.length < 8) {
      setError("รหัสใหม่ต้องยาวอย่างน้อย 8 ตัวอักษร");
      return;
    }
    if (next !== confirm) {
      setError("ยืนยันรหัสใหม่ไม่ตรงกัน");
      return;
    }
    setSubmitting(true);
    try {
      await changePassword(current, next);
      setMessage("เปลี่ยนรหัสผ่านเรียบร้อยแล้ว");
      setCurrent("");
      setNext("");
      setConfirm("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "เปลี่ยนรหัสผ่านไม่สำเร็จ");
    } finally {
      setSubmitting(false);
    }
  }

  const field =
    "mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-slate-900 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500";

  return (
    <div className="min-h-screen bg-slate-50">
      <AppHeader />
      <main className="mx-auto max-w-md space-y-4 px-4 py-6">
        <h1 className="text-lg font-semibold text-slate-900">เปลี่ยนรหัสผ่าน</h1>
        <form
          onSubmit={onSubmit}
          className="space-y-3 rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
        >
          <label className="block text-sm text-slate-600">
            รหัสผ่านปัจจุบัน
            <input
              type="password"
              autoComplete="current-password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              required
              className={field}
            />
          </label>
          <label className="block text-sm text-slate-600">
            รหัสผ่านใหม่ (อย่างน้อย 8 ตัวอักษร)
            <input
              type="password"
              autoComplete="new-password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              required
              className={field}
            />
          </label>
          <label className="block text-sm text-slate-600">
            ยืนยันรหัสผ่านใหม่
            <input
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              className={field}
            />
          </label>
          {error ? (
            <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
              {error}
            </p>
          ) : null}
          {message ? (
            <p className="rounded-md bg-green-50 px-3 py-2 text-sm text-green-800">
              {message}
            </p>
          ) : null}
          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-md bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60"
          >
            {submitting ? "กำลังบันทึก..." : "บันทึกรหัสผ่านใหม่"}
          </button>
        </form>
      </main>
    </div>
  );
}

export default function AccountPage() {
  return (
    <AuthGate>
      <AccountContent />
    </AuthGate>
  );
}
```

- [ ] **Step 3: Add the AppHeader link**

In `apps/web/src/components/AppHeader.tsx`, add a link before the logout button. Change:

```tsx
        <div className="flex items-center gap-3 text-sm">
          <span className="text-slate-600">
```

to add a `Link` — insert this just inside the `<div className="flex items-center gap-3 text-sm">` before the `<span>`:

```tsx
          <Link
            href="/account"
            className="hidden text-slate-600 hover:text-slate-900 sm:inline"
          >
            เปลี่ยนรหัสผ่าน
          </Link>
```

(`Link` from `next/link` is already imported in AppHeader.)

- [ ] **Step 4: Verify build, lint, typecheck**

Run: `cd apps/web && npx tsc --noEmit` → rc 0
Run: `cd apps/web && npm run lint` → exit 0 (existing 3 warnings)
Run: `cd apps/web && npm run build` → Compiled successfully (route `/account` listed)

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib/api.ts apps/web/src/app/account/page.tsx apps/web/src/components/AppHeader.tsx
git commit -m "feat(web): change-password page + AppHeader link"
```

---

## Self-Review

**Spec coverage:** §3 endpoint (verify current / same-check / min_length / audit) → Task 1; §4 frontend (helper, /account page, AppHeader link) → Task 2; §5 tests → Task 1 Step 1 + Task 2 Step 4. ✓

**Placeholder scan:** No TBD/TODO; full code in each step. ✓

**Type consistency:** `changePassword(currentPassword, newPassword)` maps to body `{current_password, new_password}`; endpoint returns `{"ok": true}` matching the helper's return type. Test users are per-test throwaways (pwuser…pwuser4) so the shared in-memory `admin` is never mutated. ✓

**No change to existing auth:** endpoint is additive; `/login`, `/me`, rate limiter untouched. ✓
