"""Analysis outputs: classifications, risk, exposure, images, reports, human
verification, training data, model registry, notifications, alert logs."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .users import utcnow


class EventClassification(Base):
    __tablename__ = "event_classifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("thermal_events.id", ondelete="CASCADE"), index=True)
    model_name: Mapped[str] = mapped_column(String(64), default="rules")  # lightgbm | rules
    model_version: Mapped[str] = mapped_column(String(32), default="")
    classification: Mapped[str] = mapped_column(String(40))
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    probabilities: Mapped[dict | None] = mapped_column(JSON, default=None)
    shap_values: Mapped[dict | None] = mapped_column(JSON, default=None)  # feature -> contribution (SHAP when a model exists)
    contributions: Mapped[dict | None] = mapped_column(JSON, default=None)  # feature -> contribution (rule weights when no model)
    feature_importance: Mapped[dict | None] = mapped_column(JSON, default=None)
    evidence: Mapped[list | None] = mapped_column(JSON, default=None)
    uncertainty: Mapped[str] = mapped_column(String(512), default="")
    human_explanation: Mapped[str] = mapped_column(Text, default="")
    probable_cause: Mapped[dict | None] = mapped_column(JSON, default=None)
    insufficient_evidence: Mapped[int] = mapped_column(Integer, default=0)
    ml_model_available: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RiskScore(Base):
    __tablename__ = "risk_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("thermal_events.id", ondelete="CASCADE"), index=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    score: Mapped[float] = mapped_column(Float)
    level: Mapped[str] = mapped_column(String(16))
    previous_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    momentum: Mapped[float] = mapped_column(Float, default=0.0)
    trend: Mapped[str] = mapped_column(String(16), default="STABLE")
    components: Mapped[dict | None] = mapped_column(JSON, default=None)
    change_reasons: Mapped[list | None] = mapped_column(JSON, default=None)
    priority_score: Mapped[float] = mapped_column(Float, default=0.0)
    data_status: Mapped[str] = mapped_column(String(12), default="HISTORICAL")


class AffectedArea(Base):
    __tablename__ = "affected_areas"
    __table_args__ = (Index("idx_aff_latlon", "latitude", "longitude"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("thermal_events.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    area_type: Mapped[str] = mapped_column(String(32), default="settlement")
    district: Mapped[str] = mapped_column(String(64), default="")
    state: Mapped[str] = mapped_column(String(64), default="")
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    distance_km: Mapped[float] = mapped_column(Float)
    bearing_deg: Mapped[float] = mapped_column(Float, default=0.0)
    direction: Mapped[str] = mapped_column(String(4), default="")
    downwind: Mapped[int] = mapped_column(Integer, default=0)
    exposure_level: Mapped[str] = mapped_column(String(16), default="LOW")
    exposure_score: Mapped[float] = mapped_column(Float, default=0.0)
    population: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exposed_population: Mapped[int | None] = mapped_column(Integer, nullable=True)
    basis: Mapped[str] = mapped_column(String(32), default="estimate")
    source: Mapped[str] = mapped_column(String(48), default="")


class EventImage(Base):
    __tablename__ = "event_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("thermal_events.id", ondelete="CASCADE"), index=True)
    image_type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(128), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    file_path: Mapped[str] = mapped_column(String(512), default="")
    url: Mapped[str] = mapped_column(String(1024), default="")
    source: Mapped[str] = mapped_column(String(48), default="generated")  # generated | sentinel-2 | nasa_gibs | none
    is_available: Mapped[int] = mapped_column(Integer, default=1)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    meta: Mapped[dict | None] = mapped_column(JSON, default=None)


class EventReport(Base):
    __tablename__ = "event_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("thermal_events.id", ondelete="CASCADE"), index=True)
    incident_id: Mapped[str] = mapped_column(String(32), index=True)
    file_name: Mapped[str] = mapped_column(String(128))
    file_path: Mapped[str] = mapped_column(String(512))
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    pages: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="generated")  # generating | generated | failed | stale
    generated_by: Mapped[str] = mapped_column(String(254), default="system")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    snapshot: Mapped[dict | None] = mapped_column(JSON, default=None)


class HumanVerification(Base):
    __tablename__ = "human_verifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("thermal_events.id", ondelete="CASCADE"), index=True)
    analyst_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    analyst: Mapped[str] = mapped_column(String(254))
    action: Mapped[str] = mapped_column(String(16))  # CONFIRM | CORRECT | UNCERTAIN
    original_prediction: Mapped[str] = mapped_column(String(40))
    original_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    verified_classification: Mapped[str | None] = mapped_column(String(40), nullable=True)
    probable_cause: Mapped[str] = mapped_column(String(128), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TrainingSample(Base):
    """Human-verified records -> training data for the LightGBM classifier."""

    __tablename__ = "training_samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    incident_id: Mapped[str] = mapped_column(String(32), default="")
    features: Mapped[dict] = mapped_column(JSON)
    verified_label: Mapped[str] = mapped_column(String(40))
    analyst_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    analyst: Mapped[str] = mapped_column(String(254), default="")
    verification_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    model_version: Mapped[str] = mapped_column(String(32), default="")  # model version used when the prediction was made
    origin: Mapped[str] = mapped_column(String(32), default="human_verified")


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[str] = mapped_column(String(32), unique=True)
    algorithm: Mapped[str] = mapped_column(String(32), default="LightGBM")
    file_path: Mapped[str] = mapped_column(String(512), default="")
    training_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    training_samples: Mapped[int] = mapped_column(Integer, default=0)
    accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    precision: Mapped[float | None] = mapped_column(Float, nullable=True)
    recall: Mapped[float | None] = mapped_column(Float, nullable=True)
    f1: Mapped[float | None] = mapped_column(Float, nullable=True)
    validation_dataset: Mapped[dict | None] = mapped_column(JSON, default=None)
    metrics: Mapped[dict | None] = mapped_column(JSON, default=None)
    feature_importance: Mapped[dict | None] = mapped_column(JSON, default=None)
    is_production: Mapped[int] = mapped_column(Integer, default=0)
    validated: Mapped[int] = mapped_column(Integer, default=0)
    promoted_by: Mapped[str] = mapped_column(String(254), default="")
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")


class Notification(Base):
    """In-app notification centre entries (web channel)."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    incident_id: Mapped[str] = mapped_column(String(32), default="")
    severity: Mapped[str] = mapped_column(String(16), default="HIGH")
    data_status: Mapped[str] = mapped_column(String(12), default="LIVE")
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict | None] = mapped_column(JSON, default=None)
    acknowledged: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class AlertLog(Base):
    """Every alert decision (sent / suppressed / failed) - the deduplication ledger."""

    __tablename__ = "alert_logs"
    __table_args__ = (Index("idx_alert_event_level", "event_id", "risk_level"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("thermal_events.id", ondelete="CASCADE"), index=True)
    incident_id: Mapped[str] = mapped_column(String(32), default="", index=True)
    alert_type: Mapped[str] = mapped_column(String(32), default="LIVE_EMAIL")
    risk_level: Mapped[str] = mapped_column(String(16))
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    data_status: Mapped[str] = mapped_column(String(12), default="LIVE")
    data_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # latest observation covered by this alert
    recipient: Mapped[str] = mapped_column(String(1024), default="")
    status: Mapped[str] = mapped_column(String(16), default="sent")  # sent | suppressed | failed | not_configured
    reason: Mapped[str] = mapped_column(String(256), default="")
    subject: Mapped[str] = mapped_column(String(256), default="")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    payload: Mapped[dict | None] = mapped_column(JSON, default=None)


class AlertSettings(Base):
    """Single-row admin-editable alert configuration (seeded from environment defaults)."""

    __tablename__ = "alert_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    live_alerts_enabled: Mapped[int] = mapped_column(Integer, default=1)
    high_enabled: Mapped[int] = mapped_column(Integer, default=1)
    critical_enabled: Mapped[int] = mapped_column(Integer, default=1)
    recipients: Mapped[str] = mapped_column(Text, default="")  # comma separated
    cooldown_hours: Mapped[int] = mapped_column(Integer, default=12)
    min_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    updated_by: Mapped[str] = mapped_column(String(254), default="system")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
