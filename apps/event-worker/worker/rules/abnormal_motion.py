"""Rule 7: abnormal motion (run/sprint) and abnormal crowd density."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from worker.rules.base import MESSAGE_TH_PREFIX, RuleResult

DEFAULT_RUN_SPEED_THRESHOLD = 0.15  # norm-units/s
DEFAULT_CROWD_THRESHOLD = 5


def evaluate_abnormal_motion(
    detection: dict[str, Any],
    now: datetime,
    rules_config: dict[str, Any] | None = None,
) -> RuleResult | None:
    """
    Person track speed > ``run_speed_threshold`` → ``abnormal_motion``.

    ``speed`` is expected in normalized frame units per second (0–1 scale).
    """
    cfg = rules_config or {}
    threshold = float(cfg.get("run_speed_threshold", DEFAULT_RUN_SPEED_THRESHOLD))

    label = (detection.get("label") or "").lower()
    if label != "person":
        return None

    speed = detection.get("speed")
    if speed is None:
        return None
    try:
        speed_val = float(speed)
    except (TypeError, ValueError):
        return None
    if speed_val <= threshold:
        return None

    camera_id = str(detection.get("camera_id") or detection.get("camera") or "unknown")
    camera_name = detection.get("camera_name") or camera_id
    zones = detection.get("zones") or detection.get("current_zones") or []
    zone_hint = zones[0] if zones else (detection.get("zone") or None)
    score = float(detection.get("score") or detection.get("confidence") or 0.8)
    started = detection.get("started_at") or now
    detected = detection.get("current_at") or detection.get("detected_at") or now
    track_id = detection.get("track_id")
    track_ids = [str(track_id)] if track_id is not None else []

    return RuleResult(
        event_type="abnormal_motion",
        severity="medium",
        confidence=score,
        camera_id=camera_id,
        camera_name=str(camera_name),
        zone=str(zone_hint) if zone_hint else None,
        message_th=(
            f"{MESSAGE_TH_PREFIX} ตรวจพบการเคลื่อนที่เร็วผิดปกติ "
            f"ที่กล้อง {camera_name}"
        ),
        rule={
            "code": "abnormal_motion",
            "name": "การเคลื่อนที่ผิดปกติ",
            "params": {
                "run_speed_threshold": threshold,
                "speed": speed_val,
            },
        },
        objects=[{"label": "person", "count": 1, "track_ids": track_ids}],
        started_at=started if isinstance(started, datetime) else now,
        detected_at=detected if isinstance(detected, datetime) else now,
        ended_at=detection.get("ended_at"),
        params={"speed": speed_val, "threshold": threshold},
    )


def evaluate_abnormal_crowd(
    detection: dict[str, Any],
    now: datetime,
    rules_config: dict[str, Any] | None = None,
) -> RuleResult | None:
    """``nearby_person_count >= crowd_threshold`` → ``abnormal_crowd``."""
    cfg = rules_config or {}
    threshold = int(cfg.get("crowd_threshold", DEFAULT_CROWD_THRESHOLD))

    count = detection.get("nearby_person_count")
    if count is None:
        return None
    try:
        n = int(count)
    except (TypeError, ValueError):
        return None
    if n < threshold:
        return None

    # Crowd is scene-level; label may be person or omitted.
    label = (detection.get("label") or "person").lower()
    if label not in ("person", "crowd", ""):
        # still allow when nearby_person_count is set on person detections
        if label != "person":
            return None

    camera_id = str(detection.get("camera_id") or detection.get("camera") or "unknown")
    camera_name = detection.get("camera_name") or camera_id
    zones = detection.get("zones") or detection.get("current_zones") or []
    zone_hint = zones[0] if zones else (detection.get("zone") or None)
    score = float(detection.get("score") or detection.get("confidence") or 0.85)
    started = detection.get("started_at") or now
    detected = detection.get("current_at") or detection.get("detected_at") or now

    return RuleResult(
        event_type="abnormal_crowd",
        severity="medium",
        confidence=score,
        camera_id=camera_id,
        camera_name=str(camera_name),
        zone=str(zone_hint) if zone_hint else None,
        message_th=(
            f"{MESSAGE_TH_PREFIX} ตรวจพบกลุ่มคนหนาแน่น "
            f"({n} คน) ที่กล้อง {camera_name}"
        ),
        rule={
            "code": "abnormal_crowd",
            "name": "กลุ่มคนหนาแน่น",
            "params": {
                "crowd_threshold": threshold,
                "nearby_person_count": n,
            },
        },
        objects=[{"label": "person", "count": n, "track_ids": []}],
        started_at=started if isinstance(started, datetime) else now,
        detected_at=detected if isinstance(detected, datetime) else now,
        ended_at=detection.get("ended_at"),
        params={"nearby_person_count": n, "threshold": threshold},
    )
