"""Coordinate analysis: lat/lon -> full geographic + thermal context (real data only)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.security import get_current_user
from ..config import HISTORY_LIMIT
from ..database import get_db
from ..models import HistoricalEvent, ThermalDetection, ThermalEvent
from ..services.geocode_service import in_india, nearest_district, reverse_geocode
from ..services.gis_service import gis_context
from ..services.population_service import local_density, population_in_radius
from ..services.reference_data import districts_for_state
from ..services.risk_engine import risk_level
from ..services.serializers import detection_out, event_summary
from ..services.weather_service import get_weather
from ..utils.geo import bbox_for_radius, bearing_deg, compass, haversine_km
from ..utils.timeutil import iso

router = APIRouter(prefix="/api/location", tags=["location"], dependencies=[Depends(get_current_user)])


@router.get("/analyze")
def analyze_location(lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180), radius_km: float = Query(default=25.0, ge=1, le=100), live: bool = True, db: Session = Depends(get_db)):
    geo = reverse_geocode(lat, lon, live=live)
    gis = gis_context(db, lat, lon, geo.get("state", ""), radius_km=radius_km, use_live_osm=live)
    dens = local_density(db, lat, lon, geo.get("state", ""))
    pop = population_in_radius(db, lat, lon, min(radius_km, 15.0), geo.get("state", ""))
    weather = get_weather(lat, lon, live=True) if live else {"available": False, "reason": "live weather not requested"}
    min_lat, min_lon, max_lat, max_lon = bbox_for_radius(lat, lon, radius_km)
    live_events, hist_events = [], []
    for e in db.execute(select(ThermalEvent).where(ThermalEvent.latitude.between(min_lat, max_lat), ThermalEvent.longitude.between(min_lon, max_lon))).scalars().all():
        d = haversine_km(lat, lon, e.latitude, e.longitude)
        if d <= radius_km:
            s = event_summary(e)
            s["distance_km"] = round(d, 2)
            s["direction"] = compass(bearing_deg(lat, lon, e.latitude, e.longitude), 8)
            (live_events if e.data_status == "LIVE" else hist_events).append(s)
    live_events.sort(key=lambda x: x["distance_km"])
    hist_events.sort(key=lambda x: -(x["risk_score"] or 0))
    since = datetime.now(timezone.utc) - HISTORY_LIMIT
    archive = []
    for h in db.execute(select(HistoricalEvent).where(HistoricalEvent.latitude.between(min_lat, max_lat), HistoricalEvent.longitude.between(min_lon, max_lon), HistoricalEvent.last_detected_at >= since)).scalars().all():
        d = haversine_km(lat, lon, h.latitude, h.longitude)
        if d <= radius_km:
            archive.append({"incident_id": h.incident_id, "first_detected_at": iso(h.first_detected_at), "last_detected_at": iso(h.last_detected_at), "classification": h.classification, "max_frp": round(h.max_frp, 1),
                            "detection_count": h.detection_count, "distance_km": round(d, 2), "source": h.source})
    dets = []
    for d in db.execute(select(ThermalDetection).where(ThermalDetection.latitude.between(min_lat, max_lat), ThermalDetection.longitude.between(min_lon, max_lon),
                                                       ThermalDetection.acq_datetime >= datetime.now(timezone.utc) - timedelta(days=30))).scalars().all():
        dist = haversine_km(lat, lon, d.latitude, d.longitude)
        if dist <= radius_km:
            x = detection_out(d)
            x["distance_km"] = round(dist, 2)
            dets.append(x)
    dets.sort(key=lambda x: (x["distance_km"], x["observation_timestamp"] or ""))
    ind = gis.get("nearest_industrial_any")
    lc = gis["land_cover"]
    baseline = 10 + (25 if ind and ind["distance_km"] <= 3 else 10 if ind and ind["distance_km"] <= 10 else 0) + (10 if lc.get("available") and lc["class"] in ("forest", "industrial") else 0)
    from_events = max([c["risk_score"] * max(0.0, 1 - c["distance_km"] / radius_km) for c in live_events], default=0)
    score = round(max(baseline, from_events), 1)
    return {
        "query": {"latitude": lat, "longitude": lon, "radius_km": radius_km, "in_india": in_india(lat, lon), "analysed_at": datetime.now(timezone.utc).isoformat()},
        "location": geo, "district_candidates": [d["name"] for d in districts_for_state(geo.get("state", ""))][:400], "nearest_district_centre": nearest_district(lat, lon, geo.get("state")),
        "density": dens, "land_cover": lc, "gis": gis, "population": pop, "weather": weather,
        "live_events": live_events[:20], "historical_events": hist_events[:30], "historical_archive": archive[:30], "recent_detections_30d": dets[:200],
        "risk": {"score": score, "level": risk_level(score), "basis": "Max of context baseline and distance-decayed risk of live events within radius (estimate)", "provenance": "ESTIMATE"},
        "provenance": {"location": geo.get("provider"), "gis": gis.get("provider"), "land_cover": lc.get("provenance"), "weather": weather.get("weather_source") if weather.get("available") else "UNAVAILABLE", "population": "ESTIMATE (Census 2011 / OSM)"},
    }
