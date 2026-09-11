from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .users import utcnow


class ThermalEvent(Base):
    """A spatio-temporal cluster of detections = one incident (TSI-IND-YYYY-NNNNNN)."""

    __tablename__ = "thermal_events"
    __table_args__ = (Index("idx_event_latlon", "latitude", "longitude"), Index("idx_event_status_risk", "data_status", "risk_level"))

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    bbox: Mapped[dict | None] = mapped_column(JSON, default=None)
    spatial_spread_km: Mapped[float] = mapped_column(Float, default=0.0)

    # location context (reverse geocoded)
    state: Mapped[str] = mapped_column(String(64), default="", index=True)
    district: Mapped[str] = mapped_column(String(64), default="", index=True)
    locality: Mapped[str] = mapped_column(String(128), default="")
    locality_distance_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    geocode_provider: Mapped[str] = mapped_column(String(48), default="")
    land_cover: Mapped[str] = mapped_column(String(32), default="unknown")
    population_density: Mapped[float | None] = mapped_column(Float, nullable=True)

    # temporal (first/last observed thermal activity)
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    duration_hours: Mapped[float] = mapped_column(Float, default=0.0)
    detection_count: Mapped[int] = mapped_column(Integer, default=0)
    live_detection_count: Mapped[int] = mapped_column(Integer, default=0)
    active_days: Mapped[int] = mapped_column(Integer, default=0)
    night_ratio: Mapped[float] = mapped_column(Float, default=0.0)

    # thermal signature (observed)
    max_frp: Mapped[float] = mapped_column(Float, default=0.0)
    mean_frp: Mapped[float] = mapped_column(Float, default=0.0)
    total_frp: Mapped[float] = mapped_column(Float, default=0.0)
    latest_frp: Mapped[float] = mapped_column(Float, default=0.0)
    frp_trend: Mapped[float] = mapped_column(Float, default=0.0)
    frp_growth_rate: Mapped[float] = mapped_column(Float, default=1.0)
    max_brightness: Mapped[float] = mapped_column(Float, default=0.0)
    mean_brightness: Mapped[float] = mapped_column(Float, default=0.0)
    mean_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    satellites: Mapped[str] = mapped_column(String(64), default="")
    instruments: Mapped[str] = mapped_column(String(64), default="")

    # persistence
    persistence_score: Mapped[float] = mapped_column(Float, default=0.0)
    persistence_class: Mapped[str] = mapped_column(String(16), default="ISOLATED", index=True)
    persistence_details: Mapped[dict | None] = mapped_column(JSON, default=None)

    # latest analysis snapshot (denormalised for fast listing)
    classification: Mapped[str] = mapped_column(String(40), default="UNKNOWN", index=True)
    classification_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    classification_method: Mapped[str] = mapped_column(String(32), default="")  # lightgbm | rules
    probable_cause: Mapped[str] = mapped_column(String(128), default="")
    risk_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    risk_level: Mapped[str] = mapped_column(String(16), default="LOW", index=True)
    risk_momentum: Mapped[float] = mapped_column(Float, default=0.0)
    risk_trend: Mapped[str] = mapped_column(String(16), default="STABLE")
    priority_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    priority_rank: Mapped[int] = mapped_column(Integer, default=0)
    exposed_population: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exposure_level: Mapped[str] = mapped_column(String(16), default="UNAVAILABLE")

    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)  # ACTIVE | INACTIVE | CLOSED
    data_status: Mapped[str] = mapped_column(String(12), default="HISTORICAL", index=True)  # LIVE | HISTORICAL
    ai_status: Mapped[str] = mapped_column(String(32), default="PENDING")  # PREDICTED | INSUFFICIENT_EVIDENCE | PENDING
    human_status: Mapped[str] = mapped_column(String(32), default="PENDING", index=True)  # PENDING | VERIFIED | CORRECTED | UNCERTAIN
    verified_classification: Mapped[str | None] = mapped_column(String(40), nullable=True)

    gis_context: Mapped[dict | None] = mapped_column(JSON, default=None)
    weather: Mapped[dict | None] = mapped_column(JSON, default=None)
    exposure: Mapped[dict | None] = mapped_column(JSON, default=None)
    evolution: Mapped[dict | None] = mapped_column(JSON, default=None)
    explanation: Mapped[dict | None] = mapped_column(JSON, default=None)
    risk_breakdown: Mapped[dict | None] = mapped_column(JSON, default=None)
    risk_change: Mapped[dict | None] = mapped_column(JSON, default=None)
    precautions: Mapped[dict | None] = mapped_column(JSON, default=None)
    satellite: Mapped[dict | None] = mapped_column(JSON, default=None)
    timeline: Mapped[list | None] = mapped_column(JSON, default=None)
    features: Mapped[dict | None] = mapped_column(JSON, default=None)
    provenance: Mapped[dict | None] = mapped_column(JSON, default=None)

    data_source: Mapped[str] = mapped_column(String(32), default="FIRMS")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    analysed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    enrichment_level: Mapped[str] = mapped_column(String(16), default="none")  # none | reference | live

    observations = relationship("EventObservation", back_populates="event", cascade="all, delete-orphan", order_by="EventObservation.observed_at")
    classifications = relationship("EventClassification", cascade="all, delete-orphan", order_by="EventClassification.created_at")
    risk_scores = relationship("RiskScore", cascade="all, delete-orphan", order_by="RiskScore.computed_at")
    affected_areas = relationship("AffectedArea", cascade="all, delete-orphan", order_by="AffectedArea.distance_km")
    images = relationship("EventImage", cascade="all, delete-orphan")
    reports = relationship("EventReport", cascade="all, delete-orphan", order_by="EventReport.created_at")
    verifications = relationship("HumanVerification", cascade="all, delete-orphan", order_by="HumanVerification.created_at")
    alert_logs = relationship("AlertLog", cascade="all, delete-orphan", order_by="AlertLog.created_at")


class EventObservation(Base):
    """Daily aggregate of an event (drives evolution charts + momentum)."""

    __tablename__ = "event_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("thermal_events.id", ondelete="CASCADE"), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    day: Mapped[str] = mapped_column(String(10))
    detections: Mapped[int] = mapped_column(Integer, default=0)
    max_frp: Mapped[float] = mapped_column(Float, default=0.0)
    sum_frp: Mapped[float] = mapped_column(Float, default=0.0)
    max_brightness: Mapped[float] = mapped_column(Float, default=0.0)
    spread_km: Mapped[float] = mapped_column(Float, default=0.0)
    night_detections: Mapped[int] = mapped_column(Integer, default=0)
    live_detections: Mapped[int] = mapped_column(Integer, default=0)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")

    event = relationship("ThermalEvent", back_populates="observations")


class HistoricalEvent(Base):
    """Compact archive of closed events (<= 12 months) used for recurrence features."""

    __tablename__ = "historical_events"
    __table_args__ = (Index("idx_hist_latlon", "latitude", "longitude"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[str] = mapped_column(String(32), default="", index=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    detection_count: Mapped[int] = mapped_column(Integer, default=0)
    max_frp: Mapped[float] = mapped_column(Float, default=0.0)
    classification: Mapped[str] = mapped_column(String(40), default="UNKNOWN")
    state: Mapped[str] = mapped_column(String(64), default="")
    district: Mapped[str] = mapped_column(String(64), default="")
    source: Mapped[str] = mapped_column(String(32), default="FIRMS")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
