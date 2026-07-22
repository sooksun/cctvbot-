"""Shared rule result type for event-worker rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


MESSAGE_TH_PREFIX = "พบเหตุที่ควรตรวจสอบ:"


@dataclass
class RuleResult:
    """Outcome of a single rule evaluation; None means no event."""

    event_type: str
    severity: str
    confidence: float
    camera_id: str
    message_th: str
    rule: dict[str, Any]
    objects: list[dict[str, Any]] = field(default_factory=list)
    started_at: datetime | None = None
    detected_at: datetime | None = None
    ended_at: datetime | None = None
    camera_name: str | None = None
    zone: str | None = None
    params: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.message_th.startswith(MESSAGE_TH_PREFIX):
            self.message_th = f"{MESSAGE_TH_PREFIX} {self.message_th.lstrip()}"
