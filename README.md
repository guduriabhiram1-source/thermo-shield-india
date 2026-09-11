# THERMO-SHIELD INDIA

**AI-Powered Thermal Fire & Industrial Heat Intelligence Platform — national thermal-incident decision support for all of India.**

Real data only. NASA FIRMS thermal detections are clustered into incidents, enriched with OpenStreetMap, Open-Meteo wind, Census-2011
population, land cover and Sentinel-2 evidence, then attributed (LightGBM + SHAP when a validated model exists, otherwise a transparent
rule engine), risk-scored with momentum, wind-aware exposure, population exposure, priority ranking, human verification, automatic
13-section PDF reports, Gmail two-step authentication and deduplicated live e-mail alerts.

> **No demo data.** The application never fabricates thermal events, weather, population, facility names, imagery or causes. When a source
> has no data the UI, API and PDF say **Unavailable** / **Insufficient evidence** / **Requires verification**.

---

## 1. Project overview

| Capability | Implementation |
|---|---|
| Detection | NASA FIRMS (VIIRS SNPP / NOAA-20 / NOAA-21, MODIS) — keyless public feed (24h–7d) or area API + 12-month archive with a free MAP_KEY |
| LIVE vs HISTORICAL | Every detection and event carries `data_status`, `observation_timestamp`, `ingestion_timestamp`, `source`; LIVE = observation newer than `LIVE_WINDOW_HOURS` at ingestion; events age into HISTORICAL automatically |
| 12-month limit | Enforced at ingestion (older rows rejected), in every query (clamped window), and by a maintenance job (purge / archive) |
| Event formation | DBSCAN over (x km, y km, scaled time) + attachment to open events; backend-generated `TSI-IND-YYYY-NNNNNN` |
| Persistence | ISOLATED / TEMPORARY / RECURRING / PERSISTENT, score 0-100 from real daily observations |
| GIS | OSM state polygons (36) + 788 districts (admin_level 5), Nominatim reverse geocoding, Overpass facilities / land use / places / roads, public reference facility list, Census-2011 settlement gazetteer |
| Weather | Open-Meteo current wind for live events, ERA5 archive wind at observation time for historical events |
| Land cover | OSM land-use / natural polygons (live), footprint / coarse zone estimate otherwise — always labelled |
| Population | Census-2011 reference values + OSM `population` tags → always **Estimated** |
| Attribution | 10 classes, probability distribution, evidence with provenance, uncertainty, insufficient-evidence guard |
| ML | LightGBM (28 features) + TreeSHAP; trains only on human-verified samples; candidate → validation → explicit ADMIN promotion |
| Risk | 11 weighted components → 0-100 / LOW…CRITICAL, momentum, "why did risk change?" from real component deltas |
| Exposure | Hazard circle + downwind wedge (never a plain buffer); named potentially-exposed areas from real datasets; estimated population |
| Satellite | NASA GIBS date-stamped true-colour references; Sentinel-2 L2A scene search (Earth Search STAC); three evidence tiers |
| Reports | ReportLab PDF `ThermoShield_Incident_<id>.pdf`, 13 sections, every value labelled OBSERVED / MODEL INFERENCE / ESTIMATE / HUMAN VERIFIED / UNAVAILABLE |
| Auth | Registration → 6-digit Gmail verification code (10-minute expiry, resend cooldown) → login → JWT access + rotating refresh tokens; roles ADMIN / ANALYST / VIEWER; Argon2id |
| Alerts | HIGH / CRITICAL e-mails **only** for events touched by newly ingested LIVE detections; `alert_logs` deduplication + cooldown; admin settings |
| Frontend | React 18 + TypeScript + Tailwind + React Router + Leaflet + Recharts + Lucide + TanStack Query; light/dark; responsive |

## 2. Architecture

```
NASA FIRMS ── OSM (Overpass/Nominatim) ── Open-Meteo ── Census-2011 ── OSM land use ── Sentinel-2 STAC ── platform archive (≤12 months)
      │
      ▼  ingestion → validation → normalisation → duplicate detection → 12-month limit → data_status (LIVE/HISTORICAL)
PostgreSQL / PostGIS (SQLAlchemy, Alembic, GIST spatial indexes)
      │
      ▼  DBSCAN event formation → persistence → GIS enrichment → weather → history → evolution → features
      ▼  LightGBM + SHAP (or rule engine) → exposure (wind wedge) → population → risk + momentum → priority → precautions → timeline
      │
      ├── LIVE alert pipeline (new LIVE detections only) → dedup (alert_logs) → SMTP → notification centre
      ├── Human verification → training_samples → controlled training → validated candidate → ADMIN promotion
      ├── matplotlib images → ReportLab PDF (13 sections)
      └── FastAPI (/docs) ──► React dashboard (map, incidents, analytics, reports, explainability, verification, coordinate analysis)
APScheduler: FIRMS poll (default 120 min) · maintenance every 6 h (age LIVE→HISTORICAL, purge >12 months, refresh live risk) · visuals every 3 h
```

## 3. Features (frontend routes)

`/login` `/register` `/verify-email` · `/dashboard` · `/map` · `/incidents` · `/incidents/{id}` (+ `/timeline` `/risk` `/exposure` `/images`) · `/high-risk` · `/analytics` · `/analytics/state/{state}` · `/affected-areas` · `/satellite` · `/reports` · `/reports/{id}` · `/explainability` · `/verification` · `/location-analysis` · `/settings`

Global search accepts incident IDs, states, districts, localities, facilities, classifications and raw coordinates (`16.5062, 80.6480` opens coordinate analysis). Clicking the India map opens "Analyze Location". The global date selector (LIVE, 24h, 3d, 7d, 30d, 3m, 6m, 12m, custom) drives the dashboard, map, event list, analytics and satellite pages.

## 4. Technology stack

Backend: Python 3.12+, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16 + PostGIS 3.4 (SQLite fallback for development/tests), scikit-learn (DBSCAN), LightGBM, SHAP, shapely, matplotlib, ReportLab, PyJWT, argon2-cffi, APScheduler, httpx.
Frontend: React 18, TypeScript, Vite, Tailwind CSS, React Router 6, react-leaflet (+ marker clustering), Recharts, Lucide, TanStack Query, Vitest + Testing Library.

## 5. Data sources

| Source | Use | Access |
|---|---|---|
| NASA FIRMS | thermal detections | keyless regional CSV feed; area API + archive with `NASA_FIRMS_MAP_KEY` |
| OpenStreetMap (ODbL) | state polygons, 788 districts, Nominatim geocoding, Overpass facilities / land use / places / roads | keyless (usage policies respected: 1 req/s Nominatim, ≥1.5 s Overpass, caching, circuit breakers) |
| Open-Meteo | current wind (forecast API) and archive wind (ERA5) | keyless |
| Census of India 2011 | settlement populations, state densities (bundled reference values) | bundled |
| Public reference list | refineries, power plants, mines, gas facilities (approximate positions) | bundled, merged with live OSM |
| Sentinel-2 L2A | optical scenes before/after (Earth Search STAC) | keyless; Copernicus credentials optional |
| NASA GIBS | date-stamped true-colour reference tiles (250 m) | keyless |

## 6. Data freshness

`data_source_status` records `source`, `source_timestamp`, `retrieved_at` per dataset; the dashboard shows FIRMS / weather / OSM / satellite freshness, and the header shows **LIVE DATA — last live observation … IST** or **LIVE FEED STALE**. Stale data is never called live.

## 7. One-year historical limit

`HISTORY_LIMIT_DAYS = 366`. The window is computed dynamically (e.g. `11 Sep 2025 → 11 Sep 2026`) and returned by `/api/system/status`, `/api/events` and `/api/analytics/*`. Older rows are rejected at ingestion and purged by maintenance; events are archived into `historical_events`.

## 8. Authentication & 9. Gmail verification

```
register (email, password, confirm) → account inactive → 6-digit code hashed (HMAC) + 10-min expiry → e-mail via SMTP
→ /verify-email (max 5 attempts, resend cooldown 60 s) → verified → /login → JWT access (60 min) + rotating refresh (7 d) → /refresh → /logout
```
Passwords: Argon2id, ≥10 characters with letters and digits. The first registered account (or `BOOTSTRAP_ADMIN_EMAILS`) becomes ADMIN. Auth endpoints are rate limited. Use a **Gmail App Password** — the user's Gmail password is never stored.

## 10. Live alerts

Trigger: event touched by **newly ingested LIVE** detections, `data_status = LIVE`, risk HIGH or CRITICAL, alerts enabled, confidence ≥ minimum, no `sent` alert for the same event/level within the cooldown (or same observation timestamp). Historical ingestion / backfill never enters the pipeline (`tests/test_alerts.py`). Subject: `[THERMO-SHIELD INDIA] LIVE CRITICAL THERMAL INCIDENT — {STATE}`. Body: incident ID, status, classification, risk, confidence, coordinates, locality/district/state, first/latest observation, FRP, wind, potentially exposed areas, estimated population, precautions, data sources, verification status, dashboard link and the live-data notice. Every decision (sent / suppressed / failed / not_configured) is written to `alert_logs`.

## 11-12. Database & PostGIS

Tables: `users, email_verifications, refresh_tokens, thermal_detections, thermal_events, event_observations, industrial_facilities, refineries, power_plants, mines, gas_facilities, roads, land_cover, population, weather_observations, event_classifications, risk_scores, affected_areas, event_images, event_reports, human_verifications, historical_events, alert_logs, alert_settings, audit_logs, model_versions, training_samples, notifications, ingestion_runs, data_source_status, admin_boundaries`.
On PostgreSQL every spatial table gets `geom geography(Point,4326)`, a GIST index (`idx_<table>_geom`) and a trigger that keeps it in sync with latitude/longitude. Migrations: `alembic upgrade head`.

## 13. Environment variables

Every variable is documented in [`.env.example`](.env.example). Secrets (NASA key, SMTP credentials, JWT secret, database password, Sentinel credentials) live only in `.env` / deployment environment and are never sent to the frontend.

## 14. FIRMS setup

Without a key the keyless regional feed (`FIRMS_PUBLIC_REGION=South_Asia`, `FIRMS_PUBLIC_WINDOW=48h`) is polled; rows outside the OSM India polygon are rejected. Get a free MAP_KEY at <https://firms.modaps.eosdis.nasa.gov/api/map_key/> and set `NASA_FIRMS_MAP_KEY` to use the area API and the archive backfill (`POST /api/firms/backfill`, Settings → System operations; ≤ 12 months, always HISTORICAL).

## 15. Weather · 16. Sentinel · 17. OSM setup

`WEATHER_PROVIDER=open-meteo` (keyless). `SATELLITE_PROVIDER=stac` uses Earth Search; `SENTINEL_CLIENT_ID/SECRET` are optional. `OSM_PROVIDER=overpass` enables Overpass + Nominatim (`NOMINATIM_ENABLED`); set `reference` for gazetteer-only offline mode. Rebuild boundaries with `python scripts/build_boundaries.py`.

## 18-19. ML training & SHAP

- Verified incidents (`POST /api/events/{id}/verify`) create `training_samples` (features, verified label, analyst id, timestamp, model version).
- `POST /api/ml/train` (ADMIN) trains a **candidate** only when ≥ `ML_MIN_TRAINING_SAMPLES` (40) samples across ≥ `ML_MIN_CLASSES` (2) classes exist; otherwise **ML model unavailable — insufficient validated training data**.
- Metrics (accuracy, precision, recall, F1, held-out validation ids) are stored in `model_versions`; `POST /api/ml/models/{version}/promote` (ADMIN) moves a validated candidate to production. Nothing is promoted automatically.
- With a production model, explanations are TreeSHAP values; without one, the incident shows documented rule weights and states clearly that they are not SHAP.

## 20. PDF generation

`POST /api/events/{id}/generate-pdf` → `reports/ThermoShield_Incident_<id>.pdf` (13 sections: cover, summary, maps, AI + explanation, evolution + momentum, wind & exposure, exposed areas, population, GIS/industrial assessment, images, probable cause, precautions & limitations, human verification). Missing images print "Image unavailable for this event".

## 21. Local development

```bash
git clone <repository>
cd thermal-expo
cp .env.example .env         # edit: JWT_SECRET, SMTP_*, optionally NASA_FIRMS_MAP_KEY, DATABASE_URL
```
Backend:
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows   |   source .venv/bin/activate  (Linux/macOS)
pip install -r requirements.txt
alembic upgrade head          # PostgreSQL; with an empty DATABASE_URL the SQLite dev file is created automatically
uvicorn app.main:app --reload --port 8200
```
Frontend:
```bash
cd frontend
npm install
npm run dev                   # http://localhost:5190 (proxies /api → :8200)
```
Database:
```bash
docker compose up -d postgres # PostGIS on localhost:5434 (DATABASE_URL in .env.example)
```
Development e-mail: set `EMAIL_DEV_LOG_ONLY=true` (and leave SMTP_* empty) to print verification codes to the backend log instead of sending.

## 22. Docker

```bash
docker compose up --build     # frontend :3001, backend :8201, PostGIS :5434
```
Secrets come from `.env` (not committed). Volumes persist PostgreSQL data, reports, data and models.

## 23. Testing

```bash
cd backend && python -m pytest -q      # 33 tests: auth/verification/JWT, FIRMS validation + India filter + 12-month limit + duplicates,
                                       # LIVE/HISTORICAL status, clustering, persistence, rules, risk, wind exposure, population, API, PDF,
                                       # alert deduplication and the critical "HISTORICAL never alerts / LIVE alerts" test
cd frontend && npm test                # 12 Vitest tests: login, registration, verification, protected routes, map legend/markers,
                                       # dynamic district filters, incident card + detail, theme toggle, report download
```
Tests use an isolated SQLite file, a capturing e-mail provider and a stub weather provider; no network calls are made. The FIRMS fixture is a real South_Asia feed extract.

## 24. Deployment

React (nginx / CDN) → FastAPI (uvicorn/gunicorn behind HTTPS) → PostgreSQL/PostGIS → background jobs (APScheduler inside the API, or run `ingest_service` jobs from a worker) → external APIs. Configure `CORS_ORIGINS`, `FRONTEND_URL`, `JWT_SECRET`, `SMTP_*`, `DATABASE_URL`, `NASA_FIRMS_MAP_KEY`, `ENVIRONMENT=production` (adds HSTS). Terminate TLS at the proxy.

## 25. Security

JWT (HS256) access + rotating single-use refresh tokens, Argon2id hashing, Pydantic validation, RBAC (`require_role`), CORS allow-list, in-memory rate limiting on auth endpoints, secure headers middleware, audit log, secrets only in environment. Every API route except `/api/health`, `/api/system/status`, `/api/auth/*` requires a verified login.

## 26. Data limitations

Satellite detections are point observations at 375 m / 1 km resolution; FRP is not fire size; positions are approximate; reference facility positions are approximate and public; population is Census 2011; wind is a model analysis / reanalysis; land cover from OSM is only as complete as the map. Missing data is shown as **Unavailable**.

## 27. AI limitations

Classifications are inferences from indirect evidence and never prove a cause. Without a validated model the rule engine is used and labelled. Confidence is a normalised score, not an accuracy guarantee. Exposure is a geometric estimate, not a dispersion simulation.

## 28. Human verification

ANALYST / ADMIN can CONFIRM, CHANGE CLASSIFICATION or MARK UNCERTAIN with notes. The record stores analyst id, timestamp, original prediction, verified prediction; the incident shows AI status and human status side by side; verified records become training samples.

## 29. No-fabrication policy

Every value shown is one of OBSERVED · CALCULATED · MODEL INFERENCE · ESTIMATE · HUMAN VERIFIED · UNAVAILABLE and the provenance is displayed in the UI, the API (`provenance` block) and the PDF legend. There is no demo dataset, no synthetic weather, no bootstrap-trained model, no placeholder numbers.

## Data limitation notice

THERMO-SHIELD INDIA uses satellite, GIS, weather and other external datasets. Satellite detections represent observed thermal anomalies and do not by themselves prove a fire, its exact cause, severity, or ground impact. AI classifications and exposure estimates are decision-support outputs and require appropriate human/field verification.

## Live data safety notice

LIVE ALERT: This notification is generated from newly ingested live data and is intended for decision support. It is not confirmation of an emergency. Verify with authorized emergency personnel and authoritative local sources before taking emergency action.

## API

Swagger UI at `/docs` (OAuth2 password flow: username = e-mail). Main routes: `/api/auth/*`, `/api/users`, `/api/events` (+ `/geojson`, `/priority`, `/analyze`, `/{id}`, `/{id}/timeline|risk|exposure|images|satellite|pdf|generate-pdf|verify|detections|verifications`), `/api/firms/latest|runs|ingest|live-ingest|backfill`, `/api/location/analyze`, `/api/analytics/dashboard|india|state/{state}`, `/api/boundaries/states|districts`, `/api/reports`, `/api/ml/model|training-dataset|train|models/{v}/promote`, `/api/search`, `/api/notifications`, `/api/alerts/logs|settings|test`, `/api/system/status|overview|verification-queue|audit|reanalyse-all|maintenance|generate-visuals`.

## License

MIT — see [LICENSE](LICENSE). Map data © OpenStreetMap contributors (ODbL); FIRMS data courtesy of NASA; Census data © Government of India.
