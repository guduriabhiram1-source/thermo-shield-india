"""Optical satellite evidence for an event.

Three tiers are always distinguished:
  * thermal detection     - FIRMS hotspot (observed)
  * optical reference     - date-stamped NASA GIBS true-colour tiles (VIIRS 250 m / MODIS) around the event dates
  * Sentinel-2 scenes     - L2A scenes found via STAC before / after the event (10 m), only if the catalogue returns them
  * post-event evidence   - only when a scene after the last detection exists; burn-scar interpretation requires an analyst
Sentinel-2 is never presented as an active-fire sensor. Nothing is fabricated."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from ..config import settings
from ..utils.timeutil import ensure_utc
from .satellite.base import SatelliteProvider
from .satellite.sentinel import EarthSearchStacProvider

log = logging.getLogger("thermoshield.satellite")
GIBS_WMS = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"
_providers: list[SatelliteProvider] = [EarthSearchStacProvider()]
_override: SatelliteProvider | None = None


def set_provider_override(p: SatelliteProvider | None) -> None:
    global _override
    _override = p


def active_provider() -> SatelliteProvider | None:
    if _override is not None:
        return _override
    for p in _providers:
        if p.configured():
            return p
    return None


def gibs_true_colour_url(lat: float, lon: float, day: str, half_deg: float = 0.15, size: int = 512, layer: str = "VIIRS_SNPP_CorrectedReflectance_TrueColor") -> str:
    bbox = f"{lat - half_deg},{lon - half_deg},{lat + half_deg},{lon + half_deg}"
    return f"{GIBS_WMS}?SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS={layer}&CRS=EPSG:4326&BBOX={bbox}&WIDTH={size}&HEIGHT={size}&FORMAT=image/jpeg&TIME={day}"


def satellite_evidence(lat: float, lon: float, first_detected: datetime, last_detected: datetime, search: bool = False) -> dict:
    first = ensure_utc(first_detected)
    last = ensure_utc(last_detected)
    now = datetime.now(timezone.utc)
    before_day = (first - timedelta(days=1)).date().isoformat()
    after_day = min(last + timedelta(days=1), now).date().isoformat()
    result = {
        "thermal_detection": {"status": "observed", "note": "NASA FIRMS active-fire detection (VIIRS / MODIS thermal bands). This is the observation the incident is based on."},
        "optical_reference": {
            "status": "external_links",
            "before": {"date": before_day, "url": gibs_true_colour_url(lat, lon, before_day), "provider": "NASA GIBS VIIRS SNPP true colour (250 m)"},
            "after": {"date": after_day, "url": gibs_true_colour_url(lat, lon, after_day), "provider": "NASA GIBS VIIRS SNPP true colour (250 m)"},
            "note": "Reference true-colour imagery for the dates around the event, loaded live from NASA GIBS. 250 m resolution cannot resolve most industrial fires; use for smoke / burn-scar context only.",
        },
        "sentinel2": {"status": "not_searched", "before": [], "after": [], "note": "", "provider": None},
        "post_event_evidence": {"status": "not_available", "note": "No post-event optical scene evaluated."},
        "disclaimer": "Optical imagery cannot directly observe every active fire. Thermal detection ≠ optical confirmation ≠ post-event evidence.",
        "generated_at": now.isoformat(),
    }
    p = active_provider()
    if p is None:
        result["sentinel2"] = {"status": "unavailable", "before": [], "after": [], "provider": None, "note": "Satellite imagery unavailable for this event - no Sentinel-2 provider configured (SATELLITE_PROVIDER)."}
        return result
    if not search:
        result["sentinel2"]["note"] = "Sentinel-2 scenes not searched yet - use 'Search Sentinel-2 scenes' on the incident page."
        result["sentinel2"]["provider"] = p.name
        return result
    before = p.search(lat, lon, first - timedelta(days=30), first)
    after = p.search(lat, lon, last, now)
    if before is None and after is None:
        result["sentinel2"] = {"status": "unavailable", "before": [], "after": [], "provider": p.name, "note": "Satellite imagery unavailable for this event - STAC catalogue request failed."}
        return result
    before, after = before or [], after or []
    result["sentinel2"] = {"status": "available" if (before or after) else "no_scenes", "before": before, "after": after, "provider": p.name,
                           "searched_at": now.isoformat(),
                           "note": "Sentinel-2 L2A scenes (<40% cloud) within 30 days before first detection and after last detection." if (before or after)
                           else "Satellite imagery unavailable for this event - no cloud-free Sentinel-2 L2A scene in the catalogue for these dates."}
    if after:
        result["post_event_evidence"] = {"status": "scene_available", "scene": after[0], "note": "A post-event Sentinel-2 scene exists; burn-scar / land-change interpretation requires analyst review."}
    return result
