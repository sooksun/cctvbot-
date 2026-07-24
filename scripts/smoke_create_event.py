#!/usr/bin/env python3
"""E2E smoke: write local evidence folder + POST synthetic person_after_hours.

Usage (from repo root, API running on :8000):

  set SYSTEM_API_TOKEN=...   # PowerShell: $env:SYSTEM_API_TOKEN="..."
  python scripts/smoke_create_event.py

Optional env:
  API_BASE_URL   default http://localhost:8000
  EVIDENCE_ROOT  default ./data/events
  SYSTEM_API_TOKEN  required (same as API)
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Minimal valid JPEG (1x1 pixel) so dashboard evidence paths exist without Frigate.
_MIN_JPEG = bytes(
    [
        0xFF,
        0xD8,
        0xFF,
        0xE0,
        0x00,
        0x10,
        0x4A,
        0x46,
        0x49,
        0x46,
        0x00,
        0x01,
        0x01,
        0x00,
        0x00,
        0x01,
        0x00,
        0x01,
        0x00,
        0x00,
        0xFF,
        0xDB,
        0x00,
        0x43,
        0x00,
        0x08,
        0x06,
        0x06,
        0x07,
        0x06,
        0x05,
        0x08,
        0x07,
        0x07,
        0x07,
        0x09,
        0x09,
        0x08,
        0x0A,
        0x0C,
        0x14,
        0x0D,
        0x0C,
        0x0B,
        0x0B,
        0x0C,
        0x19,
        0x12,
        0x13,
        0x0F,
        0x14,
        0x1D,
        0x1A,
        0x1F,
        0x1E,
        0x1D,
        0x1A,
        0x1C,
        0x1C,
        0x20,
        0x24,
        0x2E,
        0x27,
        0x20,
        0x22,
        0x2C,
        0x23,
        0x1C,
        0x1C,
        0x28,
        0x37,
        0x29,
        0x2C,
        0x30,
        0x31,
        0x34,
        0x34,
        0x34,
        0x1F,
        0x27,
        0x39,
        0x3D,
        0x38,
        0x32,
        0x3C,
        0x2E,
        0x33,
        0x34,
        0x32,
        0xFF,
        0xC0,
        0x00,
        0x0B,
        0x08,
        0x00,
        0x01,
        0x00,
        0x01,
        0x01,
        0x01,
        0x11,
        0x00,
        0xFF,
        0xC4,
        0x00,
        0x14,
        0x00,
        0x01,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x08,
        0xFF,
        0xC4,
        0x00,
        0x14,
        0x10,
        0x01,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0xFF,
        0xDA,
        0x00,
        0x08,
        0x01,
        0x01,
        0x00,
        0x00,
        0x3F,
        0x00,
        0x7F,
        0xFF,
        0xD9,
    ]
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _build_event_id(now: datetime, root: Path) -> str:
    """EVT-YYYYMMDD-#### using a simple day counter under evidence root."""
    day = now.strftime("%Y%m%d")
    counter = root / ".event_counter"
    seq = 0
    if counter.exists():
        try:
            stored_day, stored_seq = counter.read_text(encoding="utf-8").strip().split(":", 1)
            if stored_day == day:
                seq = int(stored_seq)
        except (ValueError, OSError):
            seq = 0
    seq += 1
    root.mkdir(parents=True, exist_ok=True)
    counter.write_text(f"{day}:{seq}", encoding="utf-8")
    return f"EVT-{day}-{seq:04d}"


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def main() -> int:
    token = (os.environ.get("SYSTEM_API_TOKEN") or "").strip()
    if not token:
        print("ERROR: SYSTEM_API_TOKEN is required", file=sys.stderr)
        return 1

    api_base = (os.environ.get("API_BASE_URL") or "http://localhost:8000").rstrip("/")
    evidence_root = Path(
        os.environ.get("EVIDENCE_ROOT") or str(_repo_root() / "data" / "events")
    )

    # Asia/Bangkok +07:00 without zoneinfo dependency for portability
    tz = timezone(timedelta(hours=7))
    now = datetime.now(tz)
    started = now - timedelta(seconds=12)
    detected = now - timedelta(seconds=5)

    event_id = _build_event_id(now, evidence_root)
    # Convention: relative_path = event_id only → {EVIDENCE_ROOT}/{event_id}/
    relative_path = event_id

    payload = {
        "event_id": event_id,
        "schema_version": "1.0",
        "source": "cctvbot",
        "camera": {
            "camera_id": "gate_front",
            "name": "ประตูหน้า",
            "stream_type": "ip_rtsp",
            "zone": "gate",
        },
        "event_type": "person_after_hours",
        "severity": "high",
        "status": "pending_review",
        "confidence": 0.91,
        "started_at": _iso(started),
        "ended_at": _iso(now),
        "detected_at": _iso(detected),
        "rule": {
            "code": "person_after_hours",
            "name": "บุคคลนอกเวลา",
            "params": {"schedule": "school_closed", "smoke": True},
        },
        "objects": [{"label": "person", "count": 1, "track_ids": ["smoke-1"]}],
        "evidence": {
            "thumb": "thumb.jpg",
            "clip": None,
            "clip_before_seconds": 30,
            "clip_after_seconds": 30,
            "relative_path": relative_path,
        },
        "message_th": "พบเหตุที่ควรตรวจสอบ: ตรวจพบบุคคลนอกเวลาทำการ ที่กล้อง ประตูหน้า (smoke)",
    }

    event_dir = evidence_root / event_id
    event_dir.mkdir(parents=True, exist_ok=True)
    (event_dir / "thumb.jpg").write_bytes(_MIN_JPEG)
    (event_dir / "event.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote evidence: {event_dir}")

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{api_base}/api/events",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-System-Token": token,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            status = resp.status
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"POST failed HTTP {e.code}: {err_body}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"POST failed: {e.reason}", file=sys.stderr)
        print(f"Is API up at {api_base}?", file=sys.stderr)
        return 1

    print(f"POST /api/events → {status}")
    print(raw)
    print()
    print("Next:")
    print(f"  Dashboard: http://localhost:3000  (login admin)")
    print(f"  Event:     http://localhost:3000/events/{event_id}")
    print("  Review as admin → confirmed triggers LINE text if configured")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
