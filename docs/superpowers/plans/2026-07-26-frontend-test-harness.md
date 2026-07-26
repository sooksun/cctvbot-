# Frontend Test Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Stand up Vitest + RTL in `apps/web` with representative seed tests.

**Architecture:** Vitest (jsdom) + React Testing Library + jest-dom; `@`→`src` alias; seed tests for `lib/labels` and `AppHeader`.

**Tech Stack:** Vitest, @testing-library/react, jsdom; Next 16 / React 19.

## Global Constraints

- All work in `apps/web`. Tests under `src/**/*.test.{ts,tsx}` (never in `app/`).
- Explicit `vitest` imports (no globals config).
- `npm test`, `npm run build`, `npm run lint`, `npx tsc --noEmit` all green.

---

### Task 1: Install + configure the harness

**Files:**
- Modify: `apps/web/package.json` (devDeps + `test` script)
- Create: `apps/web/vitest.config.ts`, `apps/web/vitest.setup.ts`

- [ ] **Step 1: Install dev deps**

Run: `cd apps/web && npm install -D vitest @vitejs/plugin-react jsdom @testing-library/react @testing-library/jest-dom @testing-library/dom`
Expected: installs latest compatible versions, updates package.json/lock, `found 0 vulnerabilities` (or unchanged advisory count).

- [ ] **Step 2: Add the `test` script** to `apps/web/package.json` scripts:

```json
    "lint": "eslint",
    "test": "vitest run"
```

- [ ] **Step 3: Create `apps/web/vitest.config.ts`**

```ts
import path from "path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  test: {
    environment: "jsdom",
    globals: false,
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
```

- [ ] **Step 4: Create `apps/web/vitest.setup.ts`**

```ts
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 5: Commit the harness**

```bash
git add apps/web/package.json apps/web/package-lock.json apps/web/vitest.config.ts apps/web/vitest.setup.ts
git commit -m "chore(web): vitest + react-testing-library harness"
```

---

### Task 2: Seed tests + verify

**Files:**
- Create: `apps/web/src/lib/labels.test.ts`
- Create: `apps/web/src/components/AppHeader.test.tsx`

- [ ] **Step 1: `src/lib/labels.test.ts`**

```ts
import { describe, expect, it } from "vitest";

import {
  EVENT_TYPES,
  EVENT_TYPE_LABELS,
  eventTypeLabel,
  formatDateTime,
  severityClass,
  statusClass,
  statusLabel,
} from "@/lib/labels";

describe("labels", () => {
  it("maps known status to Thai and falls back to the raw value", () => {
    expect(statusLabel("pending_review")).toBe("รอตรวจสอบ");
    expect(statusLabel("confirmed")).toBe("ยืนยันเหตุ");
    expect(statusLabel("weird")).toBe("weird");
  });

  it("maps event types with fallback", () => {
    expect(eventTypeLabel("person_after_hours")).toBe("บุคคลนอกเวลา");
    expect(eventTypeLabel("unknown_type")).toBe("unknown_type");
  });

  it("EVENT_TYPES equals the label keys", () => {
    expect(EVENT_TYPES).toEqual(Object.keys(EVENT_TYPE_LABELS));
    expect(EVENT_TYPES).toContain("possible_fight");
  });

  it("severity/status classes return tailwind strings", () => {
    expect(severityClass("critical")).toContain("red");
    expect(statusClass("closed")).toContain("green");
    expect(severityClass("weird")).toContain("slate");
  });

  it("formatDateTime handles null", () => {
    expect(formatDateTime(null)).toBe("-");
  });
});
```

- [ ] **Step 2: `src/components/AppHeader.test.tsx`**

```tsx
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AppHeader from "@/components/AppHeader";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

describe("AppHeader", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("shows the admin camera link + logout for an admin", () => {
    localStorage.setItem("cctvbot_role", "admin");
    localStorage.setItem("cctvbot_username", "admin1");
    render(<AppHeader />);
    expect(screen.getByText("จัดการกล้อง")).toBeInTheDocument();
    expect(screen.getByText("เปลี่ยนรหัสผ่าน")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "ออกจากระบบ" }),
    ).toBeInTheDocument();
  });

  it("hides the camera link for a viewer", () => {
    localStorage.setItem("cctvbot_role", "viewer");
    render(<AppHeader />);
    expect(screen.queryByText("จัดการกล้อง")).toBeNull();
  });
});
```

- [ ] **Step 3: Run the tests**

Run: `cd apps/web && npm test`
Expected: 2 files, all tests pass (labels + AppHeader).

- [ ] **Step 4: Confirm the harness didn't break build/lint/types**

Run: `cd apps/web && npx tsc --noEmit` → rc 0
Run: `cd apps/web && npm run lint` → exit 0 (existing warnings ok; test files clean)
Run: `cd apps/web && npm run build` → Compiled successfully

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib/labels.test.ts apps/web/src/components/AppHeader.test.tsx
git commit -m "test(web): seed tests for labels + AppHeader"
```

---

## Self-Review

**Spec coverage:** §3 stack/config → Task 1; §4 seed tests → Task 2; §6 verification → Task 2 Steps 3–4. ✓

**Placeholder scan:** full code in each step; versions resolved by `npm install -D` (latest compatible), pinned in the lockfile. ✓

**Consistency:** vitest `include` matches the seed test paths; `@` alias mirrors tsconfig; `next/navigation` mock covers `useRouter`; assertions target unique elements + the role branch (not concatenated text). Test files under `src/` (not `app/`) → not routed by Next. ✓
