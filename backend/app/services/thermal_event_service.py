"""Thermal event formation: spatio-temporal DBSCAN over FIRMS detections.

Detections are first attached to existing open events when they fall inside
the event's spatial radius AND temporal window (persistent sources keep one
incident ID). Remaining detections are clustered with DBSCAN over
(x_km, y_km, scaled_time). Event data_status is derived from its detections."""
from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import numpy as np
from sklearn.cluster import DBSCAN
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import EventObservation, ThermalDetection, ThermalEvent
from ..utils.geo import haversine_km, spread_km
from ..utils.ids import next_incident_id
from ..utils.timeutil import ensure_utc

log = logging.getLogger("thermoshield.events")


def _xy_km(lat: float, lon: float, lat0: float, lon0: float) -> tuple[float, float]:
    return (lon - lon0) * 111.32 * math.cos(math.radians(lat0)), (lat - lat0) * 111.32


def attach_to_existing_events(db: Session, detections: list[ThermalDetection]) -> tuple[list[ThermalDetection], set[int]]:
    events = db.execute(select(ThermalEvent).where(ThermalEvent.status != "CLOSED")).scalars().all()
    if not events:
        return detections, set()
    remaining = []
    eps = settings.cluster_eps_km
    window = timedelta(hours=settings.cluster_time_hours)
    touched: set[int] = set()
    # coarse spatial index by 0.1 degree cell
    grid: dict[tuple[int, int], list[ThermalEvent]] = defaultdict(list)
    for e in events:
        grid[(int(e.latitude * 10), int(e.longitude * 10))].append(e)
    for d in detections:
        best, best_d = None, eps
        ci, cj = int(d.latitude * 10), int(d.longitude * 10)
        cands = [e for i in (ci - 1, ci, ci + 1) for j in (cj - 1, cj, cj + 1) for e in grid.get((i, j), [])]
        for e in cands:
            dist = haversine_km(d.latitude, d.longitude, e.latitude, e.longitude)
            if dist <= max(eps, e.spatial_spread_km / 2 + eps / 2):
                last, first = ensure_utc(e.last_detected_at), ensure_utc(e.first_detected_at)
                if first - window <= ensure_utc(d.acq_datetime) <= last + window and dist < best_d + e.spatial_spread_km / 2:
                    best, best_d = e, dist
        if best is not None:
            d.event_id = best.id
            touched.add(best.id)
        else:
            remaining.append(d)
    db.flush()
    for eid in touched:
        update_event_aggregates(db, db.get(ThermalEvent, eid))
    return remaining, touched


def cluster_detections(db: Session, detections: list[ThermalDetection]) -> list[ThermalEvent]:
    if not detections:
        return []
    eps = settings.cluster_eps_km
    lat0 = float(np.mean([d.latitude for d in detections]))
    lon0 = float(np.mean([d.longitude for d in detections]))
    t0 = min(ensure_utc(d.acq_datetime) for d in detections)
    time_scale = eps / max(settings.cluster_time_hours, 1e-6)
    X = []
    for d in detections:
        x, y = _xy_km(d.latitude, d.longitude, lat0, lon0)
        t = (ensure_utc(d.acq_datetime) - t0).total_seconds() / 3600.0 * time_scale
        X.append([x, y, t])
    labels = DBSCAN(eps=eps, min_samples=settings.cluster_min_samples).fit_predict(np.asarray(X))
    groups: dict[int, list[ThermalDetection]] = defaultdict(list)
    for d, lab in zip(detections, labels):
        groups[int(lab) if lab >= 0 else -1000 - d.id].append(d)
    created = []
    for _, members in sorted(groups.items(), key=lambda kv: min(ensure_utc(m.acq_datetime) for m in kv[1])):
        first = min(ensure_utc(m.acq_datetime) for m in members)
        ev = ThermalEvent(incident_id=next_incident_id(db, first.year), latitude=float(np.mean([m.latitude for m in members])),
                          longitude=float(np.mean([m.longitude for m in members])), first_detected_at=first,
                          last_detected_at=max(ensure_utc(m.acq_datetime) for m in members), data_source="FIRMS")
        db.add(ev)
        db.flush()
        for m in members:
            m.event_id = ev.id
        db.flush()
        update_event_aggregates(db, ev)
        created.append(ev)
    log.info("Formed %d thermal events from %d detections", len(created), len(detections))
    return created


def form_events(db: Session, detection_ids: list[int] | None = None) -> tuple[list[ThermalEvent], set[int]]:
    """Returns (new_events, touched_existing_event_ids)."""
    q = select(ThermalDetection).where(ThermalDetection.event_id.is_(None))
    if detection_ids is not None:
        if not detection_ids:
            return [], set()
        q = q.where(ThermalDetection.id.in_(detection_ids))
    dets = list(db.execute(q.order_by(ThermalDetection.acq_datetime)).scalars().all())
    remaining, touched = attach_to_existing_events(db, dets)
    new_events = cluster_detections(db, remaining)
    db.flush()
    return new_events, touched


def compute_data_status(dets: list[ThermalDetection], now: datetime | None = None) -> str:
    """LIVE when the latest observation is inside the live window and at least one detection is LIVE."""
    now = now or datetime.now(timezone.utc)
    if not dets:
        return "HISTORICAL"
    latest = max(ensure_utc(d.acq_datetime) for d in dets)
    if now - latest > timedelta(hours=settings.live_window_hours):
        return "HISTORICAL"
    return "LIVE" if any(d.data_status == "LIVE" for d in dets) else "HISTORICAL"


def update_event_aggregates(db: Session, ev: ThermalEvent) -> ThermalEvent:
    dets = list(db.execute(select(ThermalDetection).where(ThermalDetection.event_id == ev.id).order_by(ThermalDetection.acq_datetime)).scalars().all())
    if not dets:
        return ev
    pts = [(d.latitude, d.longitude) for d in dets]
    frps = [d.frp for d in dets]
    ev.latitude = float(np.mean([p[0] for p in pts]))
    ev.longitude = float(np.mean([p[1] for p in pts]))
    ev.bbox = {"min_lat": min(p[0] for p in pts), "min_lon": min(p[1] for p in pts), "max_lat": max(p[0] for p in pts), "max_lon": max(p[1] for p in pts)}
    ev.spatial_spread_km = round(spread_km(pts), 3)
    ev.first_detected_at = ensure_utc(dets[0].acq_datetime)
    ev.last_detected_at = ensure_utc(dets[-1].acq_datetime)
    ev.duration_hours = round((ev.last_detected_at - ev.first_detected_at).total_seconds() / 3600.0, 2)
    ev.detection_count = len(dets)
    ev.live_detection_count = sum(1 for d in dets if d.data_status == "LIVE")
    days = sorted({d.acq_date.isoformat() for d in dets})
    ev.active_days = len(days)
    ev.night_ratio = round(sum(1 for d in dets if d.day_night == "N") / len(dets), 3)
    ev.max_frp = round(max(frps), 2)
    ev.mean_frp = round(float(np.mean(frps)), 2)
    ev.total_frp = round(float(np.sum(frps)), 2)
    ev.max_brightness = round(max(d.brightness for d in dets), 2)
    ev.mean_brightness = round(float(np.mean([d.brightness for d in dets])), 2)
    ev.mean_confidence = round(float(np.mean([d.confidence_score for d in dets])), 3)
    ev.satellites = ",".join(sorted({d.satellite for d in dets if d.satellite}))
    ev.instruments = ",".join(sorted({d.instrument for d in dets if d.instrument}))
    ev.data_status = compute_data_status(dets)
    by_day: dict[str, list[ThermalDetection]] = defaultdict(list)
    for d in dets:
        by_day[d.acq_date.isoformat()].append(d)
    existing = {o.day: o for o in db.execute(select(EventObservation).where(EventObservation.event_id == ev.id)).scalars().all()}
    daily_max = []
    for day in days:
        group = by_day[day]
        mx = max(g.frp for g in group)
        daily_max.append(mx)
        o = existing.pop(day, None) or EventObservation(event_id=ev.id, day=day)
        o.observed_at = ensure_utc(max(g.acq_datetime for g in group))
        o.detections = len(group)
        o.max_frp = round(mx, 2)
        o.sum_frp = round(sum(g.frp for g in group), 2)
        o.max_brightness = round(max(g.brightness for g in group), 2)
        o.spread_km = round(spread_km([(g.latitude, g.longitude) for g in group]), 3)
        o.night_detections = sum(1 for g in group if g.day_night == "N")
        o.live_detections = sum(1 for g in group if g.data_status == "LIVE")
        db.add(o)
    for stale in existing.values():
        db.delete(stale)
    ev.latest_frp = round(daily_max[-1], 2)
    if len(daily_max) >= 2:
        slope = float(np.polyfit(np.arange(len(daily_max)), daily_max, 1)[0])
        ev.frp_trend = round(slope, 3)
        ev.frp_growth_rate = round(daily_max[-1] / max(daily_max[0], 1e-3), 3)
    else:
        ev.frp_trend, ev.frp_growth_rate = 0.0, 1.0
    if datetime.now(timezone.utc) - ev.last_detected_at > timedelta(hours=72):
        ev.status = "INACTIVE" if ev.status != "CLOSED" else ev.status
    else:
        ev.status = "ACTIVE" if ev.status != "CLOSED" else ev.status
    db.flush()
    return ev


def event_detections(db: Session, ev: ThermalEvent) -> list[ThermalDetection]:
    return list(db.execute(select(ThermalDetection).where(ThermalDetection.event_id == ev.id).order_by(ThermalDetection.acq_datetime)).scalars().all())


def age_events(db: Session) -> int:
    """Demote events whose latest observation left the live window (scheduled job)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.live_window_hours)
    rows = db.execute(select(ThermalEvent).where(ThermalEvent.data_status == "LIVE", ThermalEvent.last_detected_at < cutoff)).scalars().all()
    for ev in rows:
        ev.data_status = "HISTORICAL"
        if ev.status == "ACTIVE" and datetime.now(timezone.utc) - ensure_utc(ev.last_detected_at) > timedelta(hours=72):
            ev.status = "INACTIVE"
    db.flush()
    return len(rows)
