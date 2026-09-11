from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .users import utcnow


class ThermalDetection(Base):
    """One raw NASA FIRMS hotspot (VIIRS / MODIS). A detection is an observation,
    never an incident by itself; events are formed by clustering."""

    __tablename__ = "thermal_detections"
    __table_args__ = (
        UniqueConstraint("latitude", "longitude", "acq_date", "acq_time", "satellite", name="uq_detection"),
        Index("idx_detection_latlon", "latitude", "longitude"),
        Index("idx_detection_acq", "acq_datetime"),
        Index("idx_detection_status", "data_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    acq_date: Mapped[date] = mapped_column(Date, nullable=False)
    acq_time: Mapped[str] = mapped_column(String(4), nullable=False)  # HHMM UTC
    acq_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)  # observation_timestamp
    satellite: Mapped[str] = mapped_column(String(16), default="")
    instrument: Mapped[str] = mapped_column(String(16), default="")
    confidence: Mapped[str] = mapped_column(String(8), default="")  # l/n/h or 0-100 (raw)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.5)  # normalised 0-1
    brightness: Mapped[float] = mapped_column(Float, default=0.0)  # bright_ti4 / brightness (K)
    brightness_2: Mapped[float] = mapped_column(Float, default=0.0)  # bright_ti5 / bright_t31 (K)
    frp: Mapped[float] = mapped_column(Float, default=0.0)  # MW
    scan: Mapped[float] = mapped_column(Float, default=0.0)
    track: Mapped[float] = mapped_column(Float, default=0.0)
    day_night: Mapped[str] = mapped_column(String(1), default="D")
    version: Mapped[str] = mapped_column(String(16), default="")
    source: Mapped[str] = mapped_column(String(48), default="FIRMS")  # FIRMS_PUBLIC_* | FIRMS_API_* | FIRMS_ARCHIVE_* | FIRMS_CSV
    data_status: Mapped[str] = mapped_column(String(12), default="HISTORICAL")  # LIVE | HISTORICAL
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)  # ingestion_timestamp
    ingestion_run_id: Mapped[int | None] = mapped_column(ForeignKey("ingestion_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("thermal_events.id", ondelete="SET NULL"), nullable=True, index=True)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(48), default="")
    mode: Mapped[str] = mapped_column(String(16), default="live")  # live | archive | csv
    data_status: Mapped[str] = mapped_column(String(12), default="LIVE")  # what newly ingested rows may become
    rows_received: Mapped[int] = mapped_column(Integer, default=0)
    rows_valid: Mapped[int] = mapped_column(Integer, default=0)
    rows_live: Mapped[int] = mapped_column(Integer, default=0)
    rows_historical: Mapped[int] = mapped_column(Integer, default=0)
    rows_duplicate: Mapped[int] = mapped_column(Integer, default=0)
    rows_rejected: Mapped[int] = mapped_column(Integer, default=0)
    rejection_reasons: Mapped[dict | None] = mapped_column(JSON, default=None)
    events_formed: Mapped[int] = mapped_column(Integer, default=0)
    events_touched: Mapped[int] = mapped_column(Integer, default=0)
    alerts_sent: Mapped[int] = mapped_column(Integer, default=0)
    latest_observation: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="running")
    message: Mapped[str] = mapped_column(Text, default="")
    feed_status: Mapped[dict | None] = mapped_column(JSON, default=None)


class DataSourceStatus(Base):
    """Freshness bookkeeping for every external dataset (source / source_timestamp / retrieved_at)."""

    __tablename__ = "data_source_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(64), default="")
    source_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="unknown")  # ok | failed | unavailable | not_configured
    detail: Mapped[str] = mapped_column(Text, default="")
    meta: Mapped[dict | None] = mapped_column(JSON, default=None)
