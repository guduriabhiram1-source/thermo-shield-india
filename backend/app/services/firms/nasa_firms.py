"""NASA FIRMS adapters.

1. Public regional "Active Fire Data" CSV files (keyless, updated continuously)
   https://firms.modaps.eosdis.nasa.gov/active_fire/  → last 24h / 48h / 7 days.
2. Area API (MAP_KEY) https://firms.modaps.eosdis.nasa.gov/api/area/csv/{KEY}/{SOURCE}/{W,S,E,N}/{DAYS}[/{DATE}]
   → live NRT sources and, with a start date, the archive (max 10 days per request)
   used for the 12-month historical backfill.

The MAP_KEY lives in the environment only (NASA_FIRMS_MAP_KEY / NASA_FIRMS_API_KEY)."""
from __future__ import annotations

import csv
import io
import logging
import time
from datetime import date, timedelta

import httpx

from ...config import settings
from .base import FeedResult, FirmsProvider

log = logging.getLogger("thermoshield.firms.nasa")

PUBLIC_SOURCES = {
    "suomi-npp": ("suomi-npp-viirs-c2", "SUOMI_VIIRS_C2", "VIIRS"),
    "noaa-20": ("noaa-20-viirs-c2", "J1_VIIRS_C2", "VIIRS"),
    "noaa-21": ("noaa-21-viirs-c2", "J2_VIIRS_C2", "VIIRS"),
    "modis": ("modis-c6.1", "MODIS_C6_1", "MODIS"),
}
PUBLIC_BASE = "https://firms.modaps.eosdis.nasa.gov/data/active_fire"
API_BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
INSTRUMENT_OF = {"VIIRS_SNPP_NRT": "VIIRS", "VIIRS_NOAA20_NRT": "VIIRS", "VIIRS_NOAA21_NRT": "VIIRS", "MODIS_NRT": "MODIS",
                 "VIIRS_SNPP_SP": "VIIRS", "VIIRS_NOAA20_SP": "VIIRS", "VIIRS_NOAA21_SP": "VIIRS", "MODIS_SP": "MODIS"}


def parse_csv_text(text: str, source: str = "FIRMS_CSV", instrument: str | None = None) -> list[dict]:
    rows = []
    for row in csv.DictReader(io.StringIO(text)):
        row.setdefault("source", source)
        if instrument and not row.get("instrument"):
            row["instrument"] = instrument
        rows.append(row)
    return rows


def public_feed_url(source: str, region: str | None = None, window: str | None = None) -> str:
    folder, prefix, _ = PUBLIC_SOURCES[source]
    return f"{PUBLIC_BASE}/{folder}/csv/{prefix}_{region or settings.firms_public_region}_{window or settings.firms_public_window}.csv"


class PublicFeedProvider(FirmsProvider):
    name = "firms_public"

    def configured(self) -> bool:
        return True

    def fetch_latest(self, sources: list[str] | None = None, window: str | None = None) -> FeedResult:
        sources = sources or [s.strip() for s in settings.firms_public_sources.split(",") if s.strip()]
        res = FeedResult(provider=self.name, mode="live")
        for src in sources:
            if src not in PUBLIC_SOURCES:
                res.status[src] = "unknown source"
                continue
            url = public_feed_url(src, None, window)
            try:
                r = httpx.get(url, timeout=90.0, follow_redirects=True, headers={"User-Agent": settings.user_agent})
                r.raise_for_status()
                parsed = parse_csv_text(r.text, source=f"FIRMS_PUBLIC_{src.upper()}", instrument=PUBLIC_SOURCES[src][2])
                res.rows.extend(parsed)
                res.status[src] = f"ok ({len(parsed)} rows)"
            except Exception as exc:
                res.status[src] = f"failed: {exc}"
                log.warning("FIRMS public feed %s failed: %s", url, exc)
        return res

    def fetch_archive(self, start: date, end: date) -> FeedResult:
        return FeedResult(provider=self.name, mode="archive", status={"archive": "unavailable: the keyless public feed only covers the last 7 days - set NASA_FIRMS_MAP_KEY for the 12-month archive"})


class AreaApiProvider(FirmsProvider):
    name = "firms_api"

    def configured(self) -> bool:
        return bool(settings.firms_key)

    def _get(self, source: str, days: int, start: date | None = None) -> str:
        url = f"{API_BASE}/{settings.firms_key}/{source}/{settings.firms_area}/{days}"
        if start:
            url += f"/{start.isoformat()}"
        r = httpx.get(url, timeout=120.0, headers={"User-Agent": settings.user_agent})
        r.raise_for_status()
        if r.text.lstrip().lower().startswith("invalid") or "error" in r.text[:80].lower():
            raise RuntimeError(r.text[:200])
        return r.text

    def fetch_latest(self, sources: list[str] | None = None, days: int | None = None) -> FeedResult:
        sources = sources or [s.strip() for s in settings.firms_sources.split(",") if s.strip()]
        res = FeedResult(provider=self.name, mode="live")
        for src in sources:
            try:
                text = self._get(src, days or settings.firms_days)
                parsed = parse_csv_text(text, source=f"FIRMS_API_{src}", instrument=INSTRUMENT_OF.get(src))
                res.rows.extend(parsed)
                res.status[src] = f"ok ({len(parsed)} rows)"
            except Exception as exc:
                res.status[src] = f"failed: {exc}"
                log.warning("FIRMS API %s failed: %s", src, exc)
            time.sleep(1.0)  # respect transaction limits
        return res

    def fetch_archive(self, start: date, end: date, sources: list[str] | None = None) -> FeedResult:
        """Archive pull in <=10-day chunks. NRT sources cover roughly the last 2-3 months, SP (standard processing)
        sources the older part of the 12-month window; both are requested and de-duplicated at ingestion."""
        sources = sources or [s.strip() for s in settings.firms_archive_sources.split(",") if s.strip()]
        res = FeedResult(provider=self.name, mode="archive")
        cur = start
        while cur <= end:
            days = min(10, (end - cur).days + 1)
            for src in sources:
                key = f"{src} {cur.isoformat()}+{days}d"
                try:
                    text = self._get(src, days, cur)
                    parsed = parse_csv_text(text, source=f"FIRMS_ARCHIVE_{src}", instrument=INSTRUMENT_OF.get(src))
                    res.rows.extend(parsed)
                    res.status[key] = f"ok ({len(parsed)} rows)"
                except Exception as exc:
                    res.status[key] = f"failed: {exc}"
                    log.warning("FIRMS archive %s failed: %s", key, exc)
                time.sleep(1.2)
            cur += timedelta(days=days)
        return res


def active_provider() -> FirmsProvider:
    return AreaApiProvider() if settings.firms_key else PublicFeedProvider()
