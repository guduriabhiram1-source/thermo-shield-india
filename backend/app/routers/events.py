from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..auth.security import get_current_user, require_analyst
from ..config import settings
from ..database import get_db
from ..ml.features import CLASS_LABELS, CLASSES
from ..models import EventImage, EventReport, HumanVerification, ThermalEvent, TrainingSample, User
from ..schemas import AnalyzeEventRequest, VerifyRequest
from ..services.analysis_pipeline import analyse_event
from ..services.audit import log_action
from ..services.evolution_service import build_timeline
from ..services.image_service import generate_event_images
from ..services.pdf_service import build_pdf
from ..services.priority_service import rerank_all
from ..services.serializers import detection_out, event_detail, event_summary, image_out, report_out, risk_out, verification_out
from ..services.thermal_event_service import event_detections
from ..utils.ids import next_incident_id
from ..utils.timeutil import clamp_to_history, history_window, iso

router = APIRouter(prefix="/api/events", tags=["events"], dependencies=[Depends(get_current_user)])
RANGES = {"live": None, "24h": 1, "3d": 3, "7d": 7, "30d": 30, "3m": 92, "6m": 183, "12m": 366}


def get_event(db: Session, ident: str) -> ThermalEvent:
    ev = db.execute(select(ThermalEvent).where(ThermalEvent.incident_id == ident)).scalar_one_or_none()
    if ev is None and ident.isdigit():
        ev = db.get(ThermalEvent, int(ident))
    if ev is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Incident {ident} not found")
    return ev


def resolve_range(range_: str | None, date_from: datetime | None, date_to: datetime | None) -> tuple[datetime | None, datetime | None, str]:
    """Global date selector → (from, to, data_status filter). Always clamped to the 12-month window."""
    now = datetime.now(timezone.utc)
    if range_ == "live":
        return now - timedelta(hours=settings.live_window_hours), None, "LIVE"
    if range_ in RANGES and RANGES[range_]:
        return now - timedelta(days=RANGES[range_]), None, ""
    if date_from or date_to:
        s, e = clamp_to_history(date_from, date_to, now)
        return s, e, ""
    return None, None, ""


def apply_filters(q, *, state=None, district=None, classification=None, risk_level=None, persistence=None, satellite=None, verified=None, date_from=None, date_to=None,
                  min_population=None, status_=None, data_status=None, search=None):
    if state:
        q = q.where(ThermalEvent.state == state)
    if district:
        q = q.where(ThermalEvent.district == district)
    if classification:
        q = q.where(ThermalEvent.classification.in_([c.strip().upper() for c in classification.split(",")]))
    if risk_level:
        q = q.where(ThermalEvent.risk_level.in_([r.strip().upper() for r in risk_level.split(",")]))
    if persistence:
        q = q.where(ThermalEvent.persistence_class.in_([p.strip().upper() for p in persistence.split(",")]))
    if satellite:
        q = q.where(ThermalEvent.satellites.like(f"%{satellite}%"))
    if verified == "verified":
        q = q.where(ThermalEvent.human_status != "PENDING")
    elif verified == "unverified":
        q = q.where(ThermalEvent.human_status == "PENDING")
    if date_from:
        q = q.where(ThermalEvent.last_detected_at >= date_from)
    if date_to:
        q = q.where(ThermalEvent.first_detected_at <= date_to)
    if min_population:
        q = q.where(ThermalEvent.exposed_population >= min_population)
    if status_:
        q = q.where(ThermalEvent.status == status_.upper())
    if data_status:
        q = q.where(ThermalEvent.data_status == data_status.upper())
    if search:
        like = f"%{search}%"
        q = q.where(or_(ThermalEvent.incident_id.like(like), ThermalEvent.state.like(like), ThermalEvent.district.like(like), ThermalEvent.locality.like(like),
                        ThermalEvent.classification.like(like.upper().replace(" ", "_")), ThermalEvent.probable_cause.like(like)))
    return q


@router.get("")
def list_events(
    db: Session = Depends(get_db), state: str | None = None, district: str | None = None, classification: str | None = None, risk_level: str | None = None,
    persistence: str | None = None, satellite: str | None = None, verified: str | None = Query(default=None, pattern="^(verified|unverified)$"),
    range_: str | None = Query(default=None, alias="range", pattern="^(live|24h|3d|7d|30d|3m|6m|12m|custom)$"), date_from: datetime | None = None, date_to: datetime | None = None,
    min_population: int | None = Query(default=None, ge=0), industrial_km: float | None = Query(default=None, ge=0), status_: str | None = Query(default=None, alias="status"),
    data_status: str | None = Query(default=None, pattern="^(LIVE|HISTORICAL)$"), q: str | None = None,
    sort: str = Query(default="priority", pattern="^(priority|risk|recent|frp|population|persistence)$"), limit: int = Query(default=100, ge=1, le=2000), offset: int = Query(default=0, ge=0),
):
    d_from, d_to, ds = resolve_range(range_, date_from, date_to)
    query = apply_filters(select(ThermalEvent), state=state, district=district, classification=classification, risk_level=risk_level, persistence=persistence, satellite=satellite,
                          verified=verified, date_from=d_from, date_to=d_to, min_population=min_population, status_=status_, data_status=data_status or ds, search=q)
    order = {"priority": ThermalEvent.priority_score.desc(), "risk": ThermalEvent.risk_score.desc(), "recent": ThermalEvent.last_detected_at.desc(), "frp": ThermalEvent.max_frp.desc(),
             "population": ThermalEvent.exposed_population.desc(), "persistence": ThermalEvent.persistence_score.desc()}[sort]
    rows = db.execute(query.order_by(order)).scalars().all()
    if industrial_km is not None:
        rows = [e for e in rows if (e.gis_context or {}).get("nearest_industrial_any") and e.gis_context["nearest_industrial_any"]["distance_km"] <= industrial_km]
    lo, hi = history_window()
    return {"total": len(rows), "limit": limit, "offset": offset, "range": {"from": iso(d_from), "to": iso(d_to), "data_status": data_status or ds or None},
            "history_window": {"from": iso(lo), "to": iso(hi)}, "items": [event_summary(e) for e in rows[offset: offset + limit]]}


@router.get("/geojson")
def events_geojson(db: Session = Depends(get_db), state: str | None = None, district: str | None = None, risk_level: str | None = None, classification: str | None = None,
                   range_: str | None = Query(default=None, alias="range"), date_from: datetime | None = None, date_to: datetime | None = None, data_status: str | None = None):
    d_from, d_to, ds = resolve_range(range_, date_from, date_to)
    query = apply_filters(select(ThermalEvent), state=state, district=district, classification=classification, risk_level=risk_level, date_from=d_from, date_to=d_to, data_status=data_status or ds)
    feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [e.longitude, e.latitude]}, "properties": event_summary(e)} for e in db.execute(query).scalars().all()]
    return {"type": "FeatureCollection", "features": feats}


@router.get("/priority")
def priority(db: Session = Depends(get_db), limit: int = Query(default=10, ge=1, le=100), data_status: str = Query(default="LIVE", pattern="^(LIVE|HISTORICAL)$")):
    rows = db.execute(select(ThermalEvent).where(ThermalEvent.data_status == data_status).order_by(ThermalEvent.priority_score.desc()).limit(limit)).scalars().all()
    return {"data_status": data_status, "items": [event_summary(e) for e in rows]}


@router.get("/classes")
def classes():
    return {"classes": CLASSES, "labels": CLASS_LABELS}


@router.post("/analyze")
def analyze(body: AnalyzeEventRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Re-run the full pipeline for an incident, or create an ad-hoc coordinate analysis (marked data_source=ADHOC, zero detections — nothing is invented)."""
    if body.incident_id:
        ev = get_event(db, body.incident_id)
    elif body.latitude is not None and body.longitude is not None:
        now = body.timestamp or datetime.now(timezone.utc)
        ev = ThermalEvent(incident_id=next_incident_id(db), latitude=body.latitude, longitude=body.longitude, first_detected_at=now, last_detected_at=now, detection_count=0, active_days=1,
                          data_source="ADHOC", status="INACTIVE", data_status="HISTORICAL")
        db.add(ev)
        db.flush()
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Provide incident_id or latitude/longitude")
    analyse_event(db, ev, live=body.live_enrichment, with_images=body.with_images, with_pdf=body.with_pdf, actor=user.email)
    rerank_all(db)
    log_action(db, user.email, "analyze_event", "event", ev.incident_id)
    db.commit()
    db.refresh(ev)
    return event_detail(ev, event_detections(db, ev))


@router.get("/{ident}")
def get_detail(ident: str, db: Session = Depends(get_db)):
    ev = get_event(db, ident)
    return event_detail(ev, event_detections(db, ev))


@router.get("/{ident}/detections")
def detections(ident: str, db: Session = Depends(get_db)):
    ev = get_event(db, ident)
    return {"incident_id": ev.incident_id, "items": [detection_out(d) for d in event_detections(db, ev)]}


@router.get("/{ident}/timeline")
def timeline(ident: str, db: Session = Depends(get_db)):
    ev = get_event(db, ident)
    return {"incident_id": ev.incident_id, "first_observed": iso(ev.first_detected_at), "last_observed": iso(ev.last_detected_at), "items": ev.timeline or build_timeline(db, ev), "evolution": ev.evolution}


@router.get("/{ident}/risk")
def risk(ident: str, db: Session = Depends(get_db)):
    ev = get_event(db, ident)
    return {"incident_id": ev.incident_id, "risk_score": ev.risk_score, "risk_level": ev.risk_level, "momentum": ev.risk_momentum, "trend": ev.risk_trend, "breakdown": ev.risk_breakdown,
            "change": ev.risk_change, "history": [risk_out(r) for r in ev.risk_scores], "priority_score": ev.priority_score, "priority_rank": ev.priority_rank, "data_status": ev.data_status}


@router.get("/{ident}/exposure")
def exposure(ident: str, db: Session = Depends(get_db)):
    ev = get_event(db, ident)
    return {"incident_id": ev.incident_id, "weather": ev.weather, "exposure": ev.exposure, "exposed_population": ev.exposed_population, "exposure_level": ev.exposure_level}


@router.get("/{ident}/images")
def images(ident: str, db: Session = Depends(get_db), regenerate: bool = False):
    ev = get_event(db, ident)
    if regenerate or not ev.images:
        generate_event_images(db, ev)
        db.commit()
        db.refresh(ev)
    return {"incident_id": ev.incident_id, "items": [image_out(i) for i in ev.images]}


@router.get("/{ident}/images/{image_type}.png", dependencies=[])
def image_file(ident: str, image_type: str, db: Session = Depends(get_db)):
    ev = get_event(db, ident)
    img = db.execute(select(EventImage).where(EventImage.event_id == ev.id, EventImage.image_type == image_type)).scalars().first()
    if img is None or not img.file_path or not os.path.exists(img.file_path):
        generate_event_images(db, ev)
        db.commit()
        img = db.execute(select(EventImage).where(EventImage.event_id == ev.id, EventImage.image_type == image_type)).scalars().first()
    if img is None or not img.file_path or not os.path.exists(img.file_path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image unavailable for this event")
    return FileResponse(img.file_path, media_type="image/png")


@router.get("/{ident}/satellite")
def satellite(ident: str, db: Session = Depends(get_db), search: bool = False):
    from ..services.satellite_service import satellite_evidence

    ev = get_event(db, ident)
    if search:
        ev.satellite = satellite_evidence(ev.latitude, ev.longitude, ev.first_detected_at, ev.last_detected_at, search=True)
        generate_event_images(db, ev)
        db.commit()
    return {"incident_id": ev.incident_id, "satellite": ev.satellite}


@router.get("/{ident}/pdf")
def latest_pdf(ident: str, db: Session = Depends(get_db), download: bool = True):
    ev = get_event(db, ident)
    rep = db.execute(select(EventReport).where(EventReport.event_id == ev.id, EventReport.status == "generated").order_by(EventReport.created_at.desc())).scalars().first()
    if rep is None or not os.path.exists(rep.file_path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No PDF generated yet — call POST /generate-pdf")
    return FileResponse(rep.file_path, media_type="application/pdf", headers={"Content-Disposition": f"{'attachment' if download else 'inline'}; filename={rep.file_name}"})


@router.post("/{ident}/generate-pdf")
def generate_pdf(ident: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ev = get_event(db, ident)
    rep = build_pdf(db, ev, generated_by=user.email)
    log_action(db, user.email, "generate_pdf", "event", ev.incident_id, {"status": rep.status})
    db.commit()
    if rep.status != "generated":
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"PDF generation failed: {rep.error}")
    return {"message": "Report generated successfully", "report": report_out(rep, ev)}


@router.post("/{ident}/verify")
def verify(ident: str, body: VerifyRequest, db: Session = Depends(get_db), user: User = Depends(require_analyst)):
    ev = get_event(db, ident)
    if body.action == "CORRECT" and not body.classification:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "classification is required when correcting")
    verified_cls = ev.classification if body.action == "CONFIRM" else body.classification if body.action == "CORRECT" else None
    v = HumanVerification(event_id=ev.id, analyst_id=user.id, analyst=user.email, action=body.action, original_prediction=ev.classification, original_confidence=ev.classification_confidence,
                          verified_classification=verified_cls, probable_cause=body.probable_cause, notes=body.notes)
    db.add(v)
    db.flush()
    ev.human_status = {"CONFIRM": "VERIFIED", "CORRECT": "CORRECTED", "UNCERTAIN": "UNCERTAIN"}[body.action]
    ev.verified_classification = verified_cls
    if verified_cls and ev.features:
        db.add(TrainingSample(event_id=ev.id, incident_id=ev.incident_id, features=ev.features, verified_label=verified_cls, analyst_id=user.id, analyst=user.email,
                              model_version=(ev.explanation or {}).get("model_version") or "", origin="human_verified"))
    if ev.classifications:
        cause = dict(ev.classifications[-1].probable_cause or {})
        cause["verification"] = f"{ev.human_status} by {user.email}"
        ev.classifications[-1].probable_cause = cause
    if verified_cls and verified_cls != ev.classification:
        from ..services.precautions_service import recommend_precautions

        ev.classification = verified_cls
        ev.precautions = recommend_precautions(ev)
    prov = dict(ev.provenance or {})
    prov["human_verification"] = f"HUMAN VERIFIED — {ev.human_status} by {user.email}"
    ev.provenance = prov
    build_timeline(db, ev)
    log_action(db, user.email, f"verify_{body.action.lower()}", "event", ev.incident_id, {"verified": verified_cls, "notes": body.notes})
    db.commit()
    db.refresh(ev)
    return {"message": "Verification stored", "event": event_summary(ev), "verification": verification_out(v)}


@router.get("/{ident}/verifications")
def verifications(ident: str, db: Session = Depends(get_db)):
    ev = get_event(db, ident)
    return {"incident_id": ev.incident_id, "items": [verification_out(v) for v in ev.verifications]}
