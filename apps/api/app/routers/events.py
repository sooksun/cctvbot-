import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.audit import write_audit
from app.auth import require_roles, verify_system_token
from app.config import settings
from app.db import get_db
from app.line_notify import build_line_text_for_event, send_line_text
from app.models import Camera, Event, User
from app.schemas import (
    EventCreate,
    EventResponse,
    EvidenceResponse,
    ReviewRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/events", tags=["events"])

# Allowed evidence file basenames for the file-serve endpoint.
_ALLOWED_EVIDENCE_NAMES = frozenset({"thumb.jpg", "clip.mp4", "event.json"})


def _event_to_response(event: Event) -> EventResponse:
    return EventResponse(
        event_id=event.event_id,
        camera_id=event.camera_id,
        event_type=event.event_type,
        severity=event.severity,
        status=event.status,
        confidence=event.confidence,
        started_at=event.started_at,
        ended_at=event.ended_at,
        detected_at=event.detected_at,
        rule=event.rule_json,
        objects=event.objects_json,
        evidence=event.evidence_json,
        review=event.review_json,
        notifications=event.notifications_json,
        message_th=event.message_th,
        created_at=event.created_at,
        updated_at=event.updated_at,
    )


def _client_ip(request: Request) -> Optional[str]:
    if request.client:
        return request.client.host
    return None


def _safe_evidence_dir(event_id: str, relative_path: str | None) -> Path:
    """
    Resolve evidence directory under evidence_root.

    Prefer ``relative_path == event_id`` convention. Reject absolute paths and
    ``..`` escapes so the resolved path always stays under evidence_root.
    """
    root = Path(settings.evidence_root).resolve()
    # Prefer event_id as directory name when relative_path is empty or only slashes.
    rel = (relative_path or "").strip().strip("/\\")
    if not rel:
        rel = event_id

    candidate = Path(rel)
    if candidate.is_absolute():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid evidence relative_path",
        )

    # Normalize and reject any parent-directory segments that escape root.
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid evidence relative_path",
        ) from None
    return resolved


def _upsert_camera(db: Session, camera_info, *, is_online: bool = True) -> Camera:
    camera = db.query(Camera).filter(Camera.camera_id == camera_info.camera_id).first()
    now = datetime.now(timezone.utc)
    if camera:
        camera.name = camera_info.name
        camera.stream_type = camera_info.stream_type
        camera.zone = camera_info.zone
        camera.is_online = is_online
        camera.last_seen_at = now
    else:
        camera = Camera(
            camera_id=camera_info.camera_id,
            name=camera_info.name,
            stream_type=camera_info.stream_type,
            zone=camera_info.zone,
            is_online=is_online,
            last_seen_at=now,
        )
        db.add(camera)
    return camera


@router.post(
    "",
    response_model=EventResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_system_token)],
)
def create_event(
    body: EventCreate,
    db: Annotated[Session, Depends(get_db)],
) -> EventResponse:
    existing = db.query(Event).filter(Event.event_id == body.event_id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Event already exists",
        )

    # camera_offline events mark the camera offline; other events mark online.
    online = body.event_type != "camera_offline"
    _upsert_camera(db, body.camera, is_online=online)

    # Sanitize relative_path on store: reject escapes; prefer event_id dir.
    evidence_dump = body.evidence.model_dump()
    rel = (evidence_dump.get("relative_path") or "").strip().strip("/\\")
    if not rel:
        rel = body.event_id
    try:
        _safe_evidence_dir(body.event_id, rel)
    except HTTPException:
        raise
    evidence_dump["relative_path"] = rel

    # thumb/clip must be bare filenames (no separators / .. escapes). They are
    # later joined onto the evidence dir and echoed as server paths by
    # GET .../evidence; reject traversal at the trusted-worker boundary.
    for _key in ("thumb", "clip"):
        _val = evidence_dump.get(_key)
        if _val is not None and Path(_val).name != _val:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid evidence {_key} filename",
            )

    event = Event(
        event_id=body.event_id,
        camera_id=body.camera.camera_id,
        event_type=body.event_type,
        severity=body.severity,
        status="pending_review",
        confidence=body.confidence,
        started_at=body.started_at,
        ended_at=body.ended_at,
        detected_at=body.detected_at,
        rule_json=body.rule,
        objects_json=body.objects,
        evidence_json=evidence_dump,
        review_json=None,
        notifications_json={"dashboard": True, "line_sent": False, "line_sent_at": None},
        message_th=body.message_th,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return _event_to_response(event)


@router.get("", response_model=list[EventResponse])
def list_events(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_roles("admin", "viewer"))],
    status_filter: Optional[str] = Query(None, alias="status"),
    camera_id: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[EventResponse]:
    del user  # auth only
    q = db.query(Event)
    if status_filter:
        q = q.filter(Event.status == status_filter)
    if camera_id:
        q = q.filter(Event.camera_id == camera_id)
    if event_type:
        q = q.filter(Event.event_type == event_type)
    events = (
        q.order_by(Event.created_at.desc()).limit(limit).offset(offset).all()
    )
    return [_event_to_response(e) for e in events]


@router.get("/{event_id}", response_model=EventResponse)
def get_event(
    event_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_roles("admin", "viewer"))],
) -> EventResponse:
    event = db.query(Event).filter(Event.event_id == event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    write_audit(
        db,
        who=user.username,
        action="view_event",
        event_id=event_id,
        ip=_client_ip(request),
    )
    db.commit()
    return _event_to_response(event)


@router.patch("/{event_id}/review", response_model=EventResponse)
def review_event(
    event_id: str,
    body: ReviewRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_roles("admin"))],
) -> EventResponse:
    event = db.query(Event).filter(Event.event_id == event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    if event.status != "pending_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Event is not pending review",
        )

    # Persist review first — LINE failure must not block confirmed status.
    now = datetime.now(timezone.utc)
    event.status = body.decision
    event.review_json = {
        "reviewed_by": user.username,
        "reviewed_at": now.isoformat(),
        "decision": body.decision,
        "note": body.note,
    }

    action = (
        "review_confirm" if body.decision == "confirmed" else "review_false_positive"
    )
    write_audit(
        db,
        who=user.username,
        action=action,
        event_id=event_id,
        ip=_client_ip(request),
        note=body.note,
    )

    notifications = dict(
        event.notifications_json
        or {"dashboard": True, "line_sent": False, "line_sent_at": None}
    )
    # Default: not sent until successful push.
    if body.decision == "confirmed":
        notifications["line_sent"] = False

    if body.decision == "confirmed":
        token = (settings.line_channel_access_token or "").strip()
        line_user = (settings.line_user_id or "").strip()
        if not token or not line_user:
            logger.warning(
                "LINE notify skipped for %s: empty token or user_id", event_id
            )
        else:
            camera = (
                db.query(Camera).filter(Camera.camera_id == event.camera_id).first()
            )
            camera_name = camera.name if camera else event.camera_id
            text = build_line_text_for_event(event, camera_name)
            try:
                send_line_text(token, line_user, text)
            except Exception:
                # Review already applied above; keep line_sent=false and commit.
                logger.exception(
                    "LINE notify failed for %s; review still committed", event_id
                )
            else:
                notifications["line_sent"] = True
                notifications["line_sent_at"] = now.isoformat()
                write_audit(
                    db,
                    who=user.username,
                    action="send_line",
                    event_id=event_id,
                    ip=_client_ip(request),
                    note="LINE text push after confirm",
                )

    event.notifications_json = notifications
    db.commit()
    db.refresh(event)
    return _event_to_response(event)


@router.get("/{event_id}/evidence", response_model=EvidenceResponse)
def get_evidence(
    event_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_roles("admin"))],
) -> EvidenceResponse:
    event = db.query(Event).filter(Event.event_id == event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    evidence = event.evidence_json or {}
    relative_path = evidence.get("relative_path") or event_id
    root = Path(settings.evidence_root).resolve()
    base = _safe_evidence_dir(event_id, relative_path)

    thumb_name = evidence.get("thumb")
    clip_name = evidence.get("clip")

    paths = {
        "thumb": str(base / thumb_name) if thumb_name else None,
        "clip": str(base / clip_name) if clip_name else None,
        "event_json": str(base / "event.json"),
        "directory": str(base),
    }

    write_audit(
        db,
        who=user.username,
        action="view_clip",
        event_id=event_id,
        ip=_client_ip(request),
        note="evidence metadata",
    )
    db.commit()

    return EvidenceResponse(
        event_id=event_id,
        evidence_root=str(root),
        relative_path=relative_path,
        thumb=thumb_name,
        clip=clip_name,
        clip_before_seconds=evidence.get("clip_before_seconds"),
        clip_after_seconds=evidence.get("clip_after_seconds"),
        paths=paths,
    )


@router.get("/{event_id}/evidence/file")
def get_evidence_file(
    event_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_roles("admin"))],
    name: str = Query(..., description="thumb.jpg | clip.mp4 | event.json"),
) -> FileResponse:
    """Serve an evidence file for admin (JWT). Path confined to event evidence dir."""
    event = db.query(Event).filter(Event.event_id == event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    # Only allow bare basenames from the allow-list (no path separators).
    safe_name = Path(name).name
    if safe_name != name or safe_name not in _ALLOWED_EVIDENCE_NAMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid evidence file name",
        )

    evidence = event.evidence_json or {}
    relative_path = evidence.get("relative_path") or event_id
    base = _safe_evidence_dir(event_id, relative_path)
    file_path = (base / safe_name).resolve()
    try:
        file_path.relative_to(base.resolve())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid evidence file name",
        ) from None

    if not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Evidence file not found"
        )

    write_audit(
        db,
        who=user.username,
        action="view_clip",
        event_id=event_id,
        ip=_client_ip(request),
        note=f"evidence file {safe_name}",
    )
    db.commit()

    media = {
        "thumb.jpg": "image/jpeg",
        "clip.mp4": "video/mp4",
        "event.json": "application/json",
    }.get(safe_name, "application/octet-stream")
    return FileResponse(path=file_path, media_type=media, filename=safe_name)
