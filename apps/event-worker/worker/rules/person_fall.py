"""Rule 2: person fallen / lying still beyond threshold."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from worker.rules.base import MESSAGE_TH_PREFIX, RuleResult

DEFAULT_ASPECT_THRESHOLD = 1.2
DEFAULT_STILL_SECONDS = 15.0
# Max centroid displacement (norm units) to count as "still".
DEFAULT_MOVE_THRESHOLD = 0.02


def box_aspect_ratio(box: list[float] | None) -> float | None:
    """width/height from [x1,y1,x2,y2] normalized box; None if invalid."""
    if not box or len(box) < 4:
        return None
    try:
        x1, y1, x2, y2 = (float(box[0]), float(box[1]), float(box[2]), float(box[3]))
    except (TypeError, ValueError, IndexError):
        return None
    w = abs(x2 - x1)
    h = abs(y2 - y1)
    if h <= 1e-9:
        return None
    return w / h


def box_centroid(box: list[float] | None) -> tuple[float, float] | None:
    if not box or len(box) < 4:
        return None
    try:
        x1, y1, x2, y2 = (float(box[0]), float(box[1]), float(box[2]), float(box[3]))
    except (TypeError, ValueError, IndexError):
        return None
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def _is_horizontal(
    detection: dict[str, Any],
    aspect_threshold: float,
) -> bool:
    if detection.get("pose_fallen") or detection.get("is_fallen"):
        return True
    ratio = detection.get("aspect_ratio")
    if ratio is None:
        ratio = box_aspect_ratio(detection.get("box"))
    if ratio is None:
        return False
    try:
        return float(ratio) > aspect_threshold
    except (TypeError, ValueError):
        return False


def evaluate_person_fall(
    detection: dict[str, Any],
    now: datetime,
    rules_config: dict[str, Any] | None = None,
) -> RuleResult | None:
    """
    Stateless path: emit ``person_fall_or_down`` when label is person,
    box is horizontal (w/h > threshold or pose flag), and
    ``still_duration_s`` (or derived from started_at) >= still threshold.
    """
    cfg = rules_config or {}
    aspect_threshold = float(cfg.get("fall_aspect_threshold", DEFAULT_ASPECT_THRESHOLD))
    still_seconds = float(cfg.get("fall_still_seconds", DEFAULT_STILL_SECONDS))

    label = (detection.get("label") or "").lower()
    if label != "person":
        return None
    if not _is_horizontal(detection, aspect_threshold):
        return None

    still = detection.get("still_duration_s")
    if still is None and detection.get("stationary"):
        started = detection.get("started_at")
        current = detection.get("current_at") or now
        if isinstance(started, datetime) and isinstance(current, datetime):
            still = (current - started).total_seconds()
    if still is None:
        return None
    try:
        still_s = float(still)
    except (TypeError, ValueError):
        return None
    if still_s < still_seconds:
        return None

    return _fall_result(detection, now, still_s, aspect_threshold, still_seconds)


class FallTracker:
    """
    Sequence-based fall detector: horizontal box + low centroid motion for
    ``still_seconds`` continuous time → ``person_fall_or_down``.
    """

    def __init__(
        self,
        still_seconds: float = DEFAULT_STILL_SECONDS,
        aspect_threshold: float = DEFAULT_ASPECT_THRESHOLD,
        move_threshold: float = DEFAULT_MOVE_THRESHOLD,
    ) -> None:
        self.still_seconds = still_seconds
        self.aspect_threshold = aspect_threshold
        self.move_threshold = move_threshold
        # track key -> state
        self._state: dict[str, dict[str, Any]] = {}
        self._emitted: set[str] = set()

    def reset(self) -> None:
        self._state.clear()
        self._emitted.clear()

    def update(
        self,
        detection: dict[str, Any],
        now: datetime | None = None,
    ) -> RuleResult | None:
        label = (detection.get("label") or "").lower()
        if label != "person":
            return None

        ts = now or detection.get("current_at") or detection.get("detected_at")
        if not isinstance(ts, datetime):
            return None

        camera_id = str(detection.get("camera_id") or detection.get("camera") or "unknown")
        track_id = detection.get("track_id")
        key = f"{camera_id}:{track_id}" if track_id is not None else f"{camera_id}:anon"

        horizontal = _is_horizontal(detection, self.aspect_threshold)
        centroid = box_centroid(detection.get("box"))

        if not horizontal or centroid is None:
            self._state.pop(key, None)
            self._emitted.discard(key)
            return None

        prev = self._state.get(key)
        if prev is None:
            self._state[key] = {
                "still_since": ts,
                "last_centroid": centroid,
                "started_at": detection.get("started_at") or ts,
            }
            return None

        last_c = prev["last_centroid"]
        dx = centroid[0] - last_c[0]
        dy = centroid[1] - last_c[1]
        dist = (dx * dx + dy * dy) ** 0.5
        prev["last_centroid"] = centroid

        if dist > self.move_threshold:
            prev["still_since"] = ts
            self._emitted.discard(key)
            return None

        still_for = (ts - prev["still_since"]).total_seconds()
        if still_for < self.still_seconds:
            return None
        if key in self._emitted:
            return None

        self._emitted.add(key)
        det = dict(detection)
        det.setdefault("started_at", prev["started_at"])
        return _fall_result(
            det,
            ts,
            still_for,
            self.aspect_threshold,
            self.still_seconds,
        )


def _fall_result(
    detection: dict[str, Any],
    now: datetime,
    still_s: float,
    aspect_threshold: float,
    still_seconds: float,
) -> RuleResult:
    camera_id = str(detection.get("camera_id") or detection.get("camera") or "unknown")
    camera_name = detection.get("camera_name") or camera_id
    zones = detection.get("zones") or detection.get("current_zones") or []
    zone_hint = zones[0] if zones else (detection.get("zone") or None)
    score = float(detection.get("score") or detection.get("confidence") or 0.8)
    started = detection.get("started_at") or now
    track_id = detection.get("track_id")
    track_ids = [str(track_id)] if track_id is not None else []
    ratio = detection.get("aspect_ratio")
    if ratio is None:
        ratio = box_aspect_ratio(detection.get("box"))

    return RuleResult(
        event_type="person_fall_or_down",
        severity="high",
        confidence=score,
        camera_id=camera_id,
        camera_name=str(camera_name),
        zone=str(zone_hint) if zone_hint else None,
        message_th=(
            f"{MESSAGE_TH_PREFIX} สงสัยบุคคลล้มหรือนอนนิ่ง "
            f"เกิน {int(still_seconds)} วินาที ที่กล้อง {camera_name}"
        ),
        rule={
            "code": "person_fall_or_down",
            "name": "บุคคลล้ม/นอนนิ่ง",
            "params": {
                "still_seconds": still_seconds,
                "aspect_threshold": aspect_threshold,
                "observed_still_s": still_s,
                "aspect_ratio": ratio,
            },
        },
        objects=[{"label": "person", "count": 1, "track_ids": track_ids}],
        started_at=started if isinstance(started, datetime) else now,
        detected_at=now,
        ended_at=detection.get("ended_at"),
        params={"still_duration_s": still_s, "aspect_ratio": ratio},
    )
