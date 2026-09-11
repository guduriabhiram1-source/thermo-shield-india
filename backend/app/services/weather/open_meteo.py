"""Open-Meteo adapter (keyless): current 10 m wind for live events, and the
ERA5-based archive API for the wind at the time of a historical observation."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

from ...config import settings
from ...utils.geo import compass
from .base import WeatherProvider, unavailable

log = logging.getLogger("thermoshield.weather.open_meteo")
FIELDS = "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,wind_direction_10m,wind_gusts_10m"


def _f(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


class OpenMeteoProvider(WeatherProvider):
    name = "open-meteo"

    def configured(self) -> bool:
        return settings.weather_provider == "open-meteo"

    def current(self, lat: float, lon: float) -> dict:
        try:
            r = httpx.get(settings.open_meteo_url, params={"latitude": lat, "longitude": lon, "current": FIELDS, "wind_speed_unit": "kmh", "timezone": "UTC"},
                          timeout=10.0, headers={"User-Agent": settings.user_agent})
            r.raise_for_status()
            c = r.json().get("current", {})
            d = _f(c.get("wind_direction_10m"))
            return {
                "available": True, "kind": "current", "weather_source": "open-meteo (model analysis, 10 m wind)",
                "wind_speed_kmh": _f(c.get("wind_speed_10m")), "wind_direction_deg": d, "wind_direction_compass": compass(d, 16) if d is not None else None,
                "wind_gust_kmh": _f(c.get("wind_gusts_10m")), "temperature_c": _f(c.get("temperature_2m")), "humidity_pct": _f(c.get("relative_humidity_2m")),
                "precipitation_mm": _f(c.get("precipitation")), "weather_timestamp": (c.get("time") + ":00Z") if c.get("time") and len(c.get("time")) == 16 else c.get("time"),
                "retrieved_at": datetime.now(timezone.utc).isoformat(), "note": "Open-Meteo current conditions (model analysis, not a site measurement).",
            }
        except Exception as exc:
            log.warning("Open-Meteo current request failed: %s", exc)
            return unavailable(f"Open-Meteo request failed: {exc}", self.name)

    def at_time(self, lat: float, lon: float, when: datetime) -> dict:
        """Hourly archive (ERA5 reanalysis) value nearest to `when` (UTC). Archive lags real time by ~5 days;
        for newer timestamps the forecast API's past_days window is used instead."""
        when = when if when.tzinfo else when.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - when).days
        day = when.date().isoformat()
        try:
            if age_days <= 6:
                r = httpx.get(settings.open_meteo_url, params={"latitude": lat, "longitude": lon, "hourly": FIELDS, "wind_speed_unit": "kmh", "timezone": "UTC",
                                                               "past_days": max(1, min(7, age_days + 1)), "forecast_days": 1}, timeout=12.0, headers={"User-Agent": settings.user_agent})
                src = "open-meteo forecast API (hourly, past days)"
            else:
                r = httpx.get(settings.open_meteo_archive_url, params={"latitude": lat, "longitude": lon, "hourly": FIELDS, "wind_speed_unit": "kmh", "timezone": "UTC",
                                                                       "start_date": day, "end_date": day}, timeout=15.0, headers={"User-Agent": settings.user_agent})
                src = "open-meteo archive API (ERA5 reanalysis, hourly)"
            r.raise_for_status()
            h = r.json().get("hourly", {})
            times = h.get("time", [])
            if not times:
                return unavailable("No hourly data returned for the requested time", self.name)
            target = when.replace(minute=0, second=0, microsecond=0)
            idx = min(range(len(times)), key=lambda i: abs(datetime.fromisoformat(times[i]).replace(tzinfo=timezone.utc) - target))
            d = _f(h["wind_direction_10m"][idx])
            if h["wind_speed_10m"][idx] is None:
                return unavailable("Archive value missing for the requested hour", self.name)
            return {
                "available": True, "kind": "archive", "weather_source": src,
                "wind_speed_kmh": _f(h["wind_speed_10m"][idx]), "wind_direction_deg": d, "wind_direction_compass": compass(d, 16) if d is not None else None,
                "wind_gust_kmh": _f(h.get("wind_gusts_10m", [None] * len(times))[idx]), "temperature_c": _f(h["temperature_2m"][idx]),
                "humidity_pct": _f(h["relative_humidity_2m"][idx]), "precipitation_mm": _f(h["precipitation"][idx]),
                "weather_timestamp": times[idx] + ":00Z", "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "note": "Wind at the time of the latest observation (hourly model/reanalysis value nearest to the detection time).",
            }
        except Exception as exc:
            log.warning("Open-Meteo archive request failed: %s", exc)
            return unavailable(f"Open-Meteo archive request failed: {exc}", self.name)
