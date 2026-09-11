from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import AuditLog


def log_action(db: Session, actor: str, action: str, entity_type: str = "", entity_id="", details: dict | None = None, note: str = "") -> AuditLog:
    entry = AuditLog(actor=actor or "system", action=action, entity_type=entity_type, entity_id=str(entity_id), details=details, note=note)
    db.add(entry)
    return entry
