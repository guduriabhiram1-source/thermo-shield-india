"""Optical satellite provider adapter interface (Sentinel-2 scene search)."""
from __future__ import annotations

from datetime import datetime


class SatelliteProvider:
    name = "base"

    def configured(self) -> bool:  # pragma: no cover
        return False

    def search(self, lat: float, lon: float, start: datetime, end: datetime, max_cloud: float = 40.0, limit: int = 6) -> list[dict] | None:  # pragma: no cover
        raise NotImplementedError
