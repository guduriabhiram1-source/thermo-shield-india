"""Build the India administrative-boundary datasets from OpenStreetMap.

Outputs (committed to the repository so the app works offline):
  data/boundaries/states_india.geojson   - 36 states/UTs, simplified polygons + centroid + bbox + Census-2011 density
  data/boundaries/districts_india.json   - every district (OSM admin_level=5) with state, centroid, LGD code

Usage:
  python scripts/build_boundaries.py                       # queries Overpass (slow: ~2-5 minutes, ~50 MB download)
  python scripts/build_boundaries.py --states raw_states.json --districts raw_districts.json   # from saved raw responses
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

import httpx
from shapely.geometry import LineString, MultiPolygon, Polygon, mapping, shape
from shapely.ops import polygonize, unary_union

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "boundaries"
OVERPASS = "https://overpass-api.de/api/interpreter"
Q_STATES = """[out:json][timeout:900];
area["ISO3166-1"="IN"][admin_level=2]->.in;
relation(area.in)["boundary"="administrative"]["admin_level"="4"]["ISO3166-2"~"^IN-"];
out geom;"""
Q_DISTRICTS = """[out:json][timeout:600];
area["ISO3166-1"="IN"][admin_level=2]->.in;
relation(area.in)["boundary"="administrative"]["admin_level"~"^(4|5)$"];
out tags center;"""


def fetch(query: str) -> dict:
    r = httpx.post(OVERPASS, data={"data": query}, timeout=1200.0, headers={"User-Agent": "ThermoShieldIndia/2.0 boundary builder"})
    r.raise_for_status()
    return r.json()


def relation_polygon(rel: dict):
    lines = []
    for m in rel.get("members", []):
        if m.get("type") == "way" and m.get("role") in ("outer", "") and m.get("geometry"):
            pts = [(p["lon"], p["lat"]) for p in m["geometry"]]
            if len(pts) >= 2:
                lines.append(LineString(pts))
    if not lines:
        return None
    merged = unary_union(lines)
    polys = list(polygonize(merged))
    if not polys:
        return None
    geom = unary_union(polys)
    if isinstance(geom, Polygon):
        geom = MultiPolygon([geom])
    return geom


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--states")
    ap.add_argument("--districts")
    ap.add_argument("--tolerance", type=float, default=0.01)
    a = ap.parse_args()
    raw_states = json.load(io.open(a.states, encoding="utf-8")) if a.states else fetch(Q_STATES)
    raw_districts = json.load(io.open(a.districts, encoding="utf-8")) if a.districts else fetch(Q_DISTRICTS)

    density = {}
    old = OUT_DIR / "states_india.json"
    if old.exists():
        for s in json.load(io.open(old, encoding="utf-8"))["states"]:
            density[s["name"]] = s["density"]
    # Nominatim / OSM naming aliases -> canonical display name
    features, state_polys = [], []
    for rel in raw_states["elements"]:
        tags = rel["tags"]
        name = tags.get("name:en") or tags.get("name")
        geom = relation_polygon(rel)
        if geom is None:
            print("no polygon for", name, file=sys.stderr)
            continue
        simple = geom.simplify(a.tolerance, preserve_topology=True)
        b = simple.bounds
        c = geom.representative_point()
        features.append({
            "type": "Feature",
            "properties": {"name": name, "code": tags.get("ISO3166-2", "").replace("IN-", ""), "osm_id": f"relation/{rel['id']}",
                           "density": density.get(name), "bbox": [b[1], b[0], b[3], b[2]], "centroid": [round(c.y, 4), round(c.x, 4)],
                           "wikidata": tags.get("wikidata", "")},
            "geometry": mapping(simple),
        })
        state_polys.append((name, geom))
    features.sort(key=lambda f: f["properties"]["name"])
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with io.open(OUT_DIR / "states_india.geojson", "w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "source": "OpenStreetMap administrative relations (admin_level=4), ODbL", "features": features}, fh, ensure_ascii=False)
    print("states:", len(features))

    districts = []
    from shapely.geometry import Point

    for rel in raw_districts["elements"]:
        tags = rel["tags"]
        if tags.get("admin_level") != "5" or "center" not in rel:
            continue
        name = (tags.get("name:en") or tags.get("name") or "").strip()
        if not name:
            continue
        for suffix in (" District", " district", " Zila", " zila"):
            if name.endswith(suffix):
                name = name[: -len(suffix)]
        pt = Point(rel["center"]["lon"], rel["center"]["lat"])
        state = next((s for s, g in state_polys if g.contains(pt)), None)
        if state is None:
            # nearest state polygon (islands / coastal centroids)
            state = min(state_polys, key=lambda sg: sg[1].distance(pt))[0]
        districts.append({"name": name, "state": state, "lat": round(pt.y, 4), "lon": round(pt.x, 4), "osm_id": f"relation/{rel['id']}",
                          "lgd_code": tags.get("ref:LGD:district", ""), "wikidata": tags.get("wikidata", "")})
    districts.sort(key=lambda d: (d["state"], d["name"]))
    with io.open(OUT_DIR / "districts_india.json", "w", encoding="utf-8") as fh:
        json.dump({"source": "OpenStreetMap administrative relations (admin_level=5 = district), ODbL; state assignment by point-in-polygon of relation centre",
                   "count": len(districts), "districts": districts}, fh, ensure_ascii=False, indent=0)
    from collections import Counter

    print("districts:", len(districts), Counter(d["state"] for d in districts).most_common(5))
    return 0


if __name__ == "__main__":
    sys.exit(main())
