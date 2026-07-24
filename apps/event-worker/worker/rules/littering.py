"""Rule 8: suspected littering (person + small object trajectory to ground)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from worker.rules.base import MESSAGE_TH_PREFIX, RuleResult

# COCO-style proxies for hand-carried / droppable objects.
PROXY_OBJECT_LABELS = frozenset(
    {"bottle", "cup", "bag", "backpack", "handbag", "umbrella"}
)
DEFAULT_LITTER_ZONE = "litter_watch"
DEFAULT_MIN_DROP_SECONDS = 3.0
DEFAULT_MAX_DROP_SECONDS = 8.0
# Minimum downward (positive y) centroid travel in norm units.
DEFAULT_DOWNWARD_DELTA = 0.05
# Drop per-object track state not seen within this window (bounds memory).
DEFAULT_TRACK_TTL_SECONDS = 300.0


def _proxy_objects(detection: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect proxy object dicts from detection payload."""
    found: list[dict[str, Any]] = []
    label = (detection.get("label") or "").lower()
    if label in PROXY_OBJECT_LABELS:
        found.append(detection)

    for obj in detection.get("objects") or []:
        if not isinstance(obj, dict):
            continue
        olabel = (obj.get("label") or "").lower()
        if olabel in PROXY_OBJECT_LABELS:
            found.append(obj)

    # Scene object list from multi-label Frigate batch
    for obj in detection.get("frigate_objects") or []:
        if not isinstance(obj, dict):
            continue
        olabel = (obj.get("label") or "").lower()
        if olabel in PROXY_OBJECT_LABELS:
            found.append(obj)

    return found


def _has_person(detection: dict[str, Any]) -> bool:
    label = (detection.get("label") or "").lower()
    if label == "person":
        return True
    if int(detection.get("nearby_person_count") or 0) >= 1:
        return True
    if detection.get("person_present") is True:
        return True
    for obj in detection.get("objects") or []:
        if isinstance(obj, dict) and (obj.get("label") or "").lower() == "person":
            return True
    return False


def _zones_of(obj: dict[str, Any]) -> set[str]:
    zones = obj.get("zones") or obj.get("current_zones") or []
    return {str(z) for z in zones}


def _centroid_y(obj: dict[str, Any]) -> float | None:
    box = obj.get("box")
    if not box or len(box) < 4:
        cy = obj.get("centroid_y")
        if cy is None:
            return None
        try:
            return float(cy)
        except (TypeError, ValueError):
            return None
    try:
        y1, y2 = float(box[1]), float(box[3])
        return (y1 + y2) / 2.0
    except (TypeError, ValueError, IndexError):
        return None


def evaluate_possible_littering(
    detection: dict[str, Any],
    now: datetime,
    rules_config: dict[str, Any] | None = None,
) -> RuleResult | None:
    """
    Stateless path: person present + proxy object labels + downward motion
    toward ``litter_watch`` within 3–8s.

    Feature flag ``littering_enabled`` (default True). When no proxy object
    labels are present (person-only model), returns None.
    """
    cfg = rules_config or {}
    if cfg.get("littering_enabled", True) is False:
        return None

    proxies = _proxy_objects(detection)
    if not proxies:
        return None
    if not _has_person(detection):
        return None

    litter_zone = str(cfg.get("litter_zone", DEFAULT_LITTER_ZONE))
    min_s = float(cfg.get("litter_min_seconds", DEFAULT_MIN_DROP_SECONDS))
    max_s = float(cfg.get("litter_max_seconds", DEFAULT_MAX_DROP_SECONDS))
    down_delta = float(cfg.get("litter_downward_delta", DEFAULT_DOWNWARD_DELTA))

    # Prefer explicit drop metrics on detection or first proxy.
    duration = detection.get("drop_duration_s")
    dy = detection.get("downward_delta")
    in_zone = detection.get("in_litter_zone")
    proxy_label = (proxies[0].get("label") or "object").lower()

    for p in proxies:
        pz = _zones_of(p)
        if litter_zone in pz:
            in_zone = True
        if p.get("drop_duration_s") is not None:
            duration = p.get("drop_duration_s")
        if p.get("downward_delta") is not None:
            dy = p.get("downward_delta")
        pl = (p.get("label") or "").lower()
        if pl:
            proxy_label = pl

    if in_zone is not True:
        det_zones = set(detection.get("zones") or detection.get("current_zones") or [])
        if litter_zone not in det_zones and litter_zone not in _zones_of(proxies[0]):
            return None

    if duration is None or dy is None:
        return None
    try:
        dur_s = float(duration)
        dy_val = float(dy)
    except (TypeError, ValueError):
        return None
    if not (min_s <= dur_s <= max_s):
        return None
    if dy_val < down_delta:
        return None

    return _litter_result(detection, now, proxy_label, litter_zone, dur_s, dy_val)


class LitteringTracker:
    """
    Track proxy-object centroids; if person nearby and object moves downward
    into ``litter_watch`` within 3–8s → ``possible_littering``.
    """

    def __init__(
        self,
        litter_zone: str = DEFAULT_LITTER_ZONE,
        min_seconds: float = DEFAULT_MIN_DROP_SECONDS,
        max_seconds: float = DEFAULT_MAX_DROP_SECONDS,
        downward_delta: float = DEFAULT_DOWNWARD_DELTA,
        enabled: bool = True,
        ttl_seconds: float = DEFAULT_TRACK_TTL_SECONDS,
    ) -> None:
        self.litter_zone = litter_zone
        self.min_seconds = min_seconds
        self.max_seconds = max_seconds
        self.downward_delta = downward_delta
        self.enabled = enabled
        self.ttl_seconds = ttl_seconds
        # object track key -> {start_y, start_t, person_seen, last_seen}
        self._tracks: dict[str, dict[str, Any]] = {}
        self._emitted: set[str] = set()

    def reset(self) -> None:
        self._tracks.clear()
        self._emitted.clear()

    def _evict_stale(self, now: datetime) -> None:
        """Drop object tracks not seen within ttl_seconds to bound memory."""
        cutoff = now - timedelta(seconds=self.ttl_seconds)
        stale = [
            k
            for k, st in self._tracks.items()
            if st.get("last_seen", st["start_t"]) < cutoff
        ]
        for k in stale:
            self._tracks.pop(k, None)
            self._emitted.discard(k)
        self._emitted &= set(self._tracks.keys())

    def update(
        self,
        detection: dict[str, Any],
        now: datetime | None = None,
        rules_config: dict[str, Any] | None = None,
    ) -> RuleResult | None:
        cfg = rules_config or {}
        if cfg.get("littering_enabled", self.enabled) is False:
            return None

        ts = now or detection.get("current_at") or detection.get("detected_at")
        if not isinstance(ts, datetime):
            return None

        self._evict_stale(ts)

        proxies = _proxy_objects(detection)
        if not proxies:
            return None

        person_here = _has_person(detection)
        camera_id = str(detection.get("camera_id") or detection.get("camera") or "unknown")
        litter_zone = str(cfg.get("litter_zone", self.litter_zone))
        min_s = float(cfg.get("litter_min_seconds", self.min_seconds))
        max_s = float(cfg.get("litter_max_seconds", self.max_seconds))
        down_delta = float(cfg.get("litter_downward_delta", self.downward_delta))

        for proxy in proxies:
            cy = _centroid_y(proxy)
            if cy is None:
                continue
            tid = proxy.get("track_id") or detection.get("track_id") or "obj"
            key = f"{camera_id}:{tid}:{(proxy.get('label') or 'obj').lower()}"
            zones = _zones_of(proxy) | set(
                detection.get("zones") or detection.get("current_zones") or []
            )

            state = self._tracks.get(key)
            if state is None:
                self._tracks[key] = {
                    "start_y": cy,
                    "start_t": ts,
                    "person_seen": person_here,
                    "label": (proxy.get("label") or "object").lower(),
                    "last_seen": ts,
                }
                continue

            state["last_seen"] = ts
            state["person_seen"] = state["person_seen"] or person_here
            elapsed = (ts - state["start_t"]).total_seconds()
            dy = cy - float(state["start_y"])  # positive = downward in image coords

            if elapsed > max_s:
                # restart window
                self._tracks[key] = {
                    "start_y": cy,
                    "start_t": ts,
                    "person_seen": person_here,
                    "label": state["label"],
                    "last_seen": ts,
                }
                continue

            if (
                state["person_seen"]
                and litter_zone in zones
                and min_s <= elapsed <= max_s
                and dy >= down_delta
                and key not in self._emitted
            ):
                self._emitted.add(key)
                det = dict(detection)
                det.setdefault("camera_id", camera_id)
                return _litter_result(
                    det,
                    ts,
                    state["label"],
                    litter_zone,
                    elapsed,
                    dy,
                )
        return None


def _litter_result(
    detection: dict[str, Any],
    now: datetime,
    proxy_label: str,
    litter_zone: str,
    duration_s: float,
    downward_delta: float,
) -> RuleResult:
    camera_id = str(detection.get("camera_id") or detection.get("camera") or "unknown")
    camera_name = detection.get("camera_name") or camera_id
    score = float(detection.get("score") or detection.get("confidence") or 0.7)
    started = detection.get("started_at") or now
    track_id = detection.get("track_id")
    track_ids = [str(track_id)] if track_id is not None else []

    return RuleResult(
        event_type="possible_littering",
        severity="low",
        confidence=score,
        camera_id=camera_id,
        camera_name=str(camera_name),
        zone=litter_zone,
        message_th=(
            f"{MESSAGE_TH_PREFIX} สงสัยทิ้งขยะ "
            f"({proxy_label}) โซน {litter_zone} ที่กล้อง {camera_name}"
        ),
        rule={
            "code": "possible_littering",
            "name": "สงสัยทิ้งขยะ",
            "params": {
                "proxy_label": proxy_label,
                "litter_zone": litter_zone,
                "drop_duration_s": duration_s,
                "downward_delta": downward_delta,
            },
        },
        objects=[
            {"label": "person", "count": 1, "track_ids": []},
            {"label": proxy_label, "count": 1, "track_ids": track_ids},
        ],
        started_at=started if isinstance(started, datetime) else now,
        detected_at=now,
        ended_at=detection.get("ended_at"),
        params={
            "proxy_label": proxy_label,
            "drop_duration_s": duration_s,
            "downward_delta": downward_delta,
        },
    )
