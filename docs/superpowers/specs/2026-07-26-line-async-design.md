# LINE Async (non-blocking review) — Design Spec

**Date:** 2026-07-26
**Project:** `cctvbot`
**Status:** Approved for implementation planning
**Mode:** API perf/UX fix.

---

## 1. Purpose

`review_event` sends the LINE push synchronously inside the PATCH request (httpx, 10s
timeout). On `confirmed`, the admin's review request blocks on an external HTTP call.
Move the push to a FastAPI `BackgroundTask` so the review responds immediately; the LINE
result is applied to the event afterward.

## 2. Scope

### In scope
- `review_event` schedules the LINE push via `BackgroundTasks` instead of sending inline.
- A background dispatcher that sends LINE and, on success, flags the event
  (`line_sent`, `line_sent_at`) + writes the `send_line` audit — using its own DB session.
- Update the one test that asserted synchronous `line_sent=True` in the response.

### Out of scope
- A real queue/broker (Redis/Celery), retries/backoff — `BackgroundTasks` suffices for the
  single-container pilot.
- Any change to `send_line_text` / the LINE payload.

## 3. Behaviour change (contract)

- On `decision == "confirmed"` with LINE configured: the PATCH commits the review with
  `notifications.line_sent = false` (pending) and returns **immediately**.
- The background task sends the LINE text; on success it opens a new session, sets
  `line_sent = true` + `line_sent_at`, writes the `send_line` audit, commits.
- On failure it logs and leaves `line_sent = false` — the review is already committed
  (unchanged guarantee), and now the request was never blocked.
- The dashboard reflects `line_sent = true` on the next fetch (the events list already
  auto-refreshes every 15s; the detail page has a refresh).

## 4. Implementation

`apps/api/app/routers/events.py`:
- `review_event(..., background_tasks: BackgroundTasks)`.
- Module function
  `_dispatch_line_notification(*, event_id, text, token, line_user, reviewed_by, ip)`:
  sends via `send_line_text`; on success loads the event in a fresh `SessionLocal`,
  updates `notifications_json`, writes the audit, commits.
- In the confirmed branch: build the text, `background_tasks.add_task(...)`, keep
  `notifications.line_sent = false` at commit time.
- Imports: `BackgroundTasks` (fastapi), `SessionLocal` (app.db).

## 5. Testing

`apps/api/tests/test_review_line.py`:
- `test_review_confirm_sends_line`: the response now shows `line_sent=false` (dispatched
  async); assert status `confirmed`, the mock was called with the right token/user/text,
  then re-`GET` the event and assert `line_sent=true` + `line_sent_at` set (the background
  task ran within the TestClient request cycle and updated the row).
- `test_review_confirm_audits_send_line`: unchanged — the background task writes the
  `send_line` audit (runs before the assertion; TestClient executes background tasks).
- `test_review_confirm_commits_when_line_fails`: unchanged — response `line_sent=false`,
  review committed, no `send_line` audit.
- `test_review_confirm_skips_line_when_token_empty` / `test_review_false_positive_no_line`:
  unchanged (no task scheduled).

All suites stay green: API 60→ (same count), worker 95.

## 6. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Background task runs after the response so `line_sent` is briefly stale | Dashboard auto-refresh (15s) / manual refresh reflects it; acceptable for an async notification. |
| Background task needs its own DB session | Uses `SessionLocal` (not the closed request session); commits independently. |
| TestClient background-task timing | Starlette runs background tasks within the request cycle, so tests re-GET the updated row and mocks stay active. |
| In-process task lost if the container dies mid-push | Same exposure as the previous inline try/except (LINE is best-effort after confirm); a durable queue is out of scope. |
