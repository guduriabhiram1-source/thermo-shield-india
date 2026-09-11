"""Land-cover lookup around a coordinate.

Provider `osm` (default): nearest OSM landuse / natural polygon that contains
or surrounds the point (real, mapped data; precision depends on OSM coverage).
Provider `reference`: bundled coarse named zones (low precision, labelled).
When neither has information the result is `available=False`."""
from __future__ import annotations

from ..config import settings
from ..utils.geo import haversine_km
from .reference_data import load_facilities, load_landcover_zones, load_settlements, settlement_radius_km

CLASS_LABELS = {"forest": "Forest / tree cover", "cropland": "Cropland", "built_up": "Built-up / residential", "industrial": "Industrial built-up",
                "bare": "Bare / sparse vegetation", "water": "Water body", "grassland": "Grassland / scrub", "other": "Other / unclassified"}


def _zone_hits(lat: float, lon: float) -> list[dict]:
    hits = []
    for z in load_landcover_zones()["zones"]:
        d = haversine_km(lat, lon, z["lat"], z["lon"])
        if d <= z["radius_km"]:
            hits.append({"name": z["name"], "class": z["class"], "distance_km": round(d, 1), "radius_km": z["radius_km"]})
    hits.sort(key=lambda h: h["distance_km"] / max(h["radius_km"], 1))
    return hits


def classify_landcover(lat: float, lon: float, state: str = "", live_features: list[dict] | None = None) -> dict:
    basis: list[str] = []
    primary = None
    provenance = ""
    mix: dict[str, float] = {}

    # 1. OSM land-use / natural polygons (live) - the nearest polygon centre within 1.5 km wins, others form the mix
    if live_features:
        lc_feats = [f for f in live_features if f.get("land_cover_class")]
        near = [f for f in lc_feats if f["distance_km"] <= 1.5]
        if near:
            primary = near[0]["land_cover_class"]
            basis.append(f"OSM {near[0]['tags'].get('landuse') or near[0]['tags'].get('natural') or near[0]['kind']} polygon '{near[0]['name'] or 'unnamed'}' {near[0]['distance_km']} km from the point")
            provenance = "OBSERVED (OpenStreetMap land use)"
            for f in near[:6]:
                mix[f["land_cover_class"]] = mix.get(f["land_cover_class"], 0) + 1
            tot = sum(mix.values())
            mix = {k: round(v / tot, 2) for k, v in mix.items()}

    # 2. industrial footprint from the reference facility list (within 2.5 km)
    if primary is None:
        for f in load_facilities():
            d = haversine_km(lat, lon, f["latitude"], f["longitude"])
            if d <= 2.5:
                primary = "industrial"
                basis.append(f"Within {d:.1f} km of {f['name']} ({f['category']}; reference list)")
                provenance = "ESTIMATE (facility footprint)"
                break

    # 3. settlement footprint
    if primary is None:
        for s in load_settlements():
            r = settlement_radius_km(s["population"], s["settlement_type"])
            d = haversine_km(lat, lon, s["latitude"], s["longitude"])
            if d <= r:
                primary = "industrial" if s["settlement_type"] == "industrial_area" else "built_up"
                basis.append(f"Inside estimated footprint of {s['name']} ({s['settlement_type']}, {d:.1f} km from centre; Census gazetteer)")
                provenance = "ESTIMATE (settlement footprint)"
                break

    # 4. coarse reference zones
    zones = _zone_hits(lat, lon)
    if primary is None and zones:
        primary = zones[0]["class"]
        basis.append(f"Inside coarse reference zone '{zones[0]['name']}' ({zones[0]['class']}; low precision)")
        provenance = "ESTIMATE (coarse reference zone)"

    if primary is None:
        return {"available": False, "class": "unknown", "label": "Unavailable", "basis": ["No OSM land-use polygon within 1.5 km and no reference zone covers this point"],
                "mix": {}, "zones": zones[:3], "provider": settings.landcover_provider, "provenance": "UNAVAILABLE", "is_estimate": True,
                "note": "Land cover unavailable for this location."}
    if not mix:
        mix = {primary: 1.0}
    return {"available": True, "class": primary, "label": CLASS_LABELS.get(primary, primary), "basis": basis, "mix": mix, "zones": zones[:3],
            "provider": settings.landcover_provider, "provenance": provenance, "is_estimate": not provenance.startswith("OBSERVED"),
            "note": "Land cover from OpenStreetMap land-use polygons where mapped; otherwise footprint / coarse-zone estimate. Not a per-pixel classification."}
