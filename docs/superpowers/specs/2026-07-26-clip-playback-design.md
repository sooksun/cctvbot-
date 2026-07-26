# Clip Playback — Design Spec

**Date:** 2026-07-26
**Project:** `cctvbot`
**Status:** Approved for implementation planning
**Mode:** Frontend-only (reuses the existing evidence-file endpoint).

---

## 1. Purpose

The event detail page shows the evidence thumbnail but only lists the clip filename as
text. Add on-demand clip playback for admins, reusing the existing authenticated
evidence-file endpoint.

## 2. Scope

### In scope
- On the event detail page: an admin-only "เล่นคลิป" button (shown when the event has a
  clip) that fetches `clip.mp4` as an authed blob and renders a `<video controls>`.
- Object-URL lifecycle cleanup (revoke on reload / unmount), mirroring the thumbnail.

### Out of scope
- Backend changes — `GET /api/events/{id}/evidence/file?name=clip.mp4` (admin, allow-listed,
  `video/mp4`) and `fetchEvidenceFileBlobUrl` already exist.
- HTTP range / streaming, download button, autoplay.

## 3. Approach

`apps/web/src/app/events/[eventId]/page.tsx`:
- State `clipUrl: string | null` + `clipLoading: boolean`.
- `loadClip()` → `fetchEvidenceFileBlobUrl(eventId, "clip.mp4")` → object URL (revoke any
  previous).
- Evidence section: when `admin && event.evidence.clip` — render `<video controls src>`
  once loaded, otherwise a "เล่นคลิป" button (disabled/"กำลังโหลด…" while fetching).
- Revoke `clipUrl` in `load()`'s reset and the unmount cleanup (same as `thumbUrl`).

**On-demand (not auto-load):** clips are larger than thumbnails; fetch only on click to
avoid downloading a video every time the detail page opens.

## 4. Constraint (accepted)

Blob-fetch loads the whole clip into memory (fine for MVP / LAN / admin / 30–60s clips).
True streaming would need auth in the URL because `<video src>` cannot send an
`Authorization` header — out of scope.

## 5. Testing

No frontend test harness; verify `npm run build`, `eslint`, `tsc --noEmit`. Actual
playback needs a real clip file + browser (deployment check). The fetch/render/cleanup
logic mirrors the already-working thumbnail path.

## 6. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Large clip fully in memory | On-demand button; short pilot clips; streaming deferred. |
| Object URL leak | Revoke on reload + unmount (same pattern as thumbnail). |
| Clip missing on server | 404 → caught → "โหลดคลิปไม่สำเร็จ" message. |
