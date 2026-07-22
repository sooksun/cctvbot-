"""Event-worker entrypoint: MQTT consumer + Frigate stats poll loop."""

from __future__ import annotations

import logging
import signal
import sys
import threading
import time
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
import yaml

from worker.api_client import ApiClient
from worker.config import settings
from worker.debounce import Debouncer
from worker.mqtt_consumer import (
    FRIGATE_AVAILABLE_TOPIC,
    FRIGATE_EVENTS_TOPIC,
    EventPipeline,
    parse_mqtt_payload,
)
from worker.rules.camera_health import LuminanceTamperTracker, OfflineTracker

logger = logging.getLogger(__name__)

DEFAULT_SCHEDULE = {
    "school_closed": {
        "weekdays": [{"start": "18:00", "end": "06:00"}],
        "weekends": "all_day",
    },
    "timezone": "Asia/Bangkok",
}

DEFAULT_RULES: dict[str, Any] = {
    "restricted_zones": {},
    "offline_threshold_seconds": 30,
    "luminance_threshold": 10.0,
    "luminance_streak": 3,
    # Rule 2 fall
    "fall_still_seconds": 15.0,
    "fall_aspect_threshold": 1.2,
    # Rule 7 motion / crowd
    "run_speed_threshold": 0.15,
    "crowd_threshold": 5,
    # Rule 8 littering
    "littering_enabled": True,
    "litter_zone": "litter_watch",
    "litter_min_seconds": 3.0,
    "litter_max_seconds": 8.0,
    # Rule 9 fight
    "fight_person_min": 2,
    "fight_motion_seconds": 3.0,
    "fight_speed_threshold": 0.12,
}


def load_yaml(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return dict(default)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            return dict(default)
        merged = dict(default)
        merged.update(data)
        return merged
    except (OSError, yaml.YAMLError):
        logger.exception("failed loading %s — using defaults", path)
        return dict(default)


def mean_luminance_jpeg(jpeg_bytes: bytes) -> float | None:
    """
    Mean pixel luminance (approx Y) for a JPEG snapshot.
    Uses Pillow when available; returns None if decode fails.
    """
    try:
        from PIL import Image
    except ImportError:
        logger.warning("Pillow not installed — luminance tamper disabled")
        return None
    try:
        img = Image.open(BytesIO(jpeg_bytes)).convert("L")
        # downsample for speed
        img.thumbnail((160, 160))
        hist = img.histogram()
        total = sum(hist) or 1
        return sum(i * c for i, c in enumerate(hist)) / total
    except Exception:
        logger.debug("snapshot luminance decode failed", exc_info=True)
        return None


class WorkerApp:
    def __init__(self) -> None:
        self._stop = threading.Event()
        config_dir = Path(settings.config_dir)
        self.schedule_config = load_yaml(config_dir / "schedule.yml", DEFAULT_SCHEDULE)
        self.rules_config = load_yaml(config_dir / "rules.yml", DEFAULT_RULES)
        if "timezone" not in self.schedule_config:
            self.schedule_config["timezone"] = settings.timezone

        self.api = ApiClient(
            base_url=settings.api_base_url,
            system_token=settings.system_api_token,
        )
        offline_secs = float(
            self.rules_config.get("offline_threshold_seconds", 30)
        )
        self.offline_tracker = OfflineTracker(threshold_seconds=offline_secs)
        self.luminance_tracker = LuminanceTamperTracker(
            luminance_threshold=float(
                self.rules_config.get("luminance_threshold", 10.0)
            ),
            streak_required=int(self.rules_config.get("luminance_streak", 3)),
        )
        self.pipeline = EventPipeline(
            evidence_root=settings.evidence_root,
            api_client=self.api,
            debouncer=Debouncer(window_seconds=settings.debounce_seconds),
            schedule_config=self.schedule_config,
            rules_config=self.rules_config,
            timezone_name=settings.timezone,
            offline_tracker=self.offline_tracker,
        )
        self._mqtt_client = None
        self._known_cameras: list[str] = list(
            (self.rules_config.get("restricted_zones") or {}).keys()
        )
        # drop wildcard from known list
        self._known_cameras = [c for c in self._known_cameras if c != "*"]

    def stop(self, *_args: object) -> None:
        logger.info("shutdown requested")
        self._stop.set()

    def run(self) -> None:
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

        mqtt_thread = threading.Thread(target=self._mqtt_loop, name="mqtt", daemon=True)
        mqtt_thread.start()

        logger.info(
            "event-worker started mqtt=%s:%s frigate=%s evidence=%s",
            settings.mqtt_host,
            settings.mqtt_port,
            settings.frigate_base_url,
            settings.evidence_root,
        )

        while not self._stop.is_set():
            try:
                self._poll_frigate_health()
            except Exception:
                logger.exception("frigate health poll error")
            self._stop.wait(settings.stats_poll_seconds)

        if self._mqtt_client is not None:
            try:
                self._mqtt_client.loop_stop()
                self._mqtt_client.disconnect()
            except Exception:
                pass
        self.api.close()
        logger.info("event-worker stopped")

    def _mqtt_loop(self) -> None:
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            logger.error("paho-mqtt not installed — MQTT consumer disabled")
            return

        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._mqtt_client = client

        def on_connect(client, userdata, flags, reason_code, properties=None):
            logger.info("MQTT connected rc=%s", reason_code)
            client.subscribe(FRIGATE_EVENTS_TOPIC)
            client.subscribe(FRIGATE_AVAILABLE_TOPIC)

        def on_message(client, userdata, msg):
            try:
                self._on_mqtt_message(msg.topic, msg.payload)
            except Exception:
                logger.exception("MQTT message handler error topic=%s", msg.topic)

        client.on_connect = on_connect
        client.on_message = on_message

        while not self._stop.is_set():
            try:
                client.connect(settings.mqtt_host, settings.mqtt_port, keepalive=60)
                client.loop_forever(retry_first_connection=True)
            except Exception:
                logger.exception("MQTT connection failed — retry in 5s")
                self._stop.wait(5)

    def _on_mqtt_message(self, topic: str, payload: bytes) -> None:
        if topic == FRIGATE_AVAILABLE_TOPIC:
            raw = payload.decode("utf-8", errors="replace").strip().lower()
            logger.info("frigate available=%s", raw)
            return

        data = parse_mqtt_payload(payload)
        if data is None:
            return
        event_ids = self.pipeline.handle_frigate_event(data)
        if event_ids:
            logger.info("created events from MQTT: %s", event_ids)

    def _poll_frigate_health(self) -> None:
        base = settings.frigate_base_url.rstrip("/")
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(f"{base}/api/stats")
                if resp.status_code == 200:
                    stats = resp.json()
                    cameras = list((stats.get("cameras") or {}).keys())
                    if cameras:
                        self._known_cameras = cameras
                    ids = self.pipeline.handle_frigate_stats(
                        stats, known_cameras=self._known_cameras
                    )
                    if ids:
                        logger.info("created offline events: %s", ids)
                    self._poll_snapshots_luminance(client, base, cameras or self._known_cameras)
                else:
                    logger.warning("frigate stats HTTP %s", resp.status_code)
                    # treat all known as missing → offline path
                    empty = {"cameras": {}}
                    ids = self.pipeline.handle_frigate_stats(
                        empty, known_cameras=self._known_cameras
                    )
                    if ids:
                        logger.info("created offline events (stats fail): %s", ids)
        except httpx.HTTPError:
            logger.warning("frigate unreachable at %s", base)
            if self._known_cameras:
                ids = self.pipeline.handle_frigate_stats(
                    {"cameras": {}}, known_cameras=self._known_cameras
                )
                if ids:
                    logger.info("created offline events (unreachable): %s", ids)

    def _poll_snapshots_luminance(
        self,
        client: httpx.Client,
        base: str,
        cameras: list[str],
    ) -> None:
        """
        Prefer luminance via Frigate snapshot API.
        mean luminance < 10 for 3 consecutive checks → camera_tamper.
        """
        now = self.pipeline._now()
        for cam in cameras:
            try:
                r = client.get(f"{base}/api/{cam}/latest.jpg", params={"h": 180})
                if r.status_code != 200:
                    continue
                mean_y = mean_luminance_jpeg(r.content)
                if mean_y is None:
                    continue
                result = self.luminance_tracker.update_luminance(cam, mean_y, now)
                if result is not None:
                    ids = self.pipeline._emit_results([result], now)
                    if ids:
                        logger.info("created tamper events: %s", ids)
            except httpx.HTTPError:
                continue


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        stream=sys.stdout,
    )
    WorkerApp().run()


if __name__ == "__main__":
    main()
