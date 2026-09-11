"""National priority ranking. Live and historical events are ranked in separate lists."""
from __future__ import annotations

import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ThermalEvent


def priority_score(ev: ThermalEvent) -> float:
    risk = ev.risk_score / 100.0
    pop = min(1.0, math.log10(max(ev.exposed_population or 1, 1)) / 5.0)
    gis = ev.gis_context or {}
    ind = gis.get("nearest_industrial_any")
    industrial = 0.0
    if ind:
        industrial = max(0.0, 1.0 - ind["distance_km"] / 10.0)
        if ind.get("category") in ("refinery", "gas_facility") or ind.get("subtype") in ("refinery", "lng_terminal", "tank_farm", "spr"):
            industrial = min(1.0, industrial + 0.25)
    frp = min(1.0, ev.max_frp / 250.0)
    growth = min(1.0, max(0.0, (ev.frp_growth_rate - 1.0) / 3.0))
    persistence = ev.persistence_score / 100.0
    exposure = {"LOW": 0.1, "MODERATE": 0.4, "HIGH": 0.7, "CRITICAL": 1.0}.get(ev.exposure_level, 0.1)
    hist = min(1.0, float((ev.features or {}).get("historical_event_count", 0)) / 8.0)
    score = 100 * (0.30 * risk + 0.20 * pop + 0.12 * industrial + 0.10 * frp + 0.10 * growth + 0.06 * persistence + 0.08 * exposure + 0.04 * hist)
    if ev.status != "ACTIVE":
        score *= 0.6
    return round(score, 1)


def rerank_all(db: Session) -> int:
    events = list(db.execute(select(ThermalEvent)).scalars().all())
    for ev in events:
        ev.priority_score = priority_score(ev)
    for status_ in ("LIVE", "HISTORICAL"):
        group = sorted([e for e in events if e.data_status == status_], key=lambda e: -e.priority_score)
        for i, ev in enumerate(group, start=1):
            ev.priority_rank = i
    db.flush()
    return len(events)


def priority_reason(ev: ThermalEvent) -> str:
    parts = [f"{ev.risk_level} risk ({ev.risk_score:.0f}/100)"]
    if ev.exposed_population:
        parts.append(f"population exposure ≈ {ev.exposed_population:,} (est.)")
    ind = (ev.gis_context or {}).get("nearest_industrial_any")
    if ind and ind["distance_km"] <= 5:
        parts.append(f"{ind['name']} {ind['distance_km']} km away")
    if ev.frp_growth_rate >= 1.5:
        parts.append(f"FRP growing ×{ev.frp_growth_rate:.1f}")
    if ev.persistence_class == "PERSISTENT":
        parts.append("persistent source")
    return "; ".join(parts)
