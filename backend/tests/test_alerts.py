"""CRITICAL TEST: historical events must NEVER trigger a live e-mail alert; newly ingested live events must."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import AlertLog, ThermalDetection, ThermalEvent
from app.services.alert_service import evaluate_live_alerts, get_alert_settings

from .conftest import EMAIL, auth


def _force_critical(db, ev: ThermalEvent):
    ev.risk_score, ev.risk_level, ev.classification_confidence = 85.0, "CRITICAL", 0.8
    db.flush()


def test_historical_critical_event_sends_no_email(db, seeded):
    ev = db.execute(select(ThermalEvent).where(ThermalEvent.data_status == "HISTORICAL")).scalars().first()
    assert ev is not None
    _force_critical(db, ev)
    det_ids = {d.id for d in db.execute(select(ThermalDetection).where(ThermalDetection.event_id == ev.id)).scalars().all()}
    before = len(EMAIL.sent)
    counters = evaluate_live_alerts(db, {ev.id}, det_ids)
    db.commit()
    assert len(EMAIL.sent) == before, "historical data must never send a live alert"
    assert counters["sent"] == 0 and counters["skipped_not_live"] == 1
    log = db.execute(select(AlertLog).where(AlertLog.event_id == ev.id).order_by(AlertLog.created_at.desc())).scalars().first()
    assert log.status == "suppressed" and "HISTORICAL" in log.reason


def test_live_critical_event_sends_email_once_then_dedups(db, seeded):
    ev = db.execute(select(ThermalEvent).where(ThermalEvent.data_status == "LIVE").order_by(ThermalEvent.detection_count.desc())).scalars().first()
    assert ev is not None
    _force_critical(db, ev)
    det_ids = {d.id for d in db.execute(select(ThermalDetection).where(ThermalDetection.event_id == ev.id, ThermalDetection.data_status == "LIVE")).scalars().all()}
    assert det_ids
    before = len(EMAIL.sent)
    counters = evaluate_live_alerts(db, {ev.id}, det_ids)
    db.commit()
    assert counters["sent"] == 1 and len(EMAIL.sent) == before + 1
    msg = EMAIL.sent[-1]
    assert msg.subject.startswith("[THERMO-SHIELD INDIA] LIVE CRITICAL THERMAL INCIDENT — ") and ev.state in msg.subject
    for needle in ("Incident ID: " + ev.incident_id, "Status: LIVE DATA", "Risk: 85/100 — CRITICAL", "Coordinates: Latitude", "First observed thermal activity", "Safety precautions", "Data sources: NASA FIRMS",
                   "not a confirmation of an actual fire cause", "LIVE ALERT:", f"State: {ev.state}"):
        assert needle in msg.text, needle
    assert "duty-officer@example.org" in msg.to
    log = db.execute(select(AlertLog).where(AlertLog.event_id == ev.id, AlertLog.status == "sent")).scalars().first()
    assert log and log.data_status == "LIVE" and log.recipient == "duty-officer@example.org" and log.data_timestamp is not None
    # same event, same observation again → deduplicated within cooldown
    counters2 = evaluate_live_alerts(db, {ev.id}, det_ids)
    db.commit()
    assert counters2["sent"] == 0 and counters2["suppressed"] == 1 and len(EMAIL.sent) == before + 1
    # no NEW live detection for the event → suppressed even outside cooldown
    counters3 = evaluate_live_alerts(db, {ev.id}, set())
    db.commit()
    assert counters3["sent"] == 0 and counters3["suppressed"] == 1
    # web notification centre entry created for the sent alert
    assert db.execute(select(ThermalEvent).where(ThermalEvent.id == ev.id)).scalar_one().alert_logs


def test_live_alert_respects_settings_and_thresholds(db, client, admin, seeded):
    cfg = get_alert_settings(db)
    cfg.high_enabled = 0
    db.commit()
    ev = db.execute(select(ThermalEvent).where(ThermalEvent.data_status == "LIVE").order_by(ThermalEvent.detection_count.desc()).offset(1)).scalars().first()
    ev.risk_score, ev.risk_level = 70.0, "HIGH"
    db.flush()
    det_ids = {d.id for d in db.execute(select(ThermalDetection).where(ThermalDetection.event_id == ev.id, ThermalDetection.data_status == "LIVE")).scalars().all()}
    before = len(EMAIL.sent)
    c = evaluate_live_alerts(db, {ev.id}, det_ids)
    db.commit()
    assert c["sent"] == 0 and len(EMAIL.sent) == before
    r = client.put("/api/alerts/settings", json={"high_enabled": True, "cooldown_hours": 6}, headers=auth(admin))
    assert r.status_code == 200 and r.json()["high_enabled"] is True and r.json()["cooldown_hours"] == 6
    logs = client.get("/api/alerts/logs", headers=auth(admin)).json()["items"]
    assert any(l["status"] == "sent" for l in logs) and any(l["status"] == "suppressed" for l in logs)
    n = client.get("/api/notifications", headers=auth(admin)).json()
    assert n["items"] and n["items"][0]["data_status"] == "LIVE" and "LIVE ALERT" in n["live_notice"]
    assert client.post(f"/api/notifications/{n['items'][0]['id']}/ack", headers=auth(admin)).json()["acknowledged"] is True


def test_event_aging_demotes_live_to_historical(db, seeded):
    from app.services.thermal_event_service import age_events

    ev = db.execute(select(ThermalEvent).where(ThermalEvent.data_status == "LIVE")).scalars().first()
    ev.last_detected_at = datetime.now(timezone.utc) - timedelta(hours=100)
    db.flush()
    assert age_events(db) >= 1
    db.refresh(ev)
    assert ev.data_status == "HISTORICAL"
    db.rollback()
