"""Weather / wind facade. Live events use current conditions; historical events
use the wind at the time of the last observation. Nothing is synthesised: when
the provider fails the result is `available=False` and the UI shows
'Weather data unavailable'."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..config import settings
from ..models import WeatherObservation
from ..utils.timeutil import ensure_utc
from .weather.base import WeatherProvider, unavailable
from .weather.open_meteo import OpenMeteoProvider

_providers: list[WeatherProvider] = [OpenMeteoProvider()]
_override: WeatherProvider | None = None
_cache: dict = {}
_CACHE_TTL = 1800.0


def set_provider_override(p: WeatherProvider | None) -> None:
    global _override
    _override = p
    _cache.clear()


def active_provider() -> WeatherProvider | None:
    if _override is not None:
        return _override
    for p in _providers:
        if p.configured():
            return p
    return None


def get_weather(lat: float, lon: float, when: datetime | None = None, live: bool = True) -> dict:
    p = active_provider()
    if p is None:
        return unavailable("Weather provider not configured (WEATHER_PROVIDER)", "none")
    when = ensure_utc(when)
    use_current = live or when is None or (datetime.now(timezone.utc) - when) <= timedelta(hours=settings.live_window_hours)
    key = ("cur", round(lat, 2), round(lon, 2)) if use_current else ("at", round(lat, 2), round(lon, 2), when.strftime("%Y%m%d%H"))
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < _CACHE_TTL:
        return hit[1]
    w = p.current(lat, lon) if use_current else p.at_time(lat, lon, when)
    if w.get("available"):
        _cache[key] = (time.time(), w)
    return w


def store_weather(db: Session, event_id: int | None, lat: float, lon: float, w: dict) -> WeatherObservation | None:
    if not w.get("available"):
        return None
    ts = w.get("weather_timestamp")
    try:
        wts = datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else None
    except ValueError:
        wts = None
    obs = WeatherObservation(event_id=event_id, latitude=lat, longitude=lon, weather_timestamp=wts, wind_speed_kmh=w.get("wind_speed_kmh"),
                             wind_direction_deg=w.get("wind_direction_deg"), wind_gust_kmh=w.get("wind_gust_kmh"), temperature_c=w.get("temperature_c"),
                             humidity_pct=w.get("humidity_pct"), precipitation_mm=w.get("precipitation_mm"), weather_source=w.get("weather_source", ""),
                             kind=w.get("kind", "current"), raw=w)
    db.add(obs)
    return obs
