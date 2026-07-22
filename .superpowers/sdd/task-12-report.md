# Task 12 Report: Verification checklist (definition of done)

## Status
**DONE**

## Environment
- Branch: `feat/school-cctv-mvp`
- Host: Windows (Laragon), PowerShell
- API venv: `apps/api/.venv` (Python 3.11)
- Worker venv: `apps/event-worker/.venv` (Python 3.11)
- Live stack (`db`/`api`): **not running** — smoke against real DB/HTTP skipped; covered by unit tests + static checks

---

## Step 1: API unit tests

```text
cd apps/api
.\.venv\Scripts\python.exe -m pytest -v --rootdir=.
```

| Result | Count |
|--------|------:|
| **passed** | **23** |
| failed | 0 |
| errors | 0 |
| duration | ~4.3s |

Coverage includes auth (JWT + system token), events create/list/review, evidence admin-only, health, LINE text-only push + audit (`review_confirm` / `send_line`).

**Note:** Running pytest from repo root with either app venv incorrectly collects both `apps/api/tests` and `apps/event-worker/tests` (shared package name `tests` → import collisions). Always run with `--rootdir=.` from each app directory (worker has `pytest.ini` / `testpaths: tests`).

---

## Step 2: Worker unit tests

```text
cd apps/event-worker
.\.venv\Scripts\python.exe -m pytest -v --rootdir=.
```

| Result | Count |
|--------|------:|
| **passed** | **71** |
| failed | 0 |
| errors | 0 |
| duration | ~0.3s |

Coverage: api_client, debounce, evidence (`event_id` path), schedules, rules (after hours, restricted, fall, camera offline/tamper, abnormal motion/crowd, littering, fight).

---

## Step 3: Smoke event in DB + `/data/events`

| Check | Result |
|-------|--------|
| `python -m py_compile scripts/smoke_create_event.py` | **OK** (syntax valid) |
| Live POST to API + file under `data/events/` | **Skipped** — API not reachable (`http://localhost:8000/health` timeout) |
| Unit stand-in | `test_create_event_with_system_token`, evidence path tests worker-side |

Manual when stack is up:
```bash
docker compose up -d db api web
$env:SYSTEM_API_TOKEN = "<from .env>"
python scripts/smoke_create_event.py
# expect EVT-YYYYMMDD-#### under data/events/ and row in events table
```

---

## Step 4: Review confirm + audit_logs

Live dashboard/review against running DB: **Skipped** (API down).

Verified via API unit tests:

| Assertion | Test |
|-----------|------|
| Review confirm updates status | `test_review_confirm` |
| Audit `review_confirm` | `test_review_confirm_audits_send_line` |
| Audit `send_line` when LINE configured | `test_review_confirm_audits_send_line` |
| LINE skipped when token empty | `test_review_confirm_skips_line_when_token_empty` |
| False positive does not send LINE | `test_review_false_positive_no_line` |

Router (`apps/api/app/routers/events.py`): action `review_confirm` / `review_false_positive`; on confirmed + token, `send_line` audit after `send_line_text`.

---

## Step 5: LINE payload has no media

| Artifact | Finding |
|----------|---------|
| `apps/api/app/line_notify.py` | `send_line_text` posts only `messages: [{type: "text", text: ...}]` — docstring: no images/clips |
| `apps/api/tests/test_review_line.py` | Asserts no `imageUrl`, `originalContentUrl`, `previewImageUrl`, `image` keys in push body |
| Template text | Ends with “เปิดดูภาพได้ที่ระบบภายในเท่านั้น” (no media URL) |

**PASS** — text-only LINE path confirmed by code + unit tests.

---

## Step 6: Key files / compose / final commit

### Files present
| Path | Status |
|------|--------|
| `frigate/config.yml` | EXISTS (pilot 2–4 cams, CPU default, MQTT→mosquitto) |
| `apps/web/src/app/page.tsx` | EXISTS |
| `scripts/smoke_create_event.py` | EXISTS |
| `apps/api/app/line_notify.py` | EXISTS |
| `docker-compose.yml` | EXISTS |

### docker-compose services (required set)
| Service | Present |
|---------|---------|
| `api` | yes |
| `web` | yes |
| `frigate` | yes |
| `event-worker` | yes |
| (+ `db`, `mosquitto`) | yes |

### Code changes / commit
**None.** All runnable checks green; no trivial test failures to fix.

Commit message `test: MVP verification fixes` **not** created (no code delta).

---

## Spec coverage self-review (from brief)

| Spec requirement | Task coverage | Verified this run |
|------------------|---------------|-------------------|
| Mixed IP + Analog via RTSP | 9 | `frigate/config.yml` present |
| Frigate + GPU server notes | 9 | compose + config comments |
| event-worker rules 1,2,5,7,8,9 | 6, 7 | worker tests 71 passed |
| Dual API + files | 4, 5 | API + evidence tests |
| Dashboard review | 10 | `apps/web/src/app/page.tsx` exists |
| LINE after confirm text-only | 8 | line_notify + test_review_line |
| Auth roles admin/viewer/system | 3 | test_auth 7 cases |
| Audit log | 4 | review + send_line audits |
| Local-first / no face ID | Global + 9, 10 | static (no face pipeline) |
| 2–4 pilot cameras | 9 | frigate config header |
| Schedules / zones | 5, 6, 9 | schedules + restricted tests |
| Retention 30 days Frigate | 9 config | config present (not re-parsed line-by-line) |
| Smoke / success criteria | 11, 12 | syntax OK; live smoke needs stack |

---

## Failures / gaps

1. **Live E2E smoke (Steps 3–4 HTTP/DB)** not executed — Docker/API not up on this machine.
2. **Root-level pytest** is footgun (dual `tests` packages); document per-app invocation only — not a product defect.

No product/code defects found; no fixes applied.

---

## Summary counts

| Suite | Passed | Failed |
|-------|-------:|-------:|
| API (`apps/api`) | 23 | 0 |
| event-worker | 71 | 0 |
| **Total unit** | **94** | **0** |
| Smoke script compile | OK | — |
| LINE no-media | PASS | — |
| Key files + compose services | PASS | — |
| Commit | none (no code changes) | |

---

## Final branch review fix wave (post-review)

See also: `.superpowers/sdd/final-fix-report.md`

| Item | Fix |
|------|-----|
| LINE failure blocks review | `review_event`: try/except around `send_line_text`; status/review/audit always commit; `line_sent=false` on fail |
| Evidence path traversal | `_safe_evidence_dir` on create + get; 400 on `..`/absolute escape |
| Camera offline status | create sets `is_online=False` for `camera_offline`; worker `ApiClient.put_camera_status` after dual-write |
| Serve evidence thumb | `GET /api/events/{id}/evidence/file?name=...`; web fetches blob URL for `<img>` |

**Re-test:** API **29** passed, event-worker **72** passed.  
**Commit:** `fix: harden review LINE, evidence paths, camera offline status, thumb serve`
