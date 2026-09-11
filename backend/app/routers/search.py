"""Global search: incident IDs, states, districts, localities, facilities, classifications and raw coordinates."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..auth.security import get_current_user
from ..database import get_db
from ..ml.features import CLASS_LABELS
from ..models import GasFacility, IndustrialFacility, Mine, Population, PowerPlant, Refinery, ThermalEvent
from ..services.reference_data import load_districts, load_states
from ..services.serializers import event_summary

router = APIRouter(prefix="/api/search", tags=["search"], dependencies=[Depends(get_current_user)])
COORD_RE = re.compile(r"^\s*(-?\d{1,2}(?:\.\d+)?)\s*[, ]\s*(-?\d{1,3}(?:\.\d+)?)\s*$")


@router.get("")
def search(q: str = Query(min_length=1, max_length=120), db: Session = Depends(get_db), limit: int = Query(default=8, ge=1, le=50)):
    q = q.strip()
    results: dict = {"query": q, "coordinates": None, "incidents": [], "places": [], "facilities": [], "classifications": [], "states": [], "districts": []}
    m = COORD_RE.match(q)
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            results["coordinates"] = {"latitude": lat, "longitude": lon, "action": f"/location-analysis?lat={lat}&lon={lon}"}
    like = f"%{q}%"
    evs = db.execute(select(ThermalEvent).where(or_(ThermalEvent.incident_id.like(like), ThermalEvent.state.like(like), ThermalEvent.district.like(like), ThermalEvent.locality.like(like),
                                                    ThermalEvent.classification.like(f"%{q.upper().replace(' ', '_')}%"))).order_by(ThermalEvent.priority_score.desc()).limit(limit)).scalars().all()
    results["incidents"] = [event_summary(e) for e in evs]
    for p in db.execute(select(Population).where(Population.name.like(like)).limit(limit)).scalars().all():
        results["places"].append({"name": p.name, "type": p.settlement_type, "state": p.state, "district": p.district, "latitude": p.latitude, "longitude": p.longitude, "population": p.population})
    for model in (Refinery, PowerPlant, Mine, GasFacility, IndustrialFacility):
        for f in db.execute(select(model).where(or_(model.name.like(like), model.operator.like(like))).limit(limit)).scalars().all():
            results["facilities"].append({"name": f.name, "category": f.category, "subtype": f.subtype, "operator": f.operator, "state": f.state, "district": f.district, "latitude": f.latitude, "longitude": f.longitude})
    ql = q.lower()
    results["classifications"] = [{"classification": c, "label": l} for c, l in CLASS_LABELS.items() if ql in l.lower() or ql in c.lower()]
    results["states"] = [{"name": s["name"], "code": s["code"], "centroid": s["centroid"]} for s in load_states() if ql in s["name"].lower() or ql == s["code"].lower()]
    results["districts"] = [{"name": d["name"], "state": d["state"], "lat": d["lat"], "lon": d["lon"]} for d in load_districts() if ql in d["name"].lower()][:limit]
    results["facilities"] = results["facilities"][:limit]
    return results
