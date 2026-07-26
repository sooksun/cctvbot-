# Events List — Pagination + Auto-refresh — Design Spec

**Date:** 2026-07-26
**Project:** `cctvbot`
**Status:** Approved for implementation planning
**Mode:** Internal dashboard; frontend-only.

---

## 1. Purpose

The dashboard events table loads a single fixed page (limit 50) with only a manual
refresh button. Add prev/next pagination and optional auto-refresh so operators can page
through history and see new pending events without clicking.

## 2. Scope

### In scope
- Prev/Next pagination (heuristic) + page-size selector on the dashboard events table.
- Auto-refresh toggle (default on, 15s) + "last updated" indicator.
- Frontend only: `apps/web/src/app/page.tsx`.

### Out of scope
- Exact total count / "page X of Y" (would need a backend `total`).
- Infinite scroll / virtualization; changes to any backend endpoint.

## 3. Behaviour

**Pagination (prev/next heuristic — no backend change):**
- State `offset` (start 0) and `pageSize` (start 50; options 25/50/100).
- Query uses the existing `GET /api/events?limit={pageSize}&offset={offset}`.
- **Prev** enabled when `offset > 0` → `offset -= pageSize`.
- **Next** enabled when the current page returned exactly `pageSize` rows (a full page ⇒
  probably more) → `offset += pageSize`.
- Show "หน้า {offset/pageSize + 1}" and the row range.
- Changing any filter or the page size resets `offset = 0`.

**Auto-refresh:**
- A toggle "รีเฟรชอัตโนมัติ", default **on**. When on, re-run the current query
  (same filters + offset + pageSize) every **15s**.
- Show "อัปเดตล่าสุด HH:MM:SS" (Asia/Bangkok) after each successful load.
- Changing filters/page/pageSize refetches immediately (existing effect dependency).
- Toggle off stops polling.

Camera status chips keep loading with the events (unchanged).

## 4. Testing

No frontend test harness in the project. Verify `npm run build`, `eslint`,
`tsc --noEmit` are clean. Existing suites unaffected (no backend change): API 60,
worker 90.

## 5. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Heuristic "Next" shows on an exactly-full last page (then empty next) | Acceptable; next page simply shows "ไม่พบเหตุการณ์" and Prev returns. |
| Auto-refresh refetches while the user reads / mid-filter | Toggle to pause; 15s interval is gentle; manual refresh still available. |
| Polling load on API | Admin/viewer dashboard, small pilot, 15s interval — negligible. |
