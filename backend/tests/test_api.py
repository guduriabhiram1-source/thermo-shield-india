"""API endpoint tests over the real-fixture database."""
from __future__ import annotations

from .conftest import auth


def test_events_list_filters_and_ranges(client, admin, seeded):
    r = client.get("/api/events?limit=5&sort=risk", headers=auth(admin)).json()
    assert r["total"] >= 5 and len(r["items"]) == 5 and r["history_window"]["from"]
    first = r["items"][0]
    for key in ("incident_id", "classification", "classification_method", "risk_score", "risk_level", "confidence", "state", "district", "max_frp", "persistence_score", "data_status", "first_detected_at", "last_detected_at"):
        assert key in first
    live = client.get("/api/events?range=live", headers=auth(admin)).json()
    assert live["total"] >= 1 and all(i["data_status"] == "LIVE" for i in live["items"]) and live["range"]["data_status"] == "LIVE"
    hist = client.get("/api/events?data_status=HISTORICAL", headers=auth(admin)).json()
    assert hist["total"] >= 1 and all(i["data_status"] == "HISTORICAL" for i in hist["items"])
    last30 = client.get("/api/events?range=30d", headers=auth(admin)).json()
    assert all(i["data_status"] == "LIVE" for i in last30["items"])  # the 200-day-old events fall outside 30 days
    assert client.get("/api/events?range=12m", headers=auth(admin)).json()["total"] == r["total"]
    state = first["state"]
    filt = client.get(f"/api/events?state={state}", headers=auth(admin)).json()
    assert all(i["state"] == state for i in filt["items"]) and filt["total"] >= 1
    assert client.get("/api/events?risk_level=HIGH,CRITICAL", headers=auth(admin)).status_code == 200
    assert client.get("/api/events?verified=unverified", headers=auth(admin)).json()["total"] >= 1
    gj = client.get("/api/events/geojson", headers=auth(admin)).json()
    assert gj["type"] == "FeatureCollection" and len(gj["features"]) == r["total"]
    pr = client.get("/api/events/priority?limit=3&data_status=LIVE", headers=auth(admin)).json()
    assert pr["items"] and pr["items"][0]["priority_rank"] == 1 and pr["items"][0]["data_status"] == "LIVE"


def test_event_detail_sections(client, admin, seeded):
    iid = client.get("/api/events?limit=1&sort=risk", headers=auth(admin)).json()["items"][0]["incident_id"]
    d = client.get(f"/api/events/{iid}", headers=auth(admin)).json()
    assert d["incident_id"] == iid
    for section in ("persistence", "gis_context", "weather", "exposure", "evolution", "explanation", "risk_breakdown", "risk_change", "precautions", "satellite", "timeline", "detections", "affected_areas", "probable_cause_detail", "provenance"):
        assert d[section] is not None, section
    assert d["explanation"]["rows"] and d["explanation"]["summary"] and d["explanation"]["ml_model_available"] is False
    assert d["weather"]["available"] is False  # reference pass, no weather provider called
    assert d["satellite"]["sentinel2"]["status"] == "unavailable"
    assert d["detections"][0]["provenance"].startswith("OBSERVED") and d["detections"][0]["data_status"] in ("LIVE", "HISTORICAL")
    for sub in ("timeline", "risk", "exposure", "detections", "verifications", "satellite"):
        assert client.get(f"/api/events/{iid}/{sub}", headers=auth(admin)).status_code == 200
    tl = client.get(f"/api/events/{iid}/timeline", headers=auth(admin)).json()
    assert tl["first_observed"] and tl["items"][0]["type"] == "detection"
    assert client.get("/api/events/TSI-IND-1999-000001", headers=auth(admin)).status_code == 404


def test_boundaries_and_dynamic_districts(client, admin):
    s = client.get("/api/boundaries/states", headers=auth(admin)).json()
    assert len(s["states"]) == 36
    d = client.get("/api/boundaries/districts?state=Andhra%20Pradesh", headers=auth(admin)).json()
    assert d["count"] >= 25 and {"Guntur", "Krishna", "Prakasam"} <= {x["name"] for x in d["districts"]}
    assert client.get("/api/boundaries/districts?state=Atlantis", headers=auth(admin)).status_code == 404
    gj = client.get("/api/boundaries/states.geojson", headers=auth(admin)).json()
    assert gj["type"] == "FeatureCollection" and len(gj["features"]) == 36


def test_analytics_search_and_location(client, admin, seeded):
    dash = client.get("/api/analytics/dashboard", headers=auth(admin)).json()
    assert dash["cards"]["total_events"] >= 5 and dash["events_over_time"] and dash["risk_distribution"] and dash["history_window"]["label"]
    assert dash["cards"]["total_observations"] > 0 and "freshness" in dash and "top_priority_live" in dash and "top_priority_historical" in dash
    live_only = client.get("/api/analytics/dashboard?range=live", headers=auth(admin)).json()
    assert live_only["cards"]["historical_events"] == 0
    india = client.get("/api/analytics/india", headers=auth(admin)).json()
    assert len(india["states"]) == 36 and any(s["observations"] == "no_observations" for s in india["states"])
    top_state = india["states"][0]["state"]
    st = client.get(f"/api/analytics/state/{top_state}", headers=auth(admin)).json()
    assert st["summary"]["total_events"] >= 1 and st["districts"] and st["all_districts"]
    assert client.get("/api/analytics/state/Atlantis", headers=auth(admin)).status_code == 404
    s = client.get("/api/search?q=16.5062, 80.6480", headers=auth(admin)).json()
    assert s["coordinates"]["latitude"] == 16.5062 and "location-analysis" in s["coordinates"]["action"]
    assert client.get("/api/search?q=refinery", headers=auth(admin)).json()["facilities"]
    assert client.get("/api/search?q=guntur", headers=auth(admin)).json()["districts"]
    loc = client.get("/api/location/analyze?lat=17.6935&lon=83.2685&radius_km=25&live=false", headers=auth(admin)).json()
    assert loc["location"]["state"] == "Andhra Pradesh" and loc["gis"]["nearest"]["refineries"] and loc["risk"]["level"]
    assert loc["population"]["is_estimate"] is True and loc["weather"]["available"] is False and loc["district_candidates"]
    assert client.get("/api/location/analyze?lat=95&lon=10", headers=auth(admin)).status_code == 422


def test_images_and_pdf_cycle(client, analyst, seeded):
    iid = client.get("/api/events?limit=1&sort=risk", headers=auth(analyst)).json()["items"][0]["incident_id"]
    imgs = client.get(f"/api/events/{iid}/images", headers=auth(analyst)).json()["items"]
    types = {i["type"] for i in imgs}
    assert {"hotspot_map", "context_map", "exposure_map", "affected_map", "frp_chart", "risk_chart", "shap_chart", "thermal_imagery", "optical_before", "optical_after"} <= types
    unavailable = [i for i in imgs if i["type"] == "thermal_imagery"][0]
    assert unavailable["available"] is False and "unavailable" in unavailable["description"].lower()
    png = client.get(f"/api/events/{iid}/images/hotspot_map.png", headers=auth(analyst))
    assert png.status_code == 200 and png.content[:4] == b"\x89PNG"
    gen = client.post(f"/api/events/{iid}/generate-pdf", headers=auth(analyst))
    assert gen.status_code == 200, gen.text
    rep = gen.json()["report"]
    assert rep["status"] == "generated" and rep["file_name"] == f"ThermoShield_Incident_{iid}.pdf" and rep["pages"] == 13
    pdf = client.get(f"/api/events/{iid}/pdf", headers=auth(analyst))
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    reports = client.get("/api/reports", headers=auth(analyst)).json()["items"]
    assert any(r["incident_id"] == iid and r["data_status"] for r in reports)
    assert client.get(f"/api/reports/{rep['id']}/download", headers=auth(analyst)).status_code == 200
    assert client.get(f"/api/reports/{rep['id']}/view", headers=auth(analyst)).status_code == 200
    assert client.post(f"/api/reports/{rep['id']}/regenerate", headers=auth(analyst)).json()["report"]["status"] == "generated"


def test_verification_roles_and_training_sample(client, admin, analyst, viewer, seeded):
    iid = client.get("/api/events?limit=1&sort=priority", headers=auth(admin)).json()["items"][0]["incident_id"]
    assert client.post(f"/api/events/{iid}/verify", json={"action": "CONFIRM"}, headers=auth(viewer)).status_code == 403
    assert client.post(f"/api/events/{iid}/verify", json={"action": "CONFIRM"}).status_code == 401
    assert client.post(f"/api/events/{iid}/verify", json={"action": "CORRECT"}, headers=auth(analyst)).status_code == 422
    r = client.post(f"/api/events/{iid}/verify", json={"action": "CORRECT", "classification": "AGRICULTURAL_BURN", "notes": "Confirmed with district agriculture office"}, headers=auth(analyst))
    assert r.status_code == 200, r.text
    assert r.json()["event"]["human_status"] == "CORRECTED" and r.json()["event"]["verified_classification"] == "AGRICULTURAL_BURN"
    ds = client.get("/api/ml/training-dataset", headers=auth(admin)).json()
    assert any(i["incident_id"] == iid and i["origin"] == "human_verified" and i["analyst"] == "analyst.user@example.org" for i in ds["items"])
    tl = client.get(f"/api/events/{iid}/timeline", headers=auth(admin)).json()["items"]
    assert any(t["type"] == "verified" and t["provenance"] == "HUMAN VERIFIED" for t in tl)
    q = client.get("/api/system/verification-queue", headers=auth(admin)).json()
    assert any(e["incident_id"] == iid for e in q["completed"])
    d = client.get(f"/api/events/{iid}", headers=auth(admin)).json()
    assert d["provenance"]["human_verification"].startswith("HUMAN VERIFIED")
    # ML still refuses to train on a single sample
    assert client.post("/api/ml/train", json={}, headers=auth(admin)).status_code == 409


def test_firms_endpoints_and_admin_guards(client, admin, analyst, viewer, seeded):
    latest = client.get("/api/firms/latest?limit=10", headers=auth(viewer)).json()
    assert latest["returned"] == 10 and latest["last_run"]["mode"] == "csv" and latest["live_detections"] > 0 and latest["history_window"]["days"] == 366
    assert client.post("/api/firms/ingest", json={"mode": "api"}, headers=auth(analyst)).status_code == 400  # no key configured
    assert client.post("/api/firms/backfill", json={"start_date": "2026-01-01T00:00:00Z"}, headers=auth(admin)).status_code == 400  # archive needs a key
    assert client.post("/api/firms/live-ingest", headers=auth(analyst)).status_code == 403
    csv_forced = "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight\n"
    assert client.post("/api/firms/ingest", json={"mode": "csv", "csv_text": csv_forced, "csv_data_status": "LIVE"}, headers=auth(analyst)).status_code == 403
    ov = client.get("/api/system/overview", headers=auth(viewer)).json()
    assert ov["providers"]["ml_model"].startswith("rules") and ov["counts"]["events"] > 0 and ov["data_notice"]
    assert client.get("/api/system/audit", headers=auth(viewer)).status_code == 403
    assert client.get("/api/system/audit", headers=auth(admin)).status_code == 200
