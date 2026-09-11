import os

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.security import get_current_user
from ..database import get_db
from ..models import EventReport, ThermalEvent, User
from ..services.audit import log_action
from ..services.pdf_service import build_pdf
from ..services.serializers import report_out

router = APIRouter(prefix="/api/reports", tags=["reports"], dependencies=[Depends(get_current_user)])


def _get(db: Session, report_id: int) -> tuple[EventReport, ThermalEvent]:
    rep = db.get(EventReport, report_id)
    if rep is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")
    return rep, db.get(ThermalEvent, rep.event_id)


@router.get("")
def list_reports(db: Session = Depends(get_db), status_: str | None = Query(default=None, alias="status"), limit: int = Query(default=200, ge=1, le=1000)):
    q = select(EventReport, ThermalEvent).join(ThermalEvent, ThermalEvent.id == EventReport.event_id).order_by(EventReport.created_at.desc())
    if status_:
        q = q.where(EventReport.status == status_)
    rows = db.execute(q.limit(limit)).all()
    return {"items": [report_out(r, e) for r, e in rows], "total": len(rows)}


@router.get("/{report_id}")
def get_report(report_id: int, db: Session = Depends(get_db)):
    rep, ev = _get(db, report_id)
    return report_out(rep, ev)


@router.get("/{report_id}/download")
def download(report_id: int, db: Session = Depends(get_db)):
    rep, _ = _get(db, report_id)
    if rep.status != "generated" or not os.path.exists(rep.file_path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PDF file not available")
    return FileResponse(rep.file_path, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={rep.file_name}"})


@router.get("/{report_id}/view")
def view(report_id: int, db: Session = Depends(get_db)):
    rep, _ = _get(db, report_id)
    if rep.status != "generated" or not os.path.exists(rep.file_path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PDF file not available")
    return FileResponse(rep.file_path, media_type="application/pdf", headers={"Content-Disposition": f"inline; filename={rep.file_name}"})


@router.post("/{report_id}/regenerate")
def regenerate(report_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _, ev = _get(db, report_id)
    rep = build_pdf(db, ev, generated_by=user.email)
    log_action(db, user.email, "regenerate_pdf", "event", ev.incident_id)
    db.commit()
    return {"message": "Report regenerated" if rep.status == "generated" else f"Failed: {rep.error}", "report": report_out(rep, ev)}
