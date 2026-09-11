from __future__ import annotations

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth.security import get_current_user, require_admin
from ..config import settings
from ..database import get_db
from ..ml import predict as ml_predict
from ..ml.features import CLASS_LABELS, CLASSES, FEATURE_LABELS, FEATURE_NAMES
from ..ml.rules import RULES_VERSION
from ..ml.train import InsufficientTrainingData, check_dataset, demote_production, promote_model, train_model
from ..models import ModelVersion, TrainingSample, User
from ..schemas import TrainRequest
from ..services.audit import log_action
from ..utils.timeutil import iso

router = APIRouter(prefix="/api/ml", tags=["ml"], dependencies=[Depends(get_current_user)])


def _mv_out(m: ModelVersion) -> dict:
    return {"id": m.id, "version": m.version, "algorithm": m.algorithm, "training_date": iso(m.training_date), "training_samples": m.training_samples, "accuracy": m.accuracy, "precision": m.precision,
            "recall": m.recall, "f1": m.f1, "validation_dataset": m.validation_dataset, "metrics": m.metrics, "feature_importance": m.feature_importance, "is_production": bool(m.is_production),
            "validated": bool(m.validated), "promoted_by": m.promoted_by, "promoted_at": iso(m.promoted_at), "note": m.note}


def _dataset(db: Session):
    samples = db.execute(select(TrainingSample)).scalars().all()
    y = np.asarray([CLASSES.index(s.verified_label) for s in samples], dtype=int) if samples else np.asarray([], dtype=int)
    return samples, y


@router.get("/model")
def model(db: Session = Depends(get_db)):
    info = ml_predict.model_info()
    samples, y = _dataset(db)
    ds = check_dataset(y) if len(y) else {"total": 0, "by_class": {}, "classes_with_5plus": 0, "min_total": settings.ml_min_training_samples, "min_classes": settings.ml_min_classes, "sufficient": False}
    registry = db.execute(select(ModelVersion).order_by(ModelVersion.training_date.desc()).limit(20)).scalars().all()
    return {"production": info, "ml_model_available": info.get("available", False),
            "status_message": None if info.get("available") else "ML model unavailable — insufficient validated training data. Classification currently uses the transparent rule-based attribution engine (" + RULES_VERSION + ").",
            "training_dataset": ds, "feature_labels": FEATURE_LABELS, "features": FEATURE_NAMES, "classes": CLASSES, "class_labels": CLASS_LABELS, "registry": [_mv_out(m) for m in registry],
            "policy": "Models train only on human-verified samples; a trained candidate is never used until an ADMIN explicitly promotes a validated version."}


@router.get("/training-dataset")
def training_dataset(db: Session = Depends(get_db), limit: int = Query(default=200, ge=1, le=5000)):
    rows = db.execute(select(TrainingSample).order_by(TrainingSample.verification_timestamp.desc()).limit(limit)).scalars().all()
    by_label = db.execute(select(TrainingSample.verified_label, func.count(TrainingSample.id)).group_by(TrainingSample.verified_label)).all()
    return {"total": db.execute(select(func.count(TrainingSample.id))).scalar() or 0, "by_label": [{"label": l, "label_name": CLASS_LABELS.get(l, l), "count": c} for l, c in by_label],
            "items": [{"id": r.id, "event_id": r.event_id, "incident_id": r.incident_id, "verified_label": r.verified_label, "label_name": CLASS_LABELS.get(r.verified_label, r.verified_label), "origin": r.origin,
                       "analyst": r.analyst, "analyst_id": r.analyst_id, "verification_timestamp": iso(r.verification_timestamp), "model_version": r.model_version, "features": r.features} for r in rows]}


@router.post("/train")
def train(body: TrainRequest, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    samples, y = _dataset(db)
    if not samples:
        raise HTTPException(status.HTTP_409_CONFLICT, "ML model unavailable — insufficient validated training data (0 human-verified samples)")
    X = np.asarray([[float(s.features.get(k, 0.0)) for k in FEATURE_NAMES] for s in samples], dtype=float)
    try:
        meta = train_model(X, y, [s.id for s in samples], test_size=body.test_size, min_accuracy=body.min_accuracy, note=body.note or f"Trained by {user.email} on {len(samples)} verified samples")
    except InsufficientTrainingData as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    m = ModelVersion(version=meta["version"], algorithm="LightGBM", file_path=meta["file_path"], training_samples=meta["training_samples"], accuracy=meta["metrics"]["accuracy"],
                     precision=meta["metrics"]["precision_macro"], recall=meta["metrics"]["recall_macro"], f1=meta["metrics"]["f1_macro"], validation_dataset=meta["validation_dataset"],
                     metrics=meta["metrics"], feature_importance=meta["feature_importance"], validated=1 if meta["validated"] else 0, is_production=0, note=meta["note"])
    db.add(m)
    log_action(db, user.email, "train_model", "model", meta["version"], {"metrics": meta["metrics"], "validated": meta["validated"]})
    db.commit()
    return {"message": "Candidate model trained" + (" and passed validation — promote it explicitly to use it" if meta["validated"] else " but did NOT pass validation"), "model": _mv_out(m)}


@router.post("/models/{version}/promote")
def promote(version: str, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    m = db.execute(select(ModelVersion).where(ModelVersion.version == version)).scalar_one_or_none()
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Model version not found")
    if not m.validated:
        raise HTTPException(status.HTTP_409_CONFLICT, "Model did not pass validation - cannot be promoted")
    try:
        promote_model(version)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    for old in db.execute(select(ModelVersion).where(ModelVersion.is_production == 1)).scalars().all():
        old.is_production = 0
    from datetime import datetime, timezone

    m.is_production, m.promoted_by, m.promoted_at = 1, user.email, datetime.now(timezone.utc)
    log_action(db, user.email, "promote_model", "model", version)
    db.commit()
    return {"message": f"Model {version} promoted to production", "model": _mv_out(m)}


@router.post("/models/demote")
def demote(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    removed = demote_production()
    for old in db.execute(select(ModelVersion).where(ModelVersion.is_production == 1)).scalars().all():
        old.is_production = 0
    log_action(db, user.email, "demote_model", "model", "")
    db.commit()
    return {"message": "Production model removed - rule-based attribution active" if removed else "No production model was active"}
