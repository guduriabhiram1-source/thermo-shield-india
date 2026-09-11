"""Incident ID generation: TSI-IND-YYYY-NNNNNN (backend generated, monotonic per year)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session


def next_incident_id(db: Session, year: int | None = None) -> str:
    from ..models import ThermalEvent

    year = year or datetime.now(timezone.utc).year
    prefix = f"TSI-IND-{year}-"
    last = db.execute(select(func.max(ThermalEvent.incident_id)).where(ThermalEvent.incident_id.like(f"{prefix}%"))).scalar()
    seq = int(last.split("-")[-1]) + 1 if last else 1
    return f"{prefix}{seq:06d}"
