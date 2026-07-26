# cctvbot — Session Report

**Date:** 2026-07-26
**Result:** ปิด backlog ทั้งหมด จากผลตรวจ code-status ~80% สู่ระบบพร้อม pilot
**HEAD:** `master = origin = 7d7f230`

## Test status (final)

| Suite | Result |
|-------|--------|
| API (sqlite) | 60 passed, 1 skipped |
| API (MySQL 8.0.30, real) | 61 passed |
| event-worker | 95 passed |
| web (Vitest) | 7 passed |
| npm audit (runtime) | 0 vulnerabilities |

ทุก workstream ผ่านกระบวนการเดียวกัน: **brainstorm → spec → plan → TDD → merge → push** พร้อม spec + plan ใน `docs/superpowers/`.

## งานที่ส่งมอบ (16 workstreams)

### Foundations & Security
| งาน | สรุป | commits |
|-----|------|---------|
| อัปเกรด deps + Next 16 | Next 15→16, fastapi/sqlalchemy/pydantic ฯลฯ; DB `pool_pre_ping` + evidence path hardening; npm audit runtime = 0 (pin postcss/sharp) | `91ea395` |
| Login rate limiting | in-memory fixed-window 10/60s ต่อ IP → 429 | `9f7c825` |
| ถอด passlib → bcrypt 5 | เรียก bcrypt ตรง + 72-byte truncate; hash `$2b$` เดิม verify ได้ | `ef3ed59` |
| เปลี่ยนรหัสผ่านในแอป | self-service `POST /api/auth/change-password` + หน้า `/account` | `2c4153e`, `ecfac72` |
| Alembic migrations | แทน `create_all` บน prod; migrate-then-serve; verified บน MySQL จริง | `6636bde`, `6fad70d`, `7ff1b2d` |

### Detection Core
| งาน | สรุป | commits |
|-----|------|---------|
| Person-motion enrichment (rules 7 + 9) | คำนวณ speed / nearby_count / high-motion ใน worker → abnormal_motion / crowd / fight ยิงได้จริง | `632fb29`, `4e30d0c` |
| Littering (rule 8) | object-drop + camera-level person presence (opt-in) | `92a66c0`, `0144ead` |
| Box-format fix (pixel → 0-1) | บั๊กจาก verification — Frigate ส่ง box เป็น pixel; normalize ที่ ingest กัน FP-storm | `e441c22`, `4aaab84` |

### Product Features
| งาน | สรุป | commits |
|-----|------|---------|
| Event lifecycle (action_taken / closed) | transition API + ปุ่มบนหน้า detail; เก็บใน `review_json` (ไม่แตะ schema) | `d7139cf`, `4d0cbb9` |
| Camera dashboard | preview (snapshot proxy), config (name/zone), control (enable/disable → drop event) | `b159cbd`, `b785b55` |
| Pagination + auto-refresh | prev/next + page-size + toggle รีเฟรช 15s บนรายการเหตุการณ์ | `56021c9` |
| LINE async | ย้าย push ไป `BackgroundTasks` — review ไม่บล็อกรอ ~10s | `d51f9c5` |
| Clip playback | ปุ่มเล่นคลิป (admin, on-demand) → `<video>` จาก authed blob | `7cc3403` |

### Quality & Infra
| งาน | สรุป | commits |
|-----|------|---------|
| Frontend test harness | Vitest + React Testing Library + jsdom; seed tests (labels + AppHeader) | `8ed7cdc`, `12e5fd3` |
| MySQL integration testing | รัน suite ทั้งหมดบน MySQL จริง (conftest respect `DATABASE_URL`) + e2e test | `607d863`, `c0a0f80` |
| Web Dockerfile standalone | `output:"standalone"` → runner image เล็กลง/boot เร็ว (`node server.js`) | `9489354`, `7d7f230` |

## สถานะการ Verify

| รายการ | สถานะ | หลักฐาน / เหตุผล |
|--------|-------|------------------|
| Alembic + schema บน MySQL | ✅ verified | MySQL 8.0.30 จริง: suite 61 ผ่าน, upgrade/check(no-diff)/downgrade, `DEFAULT (now())` auto-populate |
| Thai utf8mb4 + JSON columns | ✅ verified | ข้อความไทยใน `message_th` / `review_json` round-trip บน MySQL จริง |
| Frigate box format | ✅ verified + fixed | docs ยืนยัน pixel → normalize แล้ว (เหลือยืนยัน **ลำดับ** `[x1,y1,x2,y2]` กับ payload สด) |
| Unit / integration / web suites | ✅ green | API 60(+1 skip) · MySQL 61 · worker 95 · web 7 |
| Docker image builds | ⚠️ deploy-verify | Docker Desktop ไม่รัน — api migrate-then-serve + web standalone + asset paths ต้อง build จริงครั้งแรก |
| Frigate live (snapshot / MQTT / FP) | ⚠️ deploy-verify | ไม่มี Frigate/กล้อง — camera snapshot จริง, enrichment กับ MQTT จริง, จูน threshold |
| 9 npm advisories (brace-expansion) | ⛔ blocked | dev/lint toolchain เท่านั้น, runtime exposure = 0; รอ eslint-config-next รองรับ patch upstream |

## ก่อน Production (ตามลำดับ)

1. Docker build จริงบนเครื่อง deploy → ยืนยัน web standalone + api `alembic upgrade head` boot ได้
2. ต่อ Frigate + กล้อง pilot → ยืนยันลำดับ box + จูน threshold rules 7/8/9 ลด false positive
3. ตั้งค่าจริง: secrets (prod guard บังคับ), `detect_width`/`detect_height`, `FRIGATE_BASE_URL`, LINE token
4. DB เดิม (ก่อน Alembic): `ALTER TABLE cameras ADD COLUMN enabled ...` ถ้ายังไม่มี → `alembic stamp head` (หรือ recreate)
