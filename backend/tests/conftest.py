"""Test fixtures: isolated SQLite database, no external network (providers stubbed), capturing e-mail provider.

The FIRMS fixture is a REAL NASA FIRMS South_Asia public-feed extract (SNPP VIIRS, 2026-09-10); its acquisition dates are
shifted relative to 'now' so the same real rows can exercise the LIVE and the HISTORICAL ingestion paths."""
from __future__ import annotations

import csv
import io
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")
TEST_DB = Path(__file__).parent / "test_thermal_expo.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["REPORTS_DIR"] = str(Path(__file__).parent / "_reports")
for k, v in {"ENABLE_SCHEDULER": "false", "LIVE_INGEST_ON_STARTUP": "false", "BACKGROUND_VISUALS": "false", "AUTO_GENERATE_PDF": "false", "WEATHER_PROVIDER": "none",
             "OSM_PROVIDER": "reference", "NOMINATIM_ENABLED": "false", "SATELLITE_PROVIDER": "none", "LANDCOVER_PROVIDER": "reference", "NASA_FIRMS_MAP_KEY": "", "NASA_FIRMS_API_KEY": "",
             "SMTP_USERNAME": "", "SMTP_PASSWORD": "", "EMAIL_DEV_LOG_ONLY": "false", "JWT_SECRET": "test-secret-not-for-production", "ALERT_RECIPIENTS": "duty-officer@example.org",
             "ALERT_COOLDOWN_HOURS": "12", "FIRST_USER_IS_ADMIN": "true", "AUTH_RATE_LIMIT_PER_MINUTE": "500", "LIVE_WINDOW_HOURS": "48", "ALLOWED_EMAIL_DOMAINS": "", "BOOTSTRAP_ADMIN_EMAILS": ""}.items():
    os.environ[k] = v
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine, init_db  # noqa: E402
from app.services import email_service, weather_service  # noqa: E402
from app.services.email.base import EmailMessage, EmailProvider, EmailResult  # noqa: E402
from app.services.weather.base import WeatherProvider, unavailable  # noqa: E402

FIXTURE_CSV = Path(__file__).parent / "fixtures" / "firms_south_asia_24h_real_sample.csv"


class CapturingEmail(EmailProvider):
    name = "capture"

    def __init__(self):
        self.sent: list[EmailMessage] = []

    def configured(self) -> bool:
        return True

    def send(self, message: EmailMessage) -> EmailResult:
        self.sent.append(message)
        return EmailResult(status="sent", detail="captured by test provider", provider=self.name)


class StubWeather(WeatherProvider):
    """Deterministic test-only wind so the exposure geometry can be asserted. Never used outside tests."""

    name = "test-stub"
    enabled = True

    def configured(self) -> bool:
        return True

    def current(self, lat, lon):
        if not self.enabled:
            return unavailable("stub disabled", self.name)
        return {"available": True, "kind": "current", "weather_source": "test-stub", "wind_speed_kmh": 18.0, "wind_direction_deg": 225.0, "wind_direction_compass": "SW", "wind_gust_kmh": 25.0,
                "temperature_c": 30.0, "humidity_pct": 60.0, "precipitation_mm": 0.0, "weather_timestamp": datetime.now(timezone.utc).isoformat(), "retrieved_at": datetime.now(timezone.utc).isoformat()}

    def at_time(self, lat, lon, when):
        return self.current(lat, lon)


EMAIL = CapturingEmail()
WEATHER = StubWeather()


def firms_rows(days_ago: float = 0.5, limit: int | None = None) -> list[dict]:
    """Real FIRMS rows with acq_date shifted so the newest observation is `days_ago` days before now."""
    rows = list(csv.DictReader(io.open(FIXTURE_CSV, encoding="utf-8")))
    orig = max(datetime.fromisoformat(r["acq_date"]) for r in rows)
    if limit:
        rows = rows[:limit]
    shift = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days_ago)).date() - orig.date()
    out = []
    for r in rows:
        r = dict(r)
        r["acq_date"] = (datetime.fromisoformat(r["acq_date"]) + shift).date().isoformat()
        r["instrument"] = "VIIRS"
        r["source"] = "FIRMS_TEST_FIXTURE"
        out.append(r)
    return out


@pytest.fixture(scope="session", autouse=True)
def _database():
    Base.metadata.drop_all(engine)
    init_db()
    from app.services.reference_data import seed_reference_data

    with SessionLocal() as db:
        seed_reference_data(db)
    email_service.set_provider_override(EMAIL)
    weather_service.set_provider_override(WEATHER)
    yield
    engine.dispose()
    import shutil

    shutil.rmtree(Path(__file__).parent / "_reports", ignore_errors=True)
    for suffix in ("", "-wal", "-shm"):
        try:
            Path(str(TEST_DB) + suffix).unlink()
        except (FileNotFoundError, PermissionError):
            pass


@pytest.fixture(scope="session")
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _register_and_verify(client: TestClient, email: str, password: str = "StrongPassw0rd!") -> dict:
    r = client.post("/api/auth/register", json={"email": email, "password": password, "confirm_password": password, "full_name": email.split("@")[0]})
    assert r.status_code in (201, 200), r.text
    msg = next(m for m in reversed(EMAIL.sent) if email in m.to)
    code = msg.subject.split(":")[-1].strip()
    r = client.post("/api/auth/verify-email", json={"email": email, "code": code})
    assert r.status_code == 200, r.text
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="session")
def admin(client):
    return _register_and_verify(client, "admin.user@example.org")  # first verified user → ADMIN


@pytest.fixture(scope="session")
def analyst(client, admin):
    tok = _register_and_verify(client, "analyst.user@example.org")
    r = client.patch(f"/api/users/{tok['user']['id']}", json={"role": "ANALYST"}, headers={"Authorization": f"Bearer {admin['access_token']}"})
    assert r.status_code == 200, r.text
    return client.post("/api/auth/login", json={"email": "analyst.user@example.org", "password": "StrongPassw0rd!"}).json()


@pytest.fixture(scope="session")
def viewer(client, admin):
    return _register_and_verify(client, "viewer.user@example.org")


def auth(tok: dict) -> dict:
    return {"Authorization": f"Bearer {tok['access_token']}"}


@pytest.fixture(scope="session")
def seeded(client, admin):
    """Ingest real FIRMS rows twice: recent (LIVE) and 200 days old (HISTORICAL), analysed through the pipeline."""
    csv_live = _to_csv(firms_rows(days_ago=0.5))
    r = client.post("/api/firms/ingest", json={"mode": "csv", "csv_text": csv_live, "analyse": True}, headers=auth(admin))
    assert r.status_code == 200, r.text
    live_run = r.json()
    csv_hist = _to_csv(firms_rows(days_ago=200))
    r = client.post("/api/firms/ingest", json={"mode": "csv", "csv_text": csv_hist, "analyse": True}, headers=auth(admin))
    assert r.status_code == 200, r.text
    return {"live": live_run, "historical": r.json()}


def _to_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()
