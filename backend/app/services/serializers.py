"""ORM → JSON-serialisable dicts for the API (every block carries provenance)."""
from __future__ import annotations

from ..ml.features import CLASS_LABELS
from ..models import AlertLog, EventImage, EventReport, HumanVerification, Notification, RiskScore, ThermalDetection, ThermalEvent
from ..utils.timeutil import iso
from .priority_service import priority_reason


def event_summary(ev: ThermalEvent) -> dict:
    gis = ev.gis_context or {}
    ind = gis.get("nearest_industrial_any")
    return {
        "id": ev.id, "incident_id": ev.incident_id, "latitude": ev.latitude, "longitude": ev.longitude, "state": ev.state, "district": ev.district, "locality": ev.locality,
        "land_cover": ev.land_cover, "classification": ev.classification, "classification_label": CLASS_LABELS.get(ev.classification, ev.classification),
        "classification_method": ev.classification_method, "confidence": ev.classification_confidence, "probable_cause": ev.probable_cause,
        "risk_score": ev.risk_score, "risk_level": ev.risk_level, "risk_momentum": ev.risk_momentum, "risk_trend": ev.risk_trend,
        "priority_score": ev.priority_score, "priority_rank": ev.priority_rank, "priority_reason": priority_reason(ev),
        "persistence_score": ev.persistence_score, "persistence_class": ev.persistence_class,
        "max_frp": ev.max_frp, "latest_frp": ev.latest_frp, "frp_growth_rate": ev.frp_growth_rate, "max_brightness": ev.max_brightness,
        "detection_count": ev.detection_count, "live_detection_count": ev.live_detection_count, "active_days": ev.active_days, "night_ratio": ev.night_ratio,
        "first_detected_at": iso(ev.first_detected_at), "last_detected_at": iso(ev.last_detected_at), "duration_hours": ev.duration_hours,
        "satellites": ev.satellites, "instruments": ev.instruments, "exposed_population": ev.exposed_population, "exposure_level": ev.exposure_level,
        "status": ev.status, "data_status": ev.data_status, "ai_status": ev.ai_status, "human_status": ev.human_status, "verified_classification": ev.verified_classification,
        "nearest_facility": {"name": ind["name"], "category": ind["category"], "distance_km": ind["distance_km"], "source": ind.get("source")} if ind else None,
        "weather_available": bool((ev.weather or {}).get("available")), "data_source": ev.data_source, "enrichment_level": ev.enrichment_level,
        "updated_at": iso(ev.updated_at), "analysed_at": iso(ev.analysed_at), "has_report": any(r.status == "generated" for r in ev.reports),
    }


def detection_out(d: ThermalDetection) -> dict:
    return {"id": d.id, "latitude": d.latitude, "longitude": d.longitude, "observation_timestamp": iso(d.acq_datetime), "acq_date": d.acq_date.isoformat(), "acq_time": d.acq_time,
            "satellite": d.satellite, "instrument": d.instrument, "confidence": d.confidence, "confidence_score": d.confidence_score, "brightness": d.brightness, "brightness_2": d.brightness_2,
            "frp": d.frp, "scan": d.scan, "track": d.track, "day_night": d.day_night, "version": d.version, "source": d.source, "data_status": d.data_status,
            "ingestion_timestamp": iso(d.ingested_at), "event_id": d.event_id, "provenance": "OBSERVED — NASA FIRMS"}


def risk_out(r: RiskScore) -> dict:
    return {"id": r.id, "computed_at": iso(r.computed_at), "score": r.score, "level": r.level, "previous_score": r.previous_score, "momentum": r.momentum, "trend": r.trend,
            "components": r.components, "change_reasons": r.change_reasons, "data_status": r.data_status}


def image_out(i: EventImage) -> dict:
    return {"id": i.id, "type": i.image_type, "title": i.title, "description": i.description, "url": i.url, "source": i.source, "available": bool(i.is_available),
            "external": bool((i.meta or {}).get("external")), "meta": i.meta, "captured_at": iso(i.captured_at), "created_at": iso(i.created_at)}


def report_out(r: EventReport, ev: ThermalEvent | None = None) -> dict:
    out = {"id": r.id, "event_id": r.event_id, "incident_id": r.incident_id, "file_name": r.file_name, "file_size": r.file_size, "pages": r.pages, "status": r.status,
           "generated_by": r.generated_by, "error": r.error, "created_at": iso(r.created_at), "snapshot": r.snapshot, "download_url": f"/api/reports/{r.id}/download", "view_url": f"/api/reports/{r.id}/view"}
    if ev is not None:
        out.update({"state": ev.state, "district": ev.district, "locality": ev.locality, "classification": ev.classification, "classification_label": CLASS_LABELS.get(ev.classification, ev.classification),
                    "risk_score": ev.risk_score, "risk_level": ev.risk_level, "event_date": iso(ev.last_detected_at), "data_status": ev.data_status})
    return out


def verification_out(v: HumanVerification) -> dict:
    return {"id": v.id, "analyst": v.analyst, "analyst_id": v.analyst_id, "action": v.action, "original_prediction": v.original_prediction, "original_confidence": v.original_confidence,
            "verified_classification": v.verified_classification, "probable_cause": v.probable_cause, "notes": v.notes, "created_at": iso(v.created_at)}


def notification_out(n: Notification) -> dict:
    return {"id": n.id, "event_id": n.event_id, "incident_id": n.incident_id, "severity": n.severity, "data_status": n.data_status, "title": n.title, "message": n.message,
            "payload": n.payload, "acknowledged": bool(n.acknowledged), "created_at": iso(n.created_at)}


def alert_out(a: AlertLog) -> dict:
    return {"id": a.id, "event_id": a.event_id, "incident_id": a.incident_id, "alert_type": a.alert_type, "risk_level": a.risk_level, "risk_score": a.risk_score, "data_status": a.data_status,
            "data_timestamp": iso(a.data_timestamp), "recipient": a.recipient, "status": a.status, "reason": a.reason, "subject": a.subject, "sent_at": iso(a.sent_at), "created_at": iso(a.created_at)}


def event_detail(ev: ThermalEvent, detections: list[ThermalDetection]) -> dict:
    latest_cls = ev.classifications[-1] if ev.classifications else None
    d = event_summary(ev)
    d.update({
        "bbox": ev.bbox, "spatial_spread_km": ev.spatial_spread_km, "locality_distance_km": ev.locality_distance_km, "geocode_provider": ev.geocode_provider,
        "population_density": ev.population_density, "mean_frp": ev.mean_frp, "total_frp": ev.total_frp, "frp_trend": ev.frp_trend, "mean_brightness": ev.mean_brightness,
        "mean_confidence": ev.mean_confidence, "persistence": ev.persistence_details, "gis_context": ev.gis_context, "weather": ev.weather, "exposure": ev.exposure,
        "evolution": ev.evolution, "explanation": ev.explanation, "risk_breakdown": ev.risk_breakdown, "risk_change": ev.risk_change, "precautions": ev.precautions,
        "satellite": ev.satellite, "timeline": ev.timeline, "features": ev.features, "provenance": ev.provenance,
        "probable_cause_detail": latest_cls.probable_cause if latest_cls else None,
        "classification_record": {"model": latest_cls.model_name, "version": latest_cls.model_version, "uncertainty": latest_cls.uncertainty, "insufficient_evidence": bool(latest_cls.insufficient_evidence),
                                  "ml_model_available": bool(latest_cls.ml_model_available), "evidence": latest_cls.evidence, "created_at": iso(latest_cls.created_at)} if latest_cls else None,
        "detections": [detection_out(x) for x in detections], "risk_history": [risk_out(r) for r in ev.risk_scores], "affected_areas": (ev.exposure or {}).get("affected_areas", []),
        "images": [image_out(i) for i in ev.images], "reports": [report_out(r) for r in ev.reports], "verifications": [verification_out(v) for v in ev.verifications],
        "alerts": [alert_out(a) for a in ev.alert_logs], "class_labels": CLASS_LABELS,
    })
    return d
