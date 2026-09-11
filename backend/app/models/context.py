"""GIS / reference context tables (OSM-derived facilities, roads, land cover,
population, weather, admin boundaries). Every row carries its `source`."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .users import utcnow


class _FacilityMixin:
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    osm_id: Mapped[str] = mapped_column(String(32), default="", index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    operator: Mapped[str] = mapped_column(String(200), default="")
    category: Mapped[str] = mapped_column(String(48), default="")
    subtype: Mapped[str] = mapped_column(String(48), default="")
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    state: Mapped[str] = mapped_column(String(64), default="", index=True)
    district: Mapped[str] = mapped_column(String(64), default="")
    tags: Mapped[dict | None] = mapped_column(JSON, default=None)
    source: Mapped[str] = mapped_column(String(48), default="reference_public")  # osm_overpass | reference_public
    data_quality: Mapped[str] = mapped_column(String(32), default="approximate")
    source_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class IndustrialFacility(_FacilityMixin, Base):
    __tablename__ = "industrial_facilities"
    __table_args__ = (Index("idx_ind_latlon", "latitude", "longitude"),)


class Refinery(_FacilityMixin, Base):
    __tablename__ = "refineries"
    __table_args__ = (Index("idx_ref_latlon", "latitude", "longitude"),)
    capacity_mmtpa: Mapped[float] = mapped_column(Float, default=0.0)


class PowerPlant(_FacilityMixin, Base):
    __tablename__ = "power_plants"
    __table_args__ = (Index("idx_pp_latlon", "latitude", "longitude"),)
    capacity_mw: Mapped[float] = mapped_column(Float, default=0.0)
    fuel: Mapped[str] = mapped_column(String(32), default="")


class Mine(_FacilityMixin, Base):
    __tablename__ = "mines"
    __table_args__ = (Index("idx_mine_latlon", "latitude", "longitude"),)
    resource: Mapped[str] = mapped_column(String(32), default="")


class GasFacility(_FacilityMixin, Base):
    __tablename__ = "gas_facilities"
    __table_args__ = (Index("idx_gas_latlon", "latitude", "longitude"),)
    flare: Mapped[int] = mapped_column(Integer, default=0)


class Road(Base):
    __tablename__ = "roads"
    __table_args__ = (Index("idx_road_latlon", "latitude", "longitude"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    osm_id: Mapped[str] = mapped_column(String(32), default="")
    name: Mapped[str] = mapped_column(String(128))
    ref: Mapped[str] = mapped_column(String(32), default="")
    highway: Mapped[str] = mapped_column(String(32), default="")  # motorway|trunk|primary|railway
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    geometry: Mapped[list | None] = mapped_column(JSON, default=None)  # [[lat,lon],...]
    state: Mapped[str] = mapped_column(String(64), default="")
    source: Mapped[str] = mapped_column(String(48), default="reference_public")


class LandCover(Base):
    """Land-cover observations / zones. Live rows come from OSM landuse polygons,
    reference rows from the bundled coarse zone file (labelled as such)."""

    __tablename__ = "land_cover"
    __table_args__ = (Index("idx_lc_latlon", "latitude", "longitude"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    radius_km: Mapped[float] = mapped_column(Float, default=5.0)
    land_cover_class: Mapped[str] = mapped_column(String(32))  # forest|cropland|built_up|industrial|bare|water|grassland|other
    name: Mapped[str] = mapped_column(String(128), default="")
    source: Mapped[str] = mapped_column(String(48), default="reference_zone")
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Population(Base):
    """Settlement gazetteer with population (Census 2011 reference values or OSM population tags)."""

    __tablename__ = "population"
    __table_args__ = (Index("idx_pop_latlon", "latitude", "longitude"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    osm_id: Mapped[str] = mapped_column(String(32), default="", index=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    settlement_type: Mapped[str] = mapped_column(String(32), default="town")  # city|town|village|industrial_area|suburb|hamlet
    state: Mapped[str] = mapped_column(String(64), index=True)
    district: Mapped[str] = mapped_column(String(64), default="")
    population: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None = population unknown
    population_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    radius_km: Mapped[float] = mapped_column(Float, default=3.0)
    source: Mapped[str] = mapped_column(String(48), default="census_2011_reference")
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WeatherObservation(Base):
    __tablename__ = "weather_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    weather_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # source time
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    wind_speed_kmh: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_direction_deg: Mapped[float | None] = mapped_column(Float, nullable=True)  # meteorological (from)
    wind_gust_kmh: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    precipitation_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    weather_source: Mapped[str] = mapped_column(String(48), default="")
    kind: Mapped[str] = mapped_column(String(16), default="current")  # current | archive
    raw: Mapped[dict | None] = mapped_column(JSON, default=None)


class AdminBoundary(Base):
    """States / UTs and districts (OpenStreetMap administrative relations)."""

    __tablename__ = "admin_boundaries"
    __table_args__ = (Index("idx_admin_level_parent", "level", "parent"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    osm_id: Mapped[str] = mapped_column(String(32), default="", index=True)
    name: Mapped[str] = mapped_column(String(96), index=True)
    code: Mapped[str] = mapped_column(String(16), default="")
    level: Mapped[str] = mapped_column(String(16), default="state")  # state | district
    parent: Mapped[str] = mapped_column(String(96), default="India", index=True)
    min_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    centroid_lat: Mapped[float] = mapped_column(Float)
    centroid_lon: Mapped[float] = mapped_column(Float)
    population_density: Mapped[float | None] = mapped_column(Float, nullable=True)  # persons/km2 (Census 2011) - states only
    geometry: Mapped[dict | None] = mapped_column(JSON, default=None)  # simplified GeoJSON polygon (states)
    source: Mapped[str] = mapped_column(String(48), default="osm")
    note: Mapped[str] = mapped_column(Text, default="")
