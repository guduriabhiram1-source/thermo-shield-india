"""Risk engine (0-100) + risk momentum + "why did risk change?".

Components are weighted, each normalised to 0..1 and documented so the
explanation module can attribute score changes to individual drivers. When an
input is unavailable (no weather, no population data) its component is 0 and the
gap is recorded in `missing_inputs` rather than guessed."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import RiskScore, ThermalEvent
from ..utils.geo import angular_difference

WEIGHTS = {"thermal_intensity": 18, "detection_confidence": 6, "persistence": 10, "event_growth": 14, "population_proximity": 14, "population_density": 6,
           "wind_exposure": 10, "industrial_proximity": 10, "historical_recurrence": 4, "land_cover": 4, "classification": 4}
CLASS_RISK = {"INDUSTRIAL_FIRE": 1.0, "WILDFIRE": 0.85, "GAS_FLARE": 0.55, "REFINERY_ACTIVITY": 0.6, "PERSISTENT_INDUSTRIAL_HEAT": 0.5, "POWER_PLANT_ACTIVITY": 0.4,
              "MINING_ACTIVITY": 0.5, "AGRICULTURAL_BURN": 0.35, "OTHER_THERMAL_SOURCE": 0.45, "UNKNOWN": 0.3}
LAND_RISK = {"forest": 0.8, "industrial": 0.9, "built_up": 0.85, "cropland": 0.4, "grassland": 0.5, "bare": 0.15, "water": 0.05, "other": 0.3, "unknown": 0.3}
COMPONENT_LABELS = {"thermal_intensity": "FRP / thermal intensity", "detection_confidence": "Detection confidence", "persistence": "Persistence",
                    "event_growth": "Event growth (FRP + spread)", "population_proximity": "Distance to population", "population_density": "Population density",
                    "wind_exposure": "Wind toward populated area", "industrial_proximity": "Industrial facility proximity", "historical_recurrence": "Historical recurrence",
                    "land_cover": "Land cover flammability", "classification": "Event classification"}


def risk_level(score: float) -> str:
    if score <= 20:
        return "LOW"
    if score <= 40:
        return "MODERATE"
    if score <= 60:
        return "MEDIUM"
    if score <= 80:
        return "HIGH"
    return "CRITICAL"


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


def compute_components(ev: ThermalEvent, feats: dict, gis: dict, weather: dict | None, exposure: dict | None, historical_count: int) -> tuple[dict, list[str]]:
    c, missing = {}, []
    c["thermal_intensity"] = _clamp(feats["max_frp"] / 250.0) * 0.7 + _clamp(feats["latest_frp"] / 200.0) * 0.3
    c["detection_confidence"] = _clamp(feats["mean_confidence"])
    c["persistence"] = _clamp(feats["persistence_score"] / 100.0)
    growth = _clamp((feats["frp_growth_rate"] - 1.0) / 3.0) if feats["frp_growth_rate"] > 1 else 0.0
    spread_g = _clamp((feats["growth_rate_spread"] - 1.0) / 2.0)
    c["event_growth"] = 0.65 * growth + 0.35 * spread_g
    d_res = (gis.get("distances") or {}).get("residential_km")
    if d_res is None:
        c["population_proximity"] = 0.0
        missing.append("no residential area found within the search radius (population proximity = 0)")
    else:
        c["population_proximity"] = _clamp(1.0 - d_res / 15.0)
    if ev.population_density is None:
        c["population_density"] = 0.0
        missing.append("population density unavailable")
    else:
        c["population_density"] = _clamp(ev.population_density / 3000.0)
    w = weather or {}
    if w.get("available") and w.get("wind_direction_deg") is not None:
        wind_to = (w["wind_direction_deg"] + 180) % 360
        res = gis.get("nearest_residential")
        align = _clamp(1.0 - angular_difference(wind_to, res["bearing"]) / 90.0) if res else 0.0
        speed = _clamp((w.get("wind_speed_kmh") or 0) / 40.0)
        boost = {"LOW": 0.0, "MODERATE": 0.3, "HIGH": 0.7, "CRITICAL": 1.0}.get((exposure or {}).get("exposure_level", "LOW"), 0.0)
        c["wind_exposure"] = 0.45 * align + 0.25 * speed + 0.30 * boost
    else:
        c["wind_exposure"] = 0.0
        missing.append("weather unavailable (wind exposure component = 0)")
    c["industrial_proximity"] = _clamp(1.0 - feats["dist_industrial_km"] / 10.0)
    c["historical_recurrence"] = _clamp(historical_count / 8.0)
    lc = gis.get("land_cover", {})
    c["land_cover"] = LAND_RISK.get(lc.get("class", "unknown"), 0.3) if lc.get("available") else 0.3
    if not lc.get("available"):
        missing.append("land cover unavailable (neutral value used)")
    c["classification"] = CLASS_RISK.get(ev.classification, 0.3)
    return {k: round(v, 4) for k, v in c.items()}, missing


def score_from_components(components: dict) -> float:
    return round(sum(WEIGHTS[k] * components[k] for k in WEIGHTS), 1)


def compute_risk(db: Session, ev: ThermalEvent, feats: dict, gis: dict, weather: dict | None, exposure: dict | None, historical_count: int) -> RiskScore:
    components, missing = compute_components(ev, feats, gis, weather, exposure, historical_count)
    score = score_from_components(components)
    level = risk_level(score)
    prev = db.execute(select(RiskScore).where(RiskScore.event_id == ev.id).order_by(RiskScore.computed_at.desc())).scalars().first()
    previous_score = prev.score if prev else None
    momentum = round(score - previous_score, 1) if previous_score is not None else 0.0
    trend = "INCREASING" if momentum >= 3 else "DECREASING" if momentum <= -3 else "STABLE"
    prev_components = {k: (v["value"] if isinstance(v, dict) else v) for k, v in (prev.components or {}).items()} if prev else None
    reasons = explain_change(components, prev_components, momentum)
    rs = RiskScore(event_id=ev.id, score=score, level=level, previous_score=previous_score, momentum=momentum, trend=trend, data_status=ev.data_status,
                   components={k: {"value": components[k], "weight": WEIGHTS[k], "points": round(components[k] * WEIGHTS[k], 1), "label": COMPONENT_LABELS[k]} for k in WEIGHTS},
                   change_reasons=reasons, computed_at=datetime.now(timezone.utc))
    db.add(rs)
    ev.risk_score, ev.risk_level, ev.risk_momentum, ev.risk_trend = score, level, momentum, trend
    ev.risk_breakdown = {**rs.components, "_missing_inputs": missing, "_provenance": "CALCULATED"}
    ev.risk_change = {"previous": previous_score, "current": score, "momentum": momentum, "trend": trend, "reasons": reasons, "previous_at": prev.computed_at.isoformat() if prev else None,
                      "statement": _statement(previous_score, score, momentum, trend), "provenance": "CALCULATED"}
    return rs


def explain_change(current: dict, previous: dict | None, momentum: float) -> list[dict]:
    if not previous:
        return [{"component": k, "label": COMPONENT_LABELS[k], "delta_points": round(current[k] * WEIGHTS[k], 1), "text": f"{COMPONENT_LABELS[k]} contributes {current[k] * WEIGHTS[k]:.1f} points (initial assessment)"}
                for k in sorted(WEIGHTS, key=lambda k: -current[k] * WEIGHTS[k])[:5]]
    deltas = []
    for k in WEIGHTS:
        d = (current[k] - previous.get(k, 0)) * WEIGHTS[k]
        if abs(d) >= 0.5:
            deltas.append({"component": k, "label": COMPONENT_LABELS[k], "delta_points": round(d, 1), "text": _delta_text(k, d, current[k], previous.get(k, 0))})
    deltas.sort(key=lambda x: -abs(x["delta_points"]))
    return deltas[:6]


def _delta_text(k: str, d: float, cur: float, prev: float) -> str:
    sign = "+" if d > 0 else ""
    pct = (cur - prev) / max(prev, 1e-6) * 100 if prev else 0
    if k == "thermal_intensity":
        return f"{sign}{d:.0f} FRP {'increased' if d > 0 else 'decreased'} by {abs(pct):.0f}%"
    if k == "event_growth":
        return f"{sign}{d:.0f} event spread / growth {'increased' if d > 0 else 'decreased'}"
    if k == "wind_exposure":
        return f"{sign}{d:.0f} wind shifted {'toward' if d > 0 else 'away from'} populated area"
    if k == "persistence":
        return f"{sign}{d:.0f} persistence {'increased' if d > 0 else 'decreased'}"
    if k == "detection_confidence":
        return f"{sign}{d:.0f} detection confidence {'increased' if d > 0 else 'decreased'}"
    return f"{sign}{d:.0f} {COMPONENT_LABELS[k].lower()} {'increased' if d > 0 else 'decreased'}"


def _statement(prev: float | None, cur: float, momentum: float, trend: str) -> str:
    if prev is None:
        return f"Initial risk assessment: {cur:.0f}/100 ({risk_level(cur)})."
    arrow = {"INCREASING": "↑ Risk Increasing", "DECREASING": "↓ Risk Decreasing", "STABLE": "→ Stable"}[trend]
    return f"Risk changed from {prev:.0f} to {cur:.0f} (momentum {momentum:+.0f}). {arrow}."
