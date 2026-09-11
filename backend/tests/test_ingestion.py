"""FIRMS validation, India filter, 12-month limit, duplicates, LIVE/HISTORICAL status, clustering, persistence."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import ThermalDetection, ThermalEvent
from app.services.firms.nasa_firms import parse_csv_text, public_feed_url
from app.services.firms_service import classify_data_status, normalise_confidence, parse_firms_row
from app.services.geocode_service import in_india, reverse_geocode_reference
from app.services.persistence_engine import compute_persistence
from app.services.reference_data import districts_for_state, load_districts, load_states

from .conftest import FIXTURE_CSV, firms_rows


def test_firms_row_validation_and_limits():
    good = {"latitude": "17.69", "longitude": "83.27", "acq_date": datetime.now(timezone.utc).date().isoformat(), "acq_time": "715", "satellite": "N", "instrument": "VIIRS", "confidence": "h", "bright_ti4": "345.2", "frp": "55.3", "daynight": "D"}
    rec, why = parse_firms_row(good)
    assert why is None and rec["acq_time"] == "0715" and rec["confidence_score"] == 0.9 and rec["frp"] == 55.3
    assert parse_firms_row({**good, "latitude": "51.5", "longitude": "-0.1"})[1] == "outside_india"
    assert parse_firms_row({**good, "acq_date": "bad"})[1] == "invalid_date"
    assert parse_firms_row({**good, "frp": "-3"})[1] == "frp_out_of_range"
    assert parse_firms_row({**good, "acq_date": "2099-01-01"})[1] == "future_timestamp"
    old = (datetime.now(timezone.utc) - timedelta(days=400)).date().isoformat()
    assert parse_firms_row({**good, "acq_date": old})[1] == "older_than_12_months"
    assert normalise_confidence("85") == 0.85 and normalise_confidence("l") == 0.3 and normalise_confidence(None) == 0.5


def test_data_status_rules():
    now = datetime.now(timezone.utc)
    assert classify_data_status(now - timedelta(hours=5), now, "live") == "LIVE"
    assert classify_data_status(now - timedelta(hours=60), now, "live") == "HISTORICAL"
    assert classify_data_status(now - timedelta(hours=5), now, "archive") == "HISTORICAL"


def test_india_polygon_rejects_neighbours_and_geocodes_states():
    inside = [(17.69, 83.27), (28.61, 77.2), (24.8, 93.9), (34.15, 77.58), (11.62, 92.73), (31.63, 74.87), (23.83, 91.29), (27.34, 88.61), (8.09, 77.55), (23.7, 69.0)]
    outside = [(24.86, 67.0), (27.7, 85.3), (23.8, 90.4), (6.9, 79.86), (16.8, 96.1), (31.55, 74.34), (24.9, 91.87), (27.47, 89.64)]
    assert all(in_india(*p) for p in inside)
    assert not any(in_india(*p) for p in outside)
    assert reverse_geocode_reference(17.6868, 83.2185)["state"] == "Andhra Pradesh"
    assert reverse_geocode_reference(28.62, 77.21)["state"] == "Delhi"
    assert reverse_geocode_reference(26.14, 91.73)["state"] == "Assam"
    g = reverse_geocode_reference(22.35, 70.05)
    assert g["state"] == "Gujarat" and g["district"] == "Jamnagar"


def test_boundary_datasets_cover_all_india():
    assert len(load_states()) == 36
    assert len(load_districts()) > 700
    ap = [d["name"] for d in districts_for_state("Andhra Pradesh")]
    assert {"Guntur", "Krishna", "Prakasam", "Visakhapatnam"} <= set(ap)
    assert len(districts_for_state("Uttar Pradesh")) >= 70


def test_real_public_feed_sample_parses_and_filters_to_india():
    text = FIXTURE_CSV.read_text(encoding="utf-8")
    rows = parse_csv_text(text, source="FIRMS_PUBLIC_SUOMI-NPP")
    assert len(rows) > 300
    kept, reasons = 0, {}
    now = datetime(2026, 9, 11, tzinfo=timezone.utc)
    for row in rows:
        rec, why = parse_firms_row(row, now=now)
        if why:
            reasons[why] = reasons.get(why, 0) + 1
        else:
            kept += 1
            assert in_india(rec["latitude"], rec["longitude"])
    assert kept > 50 and reasons.get("outside_india", 0) > 50
    assert public_feed_url("noaa-20", "South_Asia", "24h").endswith("/noaa-20-viirs-c2/csv/J1_VIIRS_C2_South_Asia_24h.csv")


def test_ingestion_status_duplicates_and_clustering(client, seeded, db):
    live, hist = seeded["live"]["run"], seeded["historical"]["run"]
    assert live["rows_valid"] > 50 and live["rows_live"] == live["rows_valid"] and live["rows_historical"] == 0
    assert hist["rows_valid"] > 50 and hist["rows_historical"] == hist["rows_valid"] and hist["rows_live"] == 0
    assert live["rejection_reasons"].get("outside_india", 0) > 50
    # re-ingesting the same rows yields only duplicates
    from app.services.firms_service import ingest_rows

    run = ingest_rows(db, firms_rows(days_ago=0.5, limit=40), mode="csv", source_label="FIRMS_TEST_FIXTURE")
    assert run.rows_valid == 0 and run.rows_duplicate > 0
    db.rollback()
    events = db.execute(select(ThermalEvent)).scalars().all()
    assert len(events) >= 10
    assert all(e.incident_id.startswith("TSI-IND-") and len(e.incident_id) == 19 for e in events)
    statuses = {e.data_status for e in events}
    assert statuses == {"LIVE", "HISTORICAL"}
    for e in events[:50]:
        dets = db.execute(select(ThermalDetection).where(ThermalDetection.event_id == e.id)).scalars().all()
        assert len(dets) == e.detection_count and e.first_detected_at <= e.last_detected_at
        assert all(d.data_status == ("LIVE" if e.data_status == "LIVE" else d.data_status) for d in dets)
    # detections keep observation_timestamp + ingestion_timestamp + source + data_status
    d = db.execute(select(ThermalDetection)).scalars().first()
    assert d.acq_datetime and d.ingested_at and d.source == "FIRMS_TEST_FIXTURE" and d.data_status in ("LIVE", "HISTORICAL")


def test_persistence_scores_and_classes(db, seeded):
    events = db.execute(select(ThermalEvent)).scalars().all()
    classes = set()
    for e in events:
        p = compute_persistence(db, e)
        assert 0 <= p["score"] <= 100 and p["class"] in ("ISOLATED", "TEMPORARY", "RECURRING", "PERSISTENT")
        classes.add(p["class"])
    db.rollback()
    assert classes & {"ISOLATED", "TEMPORARY"}
