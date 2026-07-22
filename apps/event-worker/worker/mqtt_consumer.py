"""MQTT / Frigate event adapter + dual-write pipeline."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from worker.api_client import ApiClient
from worker.debounce import Debouncer
from worker.evidence import build_event_id, write_evidence
from worker.rules.abnormal_motion import (
    evaluate_abnormal_crowd,
    evaluate_abnormal_motion,
)
from worker.rules.base import RuleResult
from worker.rules.camera_health import OfflineTracker, evaluate_tamper_signal
from worker.rules.fight import FightTracker, evaluate_possible_fight
from worker.rules.littering import LitteringTracker, evaluate_possible_littering
from worker.rules.person_after_hours import evaluate_person_after_hours
from worker.rules.person_fall import FallTracker, evaluate_person_fall
from worker.rules.person_restricted import evaluate_person_restricted

logger = logging.getLogger(__name__)

FRIGATE_EVENTS_TOPIC = "frigate/events"
FRIGATE_AVAILABLE_TOPIC = "frigate/available"


def normalize_frigate_event(msg: dict[str, Any], tz: ZoneInfo) -> dict[str, Any] | None:
    """
    Normalize Frigate MQTT ``frigate/events`` payload to a flat detection dict.

    Frigate shape (simplified)::

        {
          "type": "new" | "update" | "end",
          "before": {...},
          "after": {
            "id": "...",
            "camera": "cam-front",
            "label": "person",
            "current_zones": ["driveway"],
            "entered_zones": ["driveway"],
            "top_score": 0.91,
            "start_time": 1720000000.0,
            "end_time": null,
            "false_positive": false,
            "stationary": false
          }
        }
    """
    # Explicit internal / health signals
    if msg.get("signal"):
        return {
            "signal": msg["signal"],
            "camera_id": msg.get("camera_id") or msg.get("camera"),
            "label": msg.get("label"),
            "score": msg.get("score"),
        }

    after = msg.get("after") or msg
    if not isinstance(after, dict):
        return None

    label = after.get("label")
    event_type = msg.get("type")

    # Skip end events with no label / long duration noise (per Task 6 note)
    if event_type == "end" and not label:
        return None

    if after.get("false_positive"):
        return None

    camera = after.get("camera") or msg.get("camera") or msg.get("camera_id")
    if not camera and not label and not msg.get("signal"):
        return None

    start_ts = after.get("start_time")
    end_ts = after.get("end_time")
    started_at = _ts_to_dt(start_ts, tz) if start_ts is not None else datetime.now(tz)
    ended_at = _ts_to_dt(end_ts, tz) if end_ts is not None else None

    zones = after.get("current_zones") or after.get("entered_zones") or msg.get("zones") or []
    box = after.get("box") or msg.get("box")
    if box is not None:
        try:
            box = [float(v) for v in box[:4]]
        except (TypeError, ValueError):
            box = None

    return {
        "camera_id": str(camera) if camera else "unknown",
        "camera_name": str(camera) if camera else "unknown",
        "label": label,
        "score": float(after.get("top_score") or after.get("score") or 0.0),
        "zones": list(zones),
        "current_zones": list(zones),
        "box": box,
        "track_id": after.get("id") or after.get("track_id"),
        "started_at": started_at,
        "current_at": datetime.now(tz),
        "ended_at": ended_at,
        "stationary": bool(after.get("stationary")),
        "false_positive": bool(after.get("false_positive")),
        "frigate_type": event_type,
        "frame_time": after.get("frame_time"),
        "speed": after.get("speed") if after.get("speed") is not None else msg.get("speed"),
        "nearby_person_count": (
            after.get("nearby_person_count")
            if after.get("nearby_person_count") is not None
            else msg.get("nearby_person_count")
        ),
        "objects": msg.get("objects") or after.get("objects") or [],
        "pose_fallen": bool(after.get("pose_fallen") or msg.get("pose_fallen")),
        "still_duration_s": after.get("still_duration_s") or msg.get("still_duration_s"),
        "high_motion_duration_s": (
            after.get("high_motion_duration_s") or msg.get("high_motion_duration_s")
        ),
        "relative_speed": after.get("relative_speed") or msg.get("relative_speed"),
        "high_relative_motion": bool(
            after.get("high_relative_motion") or msg.get("high_relative_motion")
        ),
        "drop_duration_s": after.get("drop_duration_s") or msg.get("drop_duration_s"),
        "downward_delta": after.get("downward_delta") or msg.get("downward_delta"),
        "in_litter_zone": after.get("in_litter_zone") or msg.get("in_litter_zone"),
        "person_present": after.get("person_present") or msg.get("person_present"),
    }


def _ts_to_dt(ts: float | int | str, tz: ZoneInfo) -> datetime:
    try:
        value = float(ts)
    except (TypeError, ValueError):
        return datetime.now(tz)
    return datetime.fromtimestamp(value, tz=timezone.utc).astimezone(tz)


def rule_result_to_event_dict(
    result: RuleResult,
    event_id: str,
    now: datetime,
) -> dict[str, Any]:
    """Build API/evidence event.json payload from a RuleResult."""
    started = result.started_at or now
    detected = result.detected_at or now
    return {
        "event_id": event_id,
        "schema_version": "1.0",
        "source": "cctvbot",
        "camera": {
            "camera_id": result.camera_id,
            "name": result.camera_name or result.camera_id,
            "stream_type": "ip_rtsp",
            "zone": result.zone,
        },
        "event_type": result.event_type,
        "severity": result.severity,
        "status": "pending_review",
        "confidence": result.confidence,
        "started_at": _iso(started),
        "ended_at": _iso(result.ended_at) if result.ended_at else None,
        "detected_at": _iso(detected),
        "rule": result.rule,
        "objects": result.objects,
        "evidence": {
            "thumb": None,
            "clip": None,
            "clip_before_seconds": 30,
            "clip_after_seconds": 30,
            "relative_path": event_id,
        },
        "review": {
            "reviewed_by": None,
            "reviewed_at": None,
            "decision": None,
            "note": None,
        },
        "notifications": {
            "dashboard": True,
            "line_sent": False,
            "line_sent_at": None,
        },
        "message_th": result.message_th,
    }


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


class EventPipeline:
    """Evaluate rules, dual-write evidence then API POST."""

    def __init__(
        self,
        *,
        evidence_root: Path | str,
        api_client: ApiClient,
        debouncer: Debouncer,
        schedule_config: dict[str, Any],
        rules_config: dict[str, Any],
        timezone_name: str = "Asia/Bangkok",
        offline_tracker: OfflineTracker | None = None,
        fall_tracker: FallTracker | None = None,
        littering_tracker: LitteringTracker | None = None,
        fight_tracker: FightTracker | None = None,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self.evidence_root = Path(evidence_root)
        self.api = api_client
        self.debouncer = debouncer
        self.schedule_config = schedule_config
        self.rules_config = rules_config
        self.tz = ZoneInfo(timezone_name)
        self.offline_tracker = offline_tracker or OfflineTracker()
        self.fall_tracker = fall_tracker or FallTracker(
            still_seconds=float(rules_config.get("fall_still_seconds", 15.0)),
            aspect_threshold=float(rules_config.get("fall_aspect_threshold", 1.2)),
        )
        self.littering_tracker = littering_tracker or LitteringTracker(
            enabled=bool(rules_config.get("littering_enabled", True)),
        )
        self.fight_tracker = fight_tracker or FightTracker(
            person_min=int(rules_config.get("fight_person_min", 2)),
            motion_seconds=float(rules_config.get("fight_motion_seconds", 3.0)),
            speed_threshold=float(rules_config.get("fight_speed_threshold", 0.12)),
        )
        self._now_fn = now_fn

    def _now(self) -> datetime:
        if self._now_fn is not None:
            return self._now_fn()
        return datetime.now(self.tz)

    def handle_frigate_event(self, msg: dict[str, Any]) -> list[str]:
        """
        Process one Frigate MQTT message or internal signal.
        Returns list of event_ids created (dual-written).
        """
        now = self._now()
        detection = normalize_frigate_event(msg, self.tz)
        if detection is None:
            return []

        results: list[RuleResult] = []

        # Tamper explicit / black label
        tamper = evaluate_tamper_signal(
            {
                "signal": detection.get("signal"),
                "camera_id": detection.get("camera_id"),
                "label": detection.get("label"),
                "score": detection.get("score"),
            },
            now,
        )
        if tamper is not None:
            results.append(tamper)

        # Detection rules (new/update; skip pure end noise)
        frigate_type = detection.get("frigate_type")
        if detection.get("label") and frigate_type != "end":
            after_hours = evaluate_person_after_hours(
                detection, now, self.schedule_config
            )
            if after_hours is not None:
                results.append(after_hours)

            restricted = evaluate_person_restricted(
                detection, now, self.rules_config
            )
            if restricted is not None:
                results.append(restricted)

            # Rule 2 — fall (stateless metrics and/or sequence tracker)
            fall = evaluate_person_fall(detection, now, self.rules_config)
            if fall is None:
                fall = self.fall_tracker.update(detection, now)
            if fall is not None:
                results.append(fall)

            # Rule 7 — motion + crowd
            motion = evaluate_abnormal_motion(detection, now, self.rules_config)
            if motion is not None:
                results.append(motion)
            crowd = evaluate_abnormal_crowd(detection, now, self.rules_config)
            if crowd is not None:
                results.append(crowd)

            # Rule 8 — littering (proxy objects; None if person-only model)
            litter = evaluate_possible_littering(detection, now, self.rules_config)
            if litter is None:
                litter = self.littering_tracker.update(
                    detection, now, self.rules_config
                )
            if litter is not None:
                results.append(litter)

            # Rule 9 — fight
            fight = evaluate_possible_fight(detection, now, self.rules_config)
            if fight is None:
                fight = self.fight_tracker.update(
                    detection, now, self.rules_config
                )
            if fight is not None:
                results.append(fight)

        return self._emit_results(results, now)

    def handle_frigate_stats(
        self,
        stats: dict[str, Any],
        known_cameras: list[str] | None = None,
    ) -> list[str]:
        """Process Frigate HTTP /api/stats snapshot for offline tracking."""
        now = self._now()
        results = self.offline_tracker.update(stats, now, known_cameras=known_cameras)
        return self._emit_results(results, now)

    def _emit_results(self, results: list[RuleResult], now: datetime) -> list[str]:
        event_ids: list[str] = []
        for result in results:
            if not self.debouncer.should_emit(result.camera_id, result.event_type, now):
                logger.debug(
                    "debounced %s/%s", result.camera_id, result.event_type
                )
                continue
            event_id = self._dual_write(result, now)
            if event_id:
                event_ids.append(event_id)
        return event_ids

    def _dual_write(self, result: RuleResult, now: datetime) -> str | None:
        """Write evidence FIRST, then POST API. Files survive API outage."""
        event_id = build_event_id(now, root=self.evidence_root)
        payload = rule_result_to_event_dict(result, event_id, now)

        try:
            write_evidence(self.evidence_root, payload)
        except OSError:
            logger.exception("evidence write failed for %s", event_id)
            return None

        try:
            self.api.post_event(payload)
        except Exception:
            # Dual-write guarantee: evidence already on disk
            logger.exception(
                "API post failed for %s (evidence retained at %s)",
                event_id,
                self.evidence_root / event_id,
            )
        else:
            # Explicit camera status update after successful offline emit
            # (API create also sets is_online from event_type; this is belt-and-suspenders).
            if result.event_type == "camera_offline":
                try:
                    self.api.put_camera_status(
                        result.camera_id,
                        is_online=False,
                        name=result.camera_name or result.camera_id,
                        zone=result.zone,
                    )
                except Exception:
                    logger.exception(
                        "put_camera_status offline failed for %s",
                        result.camera_id,
                    )
        return event_id


def parse_mqtt_payload(raw: bytes | str) -> dict[str, Any] | None:
    """Parse MQTT payload bytes/string to dict; return None on failure."""
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        logger.warning("invalid MQTT JSON payload")
    return None
