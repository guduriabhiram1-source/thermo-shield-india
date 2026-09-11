"""Administrative boundaries: every state / UT and every district of India (OpenStreetMap)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.security import get_current_user
from ..database import get_db
from ..models import ThermalEvent
from ..services.reference_data import districts_for_state, load_districts, load_state_geojson, load_states

router = APIRouter(prefix="/api/boundaries", tags=["boundaries"], dependencies=[Depends(get_current_user)])


@router.get("/states")
def states():
    return {"source": "OpenStreetMap administrative relations (admin_level=4), ODbL", "states": [{"name": s["name"], "code": s["code"], "centroid": s["centroid"], "bbox": s["bbox"], "density": s.get("density")} for s in load_states()]}


@router.get("/states.geojson")
def states_geojson():
    return load_state_geojson()


@router.get("/districts")
def districts(state: str | None = Query(default=None), db: Session = Depends(get_db)):
    """District options update dynamically per state (788 OSM districts). Also returns district names actually present in events so filters never miss data."""
    if state:
        if state not in {s["name"] for s in load_states()}:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown state '{state}'")
        items = districts_for_state(state)
        in_events = sorted({d for (d,) in db.execute(select(ThermalEvent.district).where(ThermalEvent.state == state, ThermalEvent.district != "").distinct()).all()})
    else:
        items = load_districts()
        in_events = sorted({d for (d,) in db.execute(select(ThermalEvent.district).where(ThermalEvent.district != "").distinct()).all()})
    names = {d["name"] for d in items}
    extra = [d for d in in_events if d not in names]
    return {"state": state, "count": len(items), "districts": [{"name": d["name"], "state": d["state"], "lat": d["lat"], "lon": d["lon"], "lgd_code": d.get("lgd_code", "")} for d in items],
            "districts_in_events_not_in_osm_list": extra, "source": "OpenStreetMap admin_level=5 relations (ODbL)"}
