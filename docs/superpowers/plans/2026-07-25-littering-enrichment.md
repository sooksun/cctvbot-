# Littering Enrichment (Rule 8) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `possible_littering` fire by injecting camera-level person presence into proxy-object detections and gating the existing `LitteringTracker`, kept off by default (opt-in).

**Architecture:** Add `PersonMotionEnricher.person_present(camera_id, now)`. In `EventPipeline`, keep the person registry fresh whenever motion OR littering enrichment is on, and under the `enrichment_available` gate inject `person_present` before the unchanged littering rule.

**Tech Stack:** Python 3.11, pytest 9.1.1, stdlib only. No new dependencies. No rule-logic changes.

## Global Constraints

- Do NOT modify `worker/rules/littering.py` or any rule logic. Integration is: one new enricher method + pipeline wiring + injecting `detection["person_present"]`.
- Person correlation is camera-level: a person track seen on the same camera within `nearby_window_seconds`.
- `enrichment_available` stays `false` by default (opt-in). `littering_enabled` stays `true`.
- Run worker commands from `apps/event-worker/` via `./.venv/Scripts/python.exe -m pytest`.
- Keep green: API 38, worker 86 (before new tests).

---

### Task 1: `person_present` on PersonMotionEnricher

**Files:**
- Modify: `apps/event-worker/worker/enrichment.py`
- Test: `apps/event-worker/tests/test_enrichment.py`

**Interfaces:**
- Produces: `PersonMotionEnricher.person_present(camera_id: str | None, now: datetime) -> bool`.

- [ ] **Step 1: Write the failing test** — append to `tests/test_enrichment.py`:

```python
def test_person_present_within_window():
    enr = PersonMotionEnricher(nearby_window_seconds=3.0)
    enr.enrich(_person("p1", [0.1, 0.1, 0.2, 0.2], camera_id="cam-a"), T0)
    assert enr.person_present("cam-a", T0 + timedelta(seconds=2)) is True
    assert enr.person_present("cam-a", T0 + timedelta(seconds=5)) is False
    assert enr.person_present("cam-b", T0) is False
    assert enr.person_present(None, T0) is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/event-worker && ./.venv/Scripts/python.exe -m pytest tests/test_enrichment.py::test_person_present_within_window -q`
Expected: FAIL — `AttributeError: 'PersonMotionEnricher' object has no attribute 'person_present'`.

- [ ] **Step 3: Implement** — add this method to `PersonMotionEnricher` (after `_nearby`):

```python
    def person_present(self, camera_id: Any, now: datetime) -> bool:
        if camera_id is None:
            return False
        cutoff = now - timedelta(seconds=self.nearby_window)
        cam = str(camera_id)
        return any(
            c == cam and st.last_seen >= cutoff
            for (c, _tid), st in self._tracks.items()
        )
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd apps/event-worker && ./.venv/Scripts/python.exe -m pytest tests/test_enrichment.py -q`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add apps/event-worker/worker/enrichment.py apps/event-worker/tests/test_enrichment.py
git commit -m "feat(worker): person_present() on enricher for littering correlation"
```

---

### Task 2: Wire littering in the pipeline + config/docs

**Files:**
- Modify: `apps/event-worker/worker/mqtt_consumer.py` (`handle_frigate_event`)
- Modify: `data/config/rules.yml` (gate comment)
- Modify: `DEPLOY.md` (littering note)
- Test: `apps/event-worker/tests/test_pipeline_littering.py` (create)

**Interfaces:**
- Consumes: `PersonMotionEnricher.person_present` (Task 1); existing `evaluate_possible_littering` / `LitteringTracker.update`.

- [ ] **Step 1: Write the failing tests** — create `apps/event-worker/tests/test_pipeline_littering.py`:

```python
"""Rule 8 littering firing through the pipeline (camera-level person presence)."""

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from worker.api_client import ApiClient
from worker.debounce import Debouncer
from worker.mqtt_consumer import EventPipeline

TZ = ZoneInfo("Asia/Bangkok")
T0 = datetime(2026, 7, 25, 12, 0, 0, tzinfo=TZ)
_SCHEDULE = {"timezone": "Asia/Bangkok", "school_closed": {"weekdays": [], "weekends": []}}


def _pipeline(tmp_path, litter_on, posted, clock):
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
            "person_motion_enrichment": False,  # isolate littering
            "enrichment_available": litter_on,
            "littering_enabled": True,
            "litter_zone": "litter_watch",
            "litter_min_seconds": 3.0,
            "litter_max_seconds": 8.0,
            "litter_downward_delta": 0.05,
            "nearby_window_seconds": 5.0,
            "motion_track_ttl_seconds": 300.0,
        },
        now_fn=lambda: clock["t"],
    )


def _person_msg(track_id, box, camera="cam-yard"):
    return {
        "type": "update",
        "after": {"camera": camera, "label": "person", "id": track_id,
                  "top_score": 0.9, "start_time": T0.timestamp(), "box": box},
    }


def _bottle_msg(track_id, box, zones, camera="cam-yard"):
    return {
        "type": "update",
        "after": {"camera": camera, "label": "bottle", "id": track_id,
                  "top_score": 0.8, "start_time": T0.timestamp(), "box": box,
                  "current_zones": zones},
    }


def test_littering_fires_person_then_bottle_drop(tmp_path):
    posted, clock = [], {"t": T0}
    p = _pipeline(tmp_path, True, posted, clock)
    p.handle_frigate_event(_person_msg("pp", [0.4, 0.3, 0.5, 0.7]))          # person present
    p.handle_frigate_event(_bottle_msg("b1", [0.45, 0.38, 0.5, 0.42], ["litter_watch"]))  # cy 0.40
    clock["t"] = T0 + timedelta(seconds=4)
    p.handle_frigate_event(_bottle_msg("b1", [0.45, 0.48, 0.5, 0.52], ["litter_watch"]))  # cy 0.50, dy 0.10
    assert "possible_littering" in posted


def test_littering_no_person_no_fire(tmp_path):
    posted, clock = [], {"t": T0}
    p = _pipeline(tmp_path, True, posted, clock)
    p.handle_frigate_event(_bottle_msg("b1", [0.45, 0.38, 0.5, 0.42], ["litter_watch"]))
    clock["t"] = T0 + timedelta(seconds=4)
    p.handle_frigate_event(_bottle_msg("b1", [0.45, 0.48, 0.5, 0.52], ["litter_watch"]))
    assert "possible_littering" not in posted


def test_littering_gated_off(tmp_path):
    posted, clock = [], {"t": T0}
    p = _pipeline(tmp_path, False, posted, clock)
    p.handle_frigate_event(_person_msg("pp", [0.4, 0.3, 0.5, 0.7]))
    p.handle_frigate_event(_bottle_msg("b1", [0.45, 0.38, 0.5, 0.42], ["litter_watch"]))
    clock["t"] = T0 + timedelta(seconds=4)
    p.handle_frigate_event(_bottle_msg("b1", [0.45, 0.48, 0.5, 0.52], ["litter_watch"]))
    assert "possible_littering" not in posted
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd apps/event-worker && ./.venv/Scripts/python.exe -m pytest tests/test_pipeline_littering.py -q`
Expected: FAIL — `test_littering_fires_person_then_bottle_drop` fails (no `person_present` injected → `person_seen` stays False → no emit). The other two pass.

- [ ] **Step 3: Rewire the enrichment dispatch in `mqtt_consumer.py`**

Replace this block (rules 7/9 + littering + the `elif` end handler):

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

        elif (
            frigate_type == "end"
            and detection.get("label")
            and self.person_motion_enrichment
        ):
            self.motion_enricher.observe_end(detection, now)
```

with:

```python
            # Person registry feeds rules 7/9 and littering's person correlation.
            if self.person_motion_enrichment or self.enrichment_available:
                self.motion_enricher.enrich(detection, now)

            # Rules 7 + 9 — fed by person-motion enrichment.
            if self.person_motion_enrichment:
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

            # Rule 8 — littering (object-drop). Inject camera-level person presence.
            if self.enrichment_available:
                detection["person_present"] = self.motion_enricher.person_present(
                    detection.get("camera_id"), now
                )
                litter = evaluate_possible_littering(detection, now, self.rules_config)
                if litter is None:
                    litter = self.littering_tracker.update(
                        detection, now, self.rules_config
                    )
                if litter is not None:
                    results.append(litter)

        elif (
            frigate_type == "end"
            and detection.get("label")
            and (self.person_motion_enrichment or self.enrichment_available)
        ):
            self.motion_enricher.observe_end(detection, now)
```

- [ ] **Step 4: Run the littering tests and the full worker suite**

Run: `cd apps/event-worker && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS — 86 + 1 (person_present) + 3 (littering pipeline) = 90 green.

- [ ] **Step 5: Update `data/config/rules.yml` gate comment**

Replace:

```yaml
# Enrichment gate — Rule 8 littering (possible_littering) still needs object-drop
# metrics (proxy-object centroid drop into litter_watch) that Frigate MQTT does not
# emit. Keep false until the object-drop enrichment layer is built. Rules 7 + 9 no
# longer depend on this flag — see person_motion_enrichment above.
enrichment_available: false
```

with:

```yaml
# Rule 8 littering gate (opt-in). Object-drop layer is wired: LitteringTracker
# detects a proxy object dropping into litter_watch and the worker injects
# camera-level person presence. Highest false-positive rule — enable PER SITE only
# after redrawing litter_watch and checking rules-7/9 FP. Rules 7 + 9 do not use it.
enrichment_available: false
```

- [ ] **Step 6: Update `DEPLOY.md` littering note**

Replace:

```markdown
- **Rule 8 littering ยัง gate ปิด** (`enrichment_available: false`) รอ object-drop enrichment layer
```

with:

```markdown
- **Rule 8 littering พร้อมแล้ว แต่ opt-in** (`enrichment_available: false` เป็น default) — object-drop layer wired แล้ว (LitteringTracker + camera-level person presence); เปิดต่อกล้องเมื่อพร้อม (FP สูงสุด)
```

- [ ] **Step 7: Verify config + both suites, then commit**

Run: `cd apps/event-worker && ./.venv/Scripts/python.exe -c "import yaml; yaml.safe_load(open(r'D:/laragon/www/cctvbot/data/config/rules.yml',encoding='utf-8')); print('rules.yml OK')"`
Run: `cd apps/event-worker && ./.venv/Scripts/python.exe -m pytest -q`  → 90 passed
Run: `cd apps/api && ./.venv/Scripts/python.exe -m pytest -q`  → 38 passed

```bash
git add apps/event-worker/worker/mqtt_consumer.py apps/event-worker/tests/test_pipeline_littering.py data/config/rules.yml DEPLOY.md
git commit -m "feat(worker): wire rule 8 littering via camera-level person presence (opt-in)"
```

---

## Self-Review

**Spec coverage:** §4 `person_present` → Task 1; pipeline wiring (enrich under either gate, inject person_present, observe_end under either gate) → Task 2 Step 3; §6 config comment → Task 2 Step 5; §7 tests (person_present + littering fires/no-person/gated) → Tasks 1–2. ✓

**Placeholder scan:** No TBD/TODO; full code in every step. ✓

**Type consistency:** `person_present(camera_id, now) -> bool` defined in Task 1, called identically in Task 2. `detection["person_present"]` matches `_has_person`'s `detection.get("person_present") is True`. ✓

**No rule-logic changes:** `worker/rules/littering.py` untouched. ✓
