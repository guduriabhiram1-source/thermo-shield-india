from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth.security import get_current_user, require_admin, require_analyst
from ..config import HISTORY_LIMIT_DAYS, settings
from ..database import get_db
from ..models import IngestionRun, ThermalDetection, User
from ..schemas import BackfillRequest, IngestRequest
from ..services import ingest_service
from ..services.alert_service import evaluate_live_alerts
from ..services.analysis_pipeline import analyse_event
from ..services.audit import log_action
from ..services.firms.nasa_firms import PUBLIC_SOURCES, AreaApiProvider, PublicFeedProvider, parse_csv_text, public_feed_url
from ..services.firms_service import ingest_rows, latest_detections, latest_observation_time
from ..services.priority_service import rerank_all
from ..services.serializers import detection_out
from ..services.thermal_event_service import form_events, update_event_aggregates
from ..utils.timeutil import history_window, iso

router = APIRouter(prefix="/api/firms", tags=["firms"], dependencies=[Depends(get_current_user)])


def _run_out(r: IngestionRun) -> dict:
    return {"id": r.id, "started_at": iso(r.started_at), "finished_at": iso(r.finished_at), "source": r.source, "mode": r.mode, "data_status": r.data_status, "rows_received": r.rows_received,
            "rows_valid": r.rows_valid, "rows_live": r.rows_live, "rows_historical": r.rows_historical, "rows_duplicate": r.rows_duplicate, "rows_rejected": r.rows_rejected,
            "rejection_reasons": r.rejection_reasons, "events_formed": r.events_formed, "events_touched": r.events_touched, "alerts_sent": r.alerts_sent, "latest_observation": iso(r.latest_observation),
            "status": r.status, "message": r.message, "feed_status": r.feed_status}


@router.get("/latest")
def latest(db: Session = Depends(get_db), limit: int = Query(default=500, ge=1, le=5000), hours: int | None = Query(default=None, ge=1, le=24 * 366), data_status: str | None = Query(default=None, pattern="^(LIVE|HISTORICAL)$")):
    rows = latest_detections(db, limit=limit, hours=hours, data_status=data_status)
    total = db.execute(select(func.count(ThermalDetection.id))).scalar()
    live_total = db.execute(select(func.count(ThermalDetection.id)).where(ThermalDetection.data_status == "LIVE")).scalar()
    last_run = db.execute(select(IngestionRun).order_by(IngestionRun.started_at.desc())).scalars().first()
    lo, hi = history_window()
    return {"total_detections": total, "live_detections": live_total, "returned": len(rows), "firms_key_configured": bool(settings.firms_key),
            "source": f"FIRMS area API ({settings.firms_sources})" if settings.firms_key else f"public feed {settings.firms_public_region} {settings.firms_public_window} ({settings.firms_public_sources})",
            "public_feeds": {s: public_feed_url(s) for s in PUBLIC_SOURCES if s in settings.firms_public_sources}, "area": settings.firms_area,
            "latest_live_observation": iso(latest_observation_time(db, "LIVE")), "latest_observation": iso(latest_observation_time(db)), "live_window_hours": settings.live_window_hours,
            "history_window": {"from": iso(lo), "to": iso(hi), "days": HISTORY_LIMIT_DAYS}, "last_run": _run_out(last_run) if last_run else None, "last_run_info": ingest_service.last_run_info,
            "items": [detection_out(d) for d in rows]}


@router.get("/runs")
def runs(db: Session = Depends(get_db), limit: int = Query(default=20, ge=1, le=200)):
    return {"items": [_run_out(r) for r in db.execute(select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(limit)).scalars().all()]}


@router.post("/ingest")
def ingest(body: IngestRequest, db: Session = Depends(get_db), user: User = Depends(require_analyst)):
    """Synchronous ingestion (API / public feed / CSV upload). CSV rows are LIVE only when newer than the live window (or when explicitly forced by an ADMIN)."""
    mode = body.mode
    if mode == "auto":
        mode = "api" if settings.firms_key else "public"
    force = None
    if mode == "public":
        feed = PublicFeedProvider().fetch_latest(window=body.window)
        if not feed.rows and all(v.startswith("failed") for v in feed.status.values()):
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"FIRMS public feeds unreachable: {feed.status}")
        rows, label, run_mode, feed_status = feed.rows, "FIRMS_PUBLIC", "live", feed.status
    elif mode == "api":
        if not settings.firms_key:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "NASA_FIRMS_MAP_KEY not configured — set it in .env (never in the frontend), or use mode=public")
        feed = AreaApiProvider().fetch_latest(sources=[s.strip() for s in body.sources.split(",")] if body.sources else None, days=body.days)
        if not feed.rows and all(v.startswith("failed") for v in feed.status.values()):
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"FIRMS API request failed: {feed.status}")
        rows, label, run_mode, feed_status = feed.rows, "FIRMS_API", "live", feed.status
    else:
        if not body.csv_text:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "csv_text is required for mode=csv")
        rows, label, run_mode, feed_status = parse_csv_text(body.csv_text, source="FIRMS_CSV"), "FIRMS_CSV", "csv", None
        if body.csv_data_status != "auto":
            if user.role != "ADMIN":
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Only ADMIN may force the data_status of uploaded rows")
            force = body.csv_data_status
    run = ingest_rows(db, rows, mode=run_mode, source_label=label, feed_status=feed_status, force_status=force)
    new_ids = set(getattr(run, "_new_detection_ids", []))
    new_events, touched_existing = form_events(db, list(new_ids))
    touched = touched_existing | {e.id for e in new_events}
    run.events_formed, run.events_touched = len(new_events), len(touched)
    analysed = 0
    counters = {}
    if body.analyse:
        for eid in sorted(touched):
            from ..models import ThermalEvent

            ev = db.get(ThermalEvent, eid)
            update_event_aggregates(db, ev)
            analyse_event(db, ev, live=False)
            analysed += 1
        rerank_all(db)
        live_new = {d.id for d in db.execute(select(ThermalDetection).where(ThermalDetection.id.in_(list(new_ids)), ThermalDetection.data_status == "LIVE")).scalars().all()} if new_ids else set()
        alert_events = {d.event_id for d in db.execute(select(ThermalDetection).where(ThermalDetection.id.in_(list(live_new)))).scalars().all() if d.event_id} if live_new else set()
        counters = evaluate_live_alerts(db, alert_events, live_new, run)
    log_action(db, user.email, "firms_ingest", "ingestion_run", run.id, {"mode": mode, "valid": run.rows_valid, "live": run.rows_live})
    db.commit()
    return {"run": _run_out(run), "events_formed": len(new_events), "events_touched": len(touched), "events_analysed": analysed, "alerts": counters}


@router.post("/live-ingest")
def trigger_live_ingest(background: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    log_action(db, user.email, "live_ingest", "system", "")
    db.commit()
    background.add_task(ingest_service.live_ingest, "manual")
    return {"message": "Live FIRMS ingest started in background"}


@router.post("/backfill")
def backfill(body: BackfillRequest, background: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """Historical backfill (≤ 12 months) through the FIRMS archive API. Ingested rows are HISTORICAL and never trigger live alerts."""
    if not settings.firms_key:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Historical data unavailable — NASA_FIRMS_MAP_KEY is required for the FIRMS archive API")
    start = body.start_date.date()
    end = (body.end_date or datetime.now(timezone.utc)).date()
    lo = datetime.now(timezone.utc).date() - timedelta(days=HISTORY_LIMIT_DAYS)
    if end < lo:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Requested range is entirely older than the 12-month window (from {lo.isoformat()})")
    log_action(db, user.email, "firms_backfill", "system", "", {"start": start.isoformat(), "end": end.isoformat()})
    db.commit()
    background.add_task(ingest_service.backfill_archive, max(start, lo), end, [s.strip() for s in body.sources.split(",")] if body.sources else None, user.email)
    return {"message": f"Historical backfill {max(start, lo).isoformat()} → {end.isoformat()} started in background (HISTORICAL data; no live alerts)"}
