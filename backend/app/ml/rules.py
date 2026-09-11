"""Transparent rule-based source attribution.

Used whenever no *validated, human-verified* LightGBM model has been promoted
to production. Every rule is an explicit, documented weight applied to a real
computed feature; the output has the same shape as the model prediction so the
UI / PDF / API stay identical, but it is labelled `method = "rules"` and
`ml_model_available = False`, and the contributions are rule weights - NOT SHAP.

No probabilities are learned here: scores are normalised evidence weights."""
from __future__ import annotations

import math

from .features import CLASSES, FEATURE_LABELS

RULES_VERSION = "rules-v2.0"


def _near(d: float, close: float, far: float) -> float:
    """1 when d <= close, 0 when d >= far, linear in between."""
    if d <= close:
        return 1.0
    if d >= far:
        return 0.0
    return 1.0 - (d - close) / (far - close)


def score_classes(f: dict) -> tuple[dict[str, float], dict[str, dict[str, float]]]:
    """Returns (class_scores, contributions[class][feature])."""
    frp = f["max_frp"]
    growth = f["frp_growth_rate"]
    night = f["night_ratio"]
    persist = f["persistence_score"] / 100.0
    spread = f["spatial_spread_km"]
    lc = int(f["land_cover_code"])
    conf = f["mean_confidence"]
    d_ind, d_ref, d_pp, d_mine, d_gas, d_store = (f["dist_industrial_km"], f["dist_refinery_km"], f["dist_power_plant_km"], f["dist_mine_km"], f["dist_gas_km"], f["dist_storage_km"])
    month = int(f["month"])
    high_frp = min(frp / 150.0, 1.5)
    growing = max(0.0, min((growth - 1.0) / 2.0, 1.0))
    stable = 1.0 - min(abs(growth - 1.0) / 0.6, 1.0)
    industrial_lc = 1.0 if lc == 3 else 0.5 if lc == 2 else 0.0
    forest_lc = 1.0 if lc == 0 else 0.4 if lc == 6 else 0.0
    crop_lc = 1.0 if lc == 1 else 0.0
    bare_lc = 1.0 if lc == 4 else 0.0
    burn_season = 1.0 if month in (3, 4, 5, 10, 11) else 0.3
    fire_season = 1.0 if month in (2, 3, 4, 5, 6) else 0.4

    C: dict[str, dict[str, float]] = {c: {} for c in CLASSES}
    # INDUSTRIAL_FIRE: sudden, intense, near industry, compact
    C["INDUSTRIAL_FIRE"] = {"dist_industrial_km": 1.4 * _near(d_ind, 1.0, 6.0), "frp_growth_rate": 1.1 * growing, "max_frp": 0.9 * high_frp,
                            "land_cover_code": 0.6 * industrial_lc, "persistence_score": -0.9 * persist, "spatial_spread_km": -0.3 * min(spread / 5.0, 1.0)}
    C["PERSISTENT_INDUSTRIAL_HEAT"] = {"dist_industrial_km": 1.2 * _near(d_ind, 1.0, 5.0), "persistence_score": 1.5 * persist, "night_ratio": 0.6 * night,
                                       "frp_growth_rate": 0.6 * stable, "land_cover_code": 0.5 * industrial_lc, "spatial_spread_km": -0.4 * min(spread / 4.0, 1.0)}
    C["WILDFIRE"] = {"land_cover_code": 1.6 * forest_lc, "spatial_spread_km": 0.9 * min(spread / 6.0, 1.0), "frp_growth_rate": 0.5 * growing,
                     "dist_industrial_km": 0.6 * (1.0 - _near(d_ind, 3.0, 15.0)), "month": 0.4 * fire_season, "persistence_score": -0.5 * max(0.0, persist - 0.5)}
    C["AGRICULTURAL_BURN"] = {"land_cover_code": 1.6 * crop_lc, "night_ratio": 0.7 * (1.0 - night), "max_frp": 0.6 * (1.0 - min(frp / 60.0, 1.0)),
                              "month": 0.6 * burn_season, "persistence_score": -0.8 * persist, "dist_industrial_km": 0.4 * (1.0 - _near(d_ind, 3.0, 12.0))}
    C["GAS_FLARE"] = {"dist_gas_km": 2.2 * _near(d_gas, 1.0, 4.0), "night_ratio": 0.7 * night, "persistence_score": 0.8 * persist,
                      "spatial_spread_km": 0.4 * (1.0 - min(spread / 2.0, 1.0)), "frp_growth_rate": 0.3 * stable}
    C["REFINERY_ACTIVITY"] = {"dist_refinery_km": 2.1 * _near(d_ref, 1.5, 5.0), "persistence_score": 0.7 * persist, "night_ratio": 0.3 * night, "frp_growth_rate": 0.3 * stable,
                              "dist_storage_km": 0.3 * _near(d_store, 1.0, 4.0)}
    C["POWER_PLANT_ACTIVITY"] = {"dist_power_plant_km": 2.1 * _near(d_pp, 1.5, 5.0), "persistence_score": 0.6 * persist, "frp_growth_rate": 0.3 * stable, "spatial_spread_km": 0.2 * (1.0 - min(spread / 2.0, 1.0))}
    C["MINING_ACTIVITY"] = {"dist_mine_km": 2.1 * _near(d_mine, 2.0, 6.0), "land_cover_code": 0.4 * bare_lc, "persistence_score": 0.4 * persist, "spatial_spread_km": 0.2 * min(spread / 3.0, 1.0)}
    C["OTHER_THERMAL_SOURCE"] = {"land_cover_code": 0.5 * (1.0 if lc in (2, 7) else 0.0), "dist_industrial_km": 0.4 * _near(d_ind, 3.0, 12.0) * (1.0 - _near(d_ind, 1.0, 3.0)),
                                 "max_frp": 0.3 * min(frp / 80.0, 1.0), "mean_confidence": 0.2 * conf}
    C["UNKNOWN"] = {"mean_confidence": 1.1 * (1.0 - conf), "detection_count": 0.9 * (1.0 if f["detection_count"] <= 1 else 0.2 if f["detection_count"] <= 2 else 0.0),
                    "max_frp": 0.7 * (1.0 - min(frp / 25.0, 1.0)), "dist_industrial_km": 0.3 * (1.0 - _near(d_ind, 5.0, 25.0)) * (1.0 - forest_lc) * (1.0 - crop_lc)}
    scores = {c: 0.25 + sum(v for v in C[c].values()) for c in CLASSES}
    return scores, C


def predict_rules(feats: dict) -> dict:
    scores, contrib = score_classes(feats)
    # softmax-style normalisation with temperature so that probabilities are never absurdly sharp
    m = max(scores.values())
    exps = {c: math.exp((s - m) * 1.6) for c, s in scores.items()}
    z = sum(exps.values())
    probs = {c: round(exps[c] / z, 4) for c in CLASSES}
    order = sorted(CLASSES, key=lambda c: -probs[c])
    top = order[0]
    contributions = {k: round(v, 4) for k, v in contrib[top].items() if abs(v) > 1e-6}
    ranked = sorted(contributions.items(), key=lambda kv: -abs(kv[1]))
    return {
        "classification": top,
        "confidence": probs[top],
        "probabilities": probs,
        "alternatives": [{"classification": c, "probability": probs[c]} for c in order[1:4]],
        "shap_values": None,
        "shap_available": False,
        "contributions": contributions,
        "contribution_ranked": [{"feature": k, "label": FEATURE_LABELS.get(k, k), "value": feats.get(k), "contribution": v} for k, v in ranked],
        "feature_importance": {},
        "model_version": RULES_VERSION,
        "model_name": "rules",
        "method": "rules",
        "ml_model_available": False,
        "method_note": "ML model unavailable - insufficient validated training data. Transparent rule-based attribution shown (documented weights on observed features); contributions are rule weights, not SHAP values.",
    }
