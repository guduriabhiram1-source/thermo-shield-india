"""Wind-aware exposure + potentially exposed areas + population exposure.

Model (documented, deliberately simple and transparent):
  * hazard radius   R_h  = f(peak FRP, classification, spread)     [1 .. 8 km]
  * downwind reach  R_dw = R_h * (1 + wind_speed/15)               [capped 25 km]
  * downwind sector = wedge centred on the direction the wind blows TO (half-angle 35°, 25° in strong wind)
  * exposure score  = distance decay × directional factor × intensity
Without wind data only the hazard circle is evaluated and the result says so.
Everything is an ESTIMATE. Area names come only from the gazetteer / OSM."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import AffectedArea, ThermalEvent
from ..utils.geo import angular_difference, circle_polygon, compass, haversine_km, sector_polygon
from .gis_service import FACILITY_TABLES, _nearby
from .population_service import _circle_overlap_fraction, population_in_radius, settlements_within

CLASS_HAZARD = {"INDUSTRIAL_FIRE": 1.3, "WILDFIRE": 1.4, "GAS_FLARE": 0.6, "REFINERY_ACTIVITY": 0.9, "PERSISTENT_INDUSTRIAL_HEAT": 0.7, "POWER_PLANT_ACTIVITY": 0.6,
                "MINING_ACTIVITY": 0.8, "AGRICULTURAL_BURN": 0.9, "OTHER_THERMAL_SOURCE": 0.8, "UNKNOWN": 0.6}


def hazard_radius_km(ev: ThermalEvent) -> float:
    base = 1.0 + 2.5 * min(ev.max_frp / 200.0, 1.5) + ev.spatial_spread_km * 0.4
    return round(max(1.0, min(8.0, base * CLASS_HAZARD.get(ev.classification, 0.8))), 2)


def exposure_level(score: float) -> str:
    if score >= 0.7:
        return "CRITICAL"
    if score >= 0.45:
        return "HIGH"
    if score >= 0.2:
        return "MODERATE"
    return "LOW"


def compute_exposure(db: Session, ev: ThermalEvent, weather: dict | None, gis: dict | None = None) -> dict:
    lat, lon = ev.latitude, ev.longitude
    w = weather or {}
    wind_ok = bool(w.get("available")) and w.get("wind_direction_deg") is not None
    wind_from = float(w.get("wind_direction_deg") or 0.0)
    wind_speed = float(w.get("wind_speed_kmh") or 0.0)
    wind_to = (wind_from + 180.0) % 360.0
    r_h = hazard_radius_km(ev)
    r_dw = round(min(25.0, r_h * (1.0 + wind_speed / 15.0)), 2) if wind_ok else r_h
    half_angle = (35.0 if wind_speed < 20 else 25.0) if wind_ok else 0.0
    intensity = min(1.0, 0.35 + ev.max_frp / 300.0)

    areas: list[dict] = []
    settlements = settlements_within(db, lat, lon, max(r_dw, r_h) + 8)
    for s in (gis or {}).get("settlements", []):  # live OSM places merged in gis_context
        if s.get("source") == "osm_overpass" and not any(haversine_km(s["latitude"], s["longitude"], x["latitude"], x["longitude"]) < 0.5 for x in settlements):
            settlements.append(s)
    for s in settlements:
        areas.append(_score_area(s["name"], s["type"], s.get("district", ""), s.get("state", ""), s["latitude"], s["longitude"], s["distance_km"], s["bearing"],
                                 s.get("population"), s.get("radius_km", 1.0), wind_ok, wind_to, half_angle, r_h, r_dw, intensity, s.get("source", ""), s.get("population_source")))
    for key, model in FACILITY_TABLES:
        for f in _nearby(db, model, lat, lon, max(r_dw, r_h) + 3):
            areas.append(_score_area(f["name"], f["category"] if f["category"] != "industrial" else "industrial_area", f["district"], f["state"], f["latitude"], f["longitude"],
                                     f["distance_km"], f["bearing"], None, 1.0, wind_ok, wind_to, half_angle, r_h, r_dw, intensity, f["source"], None))
    for f in (gis or {}).get("critical_infrastructure", []):
        areas.append(_score_area(f["name"] or f"{f['kind'].title()} (OSM, unnamed)", f["kind"], "", "", f["latitude"], f["longitude"], f["distance_km"], f["bearing"], None, 0.3,
                                 wind_ok, wind_to, half_angle, r_h, r_dw, intensity, "osm_overpass", None))
    areas = [a for a in areas if a["exposure_score"] > 0.02 or a["distance_km"] <= r_h]
    areas.sort(key=lambda a: (-a["exposure_score"], a["distance_km"]))
    areas = areas[:25]

    exposed_pop = sum(a["exposed_population"] or 0 for a in areas)
    has_pop = any(a["exposed_population"] is not None for a in areas)
    pop_circle = population_in_radius(db, lat, lon, r_h, ev.state)
    downwind_pop = sum(a["exposed_population"] or 0 for a in areas if a["downwind"])
    overall = max([a["exposure_score"] for a in areas], default=0.0)
    level = exposure_level(overall)
    by_district: dict[str, int] = {}
    for a in areas:
        if a["exposed_population"]:
            k = a["district"] or "District unavailable"
            by_district[k] = by_district.get(k, 0) + a["exposed_population"]
    exposure = {
        "wind": {"available": wind_ok, "speed_kmh": wind_speed if wind_ok else None, "direction_from_deg": wind_from if wind_ok else None,
                 "direction_from": compass(wind_from, 16) if wind_ok else None, "downwind_deg": round(wind_to, 1) if wind_ok else None,
                 "downwind": compass(wind_to, 16) if wind_ok else None, "weather_source": w.get("weather_source"), "weather_timestamp": w.get("weather_timestamp"),
                 "note": None if wind_ok else "Weather data unavailable - directional (downwind) exposure could not be evaluated; hazard circle only."},
        "hazard_radius_km": r_h, "downwind_reach_km": r_dw if wind_ok else None, "sector_half_angle_deg": half_angle if wind_ok else None,
        "hazard_circle": circle_polygon(lat, lon, r_h), "downwind_sector": sector_polygon(lat, lon, wind_to, half_angle, r_dw) if wind_ok else None,
        "exposure_level": level, "max_exposure_score": round(overall, 3), "affected_areas": areas,
        "population": {"available": has_pop, "exposed_estimate": int(exposed_pop) if has_pop else None, "downwind_estimate": int(downwind_pop) if (has_pop and wind_ok) else None,
                       "within_hazard_radius": pop_circle["total_estimate"], "within_hazard_radius_background": pop_circle["background_population"],
                       "by_settlement": [{"name": a["name"], "population": a["exposed_population"], "type": a["area_type"]} for a in areas if a["exposed_population"]],
                       "by_district": by_district, "settlements_without_population_data": [a["name"] for a in areas if a["area_type"] in ("city", "town", "village", "suburb", "hamlet") and a["population"] is None][:10],
                       "is_estimate": True, "note": "Estimated from Census 2011 reference populations / OSM population tags × footprint overlap × exposure factor. Not a headcount."},
        "model_note": "Directional exposure model: hazard circle + downwind wedge scaled by wind speed. Estimated potential exposure based on available wind and geographic data; not a plume dispersion simulation.",
        "is_estimate": True, "provenance": "ESTIMATE",
    }
    ev.exposure = exposure
    ev.exposed_population = int(exposed_pop) if has_pop else None
    ev.exposure_level = level
    db.query(AffectedArea).filter(AffectedArea.event_id == ev.id).delete()
    for a in areas:
        db.add(AffectedArea(event_id=ev.id, name=a["name"], area_type=a["area_type"], district=a["district"], state=a["state"], latitude=a["latitude"], longitude=a["longitude"],
                            distance_km=a["distance_km"], bearing_deg=a["bearing"], direction=a["direction"], downwind=1 if a["downwind"] else 0, exposure_level=a["exposure_level"],
                            exposure_score=a["exposure_score"], population=a["population"], exposed_population=a["exposed_population"], basis=a["basis"], source=a["source"]))
    return exposure


def _score_area(name, area_type, district, state, alat, alon, dist, bearing, population, radius_km, wind_ok, wind_to, half_angle, r_h, r_dw, intensity, source, population_source) -> dict:
    if wind_ok:
        diff = angular_difference(bearing, wind_to)
        downwind = diff <= half_angle * 1.3
        directional = 1.0 if diff <= half_angle else max(0.0, 1.0 - (diff - half_angle) / 60.0)
    else:
        downwind, directional = False, 0.5
    reach = r_dw if downwind else r_h * 1.5
    edge = max(0.0, dist - radius_km)
    if edge <= r_h:
        decay = 1.0
    elif edge <= reach:
        decay = 1.0 - (edge - r_h) / max(reach - r_h, 1e-6)
    else:
        decay = 0.0
    score = round(min(1.0, decay * (0.55 + 0.45 * directional) * intensity), 3)
    exposed = None
    if population is not None:
        overlap_h = _circle_overlap_fraction(dist, radius_km, r_h)
        overlap_r = _circle_overlap_fraction(dist, radius_km, reach)
        wedge_fraction = (2 * half_angle) / 360.0 if downwind else 0.35
        overlap = overlap_h + max(0.0, overlap_r - overlap_h) * wedge_fraction
        exposed = int(round(population * overlap * max(score, 0.15))) if score > 0 else 0
    return {"name": name, "area_type": area_type, "district": district, "state": state, "latitude": alat, "longitude": alon, "distance_km": round(dist, 2), "bearing": round(bearing, 1),
            "direction": compass(bearing, 8), "downwind": downwind, "exposure_score": score, "exposure_level": exposure_level(score) if score > 0 else "LOW",
            "population": int(population) if population is not None else None, "population_source": population_source, "exposed_population": exposed, "basis": "estimate", "source": source}
