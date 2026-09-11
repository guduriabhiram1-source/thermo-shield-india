"""Reverse geocoding: coordinates -> state / district / nearest locality.

* `in_india`       - point-in-polygon against the OSM state polygons (+ island boxes)
* REFERENCE tier   - OSM state polygon + nearest OSM district centre + Census gazetteer (always available, offline)
* LIVE tier        - Nominatim reverse lookup (1 request/second policy, cached, circuit breaker)."""
from __future__ import annotations

import logging
import threading
import time

import httpx

from ..config import settings
from ..utils.geo import bearing_deg, compass, haversine_km
from .reference_data import load_districts, load_settlements, load_states, state_for_point

log = logging.getLogger("thermoshield.geocode")

INDIA_BBOX = (6.0, 68.0, 37.5, 97.5)
ISLAND_BOXES = [(6.7, 92.2, 13.7, 94.3), (8.2, 71.7, 12.3, 74.0)]  # Andaman & Nicobar, Lakshadweep
STATE_ALIASES = {"NCT of Delhi": "Delhi", "National Capital Territory of Delhi": "Delhi", "Orissa": "Odisha", "Pondicherry": "Puducherry",
                 "Uttaranchal": "Uttarakhand", "Jammu & Kashmir": "Jammu and Kashmir", "Dadra and Nagar Haveli": "Dadra and Nagar Haveli and Daman and Diu",
                 "Daman and Diu": "Dadra and Nagar Haveli and Daman and Diu", "Andaman and Nicobar": "Andaman and Nicobar Islands"}


def in_india_bbox(lat: float, lon: float) -> bool:
    return INDIA_BBOX[0] <= lat <= INDIA_BBOX[2] and INDIA_BBOX[1] <= lon <= INDIA_BBOX[3]


def in_india(lat: float, lon: float) -> bool:
    if not in_india_bbox(lat, lon):
        return False
    if any(b[0] <= lat <= b[2] and b[1] <= lon <= b[3] for b in ISLAND_BOXES):
        return True
    return state_for_point(lat, lon) is not None


def nearest_district(lat: float, lon: float, state: str | None = None) -> dict | None:
    cands = [d for d in load_districts() if (not state or d["state"] == state)]
    if not cands:
        return None
    best = min(cands, key=lambda d: haversine_km(lat, lon, d["lat"], d["lon"]))
    return {**best, "distance_km": round(haversine_km(lat, lon, best["lat"], best["lon"]), 1)}


def nearest_settlements(lat: float, lon: float, limit: int = 5, max_km: float = 150.0) -> list[dict]:
    rows = []
    for r in load_settlements():
        d = haversine_km(lat, lon, r["latitude"], r["longitude"])
        if d <= max_km:
            rows.append({**r, "distance_km": round(d, 2), "bearing": round(bearing_deg(lat, lon, r["latitude"], r["longitude"]), 1)})
    rows.sort(key=lambda r: r["distance_km"])
    return rows[:limit]


def reverse_geocode_reference(lat: float, lon: float) -> dict:
    st = state_for_point(lat, lon)
    if st is None:
        st = min(load_states(), key=lambda s: haversine_km(lat, lon, s["centroid"][0], s["centroid"][1]))
        inside = False
    else:
        inside = True
    near = nearest_settlements(lat, lon, limit=3)
    dist = nearest_district(lat, lon, st["name"])
    result = {
        "country": "India" if in_india(lat, lon) else "Outside India outline",
        "state": st["name"], "state_code": st["code"], "state_match": "polygon" if inside else "nearest",
        "district": dist["name"] if dist else "", "district_basis": f"nearest OSM district centre ({dist['distance_km']} km)" if dist else "unavailable",
        "locality": "", "locality_distance_km": None, "locality_direction": "", "locality_type": "",
        "population_density": st.get("density"),
        "provider": "osm_polygon+gazetteer", "precision": "approximate",
    }
    if near:
        n = near[0]
        result.update({"locality": n["name"], "locality_distance_km": n["distance_km"], "locality_type": n["settlement_type"],
                       "locality_direction": compass(bearing_deg(n["latitude"], n["longitude"], lat, lon), 8)})
    return result


# --- Nominatim (live) ---------------------------------------------------------
_nom_lock = threading.Lock()
_nom_last = 0.0
_nom_cache: dict[tuple[float, float], dict | None] = {}
_nom_fail_until = 0.0


def reverse_geocode_nominatim(lat: float, lon: float) -> dict | None:
    global _nom_last, _nom_fail_until
    key = (round(lat, 3), round(lon, 3))
    if key in _nom_cache:
        return _nom_cache[key]
    with _nom_lock:
        if key in _nom_cache:
            return _nom_cache[key]
        if time.time() < _nom_fail_until:
            return None
        wait = 1.05 - (time.time() - _nom_last)
        if wait > 0:
            time.sleep(wait)
        try:
            r = httpx.get(f"{settings.nominatim_url}/reverse", params={"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 14, "accept-language": "en"},
                          headers={"User-Agent": settings.user_agent}, timeout=10.0)
            _nom_last = time.time()
            r.raise_for_status()
            j = r.json()
            a = j.get("address", {})
            state = STATE_ALIASES.get(a.get("state", ""), a.get("state", ""))
            district = a.get("state_district") or a.get("county") or a.get("district", "")
            for suffix in (" District", " district", " Zila"):
                if district.endswith(suffix):
                    district = district[: -len(suffix)]
            locality = a.get("city") or a.get("town") or a.get("village") or a.get("suburb") or a.get("hamlet") or a.get("municipality") or a.get("neighbourhood", "")
            ltype = next((k for k in ("city", "town", "village", "suburb", "hamlet", "municipality", "neighbourhood") if a.get(k)), "")
            out = {"state": state, "district": district, "locality": locality, "locality_type": ltype, "road": a.get("road", ""),
                   "country_code": a.get("country_code", ""), "display_name": j.get("display_name", ""), "osm_id": f"{j.get('osm_type')}/{j.get('osm_id')}",
                   "provider": "nominatim", "precision": "osm"}
            _nom_cache[key] = out
            return out
        except Exception as exc:
            _nom_last = time.time()
            _nom_fail_until = time.time() + 60
            log.warning("Nominatim reverse geocode failed: %s", exc)
            return None


def reverse_geocode(lat: float, lon: float, live: bool = True) -> dict:
    base = reverse_geocode_reference(lat, lon)
    if live and settings.osm_provider == "overpass" and settings.nominatim_enabled:
        nom = reverse_geocode_nominatim(lat, lon)
        if nom and nom.get("country_code", "in") == "in":
            known = {s["name"] for s in load_states()}
            if nom.get("state") in known:
                base["state"] = nom["state"]
                st = next(s for s in load_states() if s["name"] == nom["state"])
                base["state_code"], base["population_density"] = st["code"], st.get("density")
            if nom.get("district"):
                base["district"] = nom["district"]
                base["district_basis"] = "OSM (Nominatim)"
            if nom.get("locality"):
                base["locality"] = nom["locality"]
                base["locality_type"] = nom.get("locality_type", "")
                base["locality_distance_km"] = 0.0
                base["locality_direction"] = ""
            base["road"] = nom.get("road", "")
            base["display_name"] = nom.get("display_name", "")
            base["provider"] = "nominatim+osm_polygon"
            base["precision"] = "osm"
    return base


def data_freshness_note() -> str:
    return "OSM boundaries: OpenStreetMap ODbL (admin relations); districts admin_level=5"
