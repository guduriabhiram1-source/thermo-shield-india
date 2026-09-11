"""Live incident e-mail alert pipeline.

FIRMS LIVE INGESTION → new observation? → form / update event → risk →
HIGH / CRITICAL? → data_status == LIVE? → deduplication (alert_logs, cooldown)
→ send e-mail → store alert log.

Historical ingestion NEVER enters this pipeline: `evaluate_live_alerts` is
only called with events touched by *newly ingested LIVE* detections, and every
guard is re-checked here."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..ml.features import CLASS_LABELS
from ..models import AlertLog, AlertSettings, Notification, ThermalDetection, ThermalEvent
from ..utils.timeutil import ensure_utc, fmt_ist, fmt_utc
from . import email_service

log = logging.getLogger("thermoshield.alerts")

LIVE_NOTICE = ("LIVE ALERT: This notification is generated from newly ingested live data and is intended for decision support. It is not confirmation of an emergency. "
               "Verify with authorized emergency personnel and authoritative local sources before taking emergency action.")


def get_alert_settings(db: Session) -> AlertSettings:
    row = db.execute(select(AlertSettings).order_by(AlertSettings.id)).scalars().first()
    if row is None:
        row = AlertSettings(live_alerts_enabled=1 if settings.alerts_enabled else 0, high_enabled=1, critical_enabled=1, recipients=settings.alert_recipients,
                            cooldown_hours=settings.alert_cooldown_hours, min_confidence=settings.alert_min_confidence, updated_by="environment defaults")
        db.add(row)
        db.flush()
    return row


def recipients_of(cfg: AlertSettings) -> list[str]:
    return [e.strip() for e in (cfg.recipients or "").split(",") if e.strip()]


def _log(db: Session, ev: ThermalEvent, status: str, reason: str, recipient: str = "", subject: str = "", payload: dict | None = None) -> AlertLog:
    a = AlertLog(event_id=ev.id, incident_id=ev.incident_id, alert_type="LIVE_EMAIL", risk_level=ev.risk_level, risk_score=ev.risk_score, data_status=ev.data_status,
                 data_timestamp=ensure_utc(ev.last_detected_at), recipient=recipient, status=status, reason=reason[:256], subject=subject[:256], payload=payload,
                 sent_at=datetime.now(timezone.utc) if status == "sent" else None)
    db.add(a)
    db.flush()
    return a


def has_new_live_observation(db: Session, ev: ThermalEvent, new_detection_ids: set[int]) -> bool:
    if not new_detection_ids:
        return False
    rows = db.execute(select(ThermalDetection.id).where(ThermalDetection.event_id == ev.id, ThermalDetection.data_status == "LIVE", ThermalDetection.id.in_(list(new_detection_ids)))).all()
    return len(rows) > 0


def duplicate_within_cooldown(db: Session, ev: ThermalEvent, cooldown_hours: int) -> AlertLog | None:
    since = datetime.now(timezone.utc) - timedelta(hours=cooldown_hours)
    q = select(AlertLog).where(AlertLog.event_id == ev.id, AlertLog.status == "sent", AlertLog.risk_level == ev.risk_level).order_by(AlertLog.created_at.desc())
    last = db.execute(q).scalars().first()
    if last is None:
        return None
    created = ensure_utc(last.created_at)
    if created >= since:
        return last
    # same observation timestamp already alerted → duplicate regardless of cooldown
    if last.data_timestamp and ensure_utc(last.data_timestamp) == ensure_utc(ev.last_detected_at):
        return last
    return None


def evaluate_live_alerts(db: Session, event_ids: set[int], new_detection_ids: set[int], run=None) -> dict:
    """Evaluate alert conditions for events touched by a live ingestion run. Returns counters."""
    counters = {"evaluated": 0, "sent": 0, "suppressed": 0, "failed": 0, "not_configured": 0, "skipped_not_live": 0, "skipped_level": 0}
    if not event_ids:
        return counters
    cfg = get_alert_settings(db)
    for eid in sorted(event_ids):
        ev = db.get(ThermalEvent, eid)
        if ev is None:
            continue
        counters["evaluated"] += 1
        if ev.risk_level not in ("HIGH", "CRITICAL"):
            counters["skipped_level"] += 1
            continue
        # --- hard guards: LIVE data only, and only when this run brought a NEW live observation for the event
        if ev.data_status != "LIVE":
            _log(db, ev, "suppressed", "event data_status is HISTORICAL - live alerts are never generated from historical data")
            counters["skipped_not_live"] += 1
            continue
        if not has_new_live_observation(db, ev, new_detection_ids):
            _log(db, ev, "suppressed", "no newly ingested LIVE observation for this event in this run")
            counters["suppressed"] += 1
            continue
        if not cfg.live_alerts_enabled:
            _log(db, ev, "suppressed", "live alerts disabled in alert settings")
            counters["suppressed"] += 1
            continue
        if (ev.risk_level == "HIGH" and not cfg.high_enabled) or (ev.risk_level == "CRITICAL" and not cfg.critical_enabled):
            _log(db, ev, "suppressed", f"{ev.risk_level} alerts disabled in alert settings")
            counters["suppressed"] += 1
            continue
        if ev.classification_confidence < (cfg.min_confidence or 0.0):
            _log(db, ev, "suppressed", f"confidence {ev.classification_confidence:.2f} below minimum {cfg.min_confidence:.2f}")
            counters["suppressed"] += 1
            continue
        dup = duplicate_within_cooldown(db, ev, cfg.cooldown_hours)
        if dup is not None:
            _log(db, ev, "suppressed", f"duplicate: {ev.risk_level} alert already sent at {fmt_utc(dup.created_at)} (cooldown {cfg.cooldown_hours} h)")
            counters["suppressed"] += 1
            continue
        _web_notification(db, ev)
        rcpts = recipients_of(cfg)
        if not rcpts:
            _log(db, ev, "not_configured", "no alert recipients configured")
            counters["not_configured"] += 1
            continue
        status = email_service.email_status()
        if not status["configured"] and status["provider"] != "log-only":
            _log(db, ev, "not_configured", "SMTP not configured - alert not sent")
            counters["not_configured"] += 1
            continue
        subject, text, html_body = build_alert_email(ev)
        result = email_service.send_email(rcpts, subject, text, html_body)
        if result.status in ("sent", "logged"):
            _log(db, ev, "sent", f"{result.provider}: {result.detail}", recipient=", ".join(rcpts), subject=subject, payload={"risk": ev.risk_score, "classification": ev.classification})
            counters["sent"] += 1
            log.info("Live %s alert sent for %s to %s", ev.risk_level, ev.incident_id, rcpts)
        else:
            _log(db, ev, "failed", result.detail, recipient=", ".join(rcpts), subject=subject)
            counters["failed"] += 1
    if run is not None:
        run.alerts_sent = counters["sent"]
    db.flush()
    return counters


def _web_notification(db: Session, ev: ThermalEvent) -> Notification:
    exposure = ev.exposure or {}
    wind = exposure.get("wind", {})
    pop = exposure.get("population", {}).get("exposed_estimate")
    title = f"🚨 LIVE {ev.risk_level}-RISK THERMAL EVENT — {ev.incident_id}"
    message = (f"{CLASS_LABELS.get(ev.classification, ev.classification)} near {ev.locality or 'locality unavailable'}, {ev.district or 'district unavailable'}, {ev.state}. "
               f"Risk {ev.risk_score:.0f}/100 ({ev.risk_level}), confidence {ev.classification_confidence * 100:.0f}%, "
               f"potentially exposed population {('≈ ' + format(pop, ',') + ' (estimate)') if pop is not None else 'unavailable'}, "
               f"wind {('from ' + str(wind.get('direction_from')) + ' ' + str(wind.get('speed_kmh')) + ' km/h → downwind ' + str(wind.get('downwind'))) if wind.get('available') else 'unavailable'}.")
    n = Notification(event_id=ev.id, incident_id=ev.incident_id, severity=ev.risk_level, data_status=ev.data_status, title=title, message=message,
                     payload={"latitude": ev.latitude, "longitude": ev.longitude, "state": ev.state, "district": ev.district, "locality": ev.locality, "classification": ev.classification,
                              "risk": ev.risk_score, "risk_level": ev.risk_level, "confidence": ev.classification_confidence, "population_exposure": pop,
                              "wind": wind if wind.get("available") else None, "notice": LIVE_NOTICE})
    db.add(n)
    db.flush()
    return n


def build_alert_email(ev: ThermalEvent) -> tuple[str, str, str]:
    exposure = ev.exposure or {}
    wind = exposure.get("wind", {})
    pop = exposure.get("population", {}).get("exposed_estimate")
    areas = [a for a in exposure.get("affected_areas", []) if a["exposure_level"] in ("HIGH", "CRITICAL", "MODERATE")][:8]
    prec = (ev.precautions or {}).get("general", [])[:6]
    label = CLASS_LABELS.get(ev.classification, ev.classification)
    subject = f"[THERMO-SHIELD INDIA] LIVE {'CRITICAL' if ev.risk_level == 'CRITICAL' else 'HIGH-RISK'} THERMAL INCIDENT — {ev.state or 'STATE UNAVAILABLE'}"
    link = f"{settings.frontend_url.rstrip('/')}/incidents/{ev.incident_id}"
    wind_line = f"{wind.get('direction_from')} ({wind.get('direction_from_deg')}°), {wind.get('speed_kmh')} km/h → potential downwind direction {wind.get('downwind')} [{wind.get('weather_source')}]" if wind.get("available") else "Unavailable"
    areas_txt = "\n".join(f"  - {a['name']} ({a['area_type']}): {a['distance_km']} km {a['direction']}, exposure {a['exposure_level']}" for a in areas) or "  - No potentially exposed area identified in the available datasets"
    text = f"""THERMO-SHIELD INDIA
LIVE THERMAL RISK ALERT

Incident ID: {ev.incident_id}
Status: LIVE DATA
Classification: {label} [MODEL INFERENCE — {ev.classification_method}]
Risk: {ev.risk_score:.0f}/100 — {ev.risk_level}
Confidence: {ev.classification_confidence * 100:.0f}%

Location: {ev.locality or 'Locality unavailable'}
District: {ev.district or 'Unavailable'}
State: {ev.state or 'Unavailable'}
Coordinates: Latitude {ev.latitude:.5f}, Longitude {ev.longitude:.5f}

First observed thermal activity: {fmt_ist(ev.first_detected_at)} ({fmt_utc(ev.first_detected_at)})
Latest observation: {fmt_ist(ev.last_detected_at)} ({fmt_utc(ev.last_detected_at)})
Peak FRP: {ev.max_frp:.1f} MW [OBSERVED — NASA FIRMS] · Detections: {ev.detection_count} · Persistence: {ev.persistence_class} ({ev.persistence_score:.0f}/100)

Wind: {wind_line}

Potentially exposed areas [ESTIMATE]:
{areas_txt}

Estimated potentially exposed population: {(format(pop, ',') + ' (estimate)') if pop is not None else 'Unavailable'}

Safety precautions:
- Follow official emergency instructions
- Avoid entering affected/smoke-affected areas
- Monitor wind direction
- Keep emergency access routes clear
- Contact appropriate emergency authorities where necessary
{chr(10).join('- ' + p for p in prec)}

Data sources: NASA FIRMS (VIIRS/MODIS); weather: {wind.get('weather_source') or 'unavailable'}; GIS: OpenStreetMap + reference gazetteer; population: Census 2011 reference / OSM tags.
Verification status: AI predicted {label}; human status {ev.human_status}.
Dashboard: {link}

IMPORTANT:
This is an automated decision-support alert based on live data.
It is not a confirmation of an actual fire cause.
Verify with authorized emergency/field personnel.

{LIVE_NOTICE}
"""
    html_body = "<pre style='font-family:Segoe UI,Arial,sans-serif;font-size:14px;white-space:pre-wrap'>" + text.replace("&", "&amp;").replace("<", "&lt;") + f"</pre><p><a href='{link}'>Open incident in Thermo-Shield India</a></p>"
    return subject, text, html_body


def send_test_alert(db: Session, recipient: str, actor: str) -> dict:
    ev = db.execute(select(ThermalEvent).order_by(ThermalEvent.risk_score.desc())).scalars().first()
    if ev is None:
        return {"status": "failed", "detail": "No incident exists yet to build a sample alert from (no fabricated content is sent)."}
    subject, text, html_body = build_alert_email(ev)
    subject = "[TEST] " + subject
    text = f"TEST MESSAGE requested by {actor} — content built from a real incident record; not a live alert.\n\n" + text
    r = email_service.send_email([recipient], subject, text, html_body)
    return {"status": r.status, "detail": r.detail, "provider": r.provider, "incident_id": ev.incident_id}
