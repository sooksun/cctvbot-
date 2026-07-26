# MySQL Integration Testing — Design Spec

**Date:** 2026-07-26
**Project:** `cctvbot`
**Status:** Approved for implementation planning
**Mode:** API test infrastructure.

---

## 1. Purpose

The API suite runs only against in-memory sqlite, so nothing is exercised on the real
prod engine (MySQL/MariaDB). Let the existing suite run against MySQL, and add one
explicit end-to-end integration test, to validate JSON columns, Thai (utf8mb4) text,
indexes, defaults, and the full flows on the actual engine.

## 2. Scope

### In scope
- `conftest.py` respects an externally provided `DATABASE_URL` (default stays sqlite).
- A session-autouse fixture that creates the schema (and drops it) for non-sqlite runs.
- `tests/test_mysql_integration.py`: an end-to-end lifecycle test that runs only against
  MySQL (skipped on sqlite).
- Docs on how to run the MySQL suite.

### Out of scope
- Frigate integration (no live Frigate); CI wiring; testcontainers.
- Changing any application code (unless the run surfaces a real MySQL incompatibility —
  those get fixed as findings).

## 3. Approach

`apps/api/tests/conftest.py`:
- `os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")` — default
  unchanged; set `DATABASE_URL` externally to target MySQL. (Other test secrets stay
  hard-set.)
- Session-scoped autouse fixture `_ensure_schema`: for non-sqlite,
  `Base.metadata.create_all(engine)` at session start and `drop_all` at end (so the MySQL
  test DB is clean and re-runnable). sqlite is a no-op (the app's `init_db` + StaticPool
  handle it).

`apps/api/tests/test_mysql_integration.py`:
- `pytestmark = skipif(settings.database_url.startswith("sqlite"))`.
- One test: create event (Thai `message_th` + Thai rule name) via system token → assert
  Thai round-trips; review → confirmed; status → action_taken → closed; disable the camera
  → next event dropped (202); GET confirms persisted `status`/`review_json` on MySQL.

## 4. Running

- `pytest` (unchanged) → sqlite, the integration test is skipped.
- Create a fresh utf8mb4 DB, then
  `DATABASE_URL="mysql+pymysql://root@127.0.0.1:3306/<db>" pytest` → the whole suite +
  the integration test run on MySQL.

Documented as a short note in `apps/api/tests/test_mysql_integration.py` (module
docstring) and DEPLOY/README as appropriate.

## 5. Verification

- Full suite green on **MySQL 8.0.30** (fresh utf8mb4 DB) — any sqlite-ism that breaks on
  MySQL is a real finding and gets fixed.
- Full suite still green on sqlite (default `pytest`), integration test skipped.
- Worker suite unaffected.

## 6. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Existing tests carry sqlite-only assumptions | Running on MySQL surfaces them; fix as findings (the point of the task). |
| tz-aware datetimes stored naive on MySQL | Assertions target status/strings/round-trip, not tz equality; adjust if a real mismatch appears. |
| Thai text corruption | Test DB created `utf8mb4`; explicit Thai round-trip assertion. |
| Accidental default-behavior change | `setdefault` keeps sqlite default when `DATABASE_URL` is unset. |
