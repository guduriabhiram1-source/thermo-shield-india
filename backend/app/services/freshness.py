"""Data freshness ledger: every external dataset records source / source_timestamp / retrieved_at."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import DataSourceStatus
from ..utils.timeutil import iso


def record(db: Session, source: str, provider: str, status: str, detail: str = "", source_timestamp: datetime | None = None, meta: dict | None = None) -> DataSourceStatus:
    row = db.execute(select(DataSourceStatus).where(DataSourceStatus.source == source)).scalar_one_or_none()
    if row is None:
        row = DataSourceStatus(source=source)
        db.add(row)
    row.provider = provider
    row.status = status
    row.detail = detail[:2000]
    row.retrieved_at = datetime.now(timezone.utc)
    if source_timestamp is not None:
        row.source_timestamp = source_timestamp
    if meta is not None:
        row.meta = meta
    db.flush()
    return row


def snapshot(db: Session) -> list[dict]:
    rows = db.execute(select(DataSourceStatus).order_by(DataSourceStatus.source)).scalars().all()
    return [{"source": r.source, "provider": r.provider, "status": r.status, "detail": r.detail, "source_timestamp": iso(r.source_timestamp),
             "retrieved_at": iso(r.retrieved_at), "meta": r.meta} for r in rows]
