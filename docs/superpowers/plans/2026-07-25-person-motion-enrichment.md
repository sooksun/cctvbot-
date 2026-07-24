# Person-Motion Enrichment (Rules 7 + 9) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compute `speed`, `nearby_person_count`, and `high_motion_duration_s` in the event-worker from the Frigate MQTT person-track stream so `abnormal_motion`, `abnormal_crowd`, and `possible_fight` fire in production.

**Architecture:** A new `PersonMotionEnricher` keeps bounded per-`(camera_id, track_id)` state and, on each person detection, mutates the detection dict with the three fields the existing rules already read. It is wired into `EventPipeline.handle_frigate_event` and gated by a new `person_motion_enrichment` flag; the existing `enrichment_available` flag now gates only rule 8 (littering).

**Tech Stack:** Python 3.11, pytest 9.1.1, stdlib only (`dataclasses`, `datetime`). No new dependencies.

## Global Constraints

- Do NOT change any rule logic in `worker/rules/*`. Only populate detection fields the rules already read: `speed: float`, `high_motion_duration_s: float`, `nearby_person_count: int`.
- Enricher space is normalized: box is `[x1, y1, x2, y2]` in 0–1 (same convention as `worker/rules/person_fall.py`).
- New config keys + defaults (exact): `person_motion_enrichment: true`, `speed_ema_alpha: 0.5`, `nearby_window_seconds: 3.0`, `motion_track_ttl_seconds: 60.0`. `enrichment_available` stays `false` and now gates only littering.
- The enricher uses `fight_speed_threshold` (0.12) as the "fast" cutoff for `high_motion_duration_s`.
- Per-track state MUST be evicted after `motion_track_ttl_seconds` of no updates (bounded memory).
- Run all worker commands from `apps/event-worker/` using the venv interpreter: `./.venv/Scripts/python.exe -m pytest`.
- Existing suites must stay green: API 38, worker 76 (before new tests).

---

### Task 1: PersonMotionEnricher module

**Files:**
- Create: `apps/event-worker/worker/enrichment.py`
- Test: `apps/event-worker/tests/test_enrichment.py`

**Interfaces:**
- Produces:
  - `PersonMotionEnricher(*, speed_ema_alpha=0.5, nearby_window_seconds=3.0, track_ttl_seconds=60.0, high_motion_speed=0.12)`
  - `.enrich(detection: dict, now: datetime) -> dict` — mutates & returns detection; sets `speed`, `high_motion_duration_s`, `nearby_person_count` for `label == "person"`; no-op for other labels.
  - `.observe_end(detection: dict, now: datetime) -> None` — removes the `(camera_id, track_id)` track.
  - `.reset() -> None` — clears state (tests).

- [ ] **Step 1: Write the failing tests**

Create `apps/event-worker/tests/test_enrichment.py`:

```python
"""Unit tests for PersonMotionEnricher (rules 7 + 9 enrichment)."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from worker.enrichment import PersonMotionEnricher

TZ = ZoneInfo("Asia/Bangkok")
T0 = datetime(2026, 7, 25, 12, 0, 0, tzinfo=TZ)


def _person(track_id, box, camera_id="cam-yard"):
    return {"label": "person", "camera_id": camera_id, "track_id": track_id, "box": box}


def test_speed_zero_on_first_observation():
    enr = PersonMotionEnricher()
    d = _person("t1", [0.2, 0.2, 0.3, 0.4])
    enr.enrich(d, T0)
    assert d["speed"] == 0.0
    assert d["high_motion_duration_s"] == 0.0
    assert d["nearby_person_count"] == 1


def test_speed_computed_on_second_observation():
    enr = PersonMotionEnricher(speed_ema_alpha=0.5)
    enr.enrich(_person("t1", [0.2, 0.2, 0.3, 0.4]), T0)  # centroid x=0.25
    d2 = _person("t1", [0.5, 0.2, 0.6, 0.4])              # centroid x=0.55, moved 0.3
    enr.enrich(d2, T0 + timedelta(seconds=1))             # inst=0.3, ema=0.5*0.3=0.15
    assert abs(d2["speed"] - 0.15) < 1e-9


def test_high_motion_duration_accumulates_then_resets():
    enr = PersonMotionEnricher(speed_ema_alpha=1.0, high_motion_speed=0.12)
    enr.enrich(_person("t1", [0.2, 0.2, 0.3, 0.5]), T0)               # first obs, speed 0
    d1 = _person("t1", [0.5, 0.2, 0.6, 0.5])
    enr.enrich(d1, T0 + timedelta(seconds=1))                        # inst 0.3, high_since=t1
    assert d1["high_motion_duration_s"] == 0.0
    d2 = _person("t1", [0.2, 0.2, 0.3, 0.5])
    enr.enrich(d2, T0 + timedelta(seconds=3))                        # still fast, dur=3-1=2
    assert d2["high_motion_duration_s"] == 2.0
    d3 = _person("t1", [0.21, 0.2, 0.31, 0.5])                       # barely moves → slow
    enr.enrich(d3, T0 + timedelta(seconds=4))
    assert d3["high_motion_duration_s"] == 0.0


def test_nearby_counts_concurrent_persons():
    enr = PersonMotionEnricher(nearby_window_seconds=3.0)
    enr.enrich(_person("p1", [0.1, 0.1, 0.2, 0.2]), T0)
    d2 = _person("p2", [0.5, 0.5, 0.6, 0.6])
    enr.enrich(d2, T0 + timedelta(seconds=1))
    assert d2["nearby_person_count"] == 2


def test_end_event_decrements_nearby():
    enr = PersonMotionEnricher(nearby_window_seconds=10.0)
    enr.enrich(_person("p1", [0.1, 0.1, 0.2, 0.2]), T0)
    enr.enrich(_person("p2", [0.5, 0.5, 0.6, 0.6]), T0 + timedelta(seconds=1))
    enr.observe_end({"camera_id": "cam-yard", "track_id": "p2"}, T0 + timedelta(seconds=2))
    d = _person("p1", [0.1, 0.1, 0.2, 0.2])
    enr.enrich(d, T0 + timedelta(seconds=3))
    assert d["nearby_person_count"] == 1


def test_ttl_evicts_idle_tracks():
    enr = PersonMotionEnricher(track_ttl_seconds=60.0, nearby_window_seconds=300.0)
    enr.enrich(_person("p1", [0.1, 0.1, 0.2, 0.2]), T0)
    d = _person("p2", [0.5, 0.5, 0.6, 0.6])
    enr.enrich(d, T0 + timedelta(seconds=120))  # p1 idle > ttl → evicted
    assert d["nearby_person_count"] == 1
    assert len(enr._tracks) == 1


def test_non_person_is_noop():
    enr = PersonMotionEnricher()
    d = {"label": "bottle", "camera_id": "cam-yard", "track_id": "b1", "box": [0, 0, 1, 1]}
    enr.enrich(d, T0)
    assert "speed" not in d
    assert "nearby_person_count" not in d
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd apps/event-worker && ./.venv/Scripts/python.exe -m pytest tests/test_enrichment.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'worker.enrichment'`.

- [ ] **Step 3: Write the implementation**

Create `apps/event-worker/worker/enrichment.py`:

```python
"""Person-motion enrichment: derive speed / nearby_person_count /
high_motion_duration_s from Frigate MQTT person tracks (rules 7 + 9).

Heuristic, normalized-frame space (box = [x1, y1, x2, y2] in 0-1). No ML,
no camera calibration. State per (camera_id, track_id) is TTL-evicted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

DEFAULT_SPEED_EMA_ALPHA = 0.5
DEFAULT_NEARBY_WINDOW_SECONDS = 3.0
DEFAULT_TRACK_TTL_SECONDS = 60.0
# high_motion_duration uses the fight speed threshold as the "fast" cutoff.
DEFAULT_HIGH_MOTION_SPEED = 0.12


@dataclass
class _TrackState:
    last_centroid: tuple[float, float] | None
    last_ts: datetime
    last_seen: datetime
    ema_speed: float = 0.0
    high_since: datetime | None = None


def _centroid(box: Any) -> tuple[float, float] | None:
    if not box or len(box) < 4:
        return None
    try:
        x1, y1, x2, y2 = float(box[0]), float(box[1]), float(box[2]), float(box[3])
    except (TypeError, ValueError, IndexError):
        return None
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


class PersonMotionEnricher:
    def __init__(
        self,
        *,
        speed_ema_alpha: float = DEFAULT_SPEED_EMA_ALPHA,
        nearby_window_seconds: float = DEFAULT_NEARBY_WINDOW_SECONDS,
        track_ttl_seconds: float = DEFAULT_TRACK_TTL_SECONDS,
        high_motion_speed: float = DEFAULT_HIGH_MOTION_SPEED,
    ) -> None:
        self.alpha = speed_ema_alpha
        self.nearby_window = nearby_window_seconds
        self.ttl = track_ttl_seconds
        self.high_motion_speed = high_motion_speed
        self._tracks: dict[tuple[str, str], _TrackState] = {}

    def reset(self) -> None:
        self._tracks.clear()

    def _evict(self, now: datetime) -> None:
        cutoff = now - timedelta(seconds=self.ttl)
        for key in [k for k, st in self._tracks.items() if st.last_seen < cutoff]:
            self._tracks.pop(key, None)

    def _key(self, detection: dict[str, Any]) -> tuple[str, str] | None:
        cam = detection.get("camera_id")
        tid = detection.get("track_id")
        if cam is None or tid is None:
            return None
        return (str(cam), str(tid))

    def _nearby(self, camera_id: str, now: datetime) -> int:
        cutoff = now - timedelta(seconds=self.nearby_window)
        return sum(
            1
            for (cam, _tid), st in self._tracks.items()
            if cam == camera_id and st.last_seen >= cutoff
        )

    def enrich(self, detection: dict[str, Any], now: datetime) -> dict[str, Any]:
        if (detection.get("label") or "").lower() != "person":
            return detection
        self._evict(now)
        key = self._key(detection)
        if key is None:
            return detection

        centroid = _centroid(detection.get("box"))
        state = self._tracks.get(key)
        if state is None:
            self._tracks[key] = _TrackState(
                last_centroid=centroid, last_ts=now, last_seen=now
            )
            detection["speed"] = 0.0
            detection["high_motion_duration_s"] = 0.0
        else:
            dt = (now - state.last_ts).total_seconds()
            if centroid is not None and state.last_centroid is not None and dt > 0:
                dx = centroid[0] - state.last_centroid[0]
                dy = centroid[1] - state.last_centroid[1]
                inst = (dx * dx + dy * dy) ** 0.5 / dt
                state.ema_speed = self.alpha * inst + (1.0 - self.alpha) * state.ema_speed
                state.last_centroid = centroid
                state.last_ts = now
            if state.ema_speed >= self.high_motion_speed:
                if state.high_since is None:
                    state.high_since = now
                duration = (now - state.high_since).total_seconds()
            else:
                state.high_since = None
                duration = 0.0
            state.last_seen = now
            detection["speed"] = state.ema_speed
            detection["high_motion_duration_s"] = duration

        detection["nearby_person_count"] = self._nearby(key[0], now)
        return detection

    def observe_end(self, detection: dict[str, Any], now: datetime) -> None:
        key = self._key(detection)
        if key is not None:
            self._tracks.pop(key, None)
        self._evict(now)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd apps/event-worker && ./.venv/Scripts/python.exe -m pytest tests/test_enrichment.py -q`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add apps/event-worker/worker/enrichment.py apps/event-worker/tests/test_enrichment.py
git commit -m "feat(worker): person-motion enricher for rules 7 + 9"
```

---

### Task 2: Wire enricher into EventPipeline + gate split

**Files:**
- Modify: `apps/event-worker/worker/mqtt_consumer.py` (imports, `EventPipeline.__init__`, `handle_frigate_event`)
- Modify: `apps/event-worker/worker/main.py` (`DEFAULT_RULES`)
- Modify: `apps/event-worker/tests/test_pipeline_gating.py` (rewrite for new gate + real sequences)

**Interfaces:**
- Consumes: `PersonMotionEnricher` from Task 1.
- Produces: `EventPipeline(..., motion_enricher: PersonMotionEnricher | None = None)`; new attribute `self.person_motion_enrichment: bool`; `self.motion_enricher: PersonMotionEnricher`.

- [ ] **Step 1: Rewrite the gating tests (failing)**

Replace the entire contents of `apps/event-worker/tests/test_pipeline_gating.py`:

```python
"""Rules 7/9 gate + person-motion enrichment firing through the pipeline."""

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from worker.api_client import ApiClient
from worker.debounce import Debouncer
from worker.mqtt_consumer import EventPipeline

TZ = ZoneInfo("Asia/Bangkok")
T0 = datetime(2026, 7, 25, 12, 0, 0, tzinfo=TZ)  # Saturday-safe; school open below

# School always open so person_after_hours never fires and isolates rules 7/9.
_SCHEDULE = {"timezone": "Asia/Bangkok", "school_closed": {"weekdays": [], "weekends": []}}


def _pipeline(tmp_path, motion_on, posted, clock):
    def handler(request: httpx.Request) -> httpx.Response:
        posted.append(json.loads(request.content.decode())["event_type"])
        return httpx.Response(201, json={"ok": True})

    api = ApiClient(
        base_url="http://api:8000",
        system_token="t",
        transport=httpx.MockTransport(handler),
    )
    return EventPipeline(
        evidence_root=tmp_path,
        api_client=api,
        debouncer=Debouncer(window_seconds=0),
        schedule_config=_SCHEDULE,
        rules_config={
            "person_motion_enrichment": motion_on,
            "enrichment_available": False,
            "run_speed_threshold": 0.15,
            "crowd_threshold": 5,
            "fight_person_min": 2,
            "fight_motion_seconds": 3.0,
            "fight_speed_threshold": 0.12,
            "speed_ema_alpha": 0.5,
            "nearby_window_seconds": 5.0,
            "motion_track_ttl_seconds": 60.0,
        },
        now_fn=lambda: clock["t"],
    )


def _person_msg(track_id, box, camera="cam-yard"):
    return {
        "type": "update",
        "after": {
            "camera": camera,
            "label": "person",
            "id": track_id,
            "top_score": 0.9,
            "start_time": T0.timestamp(),
            "box": box,
        },
    }


def test_abnormal_motion_fires_when_enrichment_on(tmp_path):
    posted, clock = [], {"t": T0}
    p = _pipeline(tmp_path, True, posted, clock)
    p.handle_frigate_event(_person_msg("p1", [0.1, 0.2, 0.2, 0.5]))
    clock["t"] = T0 + timedelta(seconds=1)
    p.handle_frigate_event(_person_msg("p1", [0.6, 0.2, 0.7, 0.5]))  # moved 0.5 → ema 0.25>0.15
    assert "abnormal_motion" in posted


def test_abnormal_crowd_fires_with_five_persons(tmp_path):
    posted, clock = [], {"t": T0}
    p = _pipeline(tmp_path, True, posted, clock)
    for i in range(5):
        clock["t"] = T0 + timedelta(seconds=i * 0.1)
        p.handle_frigate_event(_person_msg(f"p{i}", [0.1, 0.1, 0.2, 0.2]))
    assert "abnormal_crowd" in posted


def test_possible_fight_fires(tmp_path):
    posted, clock = [], {"t": T0}
    p = _pipeline(tmp_path, True, posted, clock)

    def step(dt, tid, box):
        clock["t"] = T0 + timedelta(seconds=dt)
        p.handle_frigate_event(_person_msg(tid, box))

    step(0, "p1", [0.2, 0.2, 0.3, 0.5])   # p1 seed
    step(0, "p2", [0.6, 0.6, 0.7, 0.9])   # second person → nearby 2
    step(1, "p1", [0.5, 0.2, 0.6, 0.5])   # moved 0.3 → ema 0.15, high_since=t1
    step(2, "p1", [0.2, 0.2, 0.3, 0.5])   # ema 0.225
    step(3, "p1", [0.5, 0.2, 0.6, 0.5])   # dur=2 (<3)
    step(4, "p1", [0.2, 0.2, 0.3, 0.5])   # dur=3 → fight fires (nearby p1,p2 in 5s window)
    assert "possible_fight" in posted


def test_rules_79_gated_off(tmp_path):
    posted, clock = [], {"t": T0}
    p = _pipeline(tmp_path, False, posted, clock)
    p.handle_frigate_event(_person_msg("p1", [0.1, 0.2, 0.2, 0.5]))
    clock["t"] = T0 + timedelta(seconds=1)
    p.handle_frigate_event(_person_msg("p1", [0.6, 0.2, 0.7, 0.5]))
    assert "abnormal_motion" not in posted
    assert "abnormal_crowd" not in posted


def test_littering_stays_gated_by_enrichment_available(tmp_path):
    # person_motion on, but enrichment_available False → littering must not fire.
    posted, clock = [], {"t": T0}
    p = _pipeline(tmp_path, True, posted, clock)
    p.handle_frigate_event(_person_msg("p1", [0.1, 0.2, 0.2, 0.5]))
    assert "possible_littering" not in posted
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd apps/event-worker && ./.venv/Scripts/python.exe -m pytest tests/test_pipeline_gating.py -q`
Expected: FAIL — `EventPipeline` has no `person_motion_enrichment` handling; rules 7/9 do not fire from sequences (they read unset `speed`/`nearby_person_count`).

- [ ] **Step 3: Add the import and constructor wiring in `mqtt_consumer.py`**

Add to the imports block (near the other `worker.rules` imports):

```python
from worker.enrichment import PersonMotionEnricher
```

In `EventPipeline.__init__`, add a `motion_enricher` parameter (after `fight_tracker`):

```python
        fight_tracker: FightTracker | None = None,
        motion_enricher: PersonMotionEnricher | None = None,
```

Replace the existing enrichment-gate block:

```python
        self.enrichment_available = bool(
            rules_config.get("enrichment_available", False)
        )
        if not self.enrichment_available:
            logger.info(
                "enrichment_available=false — abnormal_motion/abnormal_crowd/"
                "possible_littering/possible_fight are gated off until an "
                "enrichment layer feeds speed/nearby_person_count/multi-object."
            )
```

with:

```python
        # Rule 8 littering still needs object-drop enrichment (not built yet).
        self.enrichment_available = bool(
            rules_config.get("enrichment_available", False)
        )
        # Rules 7 (motion/crowd) + 9 (fight) are fed by the person-motion enricher.
        self.person_motion_enrichment = bool(
            rules_config.get("person_motion_enrichment", False)
        )
        self.motion_enricher = motion_enricher or PersonMotionEnricher(
            speed_ema_alpha=float(rules_config.get("speed_ema_alpha", 0.5)),
            nearby_window_seconds=float(
                rules_config.get("nearby_window_seconds", 3.0)
            ),
            track_ttl_seconds=float(
                rules_config.get("motion_track_ttl_seconds", 60.0)
            ),
            high_motion_speed=float(rules_config.get("fight_speed_threshold", 0.12)),
        )
        if not self.person_motion_enrichment:
            logger.info(
                "person_motion_enrichment=false — abnormal_motion/abnormal_crowd/"
                "possible_fight gated off; enrichment_available=%s gates littering.",
                self.enrichment_available,
            )
```

- [ ] **Step 4: Replace the rule-dispatch block in `handle_frigate_event`**

Replace the existing `if self.enrichment_available:` block (rules 7/8/9) inside the `if detection.get("label") and frigate_type != "end":` branch with:

```python
            # Rules 7 + 9 — fed by person-motion enrichment.
            if self.person_motion_enrichment:
                self.motion_enricher.enrich(detection, now)
                motion = evaluate_abnormal_motion(detection, now, self.rules_config)
                if motion is not None:
                    results.append(motion)
                crowd = evaluate_abnormal_crowd(detection, now, self.rules_config)
                if crowd is not None:
                    results.append(crowd)
                fight = evaluate_possible_fight(detection, now, self.rules_config)
                if fight is None:
                    fight = self.fight_tracker.update(detection, now, self.rules_config)
                if fight is not None:
                    results.append(fight)

            # Rule 8 — littering (object-drop enrichment; still gated separately).
            if self.enrichment_available:
                litter = evaluate_possible_littering(detection, now, self.rules_config)
                if litter is None:
                    litter = self.littering_tracker.update(
                        detection, now, self.rules_config
                    )
                if litter is not None:
                    results.append(litter)
```

Then, immediately after that `if detection.get("label") and frigate_type != "end":` block closes, add an `elif` to feed track ends to the enricher:

```python
        elif (
            frigate_type == "end"
            and detection.get("label")
            and self.person_motion_enrichment
        ):
            self.motion_enricher.observe_end(detection, now)
```

- [ ] **Step 5: Add the new keys to `DEFAULT_RULES` in `main.py`**

In `worker/main.py`, in the `DEFAULT_RULES` dict, replace the `enrichment_available` line and the Rule 7 block header so the block reads:

```python
    # Rules 8/9 littering/object metrics need enrichment Frigate MQTT lacks.
    "enrichment_available": False,
    # Rules 7 + 9 person-motion enrichment (computed in-worker).
    "person_motion_enrichment": True,
    "speed_ema_alpha": 0.5,
    "nearby_window_seconds": 3.0,
    "motion_track_ttl_seconds": 60.0,
    "offline_threshold_seconds": 30,
```

(Keep every other key in `DEFAULT_RULES` unchanged — only add the four new keys and adjust the two comment lines.)

- [ ] **Step 6: Run the pipeline tests and the full worker suite**

Run: `cd apps/event-worker && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS — 76 existing + 7 enrichment + 5 pipeline gating = all green.

- [ ] **Step 7: Commit**

```bash
git add apps/event-worker/worker/mqtt_consumer.py apps/event-worker/worker/main.py apps/event-worker/tests/test_pipeline_gating.py
git commit -m "feat(worker): enable rules 7+9 via person-motion enrichment; split gate"
```

---

### Task 3: Config, docs, and full verification

**Files:**
- Modify: `data/config/rules.yml`
- Modify: `DEPLOY.md` (Frigate & rules section note)

**Interfaces:**
- Consumes: config keys read by `EventPipeline` in Task 2.

- [ ] **Step 1: Update `data/config/rules.yml`**

Replace the Rule 7 block and the enrichment-gate comment at the bottom. The Rule 7 section becomes:

```yaml
# Rule 7 — abnormal motion / crowd (fed by in-worker person-motion enrichment)
run_speed_threshold: 0.15
crowd_threshold: 5

# Person-motion enrichment (rules 7 + 9): heuristic speed / nearby count / high-motion
person_motion_enrichment: true
speed_ema_alpha: 0.5
nearby_window_seconds: 3.0
motion_track_ttl_seconds: 60.0
```

And change the bottom `enrichment_available` comment block to:

```yaml
# Enrichment gate — Rule 8 littering (possible_littering) still needs object-drop
# metrics (proxy-object centroid drop into litter_watch) that Frigate MQTT does not
# emit. Keep false until the object-drop enrichment layer is built. Rules 7 + 9 no
# longer depend on this flag — see person_motion_enrichment above.
enrichment_available: false
```

- [ ] **Step 2: Add a deploy note in `DEPLOY.md`**

In `DEPLOY.md` section 4 ("ตั้งค่า Frigate + rules"), replace the bullet:

```markdown
- **Rules 7/8/9 (motion/crowd/littering/fight) ถูก gate ปิดไว้** (`enrichment_available: false`) จนกว่าจะมี enrichment layer — ดูหมายเหตุใน `data/config/rules.yml`
```

with:

```markdown
- **Rules 7 + 9 (motion/crowd/fight) เปิดแล้ว** ผ่าน in-worker person-motion enrichment (`person_motion_enrichment: true`). จูน `run_speed_threshold` / `crowd_threshold` / `fight_*` ตามหน้างานเพื่อลด false positive
- **Rule 8 littering ยัง gate ปิด** (`enrichment_available: false`) รอ object-drop enrichment layer
- ⚠️ ก่อน production: ตรวจว่า Frigate MQTT `box` เป็น normalized `[x1,y1,x2,y2]` ตามที่ enricher สมมติ (capture payload จริงมาดู) — ถ้าเป็น pixel ต้อง normalize ด้วย detect width/height
```

- [ ] **Step 3: Run both full suites**

Run: `cd apps/event-worker && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS (88: 76 + 7 + 5).

Run: `cd apps/api && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS (38 — unchanged; sanity that nothing cross-broke).

- [ ] **Step 4: Commit**

```bash
git add data/config/rules.yml DEPLOY.md
git commit -m "docs(config): enable person-motion enrichment defaults + deploy notes"
```

---

## Self-Review

**Spec coverage:**
- §5 architecture (`PersonMotionEnricher`, pipeline wiring, end handling) → Tasks 1, 2. ✓
- §6 algorithms (speed EMA, high_motion_duration, nearby count, end) → Task 1. ✓
- §7 TTL memory → Task 1 (`test_ttl_evicts_idle_tracks`). ✓
- §8 config keys/defaults → Task 2 (DEFAULT_RULES) + Task 3 (rules.yml). ✓
- §9 field contract (`speed`/`high_motion_duration_s`/`nearby_person_count`) → Task 1. ✓
- §10 testing (enrichment unit tests, pipeline fire tests, gating rewrite) → Tasks 1, 2. ✓
- §11 box-format risk note → Task 3 (DEPLOY.md note). ✓
- Gate split (`person_motion_enrichment` vs `enrichment_available`) → Task 2. ✓

**Placeholder scan:** No TBD/TODO; every code step shows full code. ✓

**Type consistency:** `enrich(detection, now)`, `observe_end(detection, now)`, `reset()`, constructor kwargs, and `motion_enricher` param name are identical across Tasks 1–2. Fields `speed`/`high_motion_duration_s`/`nearby_person_count` match what `evaluate_abnormal_motion`/`evaluate_abnormal_crowd`/`evaluate_possible_fight` read. ✓

**Out of scope confirmed:** littering object-drop, Frigate calibration, live-Frigate integration test — none introduced.
