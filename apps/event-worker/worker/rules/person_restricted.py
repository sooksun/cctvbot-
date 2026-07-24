"""Rule 1: person inside a restricted zone."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from worker.rules.base import MESSAGE_TH_PREFIX, RuleResult


def evaluate_person_restricted(
    detection: dict[str, Any],
    now: datetime,
    rules_config: dict[str, Any],
) -> RuleResult | None:
    """
    If label is ``person`` and current_zones intersects camera restricted_zones,
    emit ``person_restricted_zone``.

    ``rules_config`` expected shape::

        {
          "restricted_zones": {
            "cam-front": ["restricted", "roof"],
            "*": ["server_room"]   # optional default
          }
        }
    """
    label = (detection.get("label") or "").lower()
    if label != "person":
        return None

    camera_id = str(detection.get("camera_id") or detection.get("camera") or "unknown")
    current_zones = set(detection.get("zones") or detection.get("current_zones") or [])
    if not current_zones:
        return None

    restricted_map: dict[str, Any] = rules_config.get("restricted_zones") or {}
    restricted_for_cam = list(restricted_map.get(camera_id) or [])
    restricted_for_cam.extend(restricted_map.get("*") or [])
    restricted_set = {str(z) for z in restricted_for_cam}
    hit = sorted(current_zones & restricted_set)
    if not hit:
        return None

    camera_name = detection.get("camera_name") or camera_id
    score = float(detection.get("score") or detection.get("confidence") or 0.8)
    started = detection.get("started_at") or now
    detected = detection.get("current_at") or detection.get("detected_at") or now
    track_id = detection.get("track_id")
    track_ids = [str(track_id)] if track_id is not None else []
    zone_str = ", ".join(hit)

    return RuleResult(
        event_type="person_restricted_zone",
        severity="high",
        confidence=score,
        camera_id=camera_id,
        camera_name=str(camera_name),
        zone=hit[0],
        message_th=(
            f"{MESSAGE_TH_PREFIX} ตรวจพบบุคคลในพื้นที่หวงห้าม "
            f"({zone_str}) ที่กล้อง {camera_name}"
        ),
        rule={
            "code": "person_restricted_zone",
            "name": "บุคคลในโซนหวงห้าม",
            "params": {"zones": hit},
        },
        objects=[{"label": "person", "count": 1, "track_ids": track_ids}],
        started_at=started if isinstance(started, datetime) else now,
        detected_at=detected if isinstance(detected, datetime) else now,
        ended_at=detection.get("ended_at"),
        params={"matched_zones": hit},
    )
