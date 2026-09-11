"""Sentinel-2 L2A scene search via the Earth Search STAC catalogue (keyless).
Optional Copernicus Data Space credentials (SENTINEL_CLIENT_ID/SECRET) are
accepted for future full-resolution access but are not required."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from ...config import settings
from .base import SatelliteProvider

log = logging.getLogger("thermoshield.satellite.stac")
last_success_at: datetime | None = None


class EarthSearchStacProvider(SatelliteProvider):
    name = "earth-search-stac"

    def configured(self) -> bool:
        return settings.satellite_provider == "stac"

    def search(self, lat: float, lon: float, start: datetime, end: datetime, max_cloud: float = 40.0, limit: int = 6) -> list[dict] | None:
        global last_success_at
        body = {"collections": ["sentinel-2-l2a"], "intersects": {"type": "Point", "coordinates": [lon, lat]},
                "datetime": f"{start.strftime('%Y-%m-%dT%H:%M:%SZ')}/{end.strftime('%Y-%m-%dT%H:%M:%SZ')}", "query": {"eo:cloud_cover": {"lt": max_cloud}},
                "limit": limit, "sortby": [{"field": "properties.datetime", "direction": "desc"}]}
        try:
            r = httpx.post(f"{settings.stac_url}/search", json=body, timeout=25.0, headers={"User-Agent": settings.user_agent})
            r.raise_for_status()
            scenes = []
            for f in r.json().get("features", []):
                p = f.get("properties", {})
                assets = f.get("assets", {})
                scenes.append({"id": f.get("id"), "datetime": p.get("datetime"), "cloud_cover": p.get("eo:cloud_cover"), "platform": p.get("platform"),
                               "thumbnail": (assets.get("thumbnail") or {}).get("href"), "visual": (assets.get("visual") or {}).get("href"),
                               "tile": p.get("s2:mgrs_tile") or p.get("grid:code"), "source": "Sentinel-2 L2A (Earth Search STAC, Element 84 / AWS)"})
            last_success_at = datetime.now(timezone.utc)
            return scenes
        except Exception as exc:
            log.warning("STAC search failed: %s", exc)
            return None
