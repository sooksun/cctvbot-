# Littering Enrichment (Rule 8) — Design Spec

**Date:** 2026-07-25
**Project:** `cctvbot`
**Status:** Approved for implementation planning
**Mode:** Local-first; worker-side heuristic. Fast-follow to person-motion enrichment.

---

## 1. Purpose

Let rule 8 `possible_littering` fire. The object-drop logic already exists in
`LitteringTracker` (tracks a proxy object's centroid drop into `litter_watch` over
3–8s and OR-accumulates person presence across the track). The only gaps are:
person correlation (Frigate sends one object per MQTT message, so a bottle message
carries no person info) and the pipeline gate. This spec closes both, keeping the
rule **off by default** (opt-in per site).

## 2. Scope

### In scope
- Add `PersonMotionEnricher.person_present(camera_id, now) -> bool` (reuses the
  existing per-camera person registry and `nearby_window_seconds`).
- Pipeline: keep the person registry fresh whenever motion OR littering enrichment
  is on; inject `person_present` onto detections before the littering rule; feed
  track ends to the enricher under the same condition.
- Tests: enricher `person_present`; pipeline littering fires / does not fire.

### Out of scope
- Spatial person↔object proximity matching (camera-level only this iteration).
- Any change to `LitteringTracker`/`evaluate_possible_littering` logic.
- Frigate model/config changes (proxy objects bottle/cup/backpack/handbag/umbrella
  are already tracked in `frigate/config.yml`).

## 3. Decisions

- **Person correlation:** camera-level presence — a person track seen on the same
  camera within `nearby_window_seconds`. Matches `LitteringTracker`'s existing
  `person_seen` semantics; the tracker OR-accumulates it across the object window so
  the dropper only needs to be present when the drop begins.
- **Rollout:** opt-in. `enrichment_available` stays `false` by default; ops enables
  per site after drawing `litter_watch` and observing rules-7/9 false-positive rates.

## 4. Architecture

`PersonMotionEnricher` (extend, `apps/event-worker/worker/enrichment.py`):

```
def person_present(self, camera_id: str | None, now: datetime) -> bool
```
Returns True if any tracked person on `camera_id` has `last_seen` within
`nearby_window_seconds`.

`EventPipeline.handle_frigate_event` (modify, `apps/event-worker/worker/mqtt_consumer.py`):
1. For a non-end labelled detection, run `motion_enricher.enrich(detection, now)`
   when `person_motion_enrichment OR enrichment_available` (populates the person
   registry; `enrich` is a no-op for non-person labels).
2. Rules 7/9 block runs only under `person_motion_enrichment` (unchanged).
3. Littering block runs under `enrichment_available`: set
   `detection["person_present"] = motion_enricher.person_present(camera_id, now)`,
   then call `evaluate_possible_littering` / `littering_tracker.update` (unchanged).
4. On `end` events, call `observe_end` when `person_motion_enrichment OR
   enrichment_available`.

## 5. Why no new rule logic

`LitteringTracker.update` already: collects proxy objects, computes centroid_y,
tracks downward delta into `litter_zone` within `[litter_min_seconds,
litter_max_seconds]`, and sets `person_seen = person_seen or _has_person(detection)`.
`_has_person` returns True when `detection["person_present"] is True`. Injecting that
flag is the entire integration.

## 6. Configuration

No new keys. Existing littering knobs stay: `litter_zone` (litter_watch),
`litter_min_seconds` (3.0), `litter_max_seconds` (8.0), `litter_downward_delta`
(0.05), `littering_enabled` (true). `enrichment_available` stays `false`
(opt-in gate); update its comment to describe the wired path.

## 7. Testing (validation bar; no live Frigate)

Enricher unit test:
- `person_present` True within `nearby_window_seconds` of a person observation,
  False after the window passes.

Pipeline tests (synthetic Frigate MQTT sequences):
- `enrichment_available: true` + a person on the camera + a bottle whose centroid
  moves downward into `litter_watch` over ~4s → `possible_littering` fires.
- Same sequence with `enrichment_available: false` → does not fire.
- Bottle drop sequence with no person observed → does not fire (person_seen False).

All existing suites stay green: API 38, worker 86.

## 8. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Camera-level correlation → FP (object falls with no litterer; bystander in frame) | Review-first workflow; opt-in default OFF; `litter_watch` zone limit; 3–8s window; downward-delta threshold; per-site tuning. |
| Frigate may only briefly detect a small dropped object | Runtime/pilot tuning of thresholds; documented as a follow-up, not a code blocker. |
| Person present only at drop start, then leaves | `LitteringTracker` OR-accumulates `person_seen` across the object window. |

## 9. Follow-ups

- Escalate to spatial person↔object proximity if camera-level FP is too high.
- Verify Frigate proxy-object `box`/`current_zones` shape against a real payload
  (shares the box-format follow-up from the person-motion spec).
