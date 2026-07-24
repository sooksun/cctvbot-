from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import require_roles, verify_system_token
from app.db import get_db
from app.models import Camera, User
from app.schemas import CameraResponse, CameraUpsert

router = APIRouter(prefix="/api/cameras", tags=["cameras"])


@router.get("", response_model=list[CameraResponse])
def list_cameras(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_roles("admin", "viewer"))],
) -> list[CameraResponse]:
    del user  # auth only
    cameras = db.query(Camera).order_by(Camera.camera_id.asc()).all()
    return [
        CameraResponse(
            camera_id=c.camera_id,
            name=c.name,
            stream_type=c.stream_type,
            zone=c.zone,
            is_online=c.is_online,
            last_seen_at=c.last_seen_at,
            created_at=c.created_at,
        )
        for c in cameras
    ]


@router.put(
    "/{camera_id}",
    response_model=CameraResponse,
    dependencies=[Depends(verify_system_token)],
)
def upsert_camera(
    camera_id: str,
    body: CameraUpsert,
    db: Annotated[Session, Depends(get_db)],
) -> CameraResponse:
    camera = db.query(Camera).filter(Camera.camera_id == camera_id).first()
    now = datetime.now(timezone.utc)

    if camera:
        if body.name is not None:
            camera.name = body.name
        if body.stream_type is not None:
            camera.stream_type = body.stream_type
        if body.zone is not None:
            camera.zone = body.zone
        camera.is_online = body.is_online
        camera.last_seen_at = now
    else:
        camera = Camera(
            camera_id=camera_id,
            name=body.name or camera_id,
            stream_type=body.stream_type or "ip_rtsp",
            zone=body.zone,
            is_online=body.is_online,
            last_seen_at=now,
        )
        db.add(camera)

    db.commit()
    db.refresh(camera)
    return CameraResponse(
        camera_id=camera.camera_id,
        name=camera.name,
        stream_type=camera.stream_type,
        zone=camera.zone,
        is_online=camera.is_online,
        last_seen_at=camera.last_seen_at,
        created_at=camera.created_at,
    )
