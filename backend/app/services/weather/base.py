"""Weather provider adapter interface. Every result is either a real observation
/ model analysis (available=True) or an explicit `available=False`."""
from __future__ import annotations

from datetime import datetime


def unavailable(reason: str, provider: str = "none") -> dict:
    return {"available": False, "weather_source": provider, "reason": reason, "wind_speed_kmh": None, "wind_direction_deg": None,
            "wind_direction_compass": None, "wind_gust_kmh": None, "temperature_c": None, "humidity_pct": None, "precipitation_mm": None,
            "weather_timestamp": None, "retrieved_at": None, "kind": "unavailable"}


class WeatherProvider:
    name = "base"

    def configured(self) -> bool:  # pragma: no cover
        return False

    def current(self, lat: float, lon: float) -> dict:  # pragma: no cover
        raise NotImplementedError

    def at_time(self, lat: float, lon: float, when: datetime) -> dict:  # pragma: no cover
        raise NotImplementedError
