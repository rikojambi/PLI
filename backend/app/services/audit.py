"""Central audit logging service."""
from fastapi import Request
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models.core import AuditLog, User


def log_audit(
    db: Session,
    actor: User | None,
    action: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    details: dict | None = None,
    request: Request | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_id=actor.id if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details_json=details or {},
        ip_address=request.client.host if request and request.client else None,
        created_at=utcnow(),
    )
    db.add(entry)
    db.flush()
    return entry
