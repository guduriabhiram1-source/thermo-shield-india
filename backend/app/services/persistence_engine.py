"""Persistence engine: ISOLATED / TEMPORARY / RECURRING / PERSISTENT.

Score 0-100 from active days, span, detection count, day-coverage ratio,
spatial consistency, night-time occurrence and FRP stability - all computed
from the event's real daily observations."""
from __future__ import annotations

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import EventObservation, ThermalEvent
from ..utils.timeutil import ensure_utc


def compute_persistence(db: Session, ev: ThermalEvent) -> dict:
    obs = list(db.execute(select(EventObservation).where(EventObservation.event_id == ev.id).order_by(EventObservation.day)).scalars().all())
    active_days = max(ev.active_days, 1)
    span_days = max(1, (ensure_utc(ev.last_detected_at).date() - ensure_utc(ev.first_detected_at).date()).days + 1)
    coverage = active_days / span_days
    frps = [o.max_frp for o in obs] or [ev.max_frp]
    frp_cv = float(np.std(frps) / max(np.mean(frps), 1e-6)) if len(frps) > 1 else 1.0
    s_days = min(active_days / 20.0, 1.0)
    s_span = min(span_days / 30.0, 1.0)
    s_count = min(ev.detection_count / 40.0, 1.0)
    s_cov = coverage
    s_spatial = 1.0 - min(ev.spatial_spread_km / 6.0, 1.0)
    s_night = ev.night_ratio
    s_stable = 1.0 - min(frp_cv, 1.0)
    score = 100 * (0.28 * s_days + 0.12 * s_span + 0.12 * s_count + 0.15 * s_cov + 0.12 * s_spatial + 0.11 * s_night + 0.10 * s_stable)
    score = round(float(max(0, min(100, score))), 1)
    if active_days >= 10 and coverage >= 0.5:
        cls = "PERSISTENT"
    elif active_days >= 4:
        cls = "RECURRING"
    elif active_days >= 2 or ev.detection_count >= 3:
        cls = "TEMPORARY"
    else:
        cls = "ISOLATED"
    gaps = [(ensure_utc(b.observed_at).date() - ensure_utc(a.observed_at).date()).days for a, b in zip(obs[:-1], obs[1:])]
    frp_pattern = "stable" if frp_cv < 0.35 else "variable" if frp_cv < 0.8 else "highly variable"
    details = {
        "score": score, "class": cls, "active_days": active_days, "span_days": span_days, "coverage_ratio": round(coverage, 3), "detections": ev.detection_count,
        "detections_per_active_day": round(ev.detection_count / active_days, 2), "spatial_spread_km": ev.spatial_spread_km, "night_day_ratio": ev.night_ratio,
        "frp_cv": round(frp_cv, 3), "frp_pattern": frp_pattern, "max_gap_days": max(gaps) if gaps else 0,
        "recurrence_frequency_per_week": round(active_days / max(span_days / 7.0, 1.0), 2),
        "components": {"active_days": round(s_days, 3), "span": round(s_span, 3), "detection_count": round(s_count, 3), "coverage": round(s_cov, 3),
                       "spatial_consistency": round(s_spatial, 3), "night_occurrence": round(s_night, 3), "frp_stability": round(s_stable, 3)},
        "summary": _summary(cls, active_days, span_days, ev.detection_count, ev.night_ratio), "provenance": "CALCULATED from observed detections",
    }
    ev.persistence_score = score
    ev.persistence_class = cls
    ev.persistence_details = details
    return details


def _summary(cls: str, active_days: int, span_days: int, count: int, night_ratio: float) -> str:
    night = "mostly at night" if night_ratio >= 0.6 else ("day and night" if night_ratio >= 0.25 else "mostly in daytime")
    if cls == "PERSISTENT":
        return f"Detected on {active_days} of {span_days} days ({count} detections, {night}) at approximately the same location → persistent thermal source."
    if cls == "RECURRING":
        return f"Detected repeatedly on {active_days} days over a {span_days}-day span ({count} detections, {night}) → recurring activity."
    if cls == "TEMPORARY":
        return f"Short-lived activity: {count} detections over {active_days} day(s) ({night}) → temporary event."
    return "Single-pass detection with no recurrence yet → isolated hotspot; persistence cannot be assessed."
