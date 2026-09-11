"""In-app notifications, alert logs and ADMIN alert settings."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.security import get_current_user, require_admin
from ..database import get_db
from ..models import AlertLog, Notification, User
from ..schemas import AlertSettingsUpdate, TestAlertRequest
from ..services import email_service
from ..services.alert_service import LIVE_NOTICE, get_alert_settings, send_test_alert
from ..services.audit import log_action
from ..services.serializers import alert_out, notification_out
from ..utils.timeutil import iso

router = APIRouter(prefix="/api", tags=["alerts"])


@router.get("/notifications", dependencies=[Depends(get_current_user)])
def list_notifications(db: Session = Depends(get_db), unacknowledged: bool = False, limit: int = Query(default=50, ge=1, le=500)):
    q = select(Notification).order_by(Notification.created_at.desc())
    if unacknowledged:
        q = q.where(Notification.acknowledged == 0)
    return {"items": [notification_out(n) for n in db.execute(q.limit(limit)).scalars().all()], "live_notice": LIVE_NOTICE, "email": email_service.email_status(),
            "note": "Live HIGH/CRITICAL e-mail alerts are generated only from newly ingested LIVE data; nothing is sent to emergency services automatically."}


@router.post("/notifications/{notification_id}/ack")
def acknowledge(notification_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    n = db.get(Notification, notification_id)
    if n is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    n.acknowledged = 1
    db.commit()
    return notification_out(n)


@router.get("/alerts/logs", dependencies=[Depends(get_current_user)])
def alert_logs(db: Session = Depends(get_db), limit: int = Query(default=100, ge=1, le=1000), status_: str | None = Query(default=None, alias="status")):
    q = select(AlertLog).order_by(AlertLog.created_at.desc())
    if status_:
        q = q.where(AlertLog.status == status_)
    return {"items": [alert_out(a) for a in db.execute(q.limit(limit)).scalars().all()]}


def _settings_out(s) -> dict:
    return {"live_alerts_enabled": bool(s.live_alerts_enabled), "high_enabled": bool(s.high_enabled), "critical_enabled": bool(s.critical_enabled), "recipients": s.recipients,
            "cooldown_hours": s.cooldown_hours, "min_confidence": s.min_confidence, "updated_by": s.updated_by, "updated_at": iso(s.updated_at), "email": email_service.email_status(),
            "effective": "active" if (s.live_alerts_enabled and email_service.email_status()["configured"] and s.recipients) else "inactive — " + ("SMTP not configured" if not email_service.email_status()["configured"] else "no recipients" if not s.recipients else "disabled")}


@router.get("/alerts/settings", dependencies=[Depends(get_current_user)])
def get_settings_(db: Session = Depends(get_db)):
    s = get_alert_settings(db)
    db.commit()
    return _settings_out(s)


@router.put("/alerts/settings")
def update_settings(body: AlertSettingsUpdate, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    s = get_alert_settings(db)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(s, k, int(v) if isinstance(v, bool) else v)
    s.updated_by = user.email
    log_action(db, user.email, "update_alert_settings", "alert_settings", s.id, body.model_dump(exclude_none=True))
    db.commit()
    return _settings_out(s)


@router.post("/alerts/test")
def test_alert(body: TestAlertRequest, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    r = send_test_alert(db, body.recipient, user.email)
    log_action(db, user.email, "test_alert", "alert", "", r)
    db.commit()
    return r
