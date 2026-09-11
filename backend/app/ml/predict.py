"""Inference: LightGBM + TreeSHAP when a validated production model exists,
otherwise the transparent rule engine (clearly labelled)."""
from __future__ import annotations

import json
import logging
import threading

import numpy as np

from ..config import MODEL_DIR
from .features import CLASSES, FEATURE_LABELS, FEATURE_NAMES, feature_vector
from .rules import predict_rules

log = logging.getLogger("thermoshield.ml.predict")
MODEL_PATH = MODEL_DIR / "lightgbm_thermal.pkl"
META_PATH = MODEL_DIR / "model_meta.json"
_lock = threading.Lock()
_model = None
_meta: dict | None = None
_explainer = None
_loaded_for: tuple[float, float] | None = None


def production_model_available() -> bool:
    return MODEL_PATH.exists() and META_PATH.exists()


def load_model(force: bool = False):
    """Loads the production model if present; returns (model, meta) or (None, None)."""
    global _model, _meta, _explainer, _loaded_for
    with _lock:
        if not production_model_available():
            _model, _meta, _explainer, _loaded_for = None, None, None, None
            return None, None
        stamp = (MODEL_PATH.stat().st_mtime, META_PATH.stat().st_mtime)
        if _model is not None and not force and _loaded_for == stamp:
            return _model, _meta
        import joblib

        _model = joblib.load(MODEL_PATH)
        _meta = json.loads(META_PATH.read_text(encoding="utf-8"))
        _loaded_for = stamp
        _explainer = None
        try:
            import shap

            _explainer = shap.TreeExplainer(_model)
        except Exception as exc:  # pragma: no cover
            log.info("shap unavailable (%s); using LightGBM pred_contrib", exc)
        return _model, _meta


def model_info() -> dict:
    _, meta = load_model()
    if meta is None:
        return {"available": False, "status": "ML model unavailable - insufficient validated training data", "fallback": "rules"}
    return {"available": True, **meta}


def _shap_for_class(X, class_index: int) -> np.ndarray:
    model, _ = load_model()
    if _explainer is not None:
        vals = _explainer.shap_values(X)
        if isinstance(vals, list):
            return np.asarray(vals[class_index])[0]
        vals = np.asarray(vals)
        if vals.ndim == 3:
            return vals[0, :, class_index]
        return vals[0]
    contrib = model.booster_.predict(X, pred_contrib=True)
    nf = len(FEATURE_NAMES) + 1
    return contrib[0, class_index * nf: class_index * nf + nf - 1]


def predict(features: dict) -> dict:
    model, meta = load_model()
    if model is None:
        return predict_rules(features)
    import pandas as pd

    classes = meta.get("classes", CLASSES)
    X = pd.DataFrame([feature_vector(features)], columns=FEATURE_NAMES)
    proba = model.predict_proba(X)[0]
    order = np.argsort(proba)[::-1]
    top = int(order[0])
    shap_vals = _shap_for_class(X, top)
    contributions = {FEATURE_NAMES[i]: round(float(shap_vals[i]), 4) for i in range(len(FEATURE_NAMES))}
    ranked = sorted(contributions.items(), key=lambda kv: -abs(kv[1]))
    probs = {c: 0.0 for c in CLASSES}
    for i, c in enumerate(classes):
        probs[c] = round(float(proba[i]), 4)
    return {
        "classification": classes[top],
        "confidence": round(float(proba[top]), 4),
        "probabilities": probs,
        "alternatives": [{"classification": classes[int(i)], "probability": round(float(proba[i]), 4)} for i in order[1:4]],
        "shap_values": contributions,
        "shap_available": True,
        "contributions": contributions,
        "contribution_ranked": [{"feature": k, "label": FEATURE_LABELS.get(k, k), "value": features.get(k), "contribution": v} for k, v in ranked],
        "feature_importance": meta.get("feature_importance", {}),
        "model_version": meta.get("version"),
        "model_name": "lightgbm",
        "method": "lightgbm",
        "ml_model_available": True,
        "method_note": f"LightGBM {meta.get('version')} trained on {meta.get('training_samples')} human-verified samples; contributions are TreeSHAP values.",
    }
