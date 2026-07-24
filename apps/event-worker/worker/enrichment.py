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
