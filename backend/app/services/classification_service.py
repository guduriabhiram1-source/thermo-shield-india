"""Multi-source attribution: LightGBM (when a validated model exists) or the
transparent rule engine, plus evidence, probable cause and the
insufficient-evidence guard. Never claims certainty."""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from ..ml import predict as ml_predict
from ..ml.features import CLASS_LABELS, FEATURE_LABELS
from ..models import EventClassification, ThermalEvent
from .explanation_service import build_explanation

log = logging.getLogger("thermoshield.classify")

PROBABLE_CAUSES = {
    "INDUSTRIAL_FIRE": ("Industrial combustion / equipment-related thermal activity", ["Industrial equipment overheating", "Furnace/boiler activity", "Storage/tank fire", "Electrical/fire incident"]),
    "PERSISTENT_INDUSTRIAL_HEAT": ("Continuous process heat from an industrial installation", ["Furnace/boiler activity", "Industrial equipment overheating"]),
    "WILDFIRE": ("Vegetation fire", ["Vegetation fire", "Combustion activity"]),
    "AGRICULTURAL_BURN": ("Agricultural residue / crop-stubble burning", ["Agricultural burning", "Combustion activity"]),
    "GAS_FLARE": ("Routine or abnormal gas flaring", ["Gas flare"]),
    "REFINERY_ACTIVITY": ("Refinery process heat / flare", ["Refinery process heat", "Gas flare", "Storage/tank fire"]),
    "POWER_PLANT_ACTIVITY": ("Thermal power-plant operation (boilers / stacks / ash handling)", ["Furnace/boiler activity", "Combustion activity"]),
    "MINING_ACTIVITY": ("Mining-related thermal activity (coal seam fire / overburden / processing)", ["Mining activity", "Combustion activity"]),
    "OTHER_THERMAL_SOURCE": ("Unclassified anthropogenic thermal source", ["Combustion activity", "Unknown"]),
    "UNKNOWN": ("Insufficient evidence to infer a cause", ["Unknown"]),
}


def _evidence(ev: ThermalEvent, feats: dict, gis: dict, persistence: dict) -> list[dict]:
    e = []
    frp = feats["max_frp"]
    e.append({"text": f"{'High' if frp >= 100 else 'Moderate' if frp >= 30 else 'Low'} fire radiative power (peak {frp:.0f} MW)", "provenance": "OBSERVED — NASA FIRMS"})
    if feats["frp_growth_rate"] >= 1.5:
        e.append({"text": f"Rapid increase in thermal intensity (×{feats['frp_growth_rate']:.1f} since first detection)", "provenance": "OBSERVED — NASA FIRMS"})
    elif feats["frp_growth_rate"] <= 0.6:
        e.append({"text": "Declining thermal intensity", "provenance": "OBSERVED — NASA FIRMS"})
    if feats["night_ratio"] >= 0.5:
        e.append({"text": f"Night-time thermal signature ({feats['night_ratio'] * 100:.0f}% night detections)", "provenance": "OBSERVED — NASA FIRMS"})
    if persistence.get("class") in ("PERSISTENT", "RECURRING"):
        e.append({"text": f"{persistence['class'].capitalize()} activity on {persistence['active_days']} days (persistence {persistence['score']}/100)", "provenance": "CALCULATED"})
    n = gis.get("nearest", {})
    for key, label in (("refineries", "refinery"), ("gas_facilities", "gas facility"), ("power_plants", "power plant"), ("mines", "mine"), ("industrial_facilities", "industrial facility")):
        f = n.get(key)
        if f and f["distance_km"] <= 5:
            e.append({"text": f"Location within {f['distance_km']} km of {f['name']} ({label})", "provenance": f"OBSERVED — {f.get('source', 'reference')}"})
    lc = gis.get("land_cover", {})
    if lc.get("available"):
        e.append({"text": f"Surrounding land cover: {lc.get('label')}", "provenance": lc.get("provenance", "ESTIMATE")})
    if feats["historical_event_count"] > 0:
        e.append({"text": f"{int(feats['historical_event_count'])} other thermal event(s) within 10 km in the last 12 months", "provenance": "OBSERVED — platform archive"})
    if feats["spatial_spread_km"] >= 3:
        e.append({"text": f"Spatial spread of {feats['spatial_spread_km']:.1f} km across detections", "provenance": "OBSERVED — NASA FIRMS"})
    return e


def _uncertainty(ev: ThermalEvent, feats: dict, pred: dict) -> str:
    notes = []
    if not pred.get("ml_model_available"):
        notes.append("rule-based attribution (no validated ML model)")
    if pred["confidence"] < 0.6:
        notes.append("confidence below 60%")
    if ev.detection_count < 3:
        notes.append("fewer than 3 detections")
    if feats["mean_confidence"] < 0.5:
        notes.append("low FIRMS detection confidence")
    alts = pred.get("alternatives", [])
    if alts and alts[0]["probability"] > 0.25:
        notes.append(f"competing hypothesis {CLASS_LABELS[alts[0]['classification']]} ({alts[0]['probability'] * 100:.0f}%)")
    if not notes:
        return "Moderate: satellite-derived inference; field verification still required."
    return "Elevated: " + "; ".join(notes) + ". Field verification required."


def insufficient_evidence(ev: ThermalEvent, feats: dict, gis: dict) -> bool:
    no_context = gis.get("nearest_industrial_any") is None or gis["nearest_industrial_any"]["distance_km"] > 10
    return ev.detection_count <= 1 and feats["mean_confidence"] < 0.5 and feats["max_frp"] < 10 and no_context


def classify_event(db: Session, ev: ThermalEvent, feats: dict, gis: dict, persistence: dict) -> EventClassification:
    try:
        pred = ml_predict.predict(feats)
    except Exception as exc:
        log.error("Model prediction failed (%s); using rule engine", exc)
        from ..ml.rules import predict_rules

        pred = predict_rules(feats)
    insufficient = insufficient_evidence(ev, feats, gis)
    cls = "UNKNOWN" if insufficient else pred["classification"]
    confidence = min(pred["confidence"], 0.3) if insufficient else pred["confidence"]
    explanation = build_explanation(pred, feats, cls)
    cause_title, cause_options = PROBABLE_CAUSES[cls]
    evidence = _evidence(ev, feats, gis, persistence)
    cause = {"title": cause_title, "options": cause_options, "confidence": round(confidence, 4), "evidence": evidence,
             "wording": "AI inference — probable cause only. Satellite data alone is not proof of the exact cause; requires field verification.",
             "verification": "Pending human verification" if ev.human_status == "PENDING" else ev.human_status, "provenance": "MODEL INFERENCE"}
    record = EventClassification(
        event_id=ev.id, model_name=pred["model_name"], model_version=str(pred.get("model_version") or ""), classification=cls, confidence=round(confidence, 4),
        probabilities=pred["probabilities"], shap_values=pred.get("shap_values"), contributions=pred.get("contributions"), feature_importance=pred.get("feature_importance"),
        evidence=evidence, uncertainty=("Insufficient evidence — Human verification required" if insufficient else _uncertainty(ev, feats, pred)),
        human_explanation=explanation["summary"], probable_cause=cause, insufficient_evidence=1 if insufficient else 0, ml_model_available=1 if pred.get("ml_model_available") else 0)
    db.add(record)
    ev.classification = cls
    ev.classification_confidence = round(confidence, 4)
    ev.classification_method = pred["model_name"]
    ev.probable_cause = cause_title
    ev.ai_status = "INSUFFICIENT_EVIDENCE" if insufficient else "PREDICTED"
    ev.explanation = {**explanation, "classification": cls, "label": CLASS_LABELS[cls], "confidence": round(confidence, 4), "probabilities": pred["probabilities"],
                      "alternatives": pred.get("alternatives", []), "contribution_ranked": pred.get("contribution_ranked", []), "feature_importance": pred.get("feature_importance", {}),
                      "model_version": pred.get("model_version"), "model_name": pred["model_name"], "insufficient_evidence": insufficient, "uncertainty": record.uncertainty,
                      "evidence": evidence, "feature_labels": FEATURE_LABELS, "provenance": "MODEL INFERENCE"}
    return record
