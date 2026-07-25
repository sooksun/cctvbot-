# Event Lifecycle (`action_taken` / `closed`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `PATCH /api/events/{id}/status` (admin) to move reviewed events through `action_taken`/`closed`, with matching dashboard buttons.

**Architecture:** A transition-validated endpoint separate from `/review` (no LINE). Lifecycle metadata is merged into the existing `review_json` JSON column (no schema change). Frontend adds a "จัดการเคส" section on the event detail page.

**Tech Stack:** FastAPI, SQLAlchemy, pydantic (`Literal`), pytest; Next 16 + React 19 + TS.

## Global Constraints

- No DB schema change — merge lifecycle fields into `review_json` (system uses `create_all`, no migrations).
- Do NOT modify `PATCH /events/{id}/review`; it keeps `confirmed`/`false_positive` + LINE.
- Transition graph (server-enforced): `confirmed → {action_taken, closed}`, `action_taken → {closed}`, `false_positive → {closed}`; everything else → 409.
- Endpoint is `require_roles("admin")`.
- Run API commands from `apps/api/` via `./.venv/Scripts/python.exe -m pytest`; web from `apps/web/` via npm.
- Keep green: API 38 (before new tests), worker 90.

---

### Task 1: Status-transition endpoint (backend)

**Files:**
- Modify: `apps/api/app/schemas.py` (add `StatusChangeRequest`)
- Modify: `apps/api/app/routers/events.py` (transition map + endpoint)
- Test: `apps/api/tests/test_events.py` (append)

**Interfaces:**
- Produces: `PATCH /api/events/{event_id}/status` with body `{status: "action_taken"|"closed", note?: str}` → `EventResponse`.

- [ ] **Step 1: Write failing tests** — append to `apps/api/tests/test_events.py`:

```python
def _viewer_headers() -> dict:
    from app.auth import create_access_token, hash_password
    from app.db import SessionLocal
    from app.models import User

    db = SessionLocal()
    try:
        if not db.query(User).filter(User.username == "viewer1").first():
            db.add(User(username="viewer1", password_hash=hash_password("x"), role="viewer"))
            db.commit()
    finally:
        db.close()
    token = create_access_token({"sub": "viewer1", "role": "viewer"})
    return {"Authorization": f"Bearer {token}"}


def _confirm(client, admin_headers, event_id):
    r = client.patch(
        f"/api/events/{event_id}/review",
        json={"decision": "confirmed"},
        headers=admin_headers,
    )
    assert r.status_code == 200


def test_status_confirmed_to_action_taken(client, admin_headers, sample_event):
    _confirm(client, admin_headers, sample_event)
    r = client.patch(
        f"/api/events/{sample_event}/status",
        json={"status": "action_taken", "note": "แจ้งครูเวร"},
        headers=admin_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "action_taken"
    assert body["review"]["action_taken_by"] == "admin"
    assert body["review"]["action_taken_note"] == "แจ้งครูเวร"
    assert body["review"]["decision"] == "confirmed"  # original review preserved


def test_status_confirmed_to_closed(client, admin_headers, sample_event):
    _confirm(client, admin_headers, sample_event)
    r = client.patch(
        f"/api/events/{sample_event}/status",
        json={"status": "closed"},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "closed"


def test_status_action_taken_to_closed(client, admin_headers, sample_event):
    _confirm(client, admin_headers, sample_event)
    client.patch(
        f"/api/events/{sample_event}/status",
        json={"status": "action_taken"},
        headers=admin_headers,
    )
    r = client.patch(
        f"/api/events/{sample_event}/status",
        json={"status": "closed"},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "closed"


def test_status_false_positive_to_closed(client, admin_headers, sample_event):
    client.patch(
        f"/api/events/{sample_event}/review",
        json={"decision": "false_positive"},
        headers=admin_headers,
    )
    r = client.patch(
        f"/api/events/{sample_event}/status",
        json={"status": "closed"},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "closed"


def test_status_pending_to_action_taken_rejected(client, admin_headers, sample_event):
    r = client.patch(
        f"/api/events/{sample_event}/status",
        json={"status": "action_taken"},
        headers=admin_headers,
    )
    assert r.status_code == 409


def test_status_closed_is_terminal(client, admin_headers, sample_event):
    _confirm(client, admin_headers, sample_event)
    client.patch(
        f"/api/events/{sample_event}/status",
        json={"status": "closed"},
        headers=admin_headers,
    )
    r = client.patch(
        f"/api/events/{sample_event}/status",
        json={"status": "closed"},
        headers=admin_headers,
    )
    assert r.status_code == 409


def test_status_invalid_target_422(client, admin_headers, sample_event):
    _confirm(client, admin_headers, sample_event)
    r = client.patch(
        f"/api/events/{sample_event}/status",
        json={"status": "confirmed"},
        headers=admin_headers,
    )
    assert r.status_code == 422


def test_status_viewer_forbidden(client, admin_headers, sample_event):
    _confirm(client, admin_headers, sample_event)
    r = client.patch(
        f"/api/events/{sample_event}/status",
        json={"status": "action_taken"},
        headers=_viewer_headers(),
    )
    assert r.status_code == 403
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd apps/api && ./.venv/Scripts/python.exe -m pytest tests/test_events.py -q -k status`
Expected: FAIL — endpoint returns 404/405 (route not defined); `StatusChangeRequest` missing.

- [ ] **Step 3: Add `StatusChangeRequest` to `schemas.py`**

`Literal` is already imported. Add after `ReviewRequest`:

```python
class StatusChangeRequest(BaseModel):
    status: Literal["action_taken", "closed"]
    note: str | None = None
```

- [ ] **Step 4: Add the transition map + endpoint to `events.py`**

Extend the schemas import:

```python
from app.schemas import (
    EventCreate,
    EventResponse,
    EvidenceResponse,
    ReviewRequest,
    StatusChangeRequest,
)
```

Add the transition map next to `_ALLOWED_EVIDENCE_NAMES`:

```python
# Allowed operational transitions after review (pending_review handled by /review).
_LIFECYCLE_TRANSITIONS: dict[str, frozenset[str]] = {
    "confirmed": frozenset({"action_taken", "closed"}),
    "action_taken": frozenset({"closed"}),
    "false_positive": frozenset({"closed"}),
}
```

Add the endpoint (after `review_event`):

```python
@router.patch("/{event_id}/status", response_model=EventResponse)
def change_event_status(
    event_id: str,
    body: StatusChangeRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_roles("admin"))],
) -> EventResponse:
    event = db.query(Event).filter(Event.event_id == event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    allowed = _LIFECYCLE_TRANSITIONS.get(event.status, frozenset())
    if body.status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot transition from {event.status} to {body.status}",
        )

    now = datetime.now(timezone.utc)
    review = dict(event.review_json or {})
    if body.status == "action_taken":
        review["action_taken_by"] = user.username
        review["action_taken_at"] = now.isoformat()
        if body.note:
            review["action_taken_note"] = body.note
        audit_action = "mark_action_taken"
    else:  # closed
        review["closed_by"] = user.username
        review["closed_at"] = now.isoformat()
        if body.note:
            review["closed_note"] = body.note
        audit_action = "close_event"

    event.status = body.status
    event.review_json = review

    write_audit(
        db,
        who=user.username,
        action=audit_action,
        event_id=event_id,
        ip=_client_ip(request),
        note=body.note,
    )
    db.commit()
    db.refresh(event)
    return _event_to_response(event)
```

- [ ] **Step 5: Run the API suite**

Run: `cd apps/api && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS — 38 + 8 = 46 green.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/schemas.py apps/api/app/routers/events.py apps/api/tests/test_events.py
git commit -m "feat(api): event lifecycle status transitions (action_taken/closed)"
```

---

### Task 2: Dashboard lifecycle buttons (frontend)

**Files:**
- Modify: `apps/web/src/lib/api.ts` (type + `changeEventStatus`)
- Modify: `apps/web/src/app/events/[eventId]/page.tsx` (section + handler + display)

**Interfaces:**
- Consumes: `PATCH /api/events/{id}/status` from Task 1.

- [ ] **Step 1: Extend the `Event.review` type + add the helper in `api.ts`**

Replace the `review` field in the `Event` interface with:

```typescript
  review: {
    reviewed_by?: string;
    reviewed_at?: string;
    decision?: string;
    note?: string | null;
    action_taken_by?: string;
    action_taken_at?: string;
    action_taken_note?: string;
    closed_by?: string;
    closed_at?: string;
    closed_note?: string;
  } | null;
```

Add after `reviewEvent`:

```typescript
export async function changeEventStatus(
  eventId: string,
  status: "action_taken" | "closed",
  note?: string,
): Promise<Event> {
  return request<Event>(`/api/events/${encodeURIComponent(eventId)}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status, note: note || null }),
  });
}
```

- [ ] **Step 2: Wire the detail page (`events/[eventId]/page.tsx`)**

(a) Add `changeEventStatus` to the `@/lib/api` import.

(b) Add a handler next to `onReview`:

```typescript
  async function onStatusChange(status: "action_taken" | "closed") {
    setSubmitting(true);
    setError(null);
    setMessage(null);
    try {
      const updated = await changeEventStatus(
        eventId,
        status,
        note.trim() || undefined,
      );
      setEvent(updated);
      setMessage(
        status === "action_taken" ? "บันทึกว่าดำเนินการแล้ว" : "ปิดเคสแล้ว",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "บันทึกไม่สำเร็จ");
    } finally {
      setSubmitting(false);
    }
  }
```

(c) Inside the existing review/result box, after the note line, add lifecycle lines:

```tsx
                  {event.review.action_taken_by ? (
                    <p className="mt-1 text-slate-600">
                      ดำเนินการโดย {event.review.action_taken_by} ·{" "}
                      {formatDateTime(event.review.action_taken_at)}
                    </p>
                  ) : null}
                  {event.review.closed_by ? (
                    <p className="mt-1 text-slate-600">
                      ปิดเคสโดย {event.review.closed_by} ·{" "}
                      {formatDateTime(event.review.closed_at)}
                    </p>
                  ) : null}
```

(d) After the `pending_review` admin review `<section>`, add the lifecycle section:

```tsx
            {admin &&
            ["confirmed", "action_taken", "false_positive"].includes(
              event.status,
            ) ? (
              <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <h2 className="text-base font-semibold text-slate-900">
                  จัดการเคส (แอดมิน)
                </h2>
                <label className="mt-3 block text-sm text-slate-600">
                  หมายเหตุ (ถ้ามี)
                  <textarea
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    rows={2}
                    className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-slate-900 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                    placeholder="รายละเอียดการดำเนินการ..."
                  />
                </label>
                <div className="mt-3 flex flex-wrap gap-2">
                  {event.status === "confirmed" ? (
                    <button
                      type="button"
                      disabled={submitting}
                      onClick={() => void onStatusChange("action_taken")}
                      className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60"
                    >
                      ดำเนินการแล้ว
                    </button>
                  ) : null}
                  <button
                    type="button"
                    disabled={submitting}
                    onClick={() => void onStatusChange("closed")}
                    className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                  >
                    ปิดเคส
                  </button>
                </div>
              </section>
            ) : null}
```

- [ ] **Step 3: Verify build, lint, typecheck**

Run: `cd apps/web && npx tsc --noEmit` → rc 0
Run: `cd apps/web && npm run lint` → exit 0 (existing 3 warnings ok)
Run: `cd apps/web && npm run build` → Compiled successfully

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/lib/api.ts "apps/web/src/app/events/[eventId]/page.tsx"
git commit -m "feat(web): event lifecycle buttons (action_taken/closed) on detail page"
```

---

## Self-Review

**Spec coverage:** §3 transition graph → Task 1 `_LIFECYCLE_TRANSITIONS`; §4 endpoint → Task 1; §5 persistence in `review_json` → Task 1 Step 4; §6 frontend → Task 2; §7 tests → Task 1 Step 1 + Task 2 Step 3. ✓

**Placeholder scan:** No TBD/TODO; complete code in each step. ✓

**Type consistency:** `changeEventStatus(eventId, status, note?)` matches the endpoint body `{status, note}`; `review.action_taken_by`/`closed_by` fields added to the `Event.review` type match what the API writes into `review_json`. Audit actions `mark_action_taken`/`close_event` are internal. ✓

**No change to `/review`:** confirmed by scope; endpoint is additive. ✓
