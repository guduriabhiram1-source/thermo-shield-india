"""Loads the bundled real reference datasets and seeds them into the database.

* data/boundaries/states_india.geojson    - OSM state/UT polygons (ODbL) + Census 2011 density
* data/boundaries/districts_india.json    - every OSM district (admin_level 5) with state + centroid
* data/population/settlements_*.csv       - Census 2011 settlement populations (reference values)
* data/reference/facilities_india.csv     - public reference list of refineries / power plants / mines / gas facilities
* data/reference/roads_india.json         - coarse national highway / railway polylines (reference)
* data/land_cover/landcover_zones_*.json  - coarse named land-cover zones (reference, low precision)

Live OSM Overpass / Nominatim results are merged on top of these at analysis time."""
from __future__ import annotations

import csv
import io
import json
import logging
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import DATA_DIR
from ..models import AdminBoundary, GasFacility, IndustrialFacility, LandCover, Mine, Population, PowerPlant, Refinery, Road
from ..utils.geo import point_in_polygon

log = logging.getLogger("thermoshield.reference")
BOUNDARY_DIR: Path = DATA_DIR / "boundaries"
REF_DIR: Path = DATA_DIR / "reference"
POP_DIR: Path = DATA_DIR / "population"
LC_DIR: Path = DATA_DIR / "land_cover"


def _read_json(path: Path) -> dict:
    with io.open(path, encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache
def load_states() -> list[dict]:
    """[{name, code, bbox[minlat,minlon,maxlat,maxlon], centroid[lat,lon], density, rings}] from the OSM GeoJSON."""
    gj = _read_json(BOUNDARY_DIR / "states_india.geojson")
    out = []
    for f in gj["features"]:
        p = f["properties"]
        rings = []
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for poly in polys:
            rings.append([[pt[1], pt[0]] for pt in poly[0]])  # outer ring as [lat, lon]
        out.append({"name": p["name"], "code": p.get("code", ""), "bbox": p["bbox"], "centroid": p["centroid"], "density": p.get("density"),
                    "osm_id": p.get("osm_id", ""), "rings": rings})
    return out


@lru_cache
def load_state_geojson() -> dict:
    return _read_json(BOUNDARY_DIR / "states_india.geojson")


@lru_cache
def load_districts() -> list[dict]:
    return _read_json(BOUNDARY_DIR / "districts_india.json")["districts"]


def districts_for_state(state: str) -> list[dict]:
    return [d for d in load_districts() if d["state"] == state]


def state_for_point(lat: float, lon: float) -> dict | None:
    """Point-in-polygon against the OSM state polygons (exact for the simplified geometry)."""
    for s in load_states():
        b = s["bbox"]
        if not (b[0] <= lat <= b[2] and b[1] <= lon <= b[3]):
            continue
        if any(point_in_polygon(lat, lon, ring) for ring in s["rings"]):
            return s
    return None


@lru_cache
def load_settlements() -> list[dict]:
    with io.open(POP_DIR / "settlements_census2011_india.csv", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        r["population"] = int(r["population"])
        r["latitude"] = float(r["latitude"])
        r["longitude"] = float(r["longitude"])
    return rows


@lru_cache
def load_facilities() -> list[dict]:
    with io.open(REF_DIR / "facilities_india.csv", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        r["latitude"] = float(r["latitude"])
        r["longitude"] = float(r["longitude"])
        r["capacity"] = float(r["capacity"] or 0)
    return rows


@lru_cache
def load_roads() -> list[dict]:
    return _read_json(REF_DIR / "roads_india.json")["roads"]


@lru_cache
def load_landcover_zones() -> dict:
    return _read_json(LC_DIR / "landcover_zones_reference_india.json")


def settlement_radius_km(population: int | None, settlement_type: str) -> float:
    if settlement_type == "industrial_area":
        return 3.0
    p = population or 0
    if p >= 5_000_000:
        return 15.0
    if p >= 1_000_000:
        return 10.0
    if p >= 300_000:
        return 6.0
    if p >= 100_000:
        return 4.0
    if p >= 30_000:
        return 2.5
    if settlement_type == "city":
        return 4.0
    if settlement_type == "town":
        return 2.0
    return 1.0


FACILITY_MODEL = {"refinery": Refinery, "power_plant": PowerPlant, "mine": Mine, "gas_facility": GasFacility, "industrial": IndustrialFacility, "storage": IndustrialFacility}


def seed_reference_data(db: Session, force: bool = False) -> dict:
    """Idempotent seed of the reference tables."""
    counts = {}
    if force or db.execute(select(AdminBoundary.id).limit(1)).first() is None:
        db.query(AdminBoundary).delete()
        gj = load_state_geojson()
        for f in gj["features"]:
            p = f["properties"]
            b = p["bbox"]
            db.add(AdminBoundary(osm_id=p.get("osm_id", ""), name=p["name"], code=p.get("code", ""), level="state", parent="India", min_lat=b[0], min_lon=b[1], max_lat=b[2], max_lon=b[3],
                                 centroid_lat=p["centroid"][0], centroid_lon=p["centroid"][1], population_density=p.get("density"), geometry=f["geometry"],
                                 source="osm_admin_level_4", note="OSM administrative relation (simplified); Census 2011 density"))
        n = 0
        for d in load_districts():
            db.add(AdminBoundary(osm_id=d["osm_id"], name=d["name"], code=d.get("lgd_code", ""), level="district", parent=d["state"], centroid_lat=d["lat"], centroid_lon=d["lon"],
                                 source="osm_admin_level_5", note="OSM district relation centre; LGD code"))
            n += 1
        counts["states"] = len(gj["features"])
        counts["districts"] = n

    if force or db.execute(select(Population.id).where(Population.source == "census_2011_reference").limit(1)).first() is None:
        for r in load_settlements():
            db.add(Population(name=r["name"], settlement_type=r["settlement_type"], state=r["state"], district=r["district"], population=r["population"], population_year=2011,
                              latitude=r["latitude"], longitude=r["longitude"], radius_km=settlement_radius_km(r["population"], r["settlement_type"]), source=r["source"]))
        counts["settlements"] = len(load_settlements())

    if force or db.execute(select(IndustrialFacility.id).limit(1)).first() is None and db.execute(select(Refinery.id).limit(1)).first() is None:
        n = 0
        for f in load_facilities():
            model = FACILITY_MODEL[f["category"]]
            kwargs = dict(name=f["name"], operator=f["operator"], category=f["category"], subtype=f["subtype"], latitude=f["latitude"], longitude=f["longitude"],
                          state=f["state"], district=f["district"], tags={"fuel_or_resource": f["fuel_or_resource"]}, source=f["source"], data_quality=f["data_quality"])
            if model is Refinery:
                kwargs["capacity_mmtpa"] = f["capacity"]
            elif model is PowerPlant:
                kwargs["capacity_mw"] = f["capacity"]
                kwargs["fuel"] = f["fuel_or_resource"]
            elif model is Mine:
                kwargs["resource"] = f["fuel_or_resource"]
            elif model is GasFacility:
                kwargs["flare"] = 1 if f["subtype"] in ("gas_processing", "oil_field", "cbm") else 0
            db.add(model(**kwargs))
            n += 1
        counts["facilities"] = n

    if force or db.execute(select(Road.id).limit(1)).first() is None:
        db.query(Road).delete()
        for r in load_roads():
            g = r["geometry"]
            mid = g[len(g) // 2]
            db.add(Road(name=r["name"], ref=r["ref"], highway=r["highway"], latitude=mid[0], longitude=mid[1], geometry=g, source="reference_public"))
        counts["roads"] = len(load_roads())

    if force or db.execute(select(LandCover.id).where(LandCover.source == "reference_zone").limit(1)).first() is None:
        for z in load_landcover_zones()["zones"]:
            db.add(LandCover(latitude=z["lat"], longitude=z["lon"], radius_km=z["radius_km"], land_cover_class=z["class"], name=z["name"], source="reference_zone"))
        counts["landcover_zones"] = len(load_landcover_zones()["zones"])

    db.commit()
    if counts:
        log.info("Reference data seeded: %s", counts)
    return counts
