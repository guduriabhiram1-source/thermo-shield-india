"""Classification, risk, wind exposure, population estimation, ML gating."""
from __future__ import annotations

from sqlalchemy import select

from app.ml import predict as ml_predict
from app.ml.features import CLASSES, FEATURE_NAMES, build_features
from app.ml.rules import predict_rules
from app.models import AffectedArea, EventClassification, RiskScore, ThermalEvent
from app.services.exposure_engine import compute_exposure
from app.services.population_service import population_in_radius
from app.services.risk_engine import WEIGHTS, compute_components, explain_change, risk_level
from app.utils.geo import bearing_deg, compass, destination_point, haversine_km, point_to_polyline_km, sector_polygon

from .conftest import WEATHER


def test_geo_helpers():
    assert 1130 < haversine_km(28.6139, 77.2090, 19.0760, 72.8777) < 1170
    assert compass(bearing_deg(0, 0, 1, 0)) == "N" and compass(bearing_deg(0, 0, 0, 1)) == "E"
    lat, lon = destination_point(20.0, 80.0, 90, 111.32 * 0.9397)
    assert abs(lat - 20.0) < 0.01 and lon > 80.9
    poly = sector_polygon(20, 80, 45, 30, 10)
    assert len(poly) > 20 and poly[0] == [20, 80]
    assert point_to_polyline_km(20.0, 80.0, [[19.0, 80.0], [21.0, 80.0]]) < 0.5


def test_rule_engine_outputs_full_distribution():
    f = {k: 0.0 for k in FEATURE_NAMES}
    f.update(max_frp=150, frp_growth_rate=2.2, mean_confidence=0.9, detection_count=9, persistence_score=25, dist_industrial_km=0.6, dist_refinery_km=0.9, land_cover_code=3, month=9)
    p = predict_rules(f)
    assert p["classification"] in CLASSES and abs(sum(p["probabilities"].values()) - 1) < 1e-3
    assert p["ml_model_available"] is False and p["shap_available"] is False and p["model_name"] == "rules"
    assert p["classification"] in ("INDUSTRIAL_FIRE", "REFINERY_ACTIVITY") and p["contribution_ranked"]
    f2 = {k: 0.0 for k in FEATURE_NAMES}
    f2.update(max_frp=12, mean_confidence=0.6, detection_count=15, active_days=1, night_ratio=0.0, land_cover_code=1, month=11, dist_industrial_km=100, dist_refinery_km=100, dist_power_plant_km=100, dist_mine_km=100, dist_gas_km=100)
    assert predict_rules(f2)["classification"] == "AGRICULTURAL_BURN"
    f3 = {k: 0.0 for k in FEATURE_NAMES}
    f3.update(max_frp=30, frp_growth_rate=1.0, mean_confidence=0.8, detection_count=20, active_days=20, night_ratio=0.9, persistence_score=90, dist_gas_km=0.4, dist_industrial_km=0.4, land_cover_code=3, month=6)
    assert predict_rules(f3)["classification"] == "GAS_FLARE"


def test_ml_model_unavailable_without_verified_data(client, admin):
    from .conftest import auth

    info = ml_predict.model_info()
    assert info["available"] is False and "insufficient validated training data" in info["status"]
    m = client.get("/api/ml/model", headers=auth(admin)).json()
    assert m["ml_model_available"] is False and "ML model unavailable" in m["status_message"]
    r = client.post("/api/ml/train", json={}, headers=auth(admin))
    assert r.status_code == 409 and "insufficient validated training data" in r.json()["detail"]


def test_risk_levels_and_change_explanation():
    assert risk_level(10) == "LOW" and risk_level(35) == "MODERATE" and risk_level(50) == "MEDIUM" and risk_level(70) == "HIGH" and risk_level(90) == "CRITICAL"
    assert sum(WEIGHTS.values()) == 100
    reasons = explain_change({k: 0.8 for k in WEIGHTS}, {k: 0.4 for k in WEIGHTS}, 30)
    assert reasons and all(r["delta_points"] > 0 for r in reasons)


def test_pipeline_outputs_for_real_events(db, seeded):
    events = db.execute(select(ThermalEvent).where(ThermalEvent.analysed_at.isnot(None))).scalars().all()
    assert len(events) >= 10
    for ev in events:
        assert ev.state and ev.risk_level in ("LOW", "MODERATE", "MEDIUM", "HIGH", "CRITICAL")
        assert ev.classification in CLASSES and 0 <= ev.classification_confidence <= 1 and ev.classification_method == "rules"
        assert ev.exposure and ev.exposure["is_estimate"] and ev.exposure["hazard_circle"]
        assert ev.explanation and ev.explanation["summary"] and ev.explanation["ml_model_available"] is False
        assert ev.precautions and ev.precautions["general"]
        assert ev.timeline and ev.timeline[0]["title"].startswith("First observed") and ev.timeline[0]["provenance"] == "OBSERVED"
        assert ev.provenance and ev.provenance["classification"].startswith("MODEL INFERENCE")
        assert ev.ai_status in ("PREDICTED", "INSUFFICIENT_EVIDENCE") and ev.human_status in ("PENDING", "VERIFIED", "CORRECTED", "UNCERTAIN")
        assert ev.risk_breakdown and "_missing_inputs" in ev.risk_breakdown
    assert db.execute(select(EventClassification)).scalars().first() is not None
    assert db.execute(select(RiskScore)).scalars().first() is not None
    # reference pass has no weather → wind exposure component 0 and recorded as missing
    ev = events[0]
    comps, missing = compute_components(ev, ev.features, ev.gis_context, {"available": False}, ev.exposure, 0)
    assert comps["wind_exposure"] == 0.0 and any("weather unavailable" in m for m in missing)
    assert list(build_features(ev, ev.gis_context, ev.weather, ev.persistence_details, 1)[0].keys()) == FEATURE_NAMES


def test_wind_exposure_with_and_without_weather(db, seeded):
    ev = db.execute(select(ThermalEvent).order_by(ThermalEvent.max_frp.desc())).scalars().first()
    w = WEATHER.current(ev.latitude, ev.longitude)
    ex = compute_exposure(db, ev, w, ev.gis_context)
    assert ex["wind"]["available"] and ex["downwind_sector"] and ex["downwind_reach_km"] >= ex["hazard_radius_km"]
    assert ex["wind"]["downwind"] == "NE"  # wind FROM SW (225°) blows TO NE
    assert all(a["name"] and a["basis"] == "estimate" for a in ex["affected_areas"])
    n_downwind = sum(1 for a in ex["affected_areas"] if a["downwind"])
    ex2 = compute_exposure(db, ev, {"available": False}, ev.gis_context)
    assert ex2["downwind_sector"] is None and ex2["wind"]["available"] is False and "unavailable" in ex2["wind"]["note"].lower()
    assert all(not a["downwind"] for a in ex2["affected_areas"])
    assert n_downwind >= 0
    assert db.execute(select(AffectedArea).where(AffectedArea.event_id == ev.id)).scalars().first() is not None
    db.rollback()


def test_population_estimate_is_labelled(db):
    pop = population_in_radius(db, 17.6868, 83.2185, 10.0, "Andhra Pradesh")  # Visakhapatnam
    assert pop["is_estimate"] is True and pop["total_estimate"] > 100000 and pop["breakdown"][0]["name"]
    empty = population_in_radius(db, 27.0, 71.0, 5.0, "Rajasthan")  # desert
    assert empty["settlement_population"] == 0 and empty["is_estimate"]
