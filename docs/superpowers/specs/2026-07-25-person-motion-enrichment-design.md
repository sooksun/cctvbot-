# Person-Motion Enrichment Layer (Rules 7 + 9) — Design Spec

**Date:** 2026-07-25
**Project:** `cctvbot`
**Status:** Approved for implementation planning
**Mode:** Local-first / on-premise; worker-side heuristics (no ML, no camera calibration)

---

## 1. Purpose

Make rules **7** (`abnormal_motion`, `abnormal_crowd`) and **9** (`possible_fight`) fire
in production. They are fully implemented and unit-tested but gated off
(`enrichment_available: false`) because Frigate MQTT does not emit the fields they
consume — `speed`, `nearby_person_count`, `high_motion_duration_s`.

This spec adds a worker-side **person-motion enrichment layer** that derives those
fields from the Frigate MQTT event stream and feeds them to the existing rules. Rule
logic is **not** changed — only the input fields are populated.

## 2. Scope

### In scope
- New `PersonMotionEnricher` in the event-worker.
- Derive `speed`, `high_motion_duration_s`, `nearby_person_count` per detection.
- Wire it into `EventPipeline` and enable rules 7 + 9 behind a dedicated flag.
- Bounded per-track state (TTL eviction).
- Unit tests using synthetic Frigate MQTT sequences.

### Out of scope (explicit)
- Rule 8 `possible_littering` (object-drop enrichment) — separate fast-follow spec.
- Frigate native speed estimation / real-world (m/s) calibration.
- Integration testing against a live Frigate instance or real cameras (no Frigate in
  the dev environment; validation is synthetic-sequence unit tests only).

## 3. Background (current state)

- `EventPipeline.__init__` reads `enrichment_available` (default `false`) and gates the
  rules-7/8/9 block in `handle_frigate_event`.
- `normalize_frigate_event` already extracts `box`, `current_zones`, `track_id`
  (`after.id`), `label`, `frigate_type`, timestamps. Rules read normalized box as
  `[x1, y1, x2, y2]` in the 0–1 range (see `person_fall.box_aspect_ratio`).
- Thresholds in `data/config/rules.yml` are expressed in **normalized frame units per
  second** (`run_speed_threshold: 0.15`, `fight_speed_threshold: 0.12`), confirming the
  original intent was heuristic normalized speed — matching this design.
- Frigate (`frigate/config.yml`) tracks `person` plus littering proxies; `person`
  filter `min_score: 0.5`, `threshold: 0.7`.

## 4. Data-source decision

**Worker heuristic** (chosen over Frigate calibration / hybrid):
- No per-camera survey/calibration — works on any camera on day one.
- Matches the existing normalized thresholds; no threshold rework.
- Accuracy is heuristic; acceptable because rules 7/9 are **review-first** (human
  confirms) and thresholds are tunable + debounced (60s).

## 5. Architecture

New module `apps/event-worker/worker/enrichment.py`:

```
class PersonMotionEnricher:
    def enrich(self, detection: dict, now: datetime) -> dict   # non-end person events
    def observe_end(self, detection: dict, now: datetime) -> None  # 'end' events
    def reset(self) -> None                                    # test helper
```

State: `self._tracks: dict[(camera_id, track_id) -> TrackState]` where
`TrackState = {last_centroid, last_ts, ema_speed, high_since, last_seen}`.

Integration in `EventPipeline.handle_frigate_event`:
1. `detection = normalize_frigate_event(...)`.
2. Tamper check (unchanged).
3. If `label` present and `frigate_type != "end"`:
   - If `person_motion_enrichment`: `self.enricher.enrich(detection, now)` (mutates
     `detection` in place, adding the three fields).
   - Run existing rules: after-hours, restricted, fall (unchanged).
   - If `person_motion_enrichment`: run `evaluate_abnormal_motion`,
     `evaluate_abnormal_crowd`, `evaluate_possible_fight` (+ `FightTracker` fallback).
   - Littering (rule 8) stays gated by `enrichment_available` (unchanged; still off).
4. Else if `frigate_type == "end"` and `label`: if `person_motion_enrichment`,
   `self.enricher.observe_end(detection, now)` so the person leaves the active count.

The enricher only handles `label == "person"` detections; non-person events pass through
untouched.

## 6. Algorithms (normalized space)

Centroid from normalized box `[x1, y1, x2, y2]`:
`centroid = ((x1 + x2) / 2, (y1 + y2) / 2)`. If box is missing/invalid, skip speed
update but still allow the nearby count (below).

### 6.1 speed (EMA-smoothed)
On each person update for a known track:
- `dt = (now - last_ts).total_seconds()`; if `dt <= 0`, keep previous state, skip.
- `inst = euclidean(centroid - last_centroid) / dt`.
- `ema_speed = alpha * inst + (1 - alpha) * prev_ema` with `alpha = speed_ema_alpha`.
- First observation of a track (no prior): `ema_speed = 0.0`, store centroid/ts.
- Set `detection["speed"] = ema_speed`.

### 6.2 high_motion_duration_s
Using `threshold = fight_speed_threshold`:
- If `ema_speed >= threshold`: if `high_since is None` set `high_since = now`;
  `duration = (now - high_since).total_seconds()`.
- Else: `high_since = None`, `duration = 0.0`.
- Set `detection["high_motion_duration_s"] = duration`.

### 6.3 nearby_person_count
After updating this track's `last_seen = now`, count tracks on the same camera whose
`last_seen` is within `nearby_window_seconds` (includes the current track). Set
`detection["nearby_person_count"] = count`. Crowd fires at `>= crowd_threshold` (5);
fight requires `>= fight_person_min` (2).

### 6.4 end handling
`observe_end` sets the track's `last_seen` far in the past / removes it so it no longer
contributes to `nearby_person_count`.

## 7. State & memory (mandatory)

On every `enrich`/`observe_end`, evict tracks whose `last_seen` is older than
`motion_track_ttl_seconds`. This bounds memory to the count of recently-active tracks
per camera, consistent with the existing `FallTracker`/`LitteringTracker` TTL pattern.

## 8. Configuration

`data/config/rules.yml` and `worker/main.py` `DEFAULT_RULES`:

| Key | Default | Meaning |
|-----|---------|---------|
| `person_motion_enrichment` | `true` | Enable enricher + rules 7 (motion/crowd) + 9 (fight). NEW. |
| `speed_ema_alpha` | `0.5` | EMA smoothing factor for per-track speed. NEW. |
| `nearby_window_seconds` | `3.0` | Window for counting concurrent persons. NEW. |
| `motion_track_ttl_seconds` | `60.0` | Evict idle track state. NEW. |
| `enrichment_available` | `false` | Now gates **only** rule 8 littering (fast-follow). REPURPOSED. |

Existing thresholds unchanged: `run_speed_threshold 0.15`, `crowd_threshold 5`,
`fight_person_min 2`, `fight_motion_seconds 3.0`, `fight_speed_threshold 0.12`.

## 9. Detection-field contract

The enricher adds exactly these keys (matching what rules already read):
`speed: float`, `high_motion_duration_s: float`, `nearby_person_count: int`.
No other keys are added or modified.

## 10. Testing strategy (validation bar for this iteration)

No live Frigate is available; validation is synthetic-sequence unit tests.

New `tests/test_enrichment.py`:
- speed computed from centroid movement across two updates; `0.0` on first observation.
- `high_motion_duration_s` accumulates while fast, resets when slow.
- `nearby_person_count` counts concurrent tracks; `end` event decrements it.
- TTL evicts idle tracks (memory bound).

Pipeline tests (new cases or extend existing):
- `abnormal_motion` fires when a person's smoothed speed exceeds `run_speed_threshold`.
- `abnormal_crowd` fires at 5 concurrent persons.
- `possible_fight` fires with 2 persons + sustained high motion ≥ `fight_motion_seconds`.

Update `tests/test_pipeline_gating.py`:
- With `person_motion_enrichment: false` → rules 7/9 do NOT fire.
- With `person_motion_enrichment: true` → rules 7/9 fire on qualifying sequences.
- Littering stays off while `enrichment_available: false`.

All existing API (38) and worker (76) tests must still pass.

## 11. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Frigate `box` may be pixel `[x,y,w,h]`, not normalized `[x1,y1,x2,y2]` | Enricher assumes normalized `[x1,y1,x2,y2]` (consistent with existing rules); **verify against a captured real Frigate payload before production** — logged as a follow-up. If pixel, normalize by detect width/height. |
| Heuristic speed noise → false positives | EMA smoothing + review-first workflow + 60s debounce + tunable thresholds. |
| Sparse MQTT updates (low fps) inflate/deflate speed | `dt`-based normalization; EMA dampening; thresholds tuned during pilot. |
| Track state growth | `motion_track_ttl_seconds` eviction on every call. |

## 12. Success criteria

- Feeding a synthetic Frigate MQTT sequence through `EventPipeline` produces
  `abnormal_motion`, `abnormal_crowd`, and `possible_fight` events (API row + evidence)
  when thresholds are crossed, and none when they are not.
- `person_motion_enrichment` toggles rules 7/9 on/off.
- Track-state memory stays bounded (TTL test passes).
- Full suites green: API 38, worker 76 + new enrichment tests.

## 13. Follow-ups (not in this spec)

- Rule 8 `possible_littering` object-drop enrichment (own spec).
- Verify Frigate `box` coordinate format against a real payload; add pixel→normalized
  handling if needed.
- Pilot threshold tuning once real cameras stream.
