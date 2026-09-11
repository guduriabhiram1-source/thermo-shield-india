"""LightGBM training pipeline - human-verified samples ONLY.

No synthetic / bootstrap records are ever generated. Training refuses to run
until the verified dataset is large and diverse enough; a trained model is
stored as a *candidate* and is promoted to production only by an explicit,
audited ADMIN action after reviewing the validation metrics.

Run:  python -m app.ml.train            (from backend/)"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

import numpy as np

from ..config import MODEL_DIR, settings
from .features import CLASSES, FEATURE_NAMES

log = logging.getLogger("thermoshield.ml.train")
PRODUCTION_MODEL = MODEL_DIR / "lightgbm_thermal.pkl"
PRODUCTION_META = MODEL_DIR / "model_meta.json"


class InsufficientTrainingData(RuntimeError):
    pass


def check_dataset(y: np.ndarray) -> dict:
    counts = {CLASSES[i]: int((y == i).sum()) for i in range(len(CLASSES)) if (y == i).sum() > 0}
    usable = {k: v for k, v in counts.items() if v >= 5}
    ok = len(y) >= settings.ml_min_training_samples and len(usable) >= settings.ml_min_classes
    return {"total": int(len(y)), "by_class": counts, "classes_with_5plus": len(usable), "min_total": settings.ml_min_training_samples,
            "min_classes": settings.ml_min_classes, "sufficient": ok}


def train_model(X: np.ndarray, y: np.ndarray, sample_ids: list[int], test_size: float = 0.25, min_accuracy: float = 0.7, seed: int = 42, note: str = "") -> dict:
    import joblib
    import lightgbm as lgb
    from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
    from sklearn.model_selection import train_test_split

    ds = check_dataset(y)
    if not ds["sufficient"]:
        raise InsufficientTrainingData(f"ML model unavailable - insufficient validated training data ({ds['total']} verified samples, "
                                       f"{ds['classes_with_5plus']} classes with >=5 samples; need >= {ds['min_total']} samples and >= {ds['min_classes']} classes)")
    present = sorted(set(int(v) for v in y))
    remap = {old: new for new, old in enumerate(present)}
    y2 = np.asarray([remap[int(v)] for v in y])
    strat = y2 if min(np.bincount(y2)) >= 2 else None
    Xtr, Xte, ytr, yte, idtr, idte = train_test_split(X, y2, np.asarray(sample_ids), test_size=test_size, random_state=seed, stratify=strat)
    model = lgb.LGBMClassifier(objective="multiclass" if len(present) > 2 else "binary", n_estimators=200, learning_rate=0.05, num_leaves=15,
                               min_child_samples=3, subsample=0.9, subsample_freq=1, colsample_bytree=0.85, reg_lambda=1.0, random_state=seed, verbose=-1)
    model.fit(Xtr, ytr, feature_name=FEATURE_NAMES)
    pred = model.predict(Xte)
    metrics = {
        "accuracy": round(float(accuracy_score(yte, pred)), 4),
        "precision_macro": round(float(precision_score(yte, pred, average="macro", zero_division=0)), 4),
        "recall_macro": round(float(recall_score(yte, pred, average="macro", zero_division=0)), 4),
        "f1_macro": round(float(f1_score(yte, pred, average="macro", zero_division=0)), 4),
        "train_samples": int(len(ytr)), "test_samples": int(len(yte)),
    }
    imp = model.booster_.feature_importance(importance_type="gain")
    total = float(imp.sum()) or 1.0
    importance = {n: round(float(v) / total, 4) for n, v in sorted(zip(FEATURE_NAMES, imp), key=lambda t: -t[1])}
    version = datetime.now(timezone.utc).strftime("v%Y%m%d-%H%M%S")
    validated = metrics["accuracy"] >= min_accuracy and metrics["test_samples"] >= 5
    meta = {
        "version": version, "algorithm": "LightGBM (TreeSHAP explanations)", "classes": [CLASSES[i] for i in present], "features": FEATURE_NAMES,
        "training_samples": int(len(y)), "verified_samples": int(len(y)), "dataset": ds, "metrics": metrics, "feature_importance": importance,
        "trained_at": datetime.now(timezone.utc).isoformat(), "validated": validated, "min_accuracy": min_accuracy, "promoted": False,
        "validation_dataset": {"test_sample_ids": [int(i) for i in idte], "train_sample_ids": [int(i) for i in idtr], "test_size": test_size},
        "note": note or "Trained on human-verified samples only",
    }
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODEL_DIR / f"lightgbm_thermal_{version}.pkl"
    meta_path = MODEL_DIR / f"model_meta_{version}.json"
    joblib.dump(model, model_path)
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    meta["file_path"] = str(model_path)
    meta["meta_path"] = str(meta_path)
    log.info("Model %s trained: %s (validated=%s)", version, metrics, validated)
    return meta


def promote_model(version: str) -> dict:
    """Copy the versioned candidate into the production slot (explicit ADMIN action)."""
    import shutil

    model_path = MODEL_DIR / f"lightgbm_thermal_{version}.pkl"
    meta_path = MODEL_DIR / f"model_meta_{version}.json"
    if not model_path.exists() or not meta_path.exists():
        raise FileNotFoundError(f"Model version {version} not found")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if not meta.get("validated"):
        raise ValueError("Model did not pass validation - cannot be promoted")
    meta["promoted"] = True
    meta["promoted_at"] = datetime.now(timezone.utc).isoformat()
    shutil.copyfile(model_path, PRODUCTION_MODEL)
    PRODUCTION_META.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    from . import predict as ml_predict

    ml_predict.load_model(force=True)
    return meta


def demote_production() -> bool:
    removed = False
    for p in (PRODUCTION_MODEL, PRODUCTION_META):
        if p.exists():
            p.unlink()
            removed = True
    from . import predict as ml_predict

    ml_predict.load_model(force=True)
    return removed


def main() -> int:  # CLI helper
    from ..database import SessionLocal
    from ..models import TrainingSample
    from sqlalchemy import select

    with SessionLocal() as db:
        samples = db.execute(select(TrainingSample)).scalars().all()
    if not samples:
        print("ML model unavailable - insufficient validated training data (0 human-verified samples)")
        return 1
    X = np.asarray([[float(s.features.get(k, 0.0)) for k in FEATURE_NAMES] for s in samples], dtype=float)
    y = np.asarray([CLASSES.index(s.verified_label) for s in samples], dtype=int)
    try:
        meta = train_model(X, y, [s.id for s in samples])
    except InsufficientTrainingData as exc:
        print(exc)
        return 1
    print(json.dumps({k: meta[k] for k in ("version", "metrics", "validated")}, indent=2))
    print("Candidate stored. Promote with POST /api/ml/models/{version}/promote (ADMIN).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
