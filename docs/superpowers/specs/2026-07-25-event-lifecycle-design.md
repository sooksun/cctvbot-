# Event Lifecycle (`action_taken` / `closed`) — Design Spec

**Date:** 2026-07-25
**Project:** `cctvbot`
**Status:** Approved for implementation planning
**Mode:** Internal dashboard (school LAN); admin-only operational workflow.

---

## 1. Purpose

The event status lifecycle in the design spec is
`pending_review → confirmed | false_positive → action_taken → closed`, but only the
first hop exists (`PATCH /events/{id}/review`). Statuses `action_taken` and `closed`
appear in the DB and the dashboard filter, yet nothing can set them. This spec adds a
transition API and matching dashboard buttons so an admin can move a reviewed event
through its operational states.

## 2. Scope

### In scope
- New `PATCH /api/events/{id}/status` endpoint (admin only) for `action_taken` / `closed`.
- Backend transition validation + audit logging + lifecycle metadata on the event.
- Dashboard buttons on the event detail page + a client API helper.
- API tests for every allowed and rejected transition.

### Out of scope
- Reopening a `closed` event (terminal).
- Bulk status changes; time-based auto-close.
- Any change to `PATCH /events/{id}/review` (it still owns `confirmed`/`false_positive`
  and the LINE push).

## 3. Transition graph (enforced server-side)

```
confirmed      → action_taken | closed
action_taken   → closed
false_positive → closed
closed         → (terminal)
pending_review → (only via /review; rejected here)
```

Any transition not in this map returns **409 Conflict**. `confirmed → closed` is
allowed directly because `action_taken` is optional.

## 4. Endpoint

`PATCH /api/events/{id}/status` — `require_roles("admin")`.

Request body (`StatusChangeRequest`):
```
status: Literal["action_taken", "closed"]
note:   str | None = None
```
`Literal` makes any other target a 422 at validation. Separation from `/review` is
deliberate: `/review` triggers the LINE push; this endpoint is a post-review
operational step and never sends LINE.

Behaviour:
1. 404 if the event does not exist.
2. 409 if `event.status → body.status` is not in the transition map.
3. On success: set `event.status = body.status`, merge lifecycle metadata into
   `review_json`, write an audit row, return the updated `EventResponse`.

## 5. Persistence (no schema change)

The system creates tables via `Base.metadata.create_all` with no Alembic migrations,
so adding a column would not apply to existing databases. Lifecycle metadata is
therefore merged into the existing `review_json` JSON column, preserving prior review
fields:

- `action_taken` → add `action_taken_by`, `action_taken_at` (ISO-8601), and
  `action_taken_note` (when a note is supplied).
- `closed` → add `closed_by`, `closed_at`, and `closed_note`.

If `review_json` is null it defaults to `{}` before merging.

Audit actions: `mark_action_taken`, `close_event` (fields: who, action, event_id, ip, note).

## 6. Frontend

`apps/web/src/lib/api.ts`:
```
changeEventStatus(eventId, status: "action_taken" | "closed", note?) -> Event
```

`apps/web/src/app/events/[eventId]/page.tsx` — a "จัดการเคส (แอดมิน)" section shown
to admins based on current status:
- `confirmed` → buttons **ดำเนินการแล้ว** (action_taken) and **ปิดเคส** (closed)
- `action_taken` → button **ปิดเคส**
- `false_positive` → button **ปิดเคส**
- otherwise → no buttons

The existing review panel already renders for `pending_review`; the new section covers
the post-review states. Lifecycle metadata (action-taken by/at, closed by/at) is shown
in the review/result box.

## 7. Testing (validation bar)

API tests (`apps/api/tests/test_events.py`, extend):
- `confirmed → action_taken` → 200, status updated, `action_taken_by` set.
- `confirmed → closed` → 200.
- `action_taken → closed` → 200 (two-step from confirmed).
- `false_positive → closed` → 200.
- `pending_review → action_taken` → 409.
- `closed → closed` (terminal) → 409.
- viewer role → 403.
- after a transition, `review_json` still contains the original `decision`/`reviewed_by`.

Frontend: verify `npm run build`, `eslint`, `tsc --noEmit` (no frontend test harness
in the project).

All existing suites stay green: API 38 (before new tests), worker 90.

## 8. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Concurrent transition race (two admins) | Last-write-wins on a single row; transition validated against current status at request time; acceptable for a small LAN team. |
| Metadata bloat in `review_json` | Only a few scalar fields added; negligible. |
| Terminal `closed` blocks legitimate reopen | Out of scope by decision; can add a reopen transition later if needed. |
