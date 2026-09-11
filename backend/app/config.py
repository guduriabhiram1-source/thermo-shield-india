"""Application configuration (environment driven).

Every secret and every external endpoint is read from environment variables or
the project `.env`. Nothing in this module is ever shipped to the frontend.
"""
from __future__ import annotations

import os
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent
DATA_DIR = PROJECT_DIR / "data"
REPORTS_DIR = Path(os.environ.get("REPORTS_DIR") or (PROJECT_DIR / "reports"))  # override for tests / deployments
MODEL_DIR = BACKEND_DIR / "app" / "ml" / "model"

# Hard platform rule: no thermal observation older than this is stored or served.
HISTORY_LIMIT_DAYS = 366
HISTORY_LIMIT = timedelta(days=HISTORY_LIMIT_DAYS)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(PROJECT_DIR / ".env", BACKEND_DIR / ".env"), env_file_encoding="utf-8", extra="ignore")

    # --- general -----------------------------------------------------------
    app_name: str = "Thermo-Shield India"
    app_version: str = "2.0.0"
    environment: str = Field(default="development", alias="ENVIRONMENT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    frontend_url: str = Field(default="http://localhost:5190", alias="FRONTEND_URL")
    backend_url: str = Field(default="http://localhost:8200", alias="BACKEND_URL")
    cors_origins: str = Field(default="http://localhost:5190,http://127.0.0.1:5190,http://localhost:3001", alias="CORS_ORIGINS")

    # --- database ----------------------------------------------------------
    # PostgreSQL + PostGIS is the production database. If DATABASE_URL is empty the
    # API falls back to a local SQLite file (development / tests only) - the same
    # ORM is used, spatial indexes and geography columns are added on PostgreSQL.
    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    sqlite_path: Path = DATA_DIR / "thermal_expo_dev.db"

    # --- auth --------------------------------------------------------------
    jwt_secret: str = Field(default="change-me-to-a-long-random-string", alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=60, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=7, alias="REFRESH_TOKEN_EXPIRE_DAYS")
    verification_code_expire_minutes: int = Field(default=10, alias="VERIFICATION_CODE_EXPIRE_MINUTES")
    verification_resend_cooldown_seconds: int = Field(default=60, alias="VERIFICATION_RESEND_COOLDOWN_SECONDS")
    bootstrap_admin_emails: str = Field(default="", alias="BOOTSTRAP_ADMIN_EMAILS")  # comma separated
    first_user_is_admin: bool = Field(default=True, alias="FIRST_USER_IS_ADMIN")
    allowed_email_domains: str = Field(default="", alias="ALLOWED_EMAIL_DOMAINS")  # empty = any domain
    auth_rate_limit_per_minute: int = Field(default=20, alias="AUTH_RATE_LIMIT_PER_MINUTE")

    # --- SMTP / Gmail --------------------------------------------------------
    smtp_host: str = Field(default="smtp.gmail.com", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_username: str = Field(default="", alias="SMTP_USERNAME")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    email_from: str = Field(default="", alias="EMAIL_FROM")
    smtp_use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")
    email_dev_log_only: bool = Field(default=False, alias="EMAIL_DEV_LOG_ONLY")  # log e-mails instead of sending (development only)

    # --- NASA FIRMS ----------------------------------------------------------
    nasa_firms_api_key: str = Field(default="", alias="NASA_FIRMS_API_KEY")
    nasa_firms_map_key: str = Field(default="", alias="NASA_FIRMS_MAP_KEY")
    firms_sources: str = Field(default="VIIRS_SNPP_NRT,VIIRS_NOAA20_NRT,VIIRS_NOAA21_NRT,MODIS_NRT", alias="FIRMS_SOURCES")
    firms_archive_sources: str = Field(default="VIIRS_SNPP_SP,MODIS_SP", alias="FIRMS_ARCHIVE_SOURCES")
    firms_area: str = Field(default="68,6,98,38", alias="FIRMS_AREA")  # India bbox W,S,E,N
    firms_days: int = Field(default=2, alias="FIRMS_DAYS")
    firms_public_region: str = Field(default="South_Asia", alias="FIRMS_PUBLIC_REGION")
    firms_public_window: str = Field(default="48h", alias="FIRMS_PUBLIC_WINDOW")  # 24h | 48h | 7d
    firms_public_sources: str = Field(default="suomi-npp,noaa-20,noaa-21,modis", alias="FIRMS_PUBLIC_SOURCES")
    firms_poll_minutes: int = Field(default=120, alias="FIRMS_POLL_MINUTES")
    live_window_hours: int = Field(default=48, alias="LIVE_WINDOW_HOURS")  # observation newer than this at ingestion => LIVE
    live_ingest_on_startup: bool = Field(default=True, alias="LIVE_INGEST_ON_STARTUP")
    live_enrich_max: int = Field(default=120, alias="LIVE_ENRICH_MAX")
    live_osm_min_frp: float = Field(default=10.0, alias="LIVE_OSM_MIN_FRP")
    enable_scheduler: bool = Field(default=True, alias="ENABLE_SCHEDULER")
    background_visuals: bool = Field(default=True, alias="BACKGROUND_VISUALS")
    background_visuals_max: int = Field(default=40, alias="BACKGROUND_VISUALS_MAX")
    auto_generate_pdf: bool = Field(default=True, alias="AUTO_GENERATE_PDF")

    # --- external providers --------------------------------------------------
    weather_provider: str = Field(default="open-meteo", alias="WEATHER_PROVIDER")  # open-meteo | openweathermap | none
    weather_api_key: str = Field(default="", alias="WEATHER_API_KEY")
    open_meteo_url: str = Field(default="https://api.open-meteo.com/v1/forecast", alias="OPEN_METEO_URL")
    open_meteo_archive_url: str = Field(default="https://archive-api.open-meteo.com/v1/archive", alias="OPEN_METEO_ARCHIVE_URL")
    osm_provider: str = Field(default="overpass", alias="OSM_PROVIDER")  # overpass | reference
    osm_overpass_url: str = Field(default="https://overpass-api.de/api/interpreter", alias="OSM_OVERPASS_URL")
    nominatim_url: str = Field(default="https://nominatim.openstreetmap.org", alias="NOMINATIM_URL")
    nominatim_enabled: bool = Field(default=True, alias="NOMINATIM_ENABLED")
    satellite_provider: str = Field(default="stac", alias="SATELLITE_PROVIDER")  # stac | none
    stac_url: str = Field(default="https://earth-search.aws.element84.com/v1", alias="STAC_URL")
    sentinel_client_id: str = Field(default="", alias="SENTINEL_CLIENT_ID")
    sentinel_client_secret: str = Field(default="", alias="SENTINEL_CLIENT_SECRET")
    landcover_provider: str = Field(default="osm", alias="LANDCOVER_PROVIDER")  # osm | reference
    population_data_source: str = Field(default="census_2011_gazetteer", alias="POPULATION_DATA_SOURCE")
    user_agent: str = Field(default="ThermoShieldIndia/2.0 (thermal incident decision support)", alias="HTTP_USER_AGENT")

    # --- alerts (defaults; editable by ADMIN in the alert settings table) ---
    alerts_enabled: bool = Field(default=True, alias="ALERTS_ENABLED")
    alert_recipients: str = Field(default="", alias="ALERT_RECIPIENTS")  # comma separated e-mails
    alert_cooldown_hours: int = Field(default=12, alias="ALERT_COOLDOWN_HOURS")
    alert_min_confidence: float = Field(default=0.0, alias="ALERT_MIN_CONFIDENCE")

    # --- clustering / analysis --------------------------------------------
    cluster_eps_km: float = Field(default=2.5, alias="CLUSTER_EPS_KM")
    cluster_time_hours: float = Field(default=48.0, alias="CLUSTER_TIME_HOURS")
    cluster_min_samples: int = 1
    gis_search_km: float = 30.0
    exposure_search_km: float = 25.0
    ml_min_training_samples: int = Field(default=40, alias="ML_MIN_TRAINING_SAMPLES")
    ml_min_classes: int = Field(default=2, alias="ML_MIN_CLASSES")

    @property
    def effective_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{self.sqlite_path.as_posix()}"

    @property
    def is_postgres(self) -> bool:
        return self.effective_database_url.startswith("postgres")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def firms_key(self) -> str:
        return (self.nasa_firms_map_key or self.nasa_firms_api_key).strip()

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_username and self.smtp_password and (self.email_from or self.smtp_username))

    @property
    def email_sender(self) -> str:
        return self.email_from or self.smtp_username

    @property
    def alert_recipient_list(self) -> list[str]:
        return [e.strip() for e in self.alert_recipients.split(",") if e.strip()]

    @property
    def bootstrap_admin_list(self) -> list[str]:
        return [e.strip().lower() for e in self.bootstrap_admin_emails.split(",") if e.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
(REPORTS_DIR / "images").mkdir(parents=True, exist_ok=True)
MODEL_DIR.mkdir(parents=True, exist_ok=True)
