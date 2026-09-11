"""Ingestion orchestration (runs in background threads / the scheduler):

* live_ingest       - pull latest FIRMS (API when a key exists, else public feed), form / extend events,
                      analyse touched events (fast reference pass + live enrichment for the top-N), then evaluate
                      LIVE alerts for events that received NEW LIVE detections.
* backfill_archive  - historical pull (<= 12 months) via the FIRMS area API; never touches the alert pipeline.
* maintenance       - age LIVE → HISTORICAL, purge > 12 months, recompute risk for live events."""
from __future__ import annotations

import logging
import threading
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from ..config import HISTORY_LIMIT_DAYS, settings
from ..database import SessionLocal
from ..models import ThermalDetection, ThermalEvent
from . import freshness
from .alert_service import evaluate_live_alerts
from .analysis_pipeline import analyse_event, archive_expired_events
from .firms.nasa_firms import AreaApiProvider, PublicFeedProvider
from .firms_service import age_live_detections, ingest_rows, purge_expired
from .priority_service import rerank_all
from .thermal_event_service import age_events, form_events, update_event_aggregates

log = logging.getLogger("thermoshield.ingest")
_ingest_lock = threading.Lock()
last_run_info: dict = {}


def _analyse_touched(db, touched: set[int], reason: str) -> tuple[int, int]:
    n = 0
    for eid in sorted(touched):
        ev = db.get(ThermalEvent, eid)
        if ev is None:
            continue
        try:
            update_event_aggregates(db, ev)
            analyse_event(db, ev, live=False)
            n += 1
            db.commit()
        except Exception:
            log.exception("Reference analysis failed for %s", ev.incident_id)
            db.rollback()
        if n and n % 50 == 0:
            log.info("[%s] reference analysis %d/%d", reason, n, len(touched))
    rerank_all(db)
    db.commit()
    top = db.execute(select(ThermalEvent).where(ThermalEvent.id.in_(list(touched))).order_by(ThermalEvent.priority_score.desc()).limit(settings.live_enrich_max)).scalars().all() if touched else []
    m = 0
    for ev in top:
        try:
            analyse_event(db, ev, live=True)
            m += 1
            db.commit()
        except Exception:
            log.exception("Live enrichment failed for %s", ev.incident_id)
            db.rollback()
        if m and m % 25 == 0:
            log.info("[%s] live enrichment %d/%d", reason, m, len(top))
    rerank_all(db)
    db.commit()
    return n, m


def live_ingest(reason: str = "scheduled") -> dict | None:
    if not _ingest_lock.acquire(blocking=False):
        log.info("Ingest already running; skipping (%s)", reason)
        return None
    started = datetime.now(timezone.utc)
    try:
        with SessionLocal() as db:
            try:
                provider = AreaApiProvider() if settings.firms_key else PublicFeedProvider()
                feed = provider.fetch_latest()
                label = "FIRMS_API" if settings.firms_key else "FIRMS_PUBLIC"
                ok = any(v.startswith("ok") for v in feed.status.values())
                freshness.record(db, "firms", f"NASA FIRMS {provider.name}", "ok" if ok else "failed", "; ".join(f"{k}: {v}" for k, v in feed.status.items()))
                if not feed.rows and not ok:
                    db.commit()
                    log.error("FIRMS feed unavailable (%s): %s", reason, feed.status)
                    last_run_info.update({"reason": reason, "status": "feed_unavailable", "feed_status": feed.status, "at": started.isoformat()})
                    return {"status": "feed_unavailable", "feed_status": feed.status}
                run = ingest_rows(db, feed.rows, mode="live", source_label=label, feed_status=feed.status)
                new_ids = set(getattr(run, "_new_detection_ids", []))
                if run.latest_observation:
                    freshness.record(db, "firms", f"NASA FIRMS {provider.name}", "ok", run.message, source_timestamp=run.latest_observation)
                new_events, touched_existing = form_events(db, list(new_ids))
                touched = touched_existing | {e.id for e in new_events}
                touched |= {eid for (eid,) in db.execute(select(ThermalEvent.id).where(ThermalEvent.analysed_at.is_(None))).all()}
                run.events_formed = len(new_events)
                run.events_touched = len(touched)
                db.commit()
                n, m = _analyse_touched(db, touched, reason)
                # --- LIVE ALERTS: only events that received NEW LIVE detections in this run
                live_new_ids = {d.id for d in db.execute(select(ThermalDetection).where(ThermalDetection.id.in_(list(new_ids)), ThermalDetection.data_status == "LIVE")).scalars().all()} if new_ids else set()
                alert_events = {d.event_id for d in db.execute(select(ThermalDetection).where(ThermalDetection.id.in_(list(live_new_ids)))).scalars().all() if d.event_id} if live_new_ids else set()
                counters = evaluate_live_alerts(db, alert_events, live_new_ids, run)
                run.message += f"; {len(touched)} events touched; alerts: {counters}"
                db.commit()
                info = {"reason": reason, "status": "ok", "run": run.message, "events_formed": len(new_events), "events_analysed": n, "events_enriched": m, "alerts": counters, "feed_status": feed.status,
                        "at": started.isoformat(), "duration_s": round((datetime.now(timezone.utc) - started).total_seconds(), 1)}
                last_run_info.update(info)
                log.info("Live ingest (%s) complete: %s", reason, info)
                return info
            except Exception:
                log.exception("Live FIRMS ingest failed (%s)", reason)
                db.rollback()
                last_run_info.update({"reason": reason, "status": "error", "at": started.isoformat()})
                return None
    finally:
        _ingest_lock.release()


def backfill_archive(start: date, end: date | None = None, sources: list[str] | None = None, actor: str = "system") -> dict:
    """Historical backfill through the FIRMS area API (requires NASA_FIRMS_MAP_KEY). Always HISTORICAL; never alerts."""
    today = datetime.now(timezone.utc).date()
    end = end or today
    lo = today - timedelta(days=HISTORY_LIMIT_DAYS)
    start = max(start, lo)
    end = min(end, today)
    if start > end:
        return {"status": "rejected", "detail": "Requested range is outside the 12-month historical window"}
    if not settings.firms_key:
        return {"status": "not_configured", "detail": "Historical data unavailable — NASA_FIRMS_MAP_KEY is required for the FIRMS archive API"}
    if not _ingest_lock.acquire(blocking=True, timeout=600):
        return {"status": "busy", "detail": "Another ingestion is running"}
    try:
        with SessionLocal() as db:
            feed = AreaApiProvider().fetch_archive(start, end, sources)
            run = ingest_rows(db, feed.rows, mode="archive", source_label="FIRMS_ARCHIVE", feed_status=feed.status, force_status="HISTORICAL")
            new_ids = getattr(run, "_new_detection_ids", [])
            new_events, touched_existing = form_events(db, list(new_ids))
            touched = touched_existing | {e.id for e in new_events}
            run.events_formed = len(new_events)
            run.events_touched = len(touched)
            db.commit()
            n, m = _analyse_touched(db, touched, f"backfill {start}..{end}")
            freshness.record(db, "firms_archive", "NASA FIRMS area API (archive)", "ok" if feed.rows else "failed", f"{start}..{end}: {run.message}", source_timestamp=run.latest_observation)
            db.commit()
            return {"status": "ok", "range": [start.isoformat(), end.isoformat()], "run": run.message, "events_formed": len(new_events), "events_analysed": n, "events_enriched": m, "feed_status": feed.status}
    finally:
        _ingest_lock.release()


def maintenance(reason: str = "scheduled") -> dict:
    """Age LIVE data into HISTORICAL, enforce the 12-month limit, refresh live-event risk (momentum)."""
    with SessionLocal() as db:
        aged_d = age_live_detections(db)
        purged = purge_expired(db)
        archived = archive_expired_events(db)
        aged_e = age_events(db)
        db.commit()
        refreshed = 0
        if reason != "startup":
            for ev in db.execute(select(ThermalEvent).where(ThermalEvent.data_status == "LIVE").order_by(ThermalEvent.priority_score.desc()).limit(settings.live_enrich_max)).scalars().all():
                try:
                    update_event_aggregates(db, ev)
                    analyse_event(db, ev, live=True)
                    refreshed += 1
                    db.commit()
                except Exception:
                    log.exception("Risk refresh failed for %s", ev.incident_id)
                    db.rollback()
            rerank_all(db)
            db.commit()
        info = {"detections_aged": aged_d, "detections_purged": purged, "events_archived": archived, "events_aged": aged_e, "live_events_refreshed": refreshed}
        log.info("Maintenance (%s): %s", reason, info)
        return info


def background_visuals(limit: int | None = None) -> int:
    from .image_service import generate_event_images
    from .pdf_service import build_pdf
    from ..models import EventReport

    n = 0
    with SessionLocal() as db:
        events = db.execute(select(ThermalEvent).order_by(ThermalEvent.data_status.desc(), ThermalEvent.priority_score.desc()).limit(limit or settings.background_visuals_max)).scalars().all()
        for ev in events:
            try:
                if not ev.images:
                    generate_event_images(db, ev)
                has_pdf = db.execute(select(EventReport.id).where(EventReport.event_id == ev.id, EventReport.status == "generated")).first()
                if settings.auto_generate_pdf and not has_pdf:
                    build_pdf(db, ev, generated_by="auto")
                db.commit()
                n += 1
            except Exception:
                log.exception("Background visual generation failed for %s", ev.incident_id)
                db.rollback()
    log.info("Background image/PDF generation finished (%d events)", n)
    return n
