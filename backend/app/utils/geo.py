"""Geospatial helpers that work identically on PostGIS and SQLite."""
from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

EARTH_RADIUS_KM = 6371.0088
COMPASS_16 = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
COMPASS_8 = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing from point 1 to point 2 (0 = North, clockwise)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def compass(bearing: float, points: int = 16) -> str:
    names = COMPASS_16 if points == 16 else COMPASS_8
    step = 360 / len(names)
    return names[int((bearing + step / 2) // step) % len(names)]


def destination_point(lat: float, lon: float, bearing: float, distance_km: float) -> tuple[float, float]:
    br = math.radians(bearing)
    d = distance_km / EARTH_RADIUS_KM
    p1 = math.radians(lat)
    l1 = math.radians(lon)
    p2 = math.asin(math.sin(p1) * math.cos(d) + math.cos(p1) * math.sin(d) * math.cos(br))
    l2 = l1 + math.atan2(math.sin(br) * math.sin(d) * math.cos(p1), math.cos(d) - math.sin(p1) * math.sin(p2))
    return math.degrees(p2), (math.degrees(l2) + 540) % 360 - 180


def angular_difference(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return 360 - d if d > 180 else d


def bbox_for_radius(lat: float, lon: float, radius_km: float) -> tuple[float, float, float, float]:
    dlat = radius_km / 111.32
    dlon = radius_km / (111.32 * max(math.cos(math.radians(lat)), 0.05))
    return lat - dlat, lon - dlon, lat + dlat, lon + dlon


def point_to_polyline_km(lat: float, lon: float, line: Sequence[Sequence[float]]) -> float:
    if not line:
        return float("inf")
    kx = 111.32 * math.cos(math.radians(lat))
    ky = 111.32
    best = float("inf")
    pts = [((p[1] - lon) * kx, (p[0] - lat) * ky) for p in line]
    if len(pts) == 1:
        return math.hypot(pts[0][0], pts[0][1])
    for (x1, y1), (x2, y2) in zip(pts[:-1], pts[1:]):
        dx, dy = x2 - x1, y2 - y1
        seg = dx * dx + dy * dy
        if seg == 0:
            d = math.hypot(x1, y1)
        else:
            t = max(0.0, min(1.0, (-x1 * dx - y1 * dy) / seg))
            d = math.hypot(x1 + t * dx, y1 + t * dy)
        best = min(best, d)
    return best


def sector_polygon(lat: float, lon: float, center_bearing: float, half_angle: float, radius_km: float, steps: int = 24) -> list[list[float]]:
    pts = [[lat, lon]]
    start = center_bearing - half_angle
    for i in range(steps + 1):
        b = start + (2 * half_angle) * i / steps
        pts.append(list(destination_point(lat, lon, b, radius_km)))
    pts.append([lat, lon])
    return pts


def circle_polygon(lat: float, lon: float, radius_km: float, steps: int = 36) -> list[list[float]]:
    return [list(destination_point(lat, lon, 360 * i / steps, radius_km)) for i in range(steps + 1)]


def centroid(points: Iterable[tuple[float, float]]) -> tuple[float, float]:
    pts = list(points)
    if not pts:
        return 0.0, 0.0
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def spread_km(points: Sequence[tuple[float, float]]) -> float:
    if len(points) < 2:
        return 0.0
    c = centroid(points)
    return 2 * max(haversine_km(c[0], c[1], p[0], p[1]) for p in points)


def point_in_polygon(lat: float, lon: float, poly: Sequence[Sequence[float]]) -> bool:
    """Ray casting; poly is [[lat, lon], ...]."""
    inside = False
    n = len(poly)
    for i in range(n):
        y1, x1 = poly[i][0], poly[i][1]
        y2, x2 = poly[(i + 1) % n][0], poly[(i + 1) % n][1]
        if (y1 > lat) != (y2 > lat):
            x_int = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if lon < x_int:
                inside = not inside
    return inside
