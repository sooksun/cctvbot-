# LINE Async Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make the confirmed-review LINE push non-blocking via FastAPI `BackgroundTasks`.

**Architecture:** `review_event` schedules a background dispatcher instead of sending inline; the dispatcher sends LINE and updates the event + audit in its own session.

**Tech Stack:** FastAPI BackgroundTasks, SQLAlchemy, pytest.

## Global Constraints

- Review still commits before the push (unchanged guarantee); the push no longer blocks the request.
- Background dispatcher uses its own `SessionLocal` (the request session is closed after the response).
- Do not change `send_line_text` or the LINE payload.
- Run API from `apps/api/` via `./.venv/Scripts/python.exe -m pytest`.
- Keep green: API (60), worker (95, untouched).

---

### Task 1: Background LINE dispatch

**Files:**
- Modify: `apps/api/app/routers/events.py`
- Test: `apps/api/tests/test_review_line.py`

- [ ] **Step 1: Update the test that assumed synchronous send**

In `apps/api/tests/test_review_line.py`, replace the body of `test_review_confirm_sends_line`
(the response-assertion + mock section) so it no longer expects `line_sent=True` in the
response, and instead re-fetches the event:

```python
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "confirmed"

    mock_send.assert_called_once()
    token, user_id, text = mock_send.call_args[0]
    assert token == "test-line-token"
    assert user_id == "Ulineuser"
    assert sample_event in text
    assert "ประตูหน้า" in text
    assert "บุคคลนอกเวลา" in text
    assert "http" not in text

    # LINE is dispatched in the background; the row is flagged after the push.
    got = client.get(f"/api/events/{sample_event}", headers=admin_headers).json()
    assert got["notifications"]["line_sent"] is True
    assert got["notifications"]["line_sent_at"] is not None
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/api && ./.venv/Scripts/python.exe -m pytest tests/test_review_line.py::test_review_confirm_sends_line -q`
Expected: FAIL — currently the code sends synchronously and the re-GET assertion path
differs / or (after we start editing) the endpoint signature isn't wired yet. (Establishes
the target behavior.)

- [ ] **Step 3: Add imports + the dispatcher in `events.py`**

Add `BackgroundTasks` to the fastapi import:
```python
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
```
Add `SessionLocal` to the db import:
```python
from app.db import SessionLocal, get_db
```

Add the module-level dispatcher (near the top, after `_ALLOWED_EVIDENCE_NAMES` / the
helpers):

```python
def _dispatch_line_notification(
    *,
    event_id: str,
    text: str,
    token: str,
    line_user: str,
    reviewed_by: str,
    ip: Optional[str],
) -> None:
    """Background: push LINE text; on success flag the event + audit (own session)."""
    try:
        send_line_text(token, line_user, text)
    except Exception:
        logger.exception("LINE notify failed for %s; review already committed", event_id)
        return
    db = SessionLocal()
    try:
        event = db.query(Event).filter(Event.event_id == event_id).first()
        if event is None:
            return
        notifications = dict(event.notifications_json or {})
        notifications["line_sent"] = True
        notifications["line_sent_at"] = datetime.now(timezone.utc).isoformat()
        event.notifications_json = notifications
        write_audit(
            db,
            who=reviewed_by,
            action="send_line",
            event_id=event_id,
            ip=ip,
            note="LINE text push after confirm",
        )
        db.commit()
    finally:
        db.close()
```

- [ ] **Step 4: Rewire `review_event` to schedule the task**

Add `background_tasks: BackgroundTasks` to the signature (after `request`):
```python
def review_event(
    event_id: str,
    body: ReviewRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_roles("admin"))],
) -> EventResponse:
```

Replace the confirmed-branch inline send block:
```python
    if body.decision == "confirmed":
        token = (settings.line_channel_access_token or "").strip()
        line_user = (settings.line_user_id or "").strip()
        if not token or not line_user:
            logger.warning(
                "LINE notify skipped for %s: empty token or user_id", event_id
            )
        else:
            camera = (
                db.query(Camera).filter(Camera.camera_id == event.camera_id).first()
            )
            camera_name = camera.name if camera else event.camera_id
            text = build_line_text_for_event(event, camera_name)
            try:
                send_line_text(token, line_user, text)
            except Exception:
                # Review already applied above; keep line_sent=false and commit.
                logger.exception(
                    "LINE notify failed for %s; review still committed", event_id
                )
            else:
                notifications["line_sent"] = True
                notifications["line_sent_at"] = now.isoformat()
                write_audit(
                    db,
                    who=user.username,
                    action="send_line",
                    event_id=event_id,
                    ip=_client_ip(request),
                    note="LINE text push after confirm",
                )
```

with the async version:
```python
    if body.decision == "confirmed":
        token = (settings.line_channel_access_token or "").strip()
        line_user = (settings.line_user_id or "").strip()
        if not token or not line_user:
            logger.warning(
                "LINE notify skipped for %s: empty token or user_id", event_id
            )
        else:
            camera = (
                db.query(Camera).filter(Camera.camera_id == event.camera_id).first()
            )
            camera_name = camera.name if camera else event.camera_id
            text = build_line_text_for_event(event, camera_name)
            # Push off-request so the review response returns immediately; the
            # dispatcher flags line_sent + writes the send_line audit on success.
            background_tasks.add_task(
                _dispatch_line_notification,
                event_id=event_id,
                text=text,
                token=token,
                line_user=line_user,
                reviewed_by=user.username,
                ip=_client_ip(request),
            )
```

(Leave the earlier `notifications["line_sent"] = False` default as-is — it now stays
false at commit and is flipped by the dispatcher.)

- [ ] **Step 5: Run the review-line + full API suite**

Run: `cd apps/api && ./.venv/Scripts/python.exe -m pytest tests/test_review_line.py -q` → all pass
Run: `cd apps/api && ./.venv/Scripts/python.exe -m pytest -q` → 60 passed

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/routers/events.py apps/api/tests/test_review_line.py
git commit -m "feat(api): dispatch LINE push in background (non-blocking review)"
```

---

## Self-Review

**Spec coverage:** §3 behaviour (schedule task, line_sent=false at commit, dispatcher flags on success) → Task 1 Steps 3–4; §5 tests → Task 1 Step 1. ✓

**Placeholder scan:** full code in each step. ✓

**Consistency:** `_dispatch_line_notification` signature matches the `add_task` kwargs; dispatcher uses `SessionLocal` + `write_audit` + `send_line_text` (all imported in events.py — `send_line_text`/`write_audit` already imported, add `SessionLocal`/`BackgroundTasks`). `datetime`/`timezone`/`Optional` already imported in events.py. The `patch("app.routers.events.send_line_text")` in tests still intercepts the dispatcher's module-global call; TestClient runs the task within the request so mocks stay active and the re-GET sees the update. ✓
