# Frigate Box Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Normalize Frigate's pixel `box` to 0–1 at ingest so the enricher and box rules behave correctly.

**Architecture:** A `_normalize_box` helper + a `detect_width`/`detect_height`-aware `normalize_frigate_event`; `EventPipeline` supplies the dims from config. No rule-logic change.

**Tech Stack:** Python 3.11, pytest. event-worker only.

## Global Constraints

- Single ingest fix point (`normalize_frigate_event`); do not touch rule files.
- `<= 1.0` boxes are treated as already-normalized and passed through unchanged (keeps existing tests + is future-proof).
- Order stays `[x1, y1, x2, y2]`.
- Run from `apps/event-worker/` via `./.venv/Scripts/python.exe -m pytest`.
- Keep green: worker 90, API 60 (untouched).

---

### Task 1: Normalize box at ingest

**Files:**
- Modify: `apps/event-worker/worker/mqtt_consumer.py`
- Modify: `apps/event-worker/worker/main.py` (DEFAULT_RULES)
- Modify: `data/config/rules.yml`
- Test: `apps/event-worker/tests/test_mqtt_normalize.py` (create)

- [ ] **Step 1: Write failing tests** — create `apps/event-worker/tests/test_mqtt_normalize.py`:

```python
"""Frigate box is pixels at detect resolution; must normalize to 0-1 at ingest."""

from zoneinfo import ZoneInfo

from worker.mqtt_consumer import _normalize_box, normalize_frigate_event

TZ = ZoneInfo("Asia/Bangkok")


def test_normalize_box_pixels():
    b = _normalize_box([415, 489, 528, 700], 1280, 720)
    assert abs(b[0] - 415 / 1280) < 1e-9
    assert abs(b[1] - 489 / 720) < 1e-9
    assert abs(b[2] - 528 / 1280) < 1e-9
    assert abs(b[3] - 700 / 720) < 1e-9
    assert all(0.0 <= v <= 1.0 for v in b)


def test_normalize_box_already_normalized_untouched():
    b = _normalize_box([0.4, 0.2, 0.55, 0.7], 1280, 720)
    assert b == [0.4, 0.2, 0.55, 0.7]


def test_normalize_box_invalid_passthrough():
    assert _normalize_box(None, 1280, 720) is None
    assert _normalize_box([1, 2], 1280, 720) == [1, 2]


def test_normalize_frigate_event_normalizes_pixel_box():
    msg = {
        "type": "update",
        "after": {
            "camera": "cam-yard",
            "label": "person",
            "id": "t1",
            "top_score": 0.9,
            "box": [415, 489, 528, 700],
        },
    }
    det = normalize_frigate_event(msg, TZ, detect_width=1280, detect_height=720)
    assert det is not None
    assert all(0.0 <= v <= 1.0 for v in det["box"])
    assert abs(det["box"][0] - 415 / 1280) < 1e-9
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd apps/event-worker && ./.venv/Scripts/python.exe -m pytest tests/test_mqtt_normalize.py -q`
Expected: FAIL — `_normalize_box` does not exist / box not normalized.

- [ ] **Step 3: Add `_normalize_box` + wire into `normalize_frigate_event`** (`mqtt_consumer.py`)

Add the helper near the top-level functions (e.g. after `_ts_to_dt`):

```python
def _normalize_box(
    box: list | None, detect_width: float, detect_height: float
) -> list | None:
    """Frigate MQTT box is pixels [x1,y1,x2,y2] at detect resolution → scale to 0-1.
    Boxes already in 0-1 (max coord <= 1) are returned unchanged."""
    if not box or len(box) < 4:
        return box
    try:
        vals = [float(v) for v in box[:4]]
    except (TypeError, ValueError):
        return box
    if max(abs(v) for v in vals) <= 1.0:
        return vals
    w = float(detect_width) or 1.0
    h = float(detect_height) or 1.0
    return [vals[0] / w, vals[1] / h, vals[2] / w, vals[3] / h]
```

Change the signature of `normalize_frigate_event`:

```python
def normalize_frigate_event(
    msg: dict[str, Any],
    tz: ZoneInfo,
    detect_width: float = 1280,
    detect_height: float = 720,
) -> dict[str, Any] | None:
```

Replace the existing box-parse block:

```python
    box = after.get("box") or msg.get("box")
    if box is not None:
        try:
            box = [float(v) for v in box[:4]]
        except (TypeError, ValueError):
            box = None
```

with:

```python
    box = after.get("box") or msg.get("box")
    if box is not None:
        try:
            box = [float(v) for v in box[:4]]
        except (TypeError, ValueError):
            box = None
        else:
            box = _normalize_box(box, detect_width, detect_height)
```

- [ ] **Step 4: Pass detect dims from the pipeline** (`mqtt_consumer.py`, `EventPipeline`)

In `EventPipeline.__init__`, after `self.tz = ZoneInfo(timezone_name)`, add:

```python
        self.detect_width = float(rules_config.get("detect_width", 1280))
        self.detect_height = float(rules_config.get("detect_height", 720))
```

In `handle_frigate_event`, change the call:

```python
        detection = normalize_frigate_event(msg, self.tz)
```
to:
```python
        detection = normalize_frigate_event(
            msg, self.tz, self.detect_width, self.detect_height
        )
```

- [ ] **Step 5: Add config defaults**

`worker/main.py` `DEFAULT_RULES` — add near the person-motion keys:
```python
    "detect_width": 1280,
    "detect_height": 720,
```

`data/config/rules.yml` — add under the person-motion enrichment block:
```yaml
# Frigate detect resolution — used to normalize pixel boxes to 0-1 at ingest.
detect_width: 1280
detect_height: 720
```

- [ ] **Step 6: Run the worker suite**

Run: `cd apps/event-worker && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS — 90 + 4 = 94 green (existing normalized-box tests unaffected).

- [ ] **Step 7: Commit**

```bash
git add apps/event-worker/worker/mqtt_consumer.py apps/event-worker/worker/main.py apps/event-worker/tests/test_mqtt_normalize.py data/config/rules.yml
git commit -m "fix(worker): normalize Frigate pixel box to 0-1 at ingest (rules 7/9 correctness)"
```

---

### Task 2: Pipeline no-false-fire regression + docs

**Files:**
- Test: `apps/event-worker/tests/test_pipeline_gating.py` (append)
- Modify: `DEPLOY.md` (box-format note resolved)

- [ ] **Step 1: Add a pixel-box no-FP pipeline test** — append to `apps/event-worker/tests/test_pipeline_gating.py`:

```python
def test_pixel_box_slow_motion_no_false_fire(tmp_path):
    # Real Frigate sends PIXEL boxes; a person moving ~50px/s on a 1280-wide frame
    # is ~0.04 norm/s — below run_speed_threshold (0.15) → no abnormal_motion.
    posted, clock = [], {"t": T0}
    p = _pipeline(tmp_path, True, posted, clock)
    p.handle_frigate_event(_person_msg("p1", [600, 300, 700, 500]))
    clock["t"] = T0 + timedelta(seconds=1)
    p.handle_frigate_event(_person_msg("p1", [650, 300, 750, 500]))  # +50px in 1s
    assert "abnormal_motion" not in posted
```

- [ ] **Step 2: Run the worker suite**

Run: `cd apps/event-worker && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS — 95 green.

- [ ] **Step 3: DEPLOY.md — mark the box-format item resolved**

Replace the earlier caveat bullet:
```markdown
- ⚠️ ก่อน production: ตรวจว่า Frigate MQTT `box` เป็น normalized `[x1,y1,x2,y2]` ตามที่ enricher สมมติ (capture payload จริงมาดู) — ถ้าเป็น pixel ต้อง normalize ด้วย detect width/height
```
with:
```markdown
- Frigate MQTT `box` เป็น **pixel** — worker normalize → 0-1 ที่ ingest ด้วย `detect_width`/`detect_height` (default 1280×720 ใน `data/config/rules.yml`; ตั้งให้ตรง `frigate/config.yml`). ⚠️ ยังต้องยืนยัน **ลำดับ** box `[x1,y1,x2,y2]` กับ payload Frigate สดตอน pilot
```

- [ ] **Step 4: Commit**

```bash
git add apps/event-worker/tests/test_pipeline_gating.py DEPLOY.md
git commit -m "test(worker): pixel-box no-false-fire regression; docs box-format resolved"
```

---

## Self-Review

**Spec coverage:** §3 approach (`_normalize_box`, signature, `<=1` short-circuit, pipeline dims) → Task 1; §4 config → Task 1 Step 5; §5 testing → Tasks 1–2. ✓

**Placeholder scan:** full code in each step. ✓

**Consistency:** `normalize_frigate_event` default dims (1280/720) match `EventPipeline` defaults and `DEFAULT_RULES`; `_normalize_box` name identical in impl + tests; order `[x1,y1,x2,y2]` unchanged. Existing tests use ≤1 boxes → untouched by the `<=1` short-circuit. ✓
