# Clip Playback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Admin on-demand clip playback on the event detail page.

**Architecture:** Frontend-only; reuse `fetchEvidenceFileBlobUrl(id, "clip.mp4")` → `<video>`.

**Tech Stack:** Next 16 + React 19 + TS.

## Global Constraints

- Single file: `apps/web/src/app/events/[eventId]/page.tsx`. No backend/api.ts change.
- Revoke the clip object URL on reload + unmount (mirror `thumbUrl`).
- On-demand (button), not auto-load.
- Verify `tsc --noEmit`, `npm run lint` (existing warnings ok), `npm run build`.

---

### Task 1: Clip playback in the event detail page

**Files:**
- Modify: `apps/web/src/app/events/[eventId]/page.tsx`

- [ ] **Step 1: Add state** — after the `thumbUrl` state:

```tsx
  const [thumbUrl, setThumbUrl] = useState<string | null>(null);
  const [clipUrl, setClipUrl] = useState<string | null>(null);
  const [clipLoading, setClipLoading] = useState(false);
```

- [ ] **Step 2: Reset clip in `load()`** — after the `setThumbUrl(...)` reset block at the top of `load`:

```tsx
    setThumbUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
    setClipUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
```

- [ ] **Step 3: Revoke clip on unmount** — extend the `useEffect` cleanup:

```tsx
    return () => {
      setThumbUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
      setClipUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
    };
```

- [ ] **Step 4: Add the `loadClip` handler** — after the `onStatusChange` function:

```tsx
  async function loadClip() {
    setClipLoading(true);
    setError(null);
    try {
      const url = await fetchEvidenceFileBlobUrl(eventId, "clip.mp4");
      setClipUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return url;
      });
    } catch {
      setError("โหลดคลิปไม่สำเร็จ");
    } finally {
      setClipLoading(false);
    }
  }
```

- [ ] **Step 5: Add the clip UI** — in the evidence section, insert between the thumbnail block and the `<ul>` (after the thumb `) : null}` and before `<ul className="space-y-1 ...">`):

```tsx
                  {admin && event.evidence.clip ? (
                    clipUrl ? (
                      <video
                        src={clipUrl}
                        controls
                        className="max-h-72 w-full rounded-lg border border-slate-200 bg-black"
                      />
                    ) : (
                      <button
                        type="button"
                        disabled={clipLoading}
                        onClick={() => void loadClip()}
                        className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                      >
                        {clipLoading ? "กำลังโหลดคลิป..." : "เล่นคลิป"}
                      </button>
                    )
                  ) : null}
```

- [ ] **Step 6: Verify build, lint, typecheck**

Run: `cd apps/web && npx tsc --noEmit` → rc 0
Run: `cd apps/web && npm run lint` → exit 0 (existing warnings ok)
Run: `cd apps/web && npm run build` → Compiled successfully

- [ ] **Step 7: Commit**

```bash
git add "apps/web/src/app/events/[eventId]/page.tsx"
git commit -m "feat(web): admin clip playback on event detail (on-demand video)"
```

---

## Self-Review

**Spec coverage:** §3 approach (clipUrl/clipLoading state, loadClip, video/button, cleanup) → Steps 1–5; §5 verify → Step 6. ✓

**Placeholder scan:** full code in each step. ✓

**Consistency:** `fetchEvidenceFileBlobUrl(id, "clip.mp4")` is already exported and typed for `"clip.mp4"`; `event.evidence.clip` gates the UI; clip URL revoked in the same two places as `thumbUrl`. No backend/api.ts change. ✓
