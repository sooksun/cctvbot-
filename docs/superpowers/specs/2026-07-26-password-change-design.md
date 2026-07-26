# Password Change (self-service) — Design Spec

**Date:** 2026-07-26
**Project:** `cctvbot`
**Status:** Approved for implementation planning
**Mode:** Internal dashboard (school LAN); authenticated self-service.

---

## 1. Purpose

The security checklist says "change `ADMIN_PASSWORD` after first login," but there is
no in-app way to do it — `seed_users` only inserts the admin when absent, so editing
`.env` does nothing to an existing user. This spec adds a self-service password-change
endpoint and a dashboard form so any logged-in user can change their own password.

## 2. Scope

### In scope
- `POST /api/auth/change-password` (any authenticated user, own password).
- Dashboard change-password page + AppHeader link + client helper.
- API tests for success and every rejection.

### Out of scope
- Admin resetting another user's password / user CRUD (that is user management — a
  separate backlog item).
- Rate limiting this endpoint (caller is already authenticated).
- Password-strength rules beyond a minimum length.

## 3. Endpoint

`POST /api/auth/change-password` — `Depends(get_current_user)`.

Request (`ChangePasswordRequest`):
```
current_password: str
new_password: str = Field(min_length=8)
```
`min_length=8` → FastAPI returns 422 for a too-short new password.

Behaviour:
1. Verify `current_password` against `user.password_hash`; wrong → **400** "รหัสผ่านปัจจุบันไม่ถูกต้อง".
2. `new_password == current_password` → **400** "รหัสใหม่ต้องต่างจากรหัสเดิม".
3. Otherwise: `user.password_hash = hash_password(new_password)`, write audit
   (`change_password`), commit, return `{"ok": true}`.

Uses the existing `verify_password` / `hash_password` (bcrypt 5, 72-byte truncation).

## 4. Frontend

`apps/web/src/lib/api.ts`:
```
changePassword(currentPassword, newPassword) -> { ok: boolean }
```

New page `apps/web/src/app/account/page.tsx` (behind `AuthGate` + `AppHeader`): a form
with current password, new password, confirm-new. Client-side: confirm must match new;
new ≥ 8 chars. On success show a success message and clear the fields; on error show
the server detail.

`apps/web/src/components/AppHeader.tsx`: add a "เปลี่ยนรหัสผ่าน" link to `/account`
for logged-in users (next to username / logout).

## 5. Testing (validation bar)

API tests (`apps/api/tests/test_auth.py`, extend):
- correct current + valid new → 200; then login with the new password succeeds and the
  old password fails.
- wrong current password → 400.
- `new == current` → 400.
- new password shorter than 8 → 422.
- unauthenticated (no bearer) → 401.

Frontend: `npm run build`, `eslint`, `tsc --noEmit` clean (no frontend test harness).

All existing suites stay green: API 47 (before new tests), worker 90.

## 6. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Stolen token used to change password | Requires the current password too; a token thief still needs the secret. |
| Weak new password | `min_length=8` server-side (422); client hint. Stronger policy is a later enhancement. |
| Seeded admin never changes default | This feature is the remediation; DEPLOY checklist points here. |
