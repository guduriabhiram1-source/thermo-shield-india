"""Event evolution (FRP / brightness / spread / detections over time) and the incident timeline (dates from real observations)."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AlertLog, EventObservation, HumanVerification, RiskScore, ThermalEvent
from ..utils.timeutil import ensure_utc, iso


def compute_evolution(db: Session, ev: ThermalEvent) -> dict:
    obs = list(db.execute(select(EventObservation).where(EventObservation.event_id == ev.id).order_by(EventObservation.day)).scalars().all())
    series = [{"day": o.day, "detections": o.detections, "max_frp": o.max_frp, "sum_frp": o.sum_frp, "max_brightness": o.max_brightness, "spread_km": o.spread_km,
               "night_detections": o.night_detections, "live_detections": o.live_detections, "risk_score": o.risk_score} for o in obs]
    frps = [o.max_frp for o in obs]
    spreads = [o.spread_km for o in obs]
    n = len(frps)
    if n >= 2:
        slope = float(np.polyfit(np.arange(n), frps, 1)[0])
        recent = frps[-1] / max(frps[-2], 1e-3)
        growth = frps[-1] / max(frps[0], 1e-3)
        spread_growth = (spreads[-1] + 0.1) / (spreads[0] + 0.1)
    else:
        slope, recent, growth, spread_growth = 0.0, 1.0, 1.0, 1.0
    if n >= 3 and growth >= 2.0 and slope > 0:
        statement, trend = "Thermal intensity is increasing rapidly.", "RAPID_INCREASE"
    elif slope > 2 and growth > 1.2:
        statement, trend = "Thermal intensity is increasing.", "INCREASING"
    elif slope < -2 and growth < 0.8:
        statement, trend = "Thermal intensity is decreasing.", "DECREASING"
    elif n == 1:
        statement, trend = "Only one observation day: no trend can be established yet.", "INSUFFICIENT"
    else:
        statement, trend = "Thermal intensity is broadly stable.", "STABLE"
    if spread_growth >= 1.8 and n >= 2:
        statement += f" Spatial extent has expanded ×{spread_growth:.1f}."
    evo = {"series": series, "days": n, "frp_slope_per_day": round(slope, 2), "frp_growth_rate": round(growth, 3), "recent_change_ratio": round(recent, 3),
           "spread_growth_rate": round(spread_growth, 3), "trend": trend, "statement": statement, "peak_day": series[int(np.argmax(frps))]["day"] if frps else None,
           "peak_frp": max(frps) if frps else 0, "frequency_per_day": round(sum(o.detections for o in obs) / max(n, 1), 2), "provenance": "CALCULATED from observed detections"}
    ev.evolution = evo
    return evo


ICONS = {"detection": "🔥", "frp_up": "📈", "frp_down": "📉", "risk_up": "⚠️", "risk_high": "🔴", "risk_critical": "🚨", "verify_pending": "👤", "verified": "✅", "spread": "↔️", "alert": "📧"}


def build_timeline(db: Session, ev: ThermalEvent) -> list[dict]:
    items: list[dict] = []
    obs = list(db.execute(select(EventObservation).where(EventObservation.event_id == ev.id).order_by(EventObservation.day)).scalars().all())
    prev = None
    for i, o in enumerate(obs):
        label = "First observed thermal detection" if i == 0 else "Thermal detection"
        items.append({"time": iso(o.observed_at), "day": o.day, "type": "detection", "icon": ICONS["detection"], "title": label,
                      "detail": f"{o.detections} detection(s), peak FRP {o.max_frp:.0f} MW" + (" · LIVE" if o.live_detections else ""), "provenance": "OBSERVED"})
        if prev is not None:
            if o.max_frp >= prev.max_frp * 1.4 and o.max_frp - prev.max_frp >= 10:
                items.append({"time": iso(o.observed_at), "day": o.day, "type": "frp_up", "icon": ICONS["frp_up"], "title": "FRP increased",
                              "detail": f"{prev.max_frp:.0f} → {o.max_frp:.0f} MW (+{(o.max_frp / max(prev.max_frp, 1e-3) - 1) * 100:.0f}%)", "provenance": "OBSERVED"})
            elif o.max_frp <= prev.max_frp * 0.6 and prev.max_frp - o.max_frp >= 10:
                items.append({"time": iso(o.observed_at), "day": o.day, "type": "frp_down", "icon": ICONS["frp_down"], "title": "FRP decreased", "detail": f"{prev.max_frp:.0f} → {o.max_frp:.0f} MW", "provenance": "OBSERVED"})
            if o.spread_km >= prev.spread_km * 1.5 and o.spread_km - prev.spread_km >= 0.5:
                items.append({"time": iso(o.observed_at), "day": o.day, "type": "spread", "icon": ICONS["spread"], "title": "Spatial expansion", "detail": f"Spread {prev.spread_km:.1f} → {o.spread_km:.1f} km", "provenance": "OBSERVED"})
        prev = o
    for r in db.execute(select(RiskScore).where(RiskScore.event_id == ev.id).order_by(RiskScore.computed_at)).scalars().all():
        day = ensure_utc(r.computed_at).date().isoformat()
        if r.previous_score is not None and r.momentum >= 8:
            items.append({"time": iso(r.computed_at), "day": day, "type": "risk_up", "icon": ICONS["risk_up"], "title": "Risk increased", "detail": f"{r.previous_score:.0f} → {r.score:.0f} ({r.level})", "provenance": "CALCULATED"})
        if r.level == "CRITICAL":
            items.append({"time": iso(r.computed_at), "day": day, "type": "risk_critical", "icon": ICONS["risk_critical"], "title": "Critical risk", "detail": f"Risk score {r.score:.0f}/100", "provenance": "CALCULATED"})
        elif r.level == "HIGH":
            items.append({"time": iso(r.computed_at), "day": day, "type": "risk_high", "icon": ICONS["risk_high"], "title": "High risk", "detail": f"Risk score {r.score:.0f}/100", "provenance": "CALCULATED"})
    for a in db.execute(select(AlertLog).where(AlertLog.event_id == ev.id, AlertLog.status == "sent").order_by(AlertLog.created_at)).scalars().all():
        items.append({"time": iso(a.sent_at or a.created_at), "day": ensure_utc(a.sent_at or a.created_at).date().isoformat(), "type": "alert", "icon": ICONS["alert"], "title": f"Live {a.risk_level} alert e-mailed", "detail": a.recipient, "provenance": "SYSTEM"})
    vers = list(db.execute(select(HumanVerification).where(HumanVerification.event_id == ev.id).order_by(HumanVerification.created_at)).scalars().all())
    if not vers:
        t = ev.analysed_at or ev.updated_at or datetime.now(timezone.utc)
        items.append({"time": iso(t), "day": ensure_utc(t).date().isoformat(), "type": "verify_pending", "icon": ICONS["verify_pending"], "title": "Human verification pending", "detail": "Awaiting analyst review", "provenance": "SYSTEM"})
    for v in vers:
        title = {"CONFIRM": "Analyst confirmed classification", "CORRECT": "Analyst corrected classification", "UNCERTAIN": "Analyst marked uncertain"}.get(v.action, "Analyst review")
        items.append({"time": iso(v.created_at), "day": ensure_utc(v.created_at).date().isoformat(), "type": "verified", "icon": ICONS["verified"], "title": title,
                      "detail": f"{v.analyst}: {v.verified_classification or v.original_prediction}" + (f" — {v.notes}" if v.notes else ""), "provenance": "HUMAN VERIFIED"})
    items.sort(key=lambda i: (i["time"] or "", 0))
    ev.timeline = items
    return items
