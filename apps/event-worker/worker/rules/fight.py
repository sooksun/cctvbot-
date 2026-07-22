"""Rule 9: suspected fight / aggressive multi-person motion."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from worker.rules.base import MESSAGE_TH_PREFIX, RuleResult

DEFAULT_FIGHT_PERSON_MIN = 2
DEFAULT_FIGHT_MOTION_SECONDS = 3.0
# Relative / high motion threshold (norm-units/s); reuses run speed scale.
DEFAULT_FIGHT_SPEED_THRESHOLD = 0.12


def evaluate_possible_fight(
    detection: dict[str, Any],
    now: datetime,
    rules_config: dict[str, Any] | None = None,
) -> RuleResult | None:
    """
    Stateless path: ``nearby_person_count >= 2`` and high relative motion
    for ``high_motion_duration_s`` ≥ fight motion threshold (default 3s).
    """
    cfg = rules_config or {}
    person_min = int(cfg.get("fight_person_min", DEFAULT_FIGHT_PERSON_MIN))
    motion_seconds = float(
        cfg.get("fight_motion_seconds", DEFAULT_FIGHT_MOTION_SECONDS)
    )
    speed_threshold = float(
        cfg.get("fight_speed_threshold", DEFAULT_FIGHT_SPEED_THRESHOLD)
    )

    count = detection.get("nearby_person_count")
    if count is None:
        return None
    try:
        n = int(count)
    except (TypeError, ValueError):
        return None
    if n < person_min:
        return None

    duration = detection.get("high_motion_duration_s")
    if duration is None:
        return None
    try:
        dur_s = float(duration)
    except (TypeError, ValueError):
        return None
    if dur_s < motion_seconds:
        return None

    # Optional speed check when provided
    speed = detection.get("speed")
    if speed is None:
        speed = detection.get("relative_speed")
    if speed is not None:
        try:
            if float(speed) < speed_threshold:
                return None
        except (TypeError, ValueError):
            return None

    return _fight_result(detection, now, n, dur_s, person_min, motion_seconds)


class FightTracker:
    """
    Sequence tracker: ≥2 nearby persons with sustained high motion ≥ 3s
    → ``possible_fight``.
    """

    def __init__(
        self,
        person_min: int = DEFAULT_FIGHT_PERSON_MIN,
        motion_seconds: float = DEFAULT_FIGHT_MOTION_SECONDS,
        speed_threshold: float = DEFAULT_FIGHT_SPEED_THRESHOLD,
    ) -> None:
        self.person_min = person_min
        self.motion_seconds = motion_seconds
        self.speed_threshold = speed_threshold
        # camera_id -> {high_since, last_count}
        self._state: dict[str, dict[str, Any]] = {}
        self._emitted: set[str] = set()

    def reset(self) -> None:
        self._state.clear()
        self._emitted.clear()

    def update(
        self,
        detection: dict[str, Any],
        now: datetime | None = None,
        rules_config: dict[str, Any] | None = None,
    ) -> RuleResult | None:
        cfg = rules_config or {}
        person_min = int(cfg.get("fight_person_min", self.person_min))
        motion_seconds = float(
            cfg.get("fight_motion_seconds", self.motion_seconds)
        )
        speed_threshold = float(
            cfg.get("fight_speed_threshold", self.speed_threshold)
        )

        ts = now or detection.get("current_at") or detection.get("detected_at")
        if not isinstance(ts, datetime):
            return None

        camera_id = str(detection.get("camera_id") or detection.get("camera") or "unknown")
        count = detection.get("nearby_person_count")
        if count is None:
            self._state.pop(camera_id, None)
            return None
        try:
            n = int(count)
        except (TypeError, ValueError):
            return None

        speed = detection.get("speed")
        if speed is None:
            speed = detection.get("relative_speed")
        try:
            speed_val = float(speed) if speed is not None else None
        except (TypeError, ValueError):
            speed_val = None

        high_motion = speed_val is not None and speed_val >= speed_threshold
        # Also accept explicit flag
        if detection.get("high_relative_motion") is True:
            high_motion = True

        if n < person_min or not high_motion:
            self._state.pop(camera_id, None)
            self._emitted.discard(camera_id)
            return None

        state = self._state.get(camera_id)
        if state is None:
            self._state[camera_id] = {
                "high_since": ts,
                "started_at": detection.get("started_at") or ts,
                "max_count": n,
            }
            return None

        state["max_count"] = max(int(state.get("max_count") or 0), n)
        elapsed = (ts - state["high_since"]).total_seconds()
        if elapsed < motion_seconds:
            return None
        if camera_id in self._emitted:
            return None

        self._emitted.add(camera_id)
        det = dict(detection)
        det.setdefault("started_at", state["started_at"])
        det["nearby_person_count"] = state["max_count"]
        return _fight_result(
            det,
            ts,
            int(state["max_count"]),
            elapsed,
            person_min,
            motion_seconds,
        )


def _fight_result(
    detection: dict[str, Any],
    now: datetime,
    person_count: int,
    duration_s: float,
    person_min: int,
    motion_seconds: float,
) -> RuleResult:
    camera_id = str(detection.get("camera_id") or detection.get("camera") or "unknown")
    camera_name = detection.get("camera_name") or camera_id
    zones = detection.get("zones") or detection.get("current_zones") or []
    zone_hint = zones[0] if zones else (detection.get("zone") or None)
    score = float(detection.get("score") or detection.get("confidence") or 0.75)
    started = detection.get("started_at") or now

    return RuleResult(
        event_type="possible_fight",
        severity="high",
        confidence=score,
        camera_id=camera_id,
        camera_name=str(camera_name),
        zone=str(zone_hint) if zone_hint else None,
        message_th=(
            f"{MESSAGE_TH_PREFIX} สงสัยการทะเลาะวิวาท "
            f"({person_count} คน) ที่กล้อง {camera_name}"
        ),
        rule={
            "code": "possible_fight",
            "name": "สงสัยทะเลาะวิวาท",
            "params": {
                "person_min": person_min,
                "motion_seconds": motion_seconds,
                "nearby_person_count": person_count,
                "high_motion_duration_s": duration_s,
            },
        },
        objects=[{"label": "person", "count": person_count, "track_ids": []}],
        started_at=started if isinstance(started, datetime) else now,
        detected_at=now,
        ended_at=detection.get("ended_at"),
        params={
            "nearby_person_count": person_count,
            "high_motion_duration_s": duration_s,
        },
    )
