"""NASA FIRMS ingestion: rows -> validated, normalised, de-duplicated
`thermal_detections` with LIVE / HISTORICAL data_status.

Pipeline: FIRMS -> ingestion -> validation -> normalisation -> duplicate
detection -> 12-month limit -> data_status -> database -> event formation."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import HISTORY_LIMIT, settings
from ..models import IngestionRun, ThermalDetection
from .firms.nasa_firms import parse_csv_text  # noqa: F401  (re-export)
from .geocode_service import in_india

log = logging.getLogger("thermoshield.firms")

CONFIDENCE_MAP = {"l": 0.3, "low": 0.3, "n": 0.6, "nominal": 0.6, "h": 0.9, "high": 0.9}
FUTURE_TOLERANCE = timedelta(hours=36)


def normalise_confidence(raw) -> float:
    if raw is None or raw == "":
        return 0.5
    s = str(raw).strip().lower()
    if s in CONFIDENCE_MAP:
        return CONFIDENCE_MAP[s]
    try:
        v = float(s)
        return max(0.0, min(1.0, v / 100.0 if v > 1 else v))
    except ValueError:
        return 0.5


def parse_firms_row(row: dict, now: datetime | None = None) -> tuple[dict | None, str | None]:
    """Convert a FIRMS CSV row (VIIRS or MODIS naming) into a detection dict. Returns (record, rejection_reason)."""
    now = now or datetime.now(timezone.utc)
    try:
        lat = float(row.get("latitude"))
        lon = float(row.get("longitude"))
    except (TypeError, ValueError):
        return None, "invalid_coordinates"
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None, "coordinates_out_of_range"
    if not in_india(lat, lon):
        return None, "outside_india"
    acq_date_raw = (row.get("acq_date") or "").strip()
    acq_time_raw = str(row.get("acq_time") or "").strip()
    try:
        acq_date = date.fromisoformat(acq_date_raw)
    except ValueError:
        return None, "invalid_date"
    acq_time = acq_time_raw.zfill(4)[:4]
    if not acq_time.isdigit():
        return None, "invalid_time"
    hh, mm = int(acq_time[:2]), int(acq_time[2:])
    if hh > 23 or mm > 59:
        return None, "invalid_time"
    acq_dt = datetime(acq_date.year, acq_date.month, acq_date.day, hh, mm, tzinfo=timezone.utc)
    if acq_dt > now + FUTURE_TOLERANCE:
        return None, "future_timestamp"
    if acq_dt < now - HISTORY_LIMIT:
        return None, "older_than_12_months"

    def fnum(*keys, default=0.0):
        for k in keys:
            v = row.get(k)
            if v not in (None, ""):
                try:
                    return float(v)
                except ValueError:
                    continue
        return default

    frp = fnum("frp")
    if frp < 0 or frp > 10000:
        return None, "frp_out_of_range"
    brightness = fnum("bright_ti4", "brightness")
    if brightness and not (200 <= brightness <= 500):
        return None, "brightness_out_of_range"
    rec = {
        "latitude": lat, "longitude": lon, "acq_date": acq_date, "acq_time": acq_time, "acq_datetime": acq_dt,
        "satellite": str(row.get("satellite") or "").strip(), "instrument": str(row.get("instrument") or "").strip(),
        "confidence": str(row.get("confidence") or "").strip(), "confidence_score": normalise_confidence(row.get("confidence")),
        "brightness": brightness, "brightness_2": fnum("bright_ti5", "bright_t31"), "frp": frp,
        "scan": fnum("scan"), "track": fnum("track"), "day_night": (str(row.get("daynight") or row.get("day_night") or "D")[:1] or "D").upper(),
        "version": str(row.get("version") or "").strip(), "source": str(row.get("source") or "FIRMS_CSV"),
    }
    return rec, None


def classify_data_status(acq_dt: datetime, ingested_at: datetime, mode: str) -> str:
    """LIVE only for observations from a live feed that are newer than LIVE_WINDOW_HOURS at ingestion time."""
    if mode == "archive":
        return "HISTORICAL"
    age = ingested_at - acq_dt
    return "LIVE" if age <= timedelta(hours=settings.live_window_hours) else "HISTORICAL"


def ingest_rows(db: Session, rows: Iterable[dict], mode: str = "live", source_label: str = "FIRMS", feed_status: dict | None = None, force_status: str | None = None) -> IngestionRun:
    """mode: live | archive | csv. Returns the IngestionRun with `_new_detection_ids` attached."""
    now = datetime.now(timezone.utc)
    run = IngestionRun(source=source_label, mode=mode, data_status="HISTORICAL" if mode == "archive" else "LIVE", feed_status=feed_status)
    db.add(run)
    db.flush()
    reasons: dict[str, int] = {}
    received = valid = dup = live = hist = 0
    latest: datetime | None = None
    new_ids: list[int] = []
    seen: set[tuple] = set()
    for row in rows:
        received += 1
        rec, why = parse_firms_row(row, now)
        if why:
            reasons[why] = reasons.get(why, 0) + 1
            continue
        key = (round(rec["latitude"], 5), round(rec["longitude"], 5), rec["acq_date"], rec["acq_time"], rec["satellite"])
        if key in seen:
            dup += 1
            continue
        seen.add(key)
        exists = db.execute(select(ThermalDetection.id).where(
            ThermalDetection.latitude == rec["latitude"], ThermalDetection.longitude == rec["longitude"], ThermalDetection.acq_date == rec["acq_date"],
            ThermalDetection.acq_time == rec["acq_time"], ThermalDetection.satellite == rec["satellite"])).first()
        if exists:
            dup += 1
            continue
        status_ = force_status or classify_data_status(rec["acq_datetime"], now, mode)
        det = ThermalDetection(**rec, data_status=status_, ingested_at=now, ingestion_run_id=run.id)
        db.add(det)
        db.flush()
        new_ids.append(det.id)
        valid += 1
        if status_ == "LIVE":
            live += 1
        else:
            hist += 1
        if latest is None or rec["acq_datetime"] > latest:
            latest = rec["acq_datetime"]
    run.rows_received, run.rows_valid, run.rows_duplicate, run.rows_live, run.rows_historical = received, valid, dup, live, hist
    run.rows_rejected = received - valid - dup
    run.rejection_reasons = reasons
    run.latest_observation = latest
    run.status = "ingested"
    run.finished_at = datetime.now(timezone.utc)
    run.message = f"{valid} new detections ({live} LIVE, {hist} HISTORICAL), {dup} duplicates, {run.rows_rejected} rejected"
    db.flush()
    run._new_detection_ids = new_ids  # type: ignore[attr-defined]
    log.info("FIRMS ingest (%s/%s): %s", mode, source_label, run.message)
    return run


def latest_detections(db: Session, limit: int = 500, hours: int | None = None, data_status: str | None = None) -> list[ThermalDetection]:
    q = select(ThermalDetection).order_by(ThermalDetection.acq_datetime.desc())
    if hours:
        q = q.where(ThermalDetection.acq_datetime >= datetime.now(timezone.utc) - timedelta(hours=hours))
    if data_status:
        q = q.where(ThermalDetection.data_status == data_status)
    return list(db.execute(q.limit(limit)).scalars().all())


def latest_observation_time(db: Session, data_status: str | None = None) -> datetime | None:
    q = select(func.max(ThermalDetection.acq_datetime))
    if data_status:
        q = q.where(ThermalDetection.data_status == data_status)
    return db.execute(q).scalar()


def age_live_detections(db: Session) -> int:
    """Demote LIVE detections whose observation is now older than the live window."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.live_window_hours)
    rows = db.execute(select(ThermalDetection).where(ThermalDetection.data_status == "LIVE", ThermalDetection.acq_datetime < cutoff)).scalars().all()
    for d in rows:
        d.data_status = "HISTORICAL"
    db.flush()
    return len(rows)


def purge_expired(db: Session) -> int:
    """Enforce the 12-month limit on stored observations."""
    cutoff = datetime.now(timezone.utc) - HISTORY_LIMIT
    n = db.query(ThermalDetection).filter(ThermalDetection.acq_datetime < cutoff).delete(synchronize_session=False)
    db.flush()
    return int(n or 0)
