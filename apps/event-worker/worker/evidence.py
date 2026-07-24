"""Evidence writer: atomic event folders under EVIDENCE_ROOT/{event_id}/."""

from __future__ import annotations

import json
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

# In-memory day sequence; also persisted as .event_counter under root for restarts.
_lock = threading.Lock()
_day_key: str | None = None
_seq: int = 0


def _reset_counters() -> None:
    """Test helper — clear in-memory sequence state."""
    global _day_key, _seq
    with _lock:
        _day_key = None
        _seq = 0


def _counter_path(root: Path) -> Path:
    return root / ".event_counter"


def _load_counter(root: Path, day: str) -> int:
    path = _counter_path(root)
    if not path.exists():
        return 0
    try:
        raw = path.read_text(encoding="utf-8").strip()
        stored_day, stored_seq = raw.split(":", 1)
        if stored_day == day:
            return int(stored_seq)
    except (ValueError, OSError):
        pass
    return 0


def _save_counter(root: Path, day: str, seq: int) -> None:
    root.mkdir(parents=True, exist_ok=True)
    path = _counter_path(root)
    tmp = root / ".event_counter.tmp"
    tmp.write_text(f"{day}:{seq}", encoding="utf-8")
    tmp.replace(path)


def build_event_id(now: datetime, root: Path | str | None = None) -> str:
    """Return EVT-YYYYMMDD-#### with per-day sequence (memory + file counter)."""
    global _day_key, _seq
    day = now.strftime("%Y%m%d")
    root_path = Path(root) if root is not None else None

    with _lock:
        if _day_key != day:
            _day_key = day
            if root_path is not None:
                _seq = _load_counter(root_path, day)
            else:
                _seq = 0
        _seq += 1
        seq = _seq
        if root_path is not None:
            _save_counter(root_path, day, seq)

    return f"EVT-{day}-{seq:04d}"


def write_evidence(
    root: Path | str,
    event_dict: dict[str, Any],
    thumb_bytes: bytes | None = None,
    clip_path: Path | str | None = None,
) -> Path:
    """
    Write evidence dir atomically: populate `.tmp-{event_id}/` then rename to `{event_id}/`.

    relative_path in event.json is set to event_id only (not events/{event_id}/).
    Returns final directory path: {root}/{event_id}/
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)

    event_id = event_dict["event_id"]
    final_dir = root / event_id
    tmp_dir = root / f".tmp-{event_id}"

    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True)

    payload = dict(event_dict)
    evidence = dict(payload.get("evidence") or {})
    evidence["relative_path"] = event_id
    if thumb_bytes is not None:
        (tmp_dir / "thumb.jpg").write_bytes(thumb_bytes)
        evidence["thumb"] = "thumb.jpg"
    if clip_path is not None:
        src = Path(clip_path)
        dest = tmp_dir / "clip.mp4"
        shutil.copy2(src, dest)
        evidence["clip"] = "clip.mp4"
    payload["evidence"] = evidence

    (tmp_dir / "event.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if final_dir.exists():
        shutil.rmtree(final_dir)
    tmp_dir.rename(final_dir)
    return final_dir
