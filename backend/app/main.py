"""Thermo-Shield India — FastAPI application entry point (REAL DATA ONLY)."""
from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from .config import settings
from .database import SessionLocal, init_db
from .routers import alerts, analytics, auth, boundaries, events, firms, location, ml, reports, search, system, users

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
for noisy in ("matplotlib", "matplotlib.category", "PIL", "fontTools", "httpx", "httpcore", "apscheduler"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
log = logging.getLogger("thermoshield")
_scheduler = None

DESCRIPTION = """AI-Powered Thermal Fire & Industrial Heat Intelligence Platform for India.

**Data policy:** real NASA FIRMS, OpenStreetMap, Open-Meteo, Sentinel-2 (STAC), Census-2011 population data only; maximum 12-month history;
every observation and event carries `data_status` LIVE or HISTORICAL; live e-mail alerts are generated only from newly ingested LIVE data.

Authenticate with `POST /api/auth/login` (JSON) or the **Authorize** button (username = e-mail) after verifying your e-mail address."""


def _startup_jobs():
    from .services import ingest_service

    try:
        ingest_service.maintenance("startup")
        if settings.live_ingest_on_startup:
            ingest_service.live_ingest("startup")
        if settings.background_visuals:
            ingest_service.background_visuals()
    except Exception:
        log.exception("Startup jobs failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler
    init_db()
    from .services.alert_service import get_alert_settings
    from .services.reference_data import seed_reference_data

    with SessionLocal() as db:
        seed_reference_data(db)
        get_alert_settings(db)
        db.commit()
    threading.Thread(target=_startup_jobs, name="startup-jobs", daemon=True).start()
    if settings.enable_scheduler:
        try:
            from apscheduler.schedulers.background import BackgroundScheduler

            from .services import ingest_service

            _scheduler = BackgroundScheduler(timezone="UTC")
            _scheduler.add_job(lambda: ingest_service.live_ingest("scheduled"), "interval", minutes=settings.firms_poll_minutes, id="firms_live_ingest", max_instances=1, coalesce=True)
            _scheduler.add_job(lambda: ingest_service.maintenance("scheduled"), "interval", hours=6, id="maintenance", max_instances=1, coalesce=True)
            _scheduler.add_job(lambda: ingest_service.background_visuals(), "interval", hours=3, id="visuals", max_instances=1, coalesce=True)
            _scheduler.start()
            log.info("Scheduler started: FIRMS every %d min, maintenance every 6 h, visuals every 3 h", settings.firms_poll_minutes)
        except Exception:
            log.exception("Scheduler failed to start")
    log.info("%s v%s ready — FIRMS %s, weather=%s, osm=%s, satellite=%s, email=%s", settings.app_name, settings.app_version, "API" if settings.firms_key else "public feed",
             settings.weather_provider, settings.osm_provider, settings.satellite_provider, "configured" if settings.smtp_configured else "NOT configured")
    yield
    if _scheduler:
        _scheduler.shutdown(wait=False)


app = FastAPI(title=settings.app_name, version=settings.app_version, description=DESCRIPTION, lifespan=lifespan, docs_url="/docs", redoc_url="/redoc")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def secure_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    if settings.environment == "production":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


for r in (auth, users, events, firms, location, analytics, boundaries, reports, ml, search, system, alerts):
    app.include_router(r.router)


@app.get("/api/health", tags=["system"])
def health():
    return {"status": "ok", "version": settings.app_version, "data_policy": "real data only"}


@app.get("/", include_in_schema=False)
def root():
    return {"app": settings.app_name, "docs": "/docs", "health": "/api/health"}


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes)
    schema.setdefault("components", {}).setdefault("securitySchemes", {})["OAuth2PasswordBearer"] = {"type": "oauth2", "flows": {"password": {"tokenUrl": "/api/auth/token", "scopes": {}}}}
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi
