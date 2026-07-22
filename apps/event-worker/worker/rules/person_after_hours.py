"""Rule 1: person detected while school is closed."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from worker.rules.base import MESSAGE_TH_PREFIX, RuleResult
from worker.schedules import is_school_closed


def evaluate_person_after_hours(
    detection: dict[str, Any],
    now: datetime,
    schedule_config: dict[str, Any],
) -> RuleResult | None:
    """
    If Frigate/normalized label is ``person`` and school is closed at ``now``,
    emit ``person_after_hours``.
    """
    label = (detection.get("label") or "").lower()
    if label != "person":
        return None
    if not is_school_closed(now, schedule_config):
        return None

    camera_id = detection.get("camera_id") or detection.get("camera") or "unknown"
    camera_name = detection.get("camera_name") or camera_id
    zones = detection.get("zones") or detection.get("current_zones") or []
    score = float(detection.get("score") or detection.get("confidence") or 0.8)
    started = detection.get("started_at") or now
    detected = detection.get("current_at") or detection.get("detected_at") or now
    track_id = detection.get("track_id")
    track_ids = [str(track_id)] if track_id is not None else []

    zone_hint = zones[0] if zones else (detection.get("zone") or "")
    detail = f"ตรวจพบบุคคลนอกเวลาทำการ ที่กล้อง {camera_name}"
    if zone_hint:
        detail += f" โซน {zone_hint}"

    return RuleResult(
        event_type="person_after_hours",
        severity="high",
        confidence=score,
        camera_id=str(camera_id),
        camera_name=str(camera_name),
        zone=str(zone_hint) if zone_hint else None,
        message_th=f"{MESSAGE_TH_PREFIX} {detail}",
        rule={
            "code": "person_after_hours",
            "name": "บุคคลนอกเวลา",
            "params": {"schedule": "school_closed"},
        },
        objects=[{"label": "person", "count": 1, "track_ids": track_ids}],
        started_at=started if isinstance(started, datetime) else now,
        detected_at=detected if isinstance(detected, datetime) else now,
        ended_at=detection.get("ended_at"),
    )
