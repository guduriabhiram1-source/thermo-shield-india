"""ORM models.

Latitude/longitude are plain columns (SQLite-compatible); on PostgreSQL a
PostGIS `geom geography(Point,4326)` column + GIST index is added to every
spatial table and kept in sync by a trigger (database.ensure_geometry_columns).
"""
from .users import User, EmailVerification, RefreshToken, AuditLog, utcnow
from .detections import ThermalDetection, IngestionRun, DataSourceStatus
from .events import ThermalEvent, EventObservation, HistoricalEvent
from .context import (
    IndustrialFacility, Refinery, PowerPlant, Mine, GasFacility, Road, LandCover, Population, WeatherObservation, AdminBoundary,
)
from .analysis import (
    EventClassification, RiskScore, AffectedArea, EventImage, EventReport, HumanVerification, TrainingSample, ModelVersion,
    Notification, AlertLog, AlertSettings,
)

__all__ = [
    "User", "EmailVerification", "RefreshToken", "AuditLog", "utcnow",
    "ThermalDetection", "IngestionRun", "DataSourceStatus",
    "ThermalEvent", "EventObservation", "HistoricalEvent",
    "IndustrialFacility", "Refinery", "PowerPlant", "Mine", "GasFacility", "Road", "LandCover", "Population", "WeatherObservation", "AdminBoundary",
    "EventClassification", "RiskScore", "AffectedArea", "EventImage", "EventReport", "HumanVerification", "TrainingSample", "ModelVersion",
    "Notification", "AlertLog", "AlertSettings",
]
