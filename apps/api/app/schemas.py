from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class CameraInfo(BaseModel):
    camera_id: str
    name: str
    stream_type: str = "ip_rtsp"
    zone: str | None = None


class EvidenceInfo(BaseModel):
    thumb: str | None = None
    clip: str | None = None
    clip_before_seconds: int = 30
    clip_after_seconds: int = 30
    relative_path: str


class EventCreate(BaseModel):
    event_id: str
    schema_version: str = "1.0"
    source: str = "cctvbot"
    camera: CameraInfo
    event_type: str
    severity: str
    status: str = "pending_review"
    confidence: float
    started_at: datetime
    ended_at: datetime | None = None
    detected_at: datetime
    rule: dict
    objects: list[dict] = Field(default_factory=list)
    evidence: EvidenceInfo
    message_th: str


class ReviewRequest(BaseModel):
    decision: Literal["confirmed", "false_positive"]
    note: str | None = None


class StatusChangeRequest(BaseModel):
    status: Literal["action_taken", "closed"]
    note: str | None = None


class EventResponse(BaseModel):
    event_id: str
    camera_id: str
    event_type: str
    severity: str
    status: str
    confidence: float | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    detected_at: datetime | None = None
    rule: Any | None = None
    objects: Any | None = None
    evidence: Any | None = None
    review: Any | None = None
    notifications: Any | None = None
    message_th: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class EvidenceResponse(BaseModel):
    event_id: str
    evidence_root: str
    relative_path: str
    thumb: str | None = None
    clip: str | None = None
    clip_before_seconds: int | None = None
    clip_after_seconds: int | None = None
    paths: dict[str, str | None]


class CameraResponse(BaseModel):
    camera_id: str
    name: str
    stream_type: str
    zone: str | None = None
    is_online: bool
    enabled: bool = True
    last_seen_at: datetime | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class CameraUpsert(BaseModel):
    name: Optional[str] = None
    stream_type: Optional[str] = None
    zone: Optional[str] = None
    is_online: bool = True


class CameraConfigUpdate(BaseModel):
    name: Optional[str] = None
    zone: Optional[str] = None
    enabled: Optional[bool] = None
