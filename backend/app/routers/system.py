from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth.security import get_current_user, require_admin
from ..config import HISTORY_LIMIT_DAYS, settings
from ..database import IS_POSTGRES, get_db
from ..models import AuditLog, EventReport, ThermalDetection, ThermalEvent, User
from ..services import email_service, freshness, ingest_service
from ..services.audit import log_action
from ..services.serializers import event_summary
from ..utils.timeutil import history_window, iso

router = APIRouter(prefix="/api/system", tags=["system"])

DATA_NOTICE = ("THERMO-SHIELD INDIA uses satellite, GIS, weather and other external datasets. Satellite detections represent observed thermal anomalies and do not by themselves prove a fire, "
               "its exact cause, severity, or ground impact. AI classifications and exposure estimates are decision-support outputs and require appropriate human/field verification.")


@router.get("/status")
def status_(db: Session = Depends(get_db)):
    """Public (unauthenticated) status: no counts, no secrets."""
    lo, hi = history_window()
    return {"app": settings.app_name, "version": settings.app_version, "time": datetime.now(timezone.utc).isoformat(), "database": "postgresql+postgis" if IS_POSTGRES else "sqlite (development fallback)",
            "data_policy": "REAL DATA ONLY — no demo / synthetic thermal data", "history_window": {"from": iso(lo), "to": iso(hi), "days": HISTORY_LIMIT_DAYS}, "live_window_hours": settings.live_window_hours,
            "email_configured": email_service.email_status()["configured"], "registration_open": True, "data_notice": DATA_NOTICE}


@router.get("/overview", dependencies=[Depends(get_current_user)])
def overview(db: Session = Depends(get_db)):
    ml = __import__("app.ml.predict", fromlist=["model_info"]).model_info()
    return {
        "providers": {"firms": ("area API" if settings.firms_key else f"public feed ({settings.firms_public_region}, {settings.firms_public_window})"), "firms_archive": "available (MAP_KEY)" if settings.firms_key else "unavailable (NASA_FIRMS_MAP_KEY missing)",
                      "weather": settings.weather_provider, "osm": settings.osm_provider, "nominatim": settings.nominatim_enabled, "satellite": settings.satellite_provider, "landcover": settings.landcover_provider,
                      "population": settings.population_data_source, "email": email_service.email_status(), "ml_model": "lightgbm" if ml.get("available") else "rules (ML model unavailable — insufficient validated training data)"},
        "counts": {"events": db.execute(select(func.count(ThermalEvent.id))).scalar(), "live_events": db.execute(select(func.count(ThermalEvent.id)).where(ThermalEvent.data_status == "LIVE")).scalar(),
                   "detections": db.execute(select(func.count(ThermalDetection.id))).scalar(), "live_detections": db.execute(select(func.count(ThermalDetection.id)).where(ThermalDetection.data_status == "LIVE")).scalar(),
                   "reports": db.execute(select(func.count(EventReport.id)).where(EventReport.status == "generated")).scalar(), "users": db.execute(select(func.count(User.id))).scalar()},
        "scheduler_enabled": settings.enable_scheduler, "firms_poll_minutes": settings.firms_poll_minutes, "auto_generate_pdf": settings.auto_generate_pdf, "freshness": freshness.snapshot(db),
        "last_ingest": ingest_service.last_run_info, "data_notice": DATA_NOTICE,
        "data_labels": {"OBSERVED": "directly obtained from a source (FIRMS, OSM, weather API, gazetteer)", "CALCULATED": "derived from observed data by documented formulas", "MODEL INFERENCE": "AI / rule inference",
                        "ESTIMATE": "calculated approximation (exposure, population, land cover)", "HUMAN VERIFIED": "confirmed / modified by an authorised analyst", "UNAVAILABLE": "no data from any source"},
    }


@router.get("/verification-queue", dependencies=[Depends(get_current_user)])
def verification_queue(db: Session = Depends(get_db), limit: int = Query(default=100, ge=1, le=500)):
    pending = db.execute(select(ThermalEvent).where(ThermalEvent.human_status == "PENDING").order_by(ThermalEvent.data_status.desc(), ThermalEvent.priority_score.desc()).limit(limit)).scalars().all()
    done = db.execute(select(ThermalEvent).where(ThermalEvent.human_status != "PENDING").order_by(ThermalEvent.updated_at.desc()).limit(limit)).scalars().all()
    return {"pending": [event_summary(e) for e in pending], "completed": [event_summary(e) for e in done]}


@router.get("/audit")
def audit(db: Session = Depends(get_db), user: User = Depends(require_admin), limit: int = Query(default=100, ge=1, le=1000)):
    rows = db.execute(select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit)).scalars().all()
    return {"items": [{"id": a.id, "timestamp": iso(a.timestamp), "actor": a.actor, "action": a.action, "entity_type": a.entity_type, "entity_id": a.entity_id, "details": a.details} for a in rows]}


def _reanalyse_job(live: bool):
    from ..database import SessionLocal
    from ..services.analysis_pipeline import reanalyse_all
    from ..services.priority_service import rerank_all

    with SessionLocal() as db:
        reanalyse_all(db, live=live)
        rerank_all(db)
        db.commit()


@router.post("/reanalyse-all")
def reanalyse_all_endpoint(background: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(require_admin), live: bool = False):
    log_action(db, user.email, "reanalyse_all", "system", "", {"live": live})
    db.commit()
    background.add_task(_reanalyse_job, live)
    return {"message": "Re-analysis of all incidents started in background (new risk snapshot → momentum)"}


@router.post("/maintenance")
def maintenance(background: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    log_action(db, user.email, "maintenance", "system", "")
    db.commit()
    background.add_task(ingest_service.maintenance, "manual")
    return {"message": "Maintenance started (age LIVE → HISTORICAL, enforce 12-month limit, refresh live risk)"}


@router.post("/generate-visuals")
def generate_visuals(background: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(require_admin), limit: int = Query(default=40, ge=1, le=500)):
    log_action(db, user.email, "generate_visuals", "system", "", {"limit": limit})
    db.commit()
    background.add_task(ingest_service.background_visuals, limit)
    return {"message": f"Image + PDF generation for the top {limit} incidents started in background"}
