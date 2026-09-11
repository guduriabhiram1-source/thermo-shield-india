"""Coordinate-based intelligence pipeline for one thermal event.

FIRMS cluster → reverse geocode → persistence → GIS + land cover → weather →
history → evolution → features → classification (+ explanation) → exposure →
risk + momentum → precautions → satellite evidence → priority → timeline."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import HISTORY_LIMIT, settings
from ..ml.features import build_features
from ..models import EventObservation, HistoricalEvent, ThermalEvent
from ..utils.geo import bbox_for_radius, haversine_km
from ..utils.timeutil import ensure_utc
from .classification_service import classify_event
from .evolution_service import build_timeline, compute_evolution
from .exposure_engine import compute_exposure
from .geocode_service import reverse_geocode
from .gis_service import gis_context
from .persistence_engine import compute_persistence
from .population_service import local_density
from .precautions_service import recommend_precautions
from .priority_service import priority_score
from .risk_engine import compute_risk
from .satellite_service import satellite_evidence
from .weather_service import get_weather, store_weather

log = logging.getLogger("thermoshield.pipeline")


def historical_count(db: Session, ev: ThermalEvent, radius_km: float = 10.0) -> int:
    """Other events / archived events within radius during the last 12 months (excluding this one)."""
    min_lat, min_lon, max_lat, max_lon = bbox_for_radius(ev.latitude, ev.longitude, radius_km)
    since = datetime.now(timezone.utc) - HISTORY_LIMIT
    n = 0
    for h in db.execute(select(HistoricalEvent).where(HistoricalEvent.latitude.between(min_lat, max_lat), HistoricalEvent.longitude.between(min_lon, max_lon), HistoricalEvent.last_detected_at >= since)).scalars().all():
        if haversine_km(ev.latitude, ev.longitude, h.latitude, h.longitude) <= radius_km:
            n += 1
    for o in db.execute(select(ThermalEvent).where(ThermalEvent.id != ev.id, ThermalEvent.latitude.between(min_lat, max_lat), ThermalEvent.longitude.between(min_lon, max_lon))).scalars().all():
        if haversine_km(ev.latitude, ev.longitude, o.latitude, o.longitude) <= radius_km:
            n += 1
    return n


def analyse_event(db: Session, ev: ThermalEvent, live: bool = True, with_images: bool = False, with_pdf: bool = False, actor: str = "system") -> ThermalEvent:
    """live=False → reference-tier context only (fast, offline); live=True → Nominatim + Overpass + weather + STAC provider calls."""
    geo = reverse_geocode(ev.latitude, ev.longitude, live=live)
    ev.state, ev.district, ev.locality = geo.get("state", ""), geo.get("district", ""), geo.get("locality", "")
    ev.locality_distance_km = geo.get("locality_distance_km")
    ev.geocode_provider = geo.get("provider", "")
    dens = local_density(db, ev.latitude, ev.longitude, ev.state)
    ev.population_density = dens.get("density_per_km2")

    persistence = compute_persistence(db, ev)

    gis = gis_context(db, ev.latitude, ev.longitude, ev.state, use_live_osm=live and ev.max_frp >= settings.live_osm_min_frp)
    gis["geocode"] = geo
    gis["density"] = dens
    ev.gis_context = gis
    ev.land_cover = gis["land_cover"]["class"] if gis["land_cover"].get("available") else "unknown"

    weather = get_weather(ev.latitude, ev.longitude, ev.last_detected_at, live=ev.data_status == "LIVE") if live else (ev.weather or {"available": False, "reason": "not requested in reference pass", "weather_source": None})
    if weather.get("available"):
        store_weather(db, ev.id, ev.latitude, ev.longitude, weather)
    ev.weather = weather

    hist = historical_count(db, ev)
    compute_evolution(db, ev)

    feats, prov = build_features(ev, gis, weather, persistence, hist)
    ev.features = feats
    classify_event(db, ev, feats, gis, persistence)

    exposure = compute_exposure(db, ev, weather, gis)
    rs = compute_risk(db, ev, feats, gis, weather, exposure, hist)
    latest_obs = db.execute(select(EventObservation).where(EventObservation.event_id == ev.id).order_by(EventObservation.day.desc())).scalars().first()
    if latest_obs:
        latest_obs.risk_score = rs.score

    ev.precautions = recommend_precautions(ev)
    if not ev.satellite or live:
        ev.satellite = satellite_evidence(ev.latitude, ev.longitude, ev.first_detected_at, ev.last_detected_at, search=False)
    ev.priority_score = priority_score(ev)
    ev.analysed_at = datetime.now(timezone.utc)
    ev.enrichment_level = "live" if live else "reference"
    ev.provenance = {
        "detections": "OBSERVED — NASA FIRMS", "location": f"OBSERVED — {geo.get('provider')}", "persistence": "CALCULATED", "gis_context": f"OBSERVED — {gis.get('provider')} ({gis.get('osm_live_status')})",
        "land_cover": gis["land_cover"].get("provenance", "UNAVAILABLE"), "weather": f"OBSERVED — {weather.get('weather_source')}" if weather.get("available") else "UNAVAILABLE",
        "classification": f"MODEL INFERENCE — {ev.classification_method}", "exposure": "ESTIMATE", "population": "ESTIMATE" if ev.exposed_population is not None else "UNAVAILABLE",
        "risk": "CALCULATED", "satellite": "OBSERVED (reference links) / not searched", "features": prov, "human_verification": ev.human_status,
    }
    build_timeline(db, ev)
    db.flush()
    if with_images:
        from .image_service import generate_event_images

        generate_event_images(db, ev)
    if with_pdf:
        from .pdf_service import build_pdf

        build_pdf(db, ev, generated_by=actor)
    db.flush()
    return ev


def reanalyse_all(db: Session, live: bool = False) -> int:
    events = db.execute(select(ThermalEvent)).scalars().all()
    n = 0
    for ev in events:
        try:
            analyse_event(db, ev, live=live)
            n += 1
            db.commit()
        except Exception:
            log.exception("Analysis failed for %s", ev.incident_id)
            db.rollback()
    return n


def archive_expired_events(db: Session) -> int:
    """Move events older than 12 months into the compact historical_events archive, then delete them."""
    cutoff = datetime.now(timezone.utc) - HISTORY_LIMIT
    old = db.execute(select(ThermalEvent).where(ThermalEvent.last_detected_at < cutoff)).scalars().all()
    for ev in old:
        db.add(HistoricalEvent(incident_id=ev.incident_id, latitude=ev.latitude, longitude=ev.longitude, first_detected_at=ev.first_detected_at, last_detected_at=ev.last_detected_at,
                               detection_count=ev.detection_count, max_frp=ev.max_frp, classification=ev.verified_classification or ev.classification, state=ev.state, district=ev.district))
        db.delete(ev)
    db.query(HistoricalEvent).filter(HistoricalEvent.last_detected_at < cutoff).delete(synchronize_session=False)
    db.flush()
    return len(old)


def event_count(db: Session) -> int:
    return int(db.execute(select(func.count(ThermalEvent.id))).scalar() or 0)
