# Final branch review — fix wave

**Branch:** `feat/school-cctv-mvp`  
**Commit message:** `fix: harden review LINE, evidence paths, camera offline status, thumb serve`  
**Date:** 2026-07-23

## Fixes applied

### 1. LINE failure must not block review commit
- **File:** `apps/api/app/routers/events.py` (`review_event`)
- Review fields (`status`, `review_json`) + `review_*` audit written first.
- `send_line_text` wrapped in `try/except`.
- Success → `notifications.line_sent=true`, audit `send_line`.
- Failure → log exception, leave `line_sent=false`, still commit `confirmed`.
- **Test:** `test_review_confirm_commits_when_line_fails` in `test_review_line.py`.

### 2. Sanitize evidence `relative_path`
- **File:** `apps/api/app/routers/events.py`
- Helper `_safe_evidence_dir`: resolve under `evidence_root`, reject absolute / `..` escapes → **400**.
- Used on create (store) and `get_evidence` / `get_evidence_file`.
- Prefer non-empty relative path; empty falls back to `event_id`.

### 3. Camera online status for offline events
- **API create:** `event_type == camera_offline` → `_upsert_camera(..., is_online=False)`; else `True`.
- **Worker:** `ApiClient.put_camera_status`; after successful dual-write offline emit, PUT camera offline.
- **Tests:** `test_create_camera_offline_sets_is_online_false`, `test_put_camera_status_sends_system_token`.

### 4. Serve evidence files (admin thumb)
- **API:** `GET /api/events/{event_id}/evidence/file?name=thumb.jpg|clip.mp4|event.json` (admin JWT).
- Basename allow-list only; path confined to event evidence dir under root.
- **Web:** `fetchEvidenceFileBlobUrl` + event detail shows `<img>` when thumb blob loads.

## Test results

| Suite | Passed | Failed |
|-------|-------:|-------:|
| `apps/api` pytest | 29 | 0 |
| `apps/event-worker` pytest | 72 | 0 |
| **Total** | **101** | **0** |

## Files touched

- `apps/api/app/routers/events.py`
- `apps/api/tests/test_events.py`
- `apps/api/tests/test_review_line.py`
- `apps/event-worker/worker/api_client.py`
- `apps/event-worker/worker/mqtt_consumer.py`
- `apps/event-worker/tests/test_api_client.py`
- `apps/web/src/lib/api.ts`
- `apps/web/src/app/events/[eventId]/page.tsx`

## Status

**DONE** — all four Important findings fixed; unit tests green.
