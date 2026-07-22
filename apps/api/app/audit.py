from typing import Optional

from sqlalchemy.orm import Session

from app.models import AuditLog


def write_audit(
    db: Session,
    who: str,
    action: str,
    event_id: Optional[str] = None,
    ip: Optional[str] = None,
    note: Optional[str] = None,
) -> AuditLog:
    entry = AuditLog(
        who=who,
        action=action,
        event_id=event_id,
        ip=ip,
        note=note,
    )
    db.add(entry)
    db.flush()
    return entry
