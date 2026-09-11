"""Turns model / rule contributions into a ranked table + a plain-language sentence.
When SHAP is available the rows are SHAP values; otherwise they are documented
rule weights and the method says so."""
from __future__ import annotations

from ..ml.features import CLASS_LABELS, FEATURE_LABELS


def describe(feature: str, value) -> str:
    v = float(value or 0)
    if feature in ("max_frp", "mean_frp", "latest_frp"):
        lvl = "High" if v >= 80 else "Moderate" if v >= 25 else "Low"
        kind = {"max_frp": "peak", "mean_frp": "mean", "latest_frp": "latest"}[feature]
        return f"{lvl} {kind} FRP ({v:.0f} MW)"
    if feature == "frp_growth_rate":
        return "Sudden FRP increase" if v >= 1.5 else "Stable FRP" if 0.8 <= v <= 1.2 else "Declining FRP" if v < 0.8 else "Rising FRP"
    if feature == "frp_trend":
        return "Rising FRP trend" if v > 5 else "Falling FRP trend" if v < -5 else "Flat FRP trend"
    if feature == "night_ratio":
        return "Night-time detection" if v >= 0.5 else "Daytime detection"
    if feature == "persistence_score":
        return "High persistence" if v >= 60 else "Low persistence" if v < 30 else "Moderate persistence"
    if feature == "mean_confidence":
        return "High detection confidence" if v >= 0.7 else "Low detection confidence" if v < 0.45 else "Nominal detection confidence"
    if feature.startswith("dist_"):
        what = FEATURE_LABELS[feature].replace("Distance to ", "")
        if v >= 99:
            return f"No {what} within search radius"
        if v < 3:
            return f"Near {what} ({v:.1f} km)"
        return f"{what} {v:.0f} km away"
    if feature == "land_cover_code":
        names = {0: "Forest land cover", 1: "Cropland land cover", 2: "Built-up land cover", 3: "Industrial land cover", 4: "Bare land", 5: "Water", 6: "Grassland", 7: "Other / unknown land cover"}
        return names.get(int(v), "Land cover")
    if feature == "detection_count":
        return f"{int(v)} detection(s)"
    if feature == "detection_frequency":
        return f"{v:.1f} detections per active day"
    if feature == "active_days":
        return f"{int(v)} active day(s)"
    if feature == "spatial_spread_km":
        return "Wide spatial spread" if v >= 3 else "Compact hotspot cluster"
    if feature == "month":
        return f"Month {int(v)} (seasonal prior)"
    if feature == "max_brightness":
        return f"Brightness temperature {v:.0f} K"
    return FEATURE_LABELS.get(feature, feature)


def build_explanation(pred: dict, feats: dict, cls: str) -> dict:
    ranked = pred.get("contribution_ranked") or []
    positives = [r for r in ranked if r["contribution"] > 0][:6]
    negatives = [r for r in ranked if r["contribution"] < 0][:4]
    rows = [{"feature": r["feature"], "label": r["label"], "value": r["value"], "description": describe(r["feature"], r["value"]), "contribution": r["contribution"],
             "direction": "supports" if r["contribution"] > 0 else "opposes"} for r in ranked[:12]]
    label = CLASS_LABELS.get(cls, cls)

    def _lc(s: str) -> str:
        return s[0].lower() + s[1:] if s else s

    if positives:
        parts = [_lc(describe(p["feature"], p["value"])) for p in positives[:3]]
        text = (", ".join(parts[:-1]) + f" and {parts[-1]}") if len(parts) > 1 else parts[0]
        summary = f"{text[0].upper() + text[1:]} were the strongest factors influencing the {label} inference."
        if negatives:
            summary += f" Strongest factor against it: {_lc(describe(negatives[0]['feature'], negatives[0]['value']))}."
    else:
        summary = f"No single factor strongly supported the {label} inference; treat the result as low-confidence."
    shap_ok = bool(pred.get("shap_available"))
    return {
        "question": "Why did the AI classify this event?", "rows": rows,
        "top_positive": [{"description": describe(p["feature"], p["value"]), "contribution": p["contribution"]} for p in positives],
        "top_negative": [{"description": describe(n["feature"], n["value"]), "contribution": n["contribution"]} for n in negatives],
        "summary": summary,
        "method": "SHAP (TreeSHAP on LightGBM), contributions in log-odds toward the predicted class" if shap_ok else "Rule-based attribution weights on observed features (no validated ML model available - not SHAP)",
        "shap_available": shap_ok, "ml_model_available": bool(pred.get("ml_model_available")), "method_note": pred.get("method_note", ""),
    }
