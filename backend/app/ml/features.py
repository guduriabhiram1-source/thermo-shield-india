"""Feature engineering for the thermal-source classifier.

`build_features` turns an event + its enrichment (GIS context, weather,
persistence, history) into a flat numeric dict in a fixed column order. Missing
context (no facility within the search radius, weather unavailable) is encoded
explicitly (distance cap / NaN-safe defaults) and recorded in `provenance`."""
from __future__ import annotations

from datetime import datetime, timezone

from ..utils.timeutil import ensure_utc

CLASSES = [
    "INDUSTRIAL_FIRE", "PERSISTENT_INDUSTRIAL_HEAT", "WILDFIRE", "AGRICULTURAL_BURN", "GAS_FLARE",
    "REFINERY_ACTIVITY", "POWER_PLANT_ACTIVITY", "MINING_ACTIVITY", "OTHER_THERMAL_SOURCE", "UNKNOWN",
]
CLASS_LABELS = {
    "INDUSTRIAL_FIRE": "Industrial Fire", "PERSISTENT_INDUSTRIAL_HEAT": "Persistent Industrial Heat", "WILDFIRE": "Wildfire",
    "AGRICULTURAL_BURN": "Agricultural Burning", "GAS_FLARE": "Gas Flare", "REFINERY_ACTIVITY": "Refinery Thermal Activity",
    "POWER_PLANT_ACTIVITY": "Power-Plant Thermal Activity", "MINING_ACTIVITY": "Mining Thermal Activity",
    "OTHER_THERMAL_SOURCE": "Other Thermal Source", "UNKNOWN": "Unknown",
}
LAND_COVER_CODES = {"forest": 0, "cropland": 1, "built_up": 2, "industrial": 3, "bare": 4, "water": 5, "grassland": 6, "other": 7, "unknown": 7}

FEATURE_NAMES = [
    "max_frp", "mean_frp", "latest_frp", "frp_trend", "frp_growth_rate", "max_brightness", "mean_confidence",
    "detection_count", "detection_frequency", "active_days", "duration_hours", "night_ratio", "persistence_score", "spatial_spread_km",
    "dist_industrial_km", "dist_refinery_km", "dist_power_plant_km", "dist_mine_km", "dist_gas_km", "dist_storage_km",
    "dist_road_km", "dist_residential_km", "land_cover_code", "population_density", "wind_speed_kmh", "wind_direction_deg",
    "historical_event_count", "month", "growth_rate_spread",
]
FEATURE_LABELS = {
    "max_frp": "Peak FRP (MW)", "mean_frp": "Mean FRP", "latest_frp": "Latest FRP", "frp_trend": "FRP trend (MW/day)",
    "frp_growth_rate": "FRP growth ratio", "max_brightness": "Peak brightness temp (K)", "mean_confidence": "Detection confidence",
    "detection_count": "Detection count", "detection_frequency": "Detections per active day", "active_days": "Active days", "duration_hours": "Duration (h)",
    "night_ratio": "Night-time ratio", "persistence_score": "Persistence score", "spatial_spread_km": "Spatial spread (km)",
    "dist_industrial_km": "Distance to industrial facility", "dist_refinery_km": "Distance to refinery", "dist_power_plant_km": "Distance to power plant",
    "dist_mine_km": "Distance to mine", "dist_gas_km": "Distance to gas facility", "dist_storage_km": "Distance to tank farm / storage",
    "dist_road_km": "Distance to road", "dist_residential_km": "Distance to residential area", "land_cover_code": "Land-cover class",
    "population_density": "Population density", "wind_speed_kmh": "Wind speed", "wind_direction_deg": "Wind direction",
    "historical_event_count": "Historical events nearby (12 months)", "month": "Month of year", "growth_rate_spread": "Spatial growth rate",
}
DIST_CAP = 100.0


def _d(v) -> float:
    return float(v) if v is not None else DIST_CAP


def build_features(ev, gis: dict, weather: dict | None, persistence: dict, historical_count: int = 0) -> tuple[dict, dict]:
    """Returns (features, provenance) - provenance records which inputs were unavailable."""
    dist = (gis or {}).get("distances", {})
    lc = (gis or {}).get("land_cover", {}).get("class", "unknown")
    evo = ev.evolution or {}
    first = ensure_utc(ev.first_detected_at) or datetime.now(timezone.utc)
    w = weather or {}
    weather_ok = w.get("available", False)
    prov = {
        "weather": "OBSERVED (" + str(w.get("weather_source")) + ")" if weather_ok else "UNAVAILABLE (wind features set to 0)",
        "facilities": "OBSERVED (" + str((gis or {}).get("provider")) + ")" if gis else "UNAVAILABLE",
        "land_cover": (gis or {}).get("land_cover", {}).get("provenance", "UNAVAILABLE"),
        "population_density": "ESTIMATE" if ev.population_density is not None else "UNAVAILABLE",
        "distances_capped_at_km": DIST_CAP,
    }
    feats = {
        "max_frp": float(ev.max_frp), "mean_frp": float(ev.mean_frp), "latest_frp": float(ev.latest_frp),
        "frp_trend": float(ev.frp_trend), "frp_growth_rate": float(ev.frp_growth_rate), "max_brightness": float(ev.max_brightness),
        "mean_confidence": float(ev.mean_confidence), "detection_count": float(ev.detection_count),
        "detection_frequency": float(ev.detection_count) / max(float(ev.active_days), 1.0), "active_days": float(ev.active_days),
        "duration_hours": float(ev.duration_hours), "night_ratio": float(ev.night_ratio), "persistence_score": float(persistence.get("score", ev.persistence_score)),
        "spatial_spread_km": float(ev.spatial_spread_km),
        "dist_industrial_km": _d(dist.get("industrial_km")), "dist_refinery_km": _d(dist.get("refinery_km")),
        "dist_power_plant_km": _d(dist.get("power_plant_km")), "dist_mine_km": _d(dist.get("mine_km")),
        "dist_gas_km": _d(dist.get("gas_facility_km")), "dist_storage_km": _d(dist.get("storage_km")),
        "dist_road_km": _d(dist.get("road_km")), "dist_residential_km": _d(dist.get("residential_km")),
        "land_cover_code": float(LAND_COVER_CODES.get(lc, 7)), "population_density": float(ev.population_density or 0.0),
        "wind_speed_kmh": float(w.get("wind_speed_kmh") or 0.0) if weather_ok else 0.0,
        "wind_direction_deg": float(w.get("wind_direction_deg") or 0.0) if weather_ok else 0.0,
        "historical_event_count": float(historical_count), "month": float(first.month),
        "growth_rate_spread": float(evo.get("spread_growth_rate", 1.0)),
    }
    return {k: feats[k] for k in FEATURE_NAMES}, prov


def feature_vector(feats: dict) -> list[float]:
    return [float(feats.get(k, 0.0)) for k in FEATURE_NAMES]
