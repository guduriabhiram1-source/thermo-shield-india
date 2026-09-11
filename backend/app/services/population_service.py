"""Population: settlements around a point and density estimates.

Sources: Census-2011 settlement reference values (bundled), OSM `population`
tags returned live by Overpass, and Census-2011 state densities. Every figure
is an ESTIMATE and labelled as such; settlements whose population is not known
are listed with population=None (never guessed)."""
from __future__ import annotations

import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AdminBoundary, Population
from ..utils.geo import bbox_for_radius, bearing_deg, compass, haversine_km


def settlements_within(db: Session, lat: float, lon: float, radius_km: float) -> list[dict]:
    min_lat, min_lon, max_lat, max_lon = bbox_for_radius(lat, lon, radius_km)
    rows = db.execute(select(Population).where(Population.latitude.between(min_lat, max_lat), Population.longitude.between(min_lon, max_lon))).scalars().all()
    out = []
    for p in rows:
        d = haversine_km(lat, lon, p.latitude, p.longitude)
        if d <= radius_km:
            b = bearing_deg(lat, lon, p.latitude, p.longitude)
            out.append({"id": p.id, "osm_id": p.osm_id, "name": p.name, "type": p.settlement_type, "state": p.state, "district": p.district, "population": p.population,
                        "population_source": f"{p.source} ({p.population_year})" if p.population is not None else None, "latitude": p.latitude, "longitude": p.longitude,
                        "radius_km": p.radius_km, "distance_km": round(d, 2), "bearing": round(b, 1), "direction": compass(b, 8), "source": p.source})
    out.sort(key=lambda r: r["distance_km"])
    return out


def state_density(db: Session, state: str) -> float | None:
    row = db.execute(select(AdminBoundary).where(AdminBoundary.name == state, AdminBoundary.level == "state")).scalar_one_or_none()
    return float(row.population_density) if row and row.population_density is not None else None


def local_density(db: Session, lat: float, lon: float, state: str) -> dict:
    base = state_density(db, state)
    near = settlements_within(db, lat, lon, 15)
    inside = [s for s in near if s["distance_km"] <= s["radius_km"] and s.get("population")]
    if inside:
        s = inside[0]
        area = math.pi * s["radius_km"] ** 2
        dens = s["population"] / max(area, 1)
        return {"density_per_km2": round(max(dens, base or 0), 1), "basis": f"Inside estimated footprint of {s['name']} ({s['population_source']})", "is_estimate": True, "available": True}
    if base is None:
        return {"density_per_km2": None, "basis": "Unavailable", "is_estimate": True, "available": False}
    return {"density_per_km2": round(base, 1), "basis": f"State average density, Census 2011 ({state})", "is_estimate": True, "available": True}


def population_in_radius(db: Session, lat: float, lon: float, radius_km: float, state: str) -> dict:
    near = settlements_within(db, lat, lon, radius_km + 15)
    total = 0
    breakdown = []
    unknown = []
    for s in near:
        overlap = _circle_overlap_fraction(s["distance_km"], s["radius_km"], radius_km)
        if overlap > 0:
            if s.get("population"):
                exposed = int(round(s["population"] * overlap))
                total += exposed
                breakdown.append({**s, "fraction_inside": round(overlap, 2), "exposed_population": exposed})
            else:
                unknown.append(s["name"])
    dens = state_density(db, state)
    background = int(dens * 0.2 * math.pi * radius_km ** 2) if dens is not None else None
    return {"radius_km": radius_km, "settlement_population": total, "background_population": background, "total_estimate": total + (background or 0),
            "breakdown": breakdown, "settlements_without_population_data": unknown[:10], "is_estimate": True, "available": True,
            "source": "Census 2011 settlement reference values + OSM population tags + state density; estimate only"}


def _circle_overlap_fraction(d: float, r_small: float, r_big: float) -> float:
    if d + r_small <= r_big:
        return 1.0
    if d >= r_big + r_small:
        return 0.0
    if r_small <= 0:
        return 1.0 if d <= r_big else 0.0
    r1, r2 = r_small, r_big
    a = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
    h2 = r1 * r1 - a * a
    if h2 <= 0:
        return 0.5
    part1 = r1 * r1 * math.acos(max(-1, min(1, a / r1)))
    part2 = r2 * r2 * math.acos(max(-1, min(1, (d - a) / r2)))
    lens = part1 + part2 - d * math.sqrt(h2)
    return max(0.0, min(1.0, lens / (math.pi * r1 * r1)))
