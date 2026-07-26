# Events List — Pagination + Auto-refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add prev/next pagination + a 15s auto-refresh toggle to the dashboard events table.

**Architecture:** Frontend only. Add `offset`/`pageSize`/`autoRefresh`/`lastUpdated` state to `DashboardContent`; pass `limit`/`offset` to the existing `listEvents`; add pagination + auto-refresh controls; a polling effect.

**Tech Stack:** Next 16 + React 19 + TS. No backend/API change.

## Global Constraints

- Single file: `apps/web/src/app/page.tsx`. No backend change (uses existing `limit`/`offset`).
- Changing a filter or the page size must reset `offset = 0`.
- "Next" is heuristic: enabled only when the current page returned exactly `pageSize` rows.
- Verify `tsc --noEmit`, `npm run lint` (existing 5 warnings ok), `npm run build`.

---

### Task 1: Pagination + auto-refresh in `page.tsx`

**Files:**
- Modify: `apps/web/src/app/page.tsx`

- [ ] **Step 1: Replace the state + `load` + effects block**

Replace:

```tsx
  const [events, setEvents] = useState<Event[]>([]);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [filters, setFilters] = useState<EventFilters>({
    status: "pending_review",
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [ev, cams] = await Promise.all([
        listEvents(filters),
        listCameras(),
      ]);
      setEvents(ev);
      setCameras(cams);
    } catch (err) {
      setError(err instanceof Error ? err.message : "โหลดข้อมูลไม่สำเร็จ");
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    void load();
  }, [load]);
```

with:

```tsx
  const [events, setEvents] = useState<Event[]>([]);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [filters, setFilters] = useState<EventFilters>({
    status: "pending_review",
  });
  const [offset, setOffset] = useState(0);
  const [pageSize, setPageSize] = useState(50);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [ev, cams] = await Promise.all([
        listEvents({ ...filters, limit: pageSize, offset }),
        listCameras(),
      ]);
      setEvents(ev);
      setCameras(cams);
      setLastUpdated(
        new Date().toLocaleTimeString("th-TH", { timeZone: "Asia/Bangkok" }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "โหลดข้อมูลไม่สำเร็จ");
    } finally {
      setLoading(false);
    }
  }, [filters, pageSize, offset]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!autoRefresh) return;
    const t = setInterval(() => void load(), 15000);
    return () => clearInterval(t);
  }, [autoRefresh, load]);

  const patchFilter = (patch: Partial<EventFilters>) => {
    setOffset(0);
    setFilters((f) => ({ ...f, ...patch }));
  };
```

- [ ] **Step 2: Route the filter selects through `patchFilter` (reset to page 1)**

Change the three filter `onChange` handlers from `setFilters((f) => ({ ...f, X: ... }))`
to `patchFilter({ X: ... })`:

- status select:
```tsx
                onChange={(e) =>
                  patchFilter({ status: e.target.value || undefined })
                }
```
- camera select:
```tsx
                onChange={(e) =>
                  patchFilter({ camera_id: e.target.value || undefined })
                }
```
- event_type select:
```tsx
                onChange={(e) =>
                  patchFilter({ event_type: e.target.value || undefined })
                }
```

- [ ] **Step 3: Add auto-refresh controls next to the manual refresh button**

Replace the manual-refresh `<div className="flex items-end">...</div>` block:

```tsx
            <div className="flex items-end">
              <button
                type="button"
                onClick={() => void load()}
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
              >
                รีเฟรช
              </button>
            </div>
```

with:

```tsx
            <label className="flex flex-col gap-1 text-xs text-slate-500">
              ต่อหน้า
              <select
                value={pageSize}
                onChange={(e) => {
                  setOffset(0);
                  setPageSize(Number(e.target.value));
                }}
                className="rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
              >
                {[25, 50, 100].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>

            <div className="flex items-end gap-3">
              <button
                type="button"
                onClick={() => void load()}
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
              >
                รีเฟรช
              </button>
              <label className="flex items-center gap-1.5 text-xs text-slate-600">
                <input
                  type="checkbox"
                  checked={autoRefresh}
                  onChange={(e) => setAutoRefresh(e.target.checked)}
                />
                รีเฟรชอัตโนมัติ (15 วิ)
              </label>
              {lastUpdated ? (
                <span className="text-xs text-slate-400">
                  อัปเดตล่าสุด {lastUpdated}
                </span>
              ) : null}
            </div>
```

- [ ] **Step 4: Add the pagination bar below the events table**

Immediately after the events `</section>` closing the events card's table (the
`</div>` that closes `overflow-x-auto` then the section), add a pagination bar inside the
section footer. Concretely, replace the table's closing:

```tsx
            </div>
          )}
        </section>
```

with:

```tsx
            </div>
          )}

          {!loading && !error ? (
            <div className="flex items-center justify-between gap-3 border-t border-slate-100 px-4 py-3 text-sm">
              <span className="text-slate-500">
                หน้า {Math.floor(offset / pageSize) + 1}
                {events.length > 0
                  ? ` · แสดง ${offset + 1}–${offset + events.length}`
                  : ""}
              </span>
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={offset === 0}
                  onClick={() => setOffset((o) => Math.max(0, o - pageSize))}
                  className="rounded-md border border-slate-300 px-3 py-1.5 text-slate-700 hover:bg-slate-50 disabled:opacity-40"
                >
                  ก่อนหน้า
                </button>
                <button
                  type="button"
                  disabled={events.length < pageSize}
                  onClick={() => setOffset((o) => o + pageSize)}
                  className="rounded-md border border-slate-300 px-3 py-1.5 text-slate-700 hover:bg-slate-50 disabled:opacity-40"
                >
                  ถัดไป
                </button>
              </div>
            </div>
          ) : null}
        </section>
```

- [ ] **Step 5: Verify build, lint, typecheck**

Run: `cd apps/web && npx tsc --noEmit` → rc 0
Run: `cd apps/web && npm run lint` → exit 0 (existing 5 warnings ok)
Run: `cd apps/web && npm run build` → Compiled successfully

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/app/page.tsx
git commit -m "feat(web): events list pagination + auto-refresh toggle"
```

---

## Self-Review

**Spec coverage:** §3 pagination (offset/pageSize/prev/next/reset) → Steps 1–4; auto-refresh (toggle/15s/last-updated) → Steps 1,3; §4 verify → Step 5. ✓

**Placeholder scan:** No TBD/TODO; full code in each step. ✓

**Consistency:** `patchFilter` resets offset on every filter change; pageSize change resets offset; `load` deps include filters/pageSize/offset so any change refetches; auto-refresh effect reuses the same `load`. `listEvents({...filters, limit, offset})` matches the existing `EventFilters` (has optional `limit`/`offset`). ✓
