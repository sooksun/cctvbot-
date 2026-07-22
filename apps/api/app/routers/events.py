import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
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


def _upsert_camera(db: Session, camera_info) -> Camera:
    camera = db.query(Camera).filter(Camera.camera_id == camera_info.camera_id).first()
    now = datetime.now(timezone.utc)
    if camera:
        camera.name = camera_info.name
        camera.stream_type = camera_info.stream_type
        camera.zone = camera_info.zone
        camera.is_online = True
        camera.last_seen_at = now
    else:
        camera = Camera(
            camera_id=camera_info.camera_id,
            name=camera_info.name,
            stream_type=camera_info.stream_type,
            zone=camera_info.zone,
            is_online=True,
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

    _upsert_camera(db, body.camera)

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
        evidence_json=body.evidence.model_dump(),
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
) -> list[EventResponse]:
    del user  # auth only
    q = db.query(Event)
    if status_filter:
        q = q.filter(Event.status == status_filter)
    if camera_id:
        q = q.filter(Event.camera_id == camera_id)
    if event_type:
        q = q.filter(Event.event_type == event_type)
    events = q.order_by(Event.created_at.desc()).all()
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

    if body.decision == "confirmed":
        token = (settings.line_channel_access_token or "").strip()
        line_user = (settings.line_user_id or "").strip()
        if not token or not line_user:
            logger.warning(
                "LINE notify skipped for %s: empty token or user_id", event_id
            )
            notifications["line_sent"] = False
        else:
            camera = (
                db.query(Camera).filter(Camera.camera_id == event.camera_id).first()
            )
            camera_name = camera.name if camera else event.camera_id
            text = build_line_text_for_event(event, camera_name)
            send_line_text(token, line_user, text)
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
    relative_path = evidence.get("relative_path", "")
    root = Path(settings.evidence_root)
    base = root / relative_path if relative_path else root / event_id

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
