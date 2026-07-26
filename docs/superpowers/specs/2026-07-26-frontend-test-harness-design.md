# Frontend Test Harness (Vitest + RTL) — Design Spec

**Date:** 2026-07-26
**Project:** `cctvbot`
**Status:** Approved for implementation planning
**Mode:** Frontend tooling (apps/web).

---

## 1. Purpose

The Next.js dashboard has no automated tests. Stand up a unit/component test harness so
frontend logic and components can be tested, and seed it with representative tests that
prove the setup works.

## 2. Scope

### In scope
- Vitest + React Testing Library + jsdom + jest-dom in `apps/web`.
- `vitest.config.ts`, `vitest.setup.ts`, a `test` npm script.
- Seed tests: `lib/labels` pure functions + an `AppHeader` component render (role logic).

### Out of scope
- End-to-end (Playwright); coverage thresholds; testing every component. This establishes
  the harness + a representative sample.

## 3. Stack & config

- Dev deps: `vitest`, `@vitejs/plugin-react`, `jsdom`, `@testing-library/react`,
  `@testing-library/jest-dom`, `@testing-library/dom` (latest compatible with React 19).
- `vitest.config.ts`: `plugins:[react()]`, `test.environment:"jsdom"`,
  `setupFiles:["./vitest.setup.ts"]`, `include:["src/**/*.test.{ts,tsx}"]`,
  `resolve.alias { "@": src }` (mirrors tsconfig `@/*`).
- `vitest.setup.ts`: `import "@testing-library/jest-dom/vitest"`.
- `package.json`: `"test": "vitest run"`.
- Tests import `{ describe, it, expect, vi }` explicitly from `"vitest"` (no globals → no
  tsconfig change).

## 4. Seed tests

- `src/lib/labels.test.ts` — `statusLabel`/`eventTypeLabel` mapping + fallback,
  `EVENT_TYPES` == keys, `severityClass`/`statusClass` tailwind strings, `formatDateTime(null)`.
- `src/components/AppHeader.test.tsx` — mock `next/navigation` (`useRouter`), seed
  `localStorage` role; assert the admin-only "จัดการกล้อง" link shows for `admin` and is
  absent for `viewer`, plus the logout button renders. Proves jsdom + RTL + mocking + role
  logic.

## 5. Build interaction

Test files live under `src/` (not `app/`), so Next never routes/bundles them; they are
only type-checked by tsc (dev deps present during `npm ci` build). They must be
type-clean. `next build` / `eslint` / `tsc --noEmit` must stay green.

## 6. Testing / verification

- `npm test` → all seed tests pass.
- `npm run build`, `npm run lint`, `npx tsc --noEmit` still green.

## 7. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| RTL/React 19 peer mismatch | RTL v16 supports React 19; install latest; adjust if npm reports a peer conflict. |
| Test deps type-checked by `next build` | Explicit `vitest` imports resolve from node_modules (present at build); tests kept type-clean. |
| Component test brittleness (nested text) | Assert on stable, unique elements (the camera link, logout button) + role branch, not concatenated username text. |
| node_modules bloat in web image | Pre-existing (web Dockerfile copies full node_modules); addressed separately by the standalone-Dockerfile task. |
