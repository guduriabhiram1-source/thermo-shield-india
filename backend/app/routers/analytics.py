from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth.security import get_current_user
from ..config import settings
from ..database import get_db
from ..ml.features import CLASS_LABELS
from ..models import AdminBoundary, EventObservation, ThermalDetection, ThermalEvent
from ..services import freshness
from ..services.firms_service import latest_observation_time
from ..services.reference_data import districts_for_state, load_states
from ..services.serializers import event_summary
from ..utils.timeutil import ensure_utc, fmt_ist, history_window, iso
from .events import apply_filters, resolve_range

router = APIRouter(prefix="/api/analytics", tags=["analytics"], dependencies=[Depends(get_current_user)])
INDUSTRIAL = {"INDUSTRIAL_FIRE", "PERSISTENT_INDUSTRIAL_HEAT", "GAS_FLARE", "REFINERY_ACTIVITY", "POWER_PLANT_ACTIVITY", "MINING_ACTIVITY"}


def _block(events: list[ThermalEvent]) -> dict:
    pops = [e.exposed_population for e in events if e.exposed_population is not None]
    return {"total_events": len(events), "live_events": sum(1 for e in events if e.data_status == "LIVE"), "historical_events": sum(1 for e in events if e.data_status == "HISTORICAL"),
            "active_events": sum(1 for e in events if e.status == "ACTIVE"), "industrial_events": sum(1 for e in events if e.classification in INDUSTRIAL),
            "wildfires": sum(1 for e in events if e.classification == "WILDFIRE"), "agricultural": sum(1 for e in events if e.classification == "AGRICULTURAL_BURN"),
            "persistent_sources": sum(1 for e in events if e.persistence_class == "PERSISTENT"), "high_risk": sum(1 for e in events if e.risk_level == "HIGH"),
            "critical": sum(1 for e in events if e.risk_level == "CRITICAL"), "verified": sum(1 for e in events if e.human_status != "PENDING"), "unverified": sum(1 for e in events if e.human_status == "PENDING"),
            "estimated_exposure": int(sum(pops)) if pops else None, "exposure_events_with_estimate": len(pops), "max_risk": max((e.risk_score for e in events), default=0),
            "avg_risk": round(sum(e.risk_score for e in events) / len(events), 1) if events else 0, "total_frp": round(sum(e.total_frp for e in events), 1),
            "total_detections": sum(e.detection_count for e in events)}


def _events(db: Session, range_, date_from, date_to, state=None):
    d_from, d_to, ds = resolve_range(range_, date_from, date_to)
    q = apply_filters(select(ThermalEvent), state=state, date_from=d_from, date_to=d_to, data_status=ds)
    return db.execute(q).scalars().all(), (d_from, d_to, ds)


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), range_: str | None = Query(default=None, alias="range"), date_from: datetime | None = None, date_to: datetime | None = None):
    events, (d_from, d_to, ds) = _events(db, range_, date_from, date_to)
    cards = _block(events)
    cards["total_observations"] = db.execute(select(func.count(ThermalDetection.id)).where(ThermalDetection.acq_datetime >= d_from) if d_from else select(func.count(ThermalDetection.id))).scalar() or 0
    cards["live_observations"] = db.execute(select(func.count(ThermalDetection.id)).where(ThermalDetection.data_status == "LIVE")).scalar() or 0
    now = datetime.now(timezone.utc)
    span_days = 30 if not d_from else max(7, min(366, (now - d_from).days + 1))
    days = [(now - timedelta(days=i)).date().isoformat() for i in range(span_days - 1, -1, -1)]
    per_day = {d: {"day": d, "new_events": 0, "detections": 0, "frp": 0.0} for d in days}
    ids = {e.id for e in events}
    for e in events:
        d = ensure_utc(e.first_detected_at).date().isoformat()
        if d in per_day:
            per_day[d]["new_events"] += 1
    if ids:
        for o in db.execute(select(EventObservation).where(EventObservation.event_id.in_(list(ids)))).scalars().all():
            if o.day in per_day:
                per_day[o.day]["detections"] += o.detections
                per_day[o.day]["frp"] += o.sum_frp
    for v in per_day.values():
        v["frp"] = round(v["frp"], 1)
    industrial_areas = Counter()
    for e in events:
        ind = (e.gis_context or {}).get("nearest_industrial_any")
        if ind and ind["distance_km"] <= 5:
            industrial_areas[ind["name"]] += 1
    pop_by_state = defaultdict(int)
    for e in events:
        if e.exposed_population:
            pop_by_state[e.state or "State unavailable"] += e.exposed_population
    live_latest = latest_observation_time(db, "LIVE")
    lo, hi = history_window()
    return {
        "generated_at": now.isoformat(), "range": {"from": iso(d_from), "to": iso(d_to), "data_status": ds or None, "label": range_ or ("custom" if d_from else "all (12 months)")},
        "history_window": {"from": iso(lo), "to": iso(hi), "label": f"{lo.strftime('%d %b %Y')} → {hi.strftime('%d %b %Y')}"},
        "live": {"latest_observation": iso(live_latest), "latest_observation_ist": fmt_ist(live_latest) if live_latest else None, "live_window_hours": settings.live_window_hours,
                 "is_stale": (now - ensure_utc(live_latest)) > timedelta(hours=settings.live_window_hours) if live_latest else True},
        "freshness": freshness.snapshot(db), "cards": cards,
        "events_by_state": [{"state": s or "State unavailable", "count": c} for s, c in Counter(e.state for e in events).most_common()],
        "classification_distribution": [{"classification": c, "label": CLASS_LABELS.get(c, c), "count": n} for c, n in Counter(e.classification for e in events).most_common()],
        "risk_distribution": [{"level": lvl, "count": Counter(e.risk_level for e in events).get(lvl, 0)} for lvl in ("LOW", "MODERATE", "MEDIUM", "HIGH", "CRITICAL")],
        "events_over_time": list(per_day.values()), "top_industrial_areas": [{"name": n, "events": c} for n, c in industrial_areas.most_common(10)],
        "population_exposure_by_state": sorted([{"state": s, "population": p} for s, p in pop_by_state.items()], key=lambda x: -x["population"])[:12],
        "top_priority_live": [event_summary(e) for e in sorted([e for e in events if e.data_status == "LIVE"], key=lambda e: -e.priority_score)[:8]],
        "top_priority_historical": [event_summary(e) for e in sorted([e for e in events if e.data_status == "HISTORICAL"], key=lambda e: -e.priority_score)[:8]],
        "recent_alerts": [event_summary(e) for e in sorted([e for e in events if e.risk_level in ("HIGH", "CRITICAL")], key=lambda e: (e.data_status != "LIVE", -e.risk_score))[:8]],
    }


@router.get("/india")
def india(db: Session = Depends(get_db), range_: str | None = Query(default=None, alias="range"), date_from: datetime | None = None, date_to: datetime | None = None):
    events, (d_from, d_to, ds) = _events(db, range_, date_from, date_to)
    by_state: dict[str, list[ThermalEvent]] = defaultdict(list)
    for e in events:
        by_state[e.state].append(e)
    states = [{"state": s["name"], "code": s["code"], "centroid": s["centroid"], "density": s.get("density"), "observations": "found" if by_state.get(s["name"]) else "no_observations", **_block(by_state.get(s["name"], []))} for s in load_states()]
    states.sort(key=lambda x: (-x["total_events"], x["state"]))
    return {"range": {"from": iso(d_from), "to": iso(d_to), "data_status": ds or None}, "national": _block(events), "states": states,
            "note": "'no_observations' means no thermal event was formed in this state for the selected range; it is not a measurement of zero fires."}


@router.get("/state/{state}")
def state_detail(state: str, db: Session = Depends(get_db), range_: str | None = Query(default=None, alias="range"), date_from: datetime | None = None, date_to: datetime | None = None):
    boundary = db.execute(select(AdminBoundary).where(AdminBoundary.name == state, AdminBoundary.level == "state")).scalar_one_or_none()
    if boundary is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown state '{state}'")
    events, (d_from, d_to, ds) = _events(db, range_, date_from, date_to, state=state)
    events.sort(key=lambda e: -e.priority_score)
    by_district: dict[str, list[ThermalEvent]] = defaultdict(list)
    for e in events:
        by_district[e.district or "District unavailable"].append(e)
    known = {d["name"]: d for d in districts_for_state(state)}
    districts = [{"district": d, "known_osm_district": d in known, "centroid": [known[d]["lat"], known[d]["lon"]] if d in known else None, **_block(evs)} for d, evs in by_district.items()]
    districts.sort(key=lambda x: -x["total_events"])
    return {"state": state, "code": boundary.code, "bbox": [boundary.min_lat, boundary.min_lon, boundary.max_lat, boundary.max_lon], "centroid": [boundary.centroid_lat, boundary.centroid_lon],
            "population_density": boundary.population_density, "range": {"from": iso(d_from), "to": iso(d_to), "data_status": ds or None}, "summary": _block(events), "districts": districts,
            "all_districts": [d["name"] for d in districts_for_state(state)],
            "classification_distribution": [{"classification": c, "label": CLASS_LABELS.get(c, c), "count": n} for c, n in Counter(e.classification for e in events).most_common()],
            "events": [event_summary(e) for e in events[:500]]}
