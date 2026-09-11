"""GIS context enrichment around a coordinate.

Two tiers, both from real datasets:
  * reference tier - bundled public facility list, Census-2011 settlement gazetteer, coarse highway polylines (always available)
  * live tier      - OSM Overpass features within a few km (facilities, residential areas, hospitals, schools, roads, railways, land use)
Only entities actually present in a dataset are ever returned."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import GasFacility, IndustrialFacility, Mine, PowerPlant, Refinery, Road
from ..utils.geo import bbox_for_radius, bearing_deg, compass, haversine_km, point_to_polyline_km
from .gis.osm import fetch_overpass
from .landcover_service import classify_landcover
from .population_service import settlements_within

log = logging.getLogger("thermoshield.gis")

FACILITY_TABLES = [("refineries", Refinery), ("power_plants", PowerPlant), ("mines", Mine), ("gas_facilities", GasFacility), ("industrial_facilities", IndustrialFacility)]
KIND_TO_CATEGORY = {"works": ("industrial_facilities", "industrial", "works"), "industrial_area": ("industrial_facilities", "industrial", "industrial_area"),
                    "quarry": ("mines", "mine", "quarry"), "power_plant": ("power_plants", "power_plant", "plant"), "flare": ("gas_facilities", "gas_facility", "flare"),
                    "petroleum_well": ("gas_facilities", "gas_facility", "petroleum_well"), "gasometer": ("gas_facilities", "gas_facility", "gasometer"),
                    "storage_tank": ("industrial_facilities", "storage", "tank_farm"), "chimney": ("industrial_facilities", "industrial", "chimney"), "kiln": ("industrial_facilities", "industrial", "kiln")}


def _nearby(db: Session, model, lat: float, lon: float, radius_km: float) -> list[dict]:
    min_lat, min_lon, max_lat, max_lon = bbox_for_radius(lat, lon, radius_km)
    rows = db.execute(select(model).where(model.latitude.between(min_lat, max_lat), model.longitude.between(min_lon, max_lon))).scalars().all()
    out = []
    for r in rows:
        d = haversine_km(lat, lon, r.latitude, r.longitude)
        if d <= radius_km:
            b = bearing_deg(lat, lon, r.latitude, r.longitude)
            item = {"id": r.id, "osm_id": r.osm_id, "name": r.name, "operator": r.operator, "category": r.category, "subtype": r.subtype, "latitude": r.latitude, "longitude": r.longitude,
                    "state": r.state, "district": r.district, "distance_km": round(d, 2), "bearing": round(b, 1), "direction": compass(b, 8), "source": r.source, "data_quality": r.data_quality}
            for extra in ("capacity_mmtpa", "capacity_mw", "fuel", "resource", "flare"):
                if hasattr(r, extra):
                    item[extra] = getattr(r, extra)
            out.append(item)
    out.sort(key=lambda x: x["distance_km"])
    return out


def nearest_roads_reference(db: Session, lat: float, lon: float) -> dict:
    roads = db.execute(select(Road)).scalars().all()
    best_road, best_rail = None, None
    for r in roads:
        d = point_to_polyline_km(lat, lon, r.geometry or [[r.latitude, r.longitude]])
        item = {"name": r.name, "ref": r.ref, "type": r.highway, "distance_km": round(d, 2), "source": r.source, "precision": "coarse polyline"}
        if r.highway == "railway":
            if best_rail is None or d < best_rail["distance_km"]:
                best_rail = item
        elif best_road is None or d < best_road["distance_km"]:
            best_road = item
    return {"nearest_road": best_road, "nearest_railway": best_rail}


def gis_context(db: Session, lat: float, lon: float, state: str = "", radius_km: float | None = None, use_live_osm: bool = True) -> dict:
    radius_km = radius_km or settings.gis_search_km
    live_requested = use_live_osm and settings.osm_provider == "overpass"
    ctx: dict = {"search_radius_km": radius_km, "provider": "reference_gazetteer", "osm_live_status": "not_requested"}
    nearest: dict = {}
    for key, model in FACILITY_TABLES:
        items = _nearby(db, model, lat, lon, radius_km)
        ctx[key] = items[:8]
        nearest[key] = items[0] if items else None
    ctx.update(nearest_roads_reference(db, lat, lon))
    settlements = settlements_within(db, lat, lon, radius_km)
    live: list[dict] | None = None
    if live_requested:
        live = fetch_overpass(lat, lon, min(radius_km, 6.0))
        if live is None:
            ctx["osm_live_status"] = "unavailable (Overpass request failed or rate-limited)"
        else:
            ctx["osm_live_status"] = f"ok ({len(live)} features within 6 km)"
            ctx["provider"] = "osm_overpass+reference_gazetteer"
            ctx["osm_live"] = [f for f in live if f["kind"] not in ("landcover",)][:80]
            ctx["osm_retrieved_at"] = datetime.now(timezone.utc).isoformat()
            _merge_live_facilities(ctx, live)
            for key, _ in FACILITY_TABLES:
                nearest[key] = ctx[key][0] if ctx[key] else None
            _merge_live_roads(ctx, live)
            settlements = _merge_live_places(settlements, live)
    ctx["nearest"] = nearest
    ctx["settlements"] = settlements[:12]
    residential = [s for s in settlements if s["type"] in ("city", "town", "village", "suburb", "hamlet", "neighbourhood", "residential", "colony")]
    ctx["nearest_residential"] = residential[0] if residential else None
    ctx["critical_infrastructure"] = [f for f in (live or []) if f["kind"] in ("hospital", "school", "college", "university", "railway_station", "fuel")][:12]
    ctx["land_cover"] = classify_landcover(lat, lon, state, live_features=live)

    def dist(key):
        return nearest[key]["distance_km"] if nearest.get(key) else None

    all_ind = [i for k in ("refineries", "power_plants", "mines", "gas_facilities", "industrial_facilities") for i in ctx[k]]
    all_ind.sort(key=lambda i: i["distance_km"])
    ctx["nearest_industrial_any"] = all_ind[0] if all_ind else None
    storage = [i for i in ctx["industrial_facilities"] if i["category"] == "storage"]
    ctx["nearest_storage"] = storage[0] if storage else None
    ctx["distances"] = {
        "refinery_km": dist("refineries"), "power_plant_km": dist("power_plants"), "mine_km": dist("mines"), "gas_facility_km": dist("gas_facilities"),
        "industrial_km": all_ind[0]["distance_km"] if all_ind else None, "storage_km": storage[0]["distance_km"] if storage else None,
        "road_km": ctx["nearest_road"]["distance_km"] if ctx.get("nearest_road") else None, "railway_km": ctx["nearest_railway"]["distance_km"] if ctx.get("nearest_railway") else None,
        "residential_km": round(max(0.0, ctx["nearest_residential"]["distance_km"] - ctx["nearest_residential"].get("radius_km", 0)), 2) if ctx["nearest_residential"] else None,
    }
    ctx["summary"] = _summary(ctx)
    return ctx


def _merge_live_facilities(ctx: dict, live: list[dict]) -> None:
    for f in live:
        mapping = KIND_TO_CATEGORY.get(f["kind"])
        if not mapping:
            continue
        key, category, subtype = mapping
        t = f.get("tags", {})
        if t.get("product") in ("oil", "petroleum", "gas", "lng") or "refiner" in (t.get("name", "") + t.get("industrial", "")).lower():
            key, category, subtype = "refineries", "refinery", "refinery"
        if t.get("plant:source") in ("coal", "gas", "oil", "biomass") or t.get("power") == "plant":
            if f["kind"] == "power_plant":
                key, category, subtype = "power_plants", "power_plant", t.get("plant:source", "plant")
        if any(haversine_km(f["latitude"], f["longitude"], x["latitude"], x["longitude"]) < 1.0 and x.get("category") == category for x in ctx[key]):
            continue
        ctx[key].append({"id": 0, "osm_id": f["osm_id"], "name": f["name"] or f"{subtype.replace('_', ' ').title()} (OSM {f['osm_id']}, unnamed)", "operator": t.get("operator", ""),
                         "category": category, "subtype": subtype, "latitude": f["latitude"], "longitude": f["longitude"], "state": "", "district": "",
                         "distance_km": f["distance_km"], "bearing": f["bearing"], "direction": f["direction"], "source": "osm_overpass", "data_quality": "osm"})
        ctx[key].sort(key=lambda x: x["distance_km"])
        ctx[key] = ctx[key][:8]


def _merge_live_roads(ctx: dict, live: list[dict]) -> None:
    roads = [f for f in live if f["kind"] == "road"]
    rails = [f for f in live if f["kind"] == "railway"]
    if roads:
        r = roads[0]
        ctx["nearest_road"] = {"name": r["name"] or r["tags"].get("ref", "") or f"{r['tags'].get('highway', 'road')} (unnamed)", "ref": r["tags"].get("ref", ""),
                               "type": r["tags"].get("highway", ""), "distance_km": r["distance_km"], "source": "osm_overpass", "precision": "way centre"}
    if rails:
        r = rails[0]
        ctx["nearest_railway"] = {"name": r["name"] or "Railway line (OSM)", "ref": r["tags"].get("ref", ""), "type": "railway", "distance_km": r["distance_km"], "source": "osm_overpass", "precision": "way centre"}


def _merge_live_places(settlements: list[dict], live: list[dict]) -> list[dict]:
    out = list(settlements)
    for f in live:
        if f["kind"] not in ("place", "residential"):
            continue
        name = f["name"] or ("Residential area (OSM, unnamed)" if f["kind"] == "residential" else "")
        if not name:
            continue
        if any(haversine_km(f["latitude"], f["longitude"], s["latitude"], s["longitude"]) < 1.0 for s in out):
            continue
        ptype = f["tags"].get("place", "residential")
        out.append({"id": 0, "osm_id": f["osm_id"], "name": name, "type": ptype, "state": "", "district": "", "population": f.get("population"),
                    "population_source": f"OSM population tag ({f.get('population_date') or 'undated'})" if f.get("population") else None,
                    "latitude": f["latitude"], "longitude": f["longitude"], "radius_km": {"city": 4.0, "town": 2.0, "suburb": 1.5, "village": 1.0, "hamlet": 0.5, "neighbourhood": 0.7, "residential": 0.5}.get(ptype, 0.8),
                    "distance_km": f["distance_km"], "bearing": f["bearing"], "direction": f["direction"], "source": "osm_overpass"})
    out.sort(key=lambda s: s["distance_km"])
    return out


def _summary(ctx: dict) -> list[str]:
    lines = []
    n = ctx["nearest"]
    for key, label in (("refineries", "refinery"), ("power_plants", "power plant"), ("mines", "mine"), ("gas_facilities", "gas facility"), ("industrial_facilities", "industrial facility")):
        if n.get(key):
            f = n[key]
            lines.append(f"Nearest {label}: {f['name']} ({f['distance_km']} km {f['direction']}; {f['source']})")
    if ctx.get("nearest_residential"):
        r = ctx["nearest_residential"]
        lines.append(f"Nearest residential area: {r['name']} ({r['distance_km']} km {r['direction']})")
    if ctx.get("nearest_road"):
        lines.append(f"Nearest road: {ctx['nearest_road']['name']} ({ctx['nearest_road']['distance_km']} km)")
    if ctx.get("nearest_railway"):
        lines.append(f"Nearest railway: {ctx['nearest_railway']['name']} ({ctx['nearest_railway']['distance_km']} km)")
    lc = ctx.get("land_cover", {})
    if lc.get("available"):
        lines.append(f"Land cover: {lc.get('label')} ({lc.get('provenance')})")
    else:
        lines.append("Land cover: unavailable")
    return lines
