import json
from datetime import datetime, timezone
from pathlib import Path

from worker.evidence import build_event_id, write_evidence


def _minimal_event(event_id: str = "EVT-20260722-0001") -> dict:
    return {
        "event_id": event_id,
        "schema_version": "1.0",
        "source": "cctvbot",
        "camera": {
            "camera_id": "cam-front",
            "name": "ประตูหน้า",
            "stream_type": "ip_rtsp",
            "zone": "gate",
        },
        "event_type": "person_after_hours",
        "severity": "high",
        "status": "pending_review",
        "confidence": 0.91,
        "started_at": "2026-07-22T22:00:00+07:00",
        "ended_at": None,
        "detected_at": "2026-07-22T22:00:01+07:00",
        "rule": {"code": "person_after_hours", "name": "บุคคลนอกเวลา", "params": {}},
        "objects": [{"label": "person", "count": 1, "track_ids": ["1"]}],
        "evidence": {
            "thumb": "thumb.jpg",
            "clip": None,
            "clip_before_seconds": 30,
            "clip_after_seconds": 30,
            "relative_path": event_id,
        },
        "message_th": "พบเหตุที่ควรตรวจสอบ: ทดสอบ",
    }


def test_write_evidence_creates_event_json(tmp_path: Path):
    event = _minimal_event()
    path = write_evidence(tmp_path, event)
    assert path == tmp_path / "EVT-20260722-0001"
    assert (path / "event.json").exists()
    data = json.loads((path / "event.json").read_text(encoding="utf-8"))
    assert data["event_id"] == "EVT-20260722-0001"
    assert data["message_th"] == "พบเหตุที่ควรตรวจสอบ: ทดสอบ"


def test_write_evidence_relative_path_is_event_id_only(tmp_path: Path):
    event = _minimal_event()
    path = write_evidence(tmp_path, event)
    data = json.loads((path / "event.json").read_text(encoding="utf-8"))
    rel = data["evidence"]["relative_path"].rstrip("/")
    assert rel == "EVT-20260722-0001"
    assert not rel.startswith("events/")


def test_write_evidence_writes_thumb(tmp_path: Path):
    event = _minimal_event()
    thumb = b"\xff\xd8\xfffake-jpeg"
    path = write_evidence(tmp_path, event, thumb_bytes=thumb)
    assert (path / "thumb.jpg").read_bytes() == thumb


def test_write_evidence_copies_clip(tmp_path: Path):
    event = _minimal_event()
    clip_src = tmp_path / "source_clip.mp4"
    clip_src.write_bytes(b"fake-mp4-bytes")
    path = write_evidence(tmp_path, event, clip_path=clip_src)
    assert (path / "clip.mp4").read_bytes() == b"fake-mp4-bytes"
    data = json.loads((path / "event.json").read_text(encoding="utf-8"))
    assert data["evidence"]["clip"] == "clip.mp4"


def test_write_evidence_atomic_no_tmp_left(tmp_path: Path):
    event = _minimal_event()
    path = write_evidence(tmp_path, event)
    leftovers = list(tmp_path.glob(".tmp-*"))
    assert leftovers == []
    assert path.exists()
    assert path.is_dir()


def test_build_event_id_format():
    now = datetime(2026, 7, 22, 15, 30, tzinfo=timezone.utc)
    eid = build_event_id(now)
    assert eid.startswith("EVT-20260722-")
    seq = eid.rsplit("-", 1)[-1]
    assert len(seq) == 4
    assert seq.isdigit()


def test_build_event_id_increments_same_day(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("EVIDENCE_ROOT", str(tmp_path))
    # re-import counter state via reset helper if present
    from worker import evidence as evidence_mod

    evidence_mod._reset_counters()
    now = datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc)
    a = build_event_id(now, root=tmp_path)
    b = build_event_id(now, root=tmp_path)
    assert a == "EVT-20260722-0001"
    assert b == "EVT-20260722-0002"


def test_build_event_id_resets_on_new_day(tmp_path: Path):
    from worker import evidence as evidence_mod

    evidence_mod._reset_counters()
    d1 = datetime(2026, 7, 22, 23, 0, tzinfo=timezone.utc)
    d2 = datetime(2026, 7, 23, 1, 0, tzinfo=timezone.utc)
    a = build_event_id(d1, root=tmp_path)
    b = build_event_id(d2, root=tmp_path)
    assert a == "EVT-20260722-0001"
    assert b == "EVT-20260723-0001"
