# Frigate Box Normalization (pixel → 0–1) — Design Spec

**Date:** 2026-07-26
**Project:** `cctvbot`
**Status:** Approved for implementation planning
**Mode:** event-worker bugfix (surfaced by real-Frigate-docs verification).

---

## 1. Purpose

Verification against the Frigate docs confirmed the `frigate/events` MQTT `after.box`
is **pixel** coordinates (e.g. `[415, 489, 528, 700]`), not normalized 0–1. The worker's
`normalize_frigate_event` passes the box through unchanged, while the person-motion
enricher and the box-based rules (fall, littering) all assume normalized 0–1. In
production this makes derived speed/centroid-motion values pixel-scaled — orders of
magnitude over the normalized thresholds — so `abnormal_motion`/`possible_fight` would
false-fire and `FallTracker` motion checks would misbehave. Fix by normalizing the box
to 0–1 at the single ingest point.

## 2. Scope

### In scope
- Normalize `box` to 0–1 inside `normalize_frigate_event` so every downstream consumer
  (enricher + all rules) receives normalized coordinates.
- `detect_width`/`detect_height` config (default 1280×720, matching `frigate/config.yml`).
- Tests for pixel→normalized conversion and a pipeline no-false-fire case.

### Out of scope
- Per-camera detect dimensions (assumes uniform resolution; can later read Frigate
  stats). Confirming the exact box **order** on a live payload (order kept as the
  existing `[x1,y1,x2,y2]`).
- Any change to rule logic (they already consume normalized boxes correctly).

## 3. Approach

Single fix point: `normalize_frigate_event(msg, tz, detect_width=1280, detect_height=720)`.

`_normalize_box(box, w, h)`:
- Parse the first 4 values as floats; return unchanged on invalid input.
- If `max(abs(v)) <= 1.0` → already normalized → return as-is (keeps existing
  normalized-box tests and any future normalized Frigate output working).
- Otherwise (pixels) → `[x1/w, y1/h, x2/w, y2/h]`.

`EventPipeline` reads `detect_width`/`detect_height` from `rules_config` (defaults
1280/720) and passes them to `normalize_frigate_event`.

Order assumption `[x1, y1, x2, y2]` is unchanged — consistent with the existing rules
(`person_fall.box_aspect_ratio`) and the docs example (both coordinate pairs increasing).

## 4. Config

`data/config/rules.yml` + `worker/main.py` `DEFAULT_RULES`:
```
detect_width: 1280
detect_height: 720
```

## 5. Testing

- `_normalize_box`: pixel `[415,489,528,700]` on 1280×720 → `[0.324…, 0.679…, 0.4125, 0.972…]`;
  normalized `[0.4,0.2,0.55,0.7]` → unchanged; invalid/short → unchanged.
- `normalize_frigate_event`: a Frigate-shaped msg with a pixel box yields a normalized
  `detection["box"]`.
- Pipeline: two person updates with **pixel** boxes moving ~50px/s → smoothed speed
  ≈ 0.04 < `run_speed_threshold` (0.15) → `abnormal_motion` does NOT fire (proves the fix;
  pre-fix this would fire).
- All existing suites stay green (their boxes are ≤1 → passed through): worker 90, API 60.

## 6. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Box order is actually `[x,y,w,h]` not `[x1,y1,x2,y2]` | Kept the existing order assumption (already in the rules); flagged to confirm on a live payload — a wrong order would already have affected the pre-existing rules, so this fix does not regress it. |
| Cameras at a different resolution than 1280×720 | Config `detect_width/height`; per-camera dims deferred. The `>1` heuristic still normalizes; only the scale factor would differ. |
| A future Frigate that emits normalized boxes | The `<=1` short-circuit leaves them untouched. |
