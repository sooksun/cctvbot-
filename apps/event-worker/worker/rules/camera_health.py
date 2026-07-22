"""Rule 5: camera offline tracker + tamper heuristics."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from worker.rules.base import MESSAGE_TH_PREFIX, RuleResult

# Offline ≥ 30 seconds (design default).
DEFAULT_OFFLINE_SECONDS = 30
# Mean luminance below this for N consecutive checks → camera_tamper.
DEFAULT_LUMINANCE_THRESHOLD = 10.0
DEFAULT_LUMINANCE_STREAK = 3


class OfflineTracker:
    """
    Track per-camera offline duration from Frigate stats snapshots.

    A camera is considered unhealthy when it is missing from stats or
    ``camera_fps == 0``. After ``threshold_seconds`` continuous unhealthy
    time, ``update`` returns a ``camera_offline`` RuleResult (once until recovery).
    """

    def __init__(self, threshold_seconds: float = DEFAULT_OFFLINE_SECONDS) -> None:
        self.threshold_seconds = threshold_seconds
        # camera_id -> first unhealthy timestamp
        self._down_since: dict[str, datetime] = {}
        # cameras already emitted while still down (debounce at rule layer too)
        self._emitted: set[str] = set()
        self._known: set[str] = set()

    def reset(self) -> None:
        self._down_since.clear()
        self._emitted.clear()
        self._known.clear()

    def update(
        self,
        stats: dict[str, Any],
        now: datetime,
        known_cameras: list[str] | None = None,
    ) -> list[RuleResult]:
        """
        Ingest a Frigate ``/api/stats``-like payload.

        Expected shape (subset)::

            {
              "cameras": {
                "cam-front": {"camera_fps": 5.0, ...},
                "cam-back": {"camera_fps": 0.0, ...}
              }
            }
        """
        cameras_block = stats.get("cameras") or {}
        present = set(cameras_block.keys())
        if known_cameras:
            self._known.update(known_cameras)
        self._known.update(present)

        unhealthy: set[str] = set()
        for cam_id in self._known:
            cam_stats = cameras_block.get(cam_id)
            if cam_stats is None:
                unhealthy.add(cam_id)
                continue
            fps = cam_stats.get("camera_fps")
            if fps is None:
                # missing fps field — treat as unknown healthy only if other fields exist
                fps = cam_stats.get("detection_fps", 1.0)
            try:
                fps_val = float(fps)
            except (TypeError, ValueError):
                fps_val = 0.0
            if fps_val <= 0.0:
                unhealthy.add(cam_id)

        results: list[RuleResult] = []
        # recover
        for cam_id in list(self._down_since.keys()):
            if cam_id not in unhealthy:
                self._down_since.pop(cam_id, None)
                self._emitted.discard(cam_id)

        for cam_id in unhealthy:
            if cam_id not in self._down_since:
                self._down_since[cam_id] = now
            down_for = now - self._down_since[cam_id]
            if down_for >= timedelta(seconds=self.threshold_seconds):
                if cam_id in self._emitted:
                    continue
                self._emitted.add(cam_id)
                results.append(
                    RuleResult(
                        event_type="camera_offline",
                        severity="critical",
                        confidence=1.0,
                        camera_id=cam_id,
                        camera_name=cam_id,
                        message_th=(
                            f"{MESSAGE_TH_PREFIX} กล้อง {cam_id} ออฟไลน์ "
                            f"เกิน {int(self.threshold_seconds)} วินาที"
                        ),
                        rule={
                            "code": "camera_offline",
                            "name": "กล้องออฟไลน์",
                            "params": {
                                "threshold_seconds": self.threshold_seconds,
                                "down_seconds": down_for.total_seconds(),
                            },
                        },
                        objects=[],
                        started_at=self._down_since[cam_id],
                        detected_at=now,
                    )
                )
        return results


class LuminanceTamperTracker:
    """
    Poll snapshot brightness; if mean luminance < threshold for
    ``streak`` consecutive checks → ``camera_tamper``.

    Also accepts explicit internal signal via :func:`evaluate_tamper_signal`.
    """

    def __init__(
        self,
        luminance_threshold: float = DEFAULT_LUMINANCE_THRESHOLD,
        streak_required: int = DEFAULT_LUMINANCE_STREAK,
    ) -> None:
        self.luminance_threshold = luminance_threshold
        self.streak_required = streak_required
        self._dark_streak: dict[str, int] = {}
        self._emitted: set[str] = set()

    def reset(self) -> None:
        self._dark_streak.clear()
        self._emitted.clear()

    def update_luminance(
        self,
        camera_id: str,
        mean_luminance: float,
        now: datetime,
    ) -> RuleResult | None:
        """Record one brightness sample; emit tamper after consecutive dark frames."""
        if mean_luminance < self.luminance_threshold:
            self._dark_streak[camera_id] = self._dark_streak.get(camera_id, 0) + 1
        else:
            self._dark_streak[camera_id] = 0
            self._emitted.discard(camera_id)
            return None

        if self._dark_streak[camera_id] < self.streak_required:
            return None
        if camera_id in self._emitted:
            return None
        self._emitted.add(camera_id)
        return _tamper_result(
            camera_id,
            now,
            reason="low_luminance",
            params={
                "mean_luminance": mean_luminance,
                "threshold": self.luminance_threshold,
                "streak": self._dark_streak[camera_id],
            },
        )


def evaluate_tamper_signal(
    payload: dict[str, Any],
    now: datetime,
) -> RuleResult | None:
    """
    Emit ``camera_tamper`` for:

    - Explicit internal signal: ``{"signal": "tamper", "camera_id": "..."}``
    - Frigate ``black`` label / detection when configured as object label
    """
    signal = (payload.get("signal") or "").lower()
    label = (payload.get("label") or "").lower()
    camera_id = str(payload.get("camera_id") or payload.get("camera") or "")

    if signal == "tamper" and camera_id:
        return _tamper_result(
            camera_id,
            now,
            reason="explicit_signal",
            params={"signal": "tamper"},
        )

    # Frigate "black" object detection (optional custom model / filter)
    if label == "black" and camera_id:
        return _tamper_result(
            camera_id,
            now,
            reason="frigate_black_label",
            params={"label": "black"},
            confidence=float(payload.get("score") or 0.9),
        )
    return None


def maybe_tamper(frame_score: float | None) -> RuleResult | None:
    """
    Optional stub until snapshot analysis is wired.

    Returns None always in MVP unless frame_score is provided and extreme;
    prefer :class:`LuminanceTamperTracker` or :func:`evaluate_tamper_signal`.
    """
    if frame_score is None:
        return None
    # Reserved for future frame-score based heuristics
    return None


def _tamper_result(
    camera_id: str,
    now: datetime,
    reason: str,
    params: dict[str, Any] | None = None,
    confidence: float = 0.85,
) -> RuleResult:
    return RuleResult(
        event_type="camera_tamper",
        severity="critical",
        confidence=confidence,
        camera_id=camera_id,
        camera_name=camera_id,
        message_th=(
            f"{MESSAGE_TH_PREFIX} สงสัยกล้องถูกปิดบังหรือขยับ "
            f"ที่กล้อง {camera_id}"
        ),
        rule={
            "code": "camera_tamper",
            "name": "กล้องถูกแทรกแซง",
            "params": {"reason": reason, **(params or {})},
        },
        objects=[],
        started_at=now,
        detected_at=now,
        params={"reason": reason, **(params or {})},
    )
