"""OpenStreetMap Overpass adapter: industrial facilities, power plants, mines,
storage, flares, hospitals, schools, residential areas, places (with population
tags where mapped), land-use polygons, roads and railways around a point.

Rate-limited (>= 1.5 s between requests), cached per 0.05° cell and radius,
2-minute circuit breaker on failure. Nothing is returned that OSM did not
return."""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

import httpx

from ...config import settings
from ...utils.geo import bearing_deg, compass, haversine_km

log = logging.getLogger("thermoshield.gis.osm")

_lock = threading.Lock()
_cache: dict = {}
_fail_until = 0.0
_last = 0.0
last_success_at: datetime | None = None

QUERY = """
[out:json][timeout:20];
(
  nwr(around:{r},{lat},{lon})["man_made"~"^(works|flare|storage_tank|chimney|kiln|petroleum_well|gasometer)$"];
  nwr(around:{r},{lat},{lon})["landuse"~"^(industrial|quarry|residential|forest|farmland|farmyard|orchard|plantation|meadow|grass|commercial|retail|brownfield|landfill)$"];
  nwr(around:{r},{lat},{lon})["natural"~"^(wood|scrub|grassland|heath|water|wetland|bare_rock|sand|scree)$"];
  nwr(around:{r},{lat},{lon})["power"~"^(plant|substation)$"];
  nwr(around:{r},{lat},{lon})["industrial"];
  nwr(around:{r},{lat},{lon})["amenity"~"^(hospital|school|college|university|fuel)$"];
  nwr(around:{r},{lat},{lon})["railway"="station"];
  node(around:{r},{lat},{lon})["place"~"^(city|town|village|suburb|hamlet|neighbourhood|locality)$"];
  way(around:{rr},{lat},{lon})["highway"~"^(motorway|trunk|primary|secondary)$"];
  way(around:{rr},{lat},{lon})["railway"="rail"];
);
out tags center 120;
"""

LANDUSE_CLASS = {"industrial": "industrial", "quarry": "bare", "residential": "built_up", "commercial": "built_up", "retail": "built_up", "brownfield": "industrial",
                 "landfill": "industrial", "forest": "forest", "farmland": "cropland", "farmyard": "cropland", "orchard": "cropland", "plantation": "cropland",
                 "meadow": "grassland", "grass": "grassland"}
NATURAL_CLASS = {"wood": "forest", "scrub": "grassland", "grassland": "grassland", "heath": "grassland", "water": "water", "wetland": "water", "bare_rock": "bare", "sand": "bare", "scree": "bare"}


def _kind(tags: dict) -> str | None:
    if tags.get("man_made") in ("works", "flare", "storage_tank", "chimney", "kiln", "petroleum_well", "gasometer"):
        return tags["man_made"]
    if tags.get("power") == "plant":
        return "power_plant"
    if tags.get("power") == "substation":
        return "substation"
    if tags.get("landuse") == "industrial" or tags.get("industrial"):
        return "industrial_area"
    if tags.get("landuse") == "quarry":
        return "quarry"
    if tags.get("landuse") in ("residential", "commercial", "retail"):
        return "residential"
    if tags.get("landuse") in LANDUSE_CLASS or tags.get("natural") in NATURAL_CLASS:
        return "landcover"
    if tags.get("amenity") in ("hospital", "school", "college", "university", "fuel"):
        return tags["amenity"]
    if tags.get("railway") == "station":
        return "railway_station"
    if tags.get("place"):
        return "place"
    if tags.get("highway"):
        return "road"
    if tags.get("railway") == "rail":
        return "railway"
    return None


def _fetch(lat: float, lon: float, radius_km: float, road_radius_km: float) -> list[dict] | None:
    global last_success_at
    q = QUERY.format(r=int(radius_km * 1000), rr=int(road_radius_km * 1000), lat=lat, lon=lon)
    try:
        r = httpx.post(settings.osm_overpass_url, data={"data": q}, timeout=40.0, headers={"User-Agent": settings.user_agent})
        r.raise_for_status()
        feats = []
        for el in r.json().get("elements", []):
            la = el.get("lat") or el.get("center", {}).get("lat")
            lo = el.get("lon") or el.get("center", {}).get("lon")
            if la is None:
                continue
            tags = el.get("tags", {})
            kind = _kind(tags)
            if kind is None:
                continue
            d = haversine_km(lat, lon, la, lo)
            b = bearing_deg(lat, lon, la, lo)
            pop = None
            if tags.get("population"):
                try:
                    pop = int(str(tags["population"]).replace(",", "").split(".")[0])
                except ValueError:
                    pop = None
            lc = LANDUSE_CLASS.get(tags.get("landuse", ""), NATURAL_CLASS.get(tags.get("natural", ""))) if kind in ("landcover", "residential", "industrial_area", "quarry") else None
            feats.append({
                "osm_id": f"{el['type']}/{el['id']}", "name": tags.get("name:en") or tags.get("name") or tags.get("operator") or "",
                "kind": kind, "latitude": la, "longitude": lo, "distance_km": round(d, 2), "bearing": round(b, 1), "direction": compass(b, 8),
                "population": pop, "population_date": tags.get("population:date"), "land_cover_class": lc or ("built_up" if kind == "residential" else "industrial" if kind in ("industrial_area",) else "bare" if kind == "quarry" else None),
                "tags": {k: v for k, v in tags.items() if k in ("name", "operator", "man_made", "landuse", "natural", "power", "amenity", "product", "industrial", "place", "highway", "ref", "railway", "plant:source", "plant:output:electricity", "resource", "substance", "content")},
                "source": "osm_overpass",
            })
        feats.sort(key=lambda f: f["distance_km"])
        last_success_at = datetime.now(timezone.utc)
        return feats
    except Exception as exc:
        log.warning("Overpass query failed: %s", exc)
        return None


def fetch_overpass(lat: float, lon: float, radius_km: float = 6.0, road_radius_km: float = 3.0) -> list[dict] | None:
    global _fail_until, _last
    key = (round(lat / 0.05) * 0.05, round(lon / 0.05) * 0.05, int(radius_km))
    if key in _cache:
        return _cache[key]
    with _lock:
        if key in _cache:
            return _cache[key]
        if time.time() < _fail_until:
            return None
        wait = 1.5 - (time.time() - _last)
        if wait > 0:
            time.sleep(wait)
        result = _fetch(lat, lon, radius_km, road_radius_km)
        _last = time.time()
        if result is None:
            _fail_until = time.time() + 120
        else:
            _cache[key] = result
            if len(_cache) > 5000:
                _cache.clear()
        return result
