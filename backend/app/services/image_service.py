"""Generates the visual evidence set for an incident with matplotlib.

All images are generated visualisations of observed detections and model
outputs. No satellite imagery is synthesised: when optical imagery is not
available an explicit "unavailable" entry is recorded instead."""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Polygon  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from ..config import REPORTS_DIR  # noqa: E402
from ..models import EventImage, RiskScore, ThermalDetection, ThermalEvent  # noqa: E402
from .reference_data import load_roads  # noqa: E402

log = logging.getLogger("thermoshield.images")
IMG_DIR = REPORTS_DIR / "images"
RISK_COLORS = {"LOW": "#22c55e", "MODERATE": "#a3e635", "MEDIUM": "#facc15", "HIGH": "#f97316", "CRITICAL": "#ef4444"}
EXPO_COLORS = {"LOW": "#22c55e", "MODERATE": "#facc15", "HIGH": "#f97316", "CRITICAL": "#ef4444"}
FACILITY_MARKERS = {"refinery": ("s", "#7c3aed"), "power_plant": ("^", "#0ea5e9"), "mine": ("D", "#a16207"), "gas_facility": ("P", "#db2777"), "industrial": ("h", "#475569"), "storage": ("v", "#0f766e")}


def _km_extent(ax, lat, lon, radius_km):
    dlat = radius_km / 111.32
    dlon = radius_km / (111.32 * max(math.cos(math.radians(lat)), 0.05))
    ax.set_xlim(lon - dlon, lon + dlon)
    ax.set_ylim(lat - dlat, lat + dlat)
    ax.set_aspect(1 / max(math.cos(math.radians(lat)), 0.05))


def _style(ax, title):
    ax.set_title(title, fontsize=11, fontweight="bold", loc="left")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.grid(True, alpha=0.25, linestyle="--")


def _save(fig, path):
    fig.tight_layout()
    fig.savefig(path, dpi=130, facecolor="white")
    plt.close(fig)


def _facilities(ax, gis: dict):
    for key in ("refineries", "power_plants", "mines", "gas_facilities", "industrial_facilities"):
        for f in gis.get(key, []):
            m, c = FACILITY_MARKERS.get(f.get("category"), ("o", "#64748b"))
            ax.scatter(f["longitude"], f["latitude"], marker=m, c=c, s=70, edgecolors="black", linewidths=0.5, zorder=4)
            ax.annotate(f["name"][:28], (f["longitude"], f["latitude"]), fontsize=6.5, xytext=(4, 4), textcoords="offset points", color="#1e293b")


def _roads(ax, lat, lon, radius_km):
    for r in load_roads():
        g = r["geometry"]
        if any(abs(p[0] - lat) < radius_km / 100 and abs(p[1] - lon) < radius_km / 100 for p in g):
            style = ":" if r["highway"] == "railway" else "-"
            ax.plot([p[1] for p in g], [p[0] for p in g], style, color="#94a3b8" if r["highway"] != "railway" else "#475569", linewidth=1.2, zorder=2)


def hotspot_map(ev: ThermalEvent, dets: list[ThermalDetection], path):
    fig, ax = plt.subplots(figsize=(7, 6))
    radius = max(4.0, ev.spatial_spread_km * 1.5 + 2)
    _km_extent(ax, ev.latitude, ev.longitude, radius)
    frps = [d.frp for d in dets]
    sc = ax.scatter([d.longitude for d in dets], [d.latitude for d in dets], c=frps, cmap="inferno", s=[30 + min(f, 300) for f in frps], edgecolors="black", linewidths=0.4, alpha=0.9, zorder=5)
    fig.colorbar(sc, ax=ax, label="FRP (MW)", shrink=0.8)
    ax.scatter([ev.longitude], [ev.latitude], marker="x", c="cyan", s=120, linewidths=2.5, zorder=6, label="Event centroid")
    if ev.bbox:
        b = ev.bbox
        ax.add_patch(Polygon([[b["min_lon"], b["min_lat"]], [b["max_lon"], b["min_lat"]], [b["max_lon"], b["max_lat"]], [b["min_lon"], b["max_lat"]]], closed=True, fill=False, edgecolor="cyan", linestyle="--", linewidth=1.2, label="Event bounding box"))
    ax.legend(loc="lower right", fontsize=7)
    _style(ax, f"{ev.incident_id} — FIRMS hotspot detections ({len(dets)} pts, {ev.satellites or 'VIIRS/MODIS'}) [{ev.data_status}]")
    fig.text(0.01, 0.005, "Generated visualisation of NASA FIRMS detections (observed data). Not an image of the fire.", fontsize=6.5, color="#64748b")
    _save(fig, path)


def context_map(ev: ThermalEvent, gis: dict, path):
    fig, ax = plt.subplots(figsize=(7, 6))
    radius = 22.0
    _km_extent(ax, ev.latitude, ev.longitude, radius)
    _roads(ax, ev.latitude, ev.longitude, radius)
    for s in gis.get("settlements", []):
        pop = s.get("population") or 0
        ax.scatter(s["longitude"], s["latitude"], marker="o", c="#16a34a", s=25 + min(pop / 20000, 220), alpha=0.6, edgecolors="black", linewidths=0.4, zorder=3)
        ax.annotate(s["name"], (s["longitude"], s["latitude"]), fontsize=7, xytext=(4, -9), textcoords="offset points", color="#14532d")
    _facilities(ax, gis)
    ax.scatter([ev.longitude], [ev.latitude], marker="*", c="#ef4444", s=260, edgecolors="black", zorder=7, label="Thermal event")
    ax.legend(loc="lower right", fontsize=7)
    lc = gis.get("land_cover", {})
    _style(ax, f"{ev.incident_id} — Surrounding GIS context (land cover: {lc.get('label') if lc.get('available') else 'unavailable'})")
    fig.text(0.01, 0.005, f"Facilities/settlements: {gis.get('provider', 'reference')}; roads: reference polylines. Positions approximate where noted.", fontsize=6.5, color="#64748b")
    _save(fig, path)


def exposure_map(ev: ThermalEvent, exposure: dict, path, labelled: bool = False):
    fig, ax = plt.subplots(figsize=(7, 6))
    reach = exposure.get("downwind_reach_km") or exposure.get("hazard_radius_km", 3) or 3
    radius = max(reach * 1.4, 8)
    _km_extent(ax, ev.latitude, ev.longitude, radius)
    circ = exposure.get("hazard_circle", [])
    if circ:
        ax.add_patch(Polygon([[p[1], p[0]] for p in circ], closed=True, facecolor="#ef4444", alpha=0.18, edgecolor="#ef4444", linewidth=1.2, label=f"Hazard radius {exposure.get('hazard_radius_km')} km (est.)"))
    sec = exposure.get("downwind_sector")
    if sec:
        ax.add_patch(Polygon([[p[1], p[0]] for p in sec], closed=True, facecolor="#f97316", alpha=0.22, edgecolor="#f97316", linewidth=1.2, label=f"Downwind exposure sector {reach} km (est.)"))
    for a in exposure.get("affected_areas", []):
        c = EXPO_COLORS.get(a["exposure_level"], "#22c55e")
        ax.scatter(a["longitude"], a["latitude"], c=c, s=60, edgecolors="black", linewidths=0.5, zorder=5)
        txt = f"{a['name']}\n{a['distance_km']} km {a['direction']} · {a['exposure_level']}" if labelled else a["name"][:20]
        ax.annotate(txt, (a["longitude"], a["latitude"]), fontsize=6, xytext=(4, 4), textcoords="offset points")
    w = exposure.get("wind", {})
    if w.get("available"):
        ang = math.radians(90 - w.get("downwind_deg", 0))
        L = radius / 111.32 * 0.35
        ax.annotate("", xy=(ev.longitude + L * math.cos(ang) / max(math.cos(math.radians(ev.latitude)), 0.05), ev.latitude + L * math.sin(ang)), xytext=(ev.longitude, ev.latitude), arrowprops=dict(arrowstyle="-|>", color="#1d4ed8", lw=2.5), zorder=8)
        ax.text(ev.longitude, ev.latitude + radius / 111.32 * 0.9, f"Wind {w.get('speed_kmh')} km/h from {w.get('direction_from')} → downwind {w.get('downwind')}", fontsize=8, ha="center", color="#1d4ed8", bbox=dict(boxstyle="round", fc="white", alpha=0.8))
    else:
        ax.text(ev.longitude, ev.latitude + radius / 111.32 * 0.9, "Weather data unavailable — hazard circle only", fontsize=8, ha="center", color="#b91c1c", bbox=dict(boxstyle="round", fc="white", alpha=0.8))
    ax.scatter([ev.longitude], [ev.latitude], marker="*", c="#ef4444", s=260, edgecolors="black", zorder=9)
    for lvl, c in EXPO_COLORS.items():
        ax.scatter([], [], c=c, s=40, label=f"{lvl} exposure")
    ax.legend(loc="lower right", fontsize=6.5)
    _style(ax, f"{ev.incident_id} — {'Potentially exposed areas' if labelled else 'Wind-aware exposure model'} (estimate)")
    fig.text(0.01, 0.005, "Directional exposure estimate (hazard circle + downwind wedge). Not a dispersion simulation.", fontsize=6.5, color="#64748b")
    _save(fig, path)


def frp_chart(ev: ThermalEvent, evo: dict, path):
    series = evo.get("series", [])
    fig, ax1 = plt.subplots(figsize=(7, 3.8))
    days = [s["day"][5:] for s in series]
    ax1.bar(days, [s["detections"] for s in series], color="#93c5fd", alpha=0.6, label="Detections / day")
    ax1.set_ylabel("Detections")
    ax2 = ax1.twinx()
    ax2.plot(days, [s["max_frp"] for s in series], "-o", color="#ef4444", label="Peak FRP (MW)")
    ax2.plot(days, [s["max_brightness"] - 273.15 for s in series], "--s", color="#f59e0b", label="Peak brightness (°C)", markersize=4)
    ax2.set_ylabel("FRP (MW) / Brightness (°C)")
    ax1.set_title(f"{ev.incident_id} — Event evolution: {evo.get('statement', '')}", fontsize=10, fontweight="bold", loc="left")
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, fontsize=7, loc="upper left")
    ax1.tick_params(axis="x", labelrotation=45, labelsize=7)
    ax1.grid(True, alpha=0.25)
    _save(fig, path)


def risk_chart(ev: ThermalEvent, risks: list[RiskScore], path):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8, 3.8), gridspec_kw={"width_ratios": [1.1, 1]})
    if risks:
        xs = [r.computed_at.strftime("%d %b %H:%M") for r in risks]
        ys = [r.score for r in risks]
        ax1.plot(xs, ys, "-o", color="#ef4444")
        for x, y in zip(xs, ys):
            ax1.annotate(f"{y:.0f}", (x, y), fontsize=7, xytext=(0, 6), textcoords="offset points", ha="center")
        for lvl, (lo, hi) in {"LOW": (0, 20), "MODERATE": (20, 40), "MEDIUM": (40, 60), "HIGH": (60, 80), "CRITICAL": (80, 100)}.items():
            ax1.axhspan(lo, hi, color=RISK_COLORS[lvl], alpha=0.08)
        ax1.set_ylim(0, 100)
        ax1.tick_params(axis="x", labelrotation=30, labelsize=7)
    ax1.set_title(f"Risk score history — momentum {ev.risk_momentum:+.0f} ({ev.risk_trend})", fontsize=9, fontweight="bold", loc="left")
    ax1.grid(True, alpha=0.25)
    comps = {k: v for k, v in (ev.risk_breakdown or {}).items() if isinstance(v, dict)}
    ax2.barh([v["label"] for v in comps.values()], [v["points"] for v in comps.values()], color="#f97316")
    ax2.set_title("Risk components (points)", fontsize=9, fontweight="bold", loc="left")
    ax2.tick_params(axis="y", labelsize=7)
    ax2.invert_yaxis()
    _save(fig, path)


def shap_chart(ev: ThermalEvent, path):
    exp = ev.explanation or {}
    rows = exp.get("rows", [])[:10]
    fig, ax = plt.subplots(figsize=(7, 4))
    if rows:
        labels = [r["description"] for r in rows][::-1]
        vals = [r["contribution"] for r in rows][::-1]
        ys = list(range(len(vals)))
        ax.barh(ys, vals, color=["#ef4444" if v > 0 else "#3b82f6" for v in vals])
        ax.set_yticks(ys)
        ax.set_yticklabels(labels)
        for i, v in enumerate(vals):
            ax.text(v, i, f" {v:+.2f}", va="center", ha="left" if v >= 0 else "right", fontsize=7)
        ax.axvline(0, color="black", linewidth=0.8)
    method = "SHAP contribution (log-odds)" if exp.get("shap_available") else "Rule weight (no validated ML model — not SHAP)"
    ax.set_xlabel(method)
    ax.set_title(f"Why did the AI classify this as {exp.get('label', ev.classification)}?", fontsize=10, fontweight="bold", loc="left")
    ax.tick_params(axis="y", labelsize=7.5)
    _save(fig, path)


IMAGE_SPECS = [
    ("hotspot_map", "Thermal event map", "NASA FIRMS hotspot visualisation (observed detections, coloured by FRP)"),
    ("context_map", "OSM / GIS context map", "Facilities, settlements and roads around the event (OSM + reference gazetteer)"),
    ("exposure_map", "Wind exposure map", "Hazard radius and downwind exposure wedge (estimate)"),
    ("affected_map", "Potentially exposed area map", "Potentially exposed areas with distance, direction and exposure level (estimate)"),
    ("frp_chart", "FRP / brightness evolution chart", "Daily peak FRP, brightness temperature and detection frequency"),
    ("risk_chart", "Risk momentum chart", "Risk score history and component breakdown"),
    ("shap_chart", "Explanation chart", "Feature contributions toward the inferred class"),
]


def generate_event_images(db: Session, ev: ThermalEvent) -> list[EventImage]:
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    dets = list(db.execute(select(ThermalDetection).where(ThermalDetection.event_id == ev.id)).scalars().all())
    risks = list(db.execute(select(RiskScore).where(RiskScore.event_id == ev.id).order_by(RiskScore.computed_at)).scalars().all())
    db.query(EventImage).filter(EventImage.event_id == ev.id).delete()
    out = []
    gen = {"hotspot_map": lambda p: hotspot_map(ev, dets, p), "context_map": lambda p: context_map(ev, ev.gis_context or {}, p), "exposure_map": lambda p: exposure_map(ev, ev.exposure or {}, p),
           "affected_map": lambda p: exposure_map(ev, ev.exposure or {}, p, labelled=True), "frp_chart": lambda p: frp_chart(ev, ev.evolution or {}, p),
           "risk_chart": lambda p: risk_chart(ev, risks, p), "shap_chart": lambda p: shap_chart(ev, p)}
    for itype, title, desc in IMAGE_SPECS:
        path = IMG_DIR / f"{ev.incident_id}_{itype}.png"
        try:
            if itype == "hotspot_map" and not dets:
                raise ValueError("no detections")
            gen[itype](path)
            img = EventImage(event_id=ev.id, image_type=itype, title=title, description=desc, file_path=str(path), url=f"/api/events/{ev.incident_id}/images/{itype}.png", source="generated", is_available=1, created_at=datetime.now(timezone.utc))
        except Exception as exc:
            log.warning("Image %s unavailable for %s: %s", itype, ev.incident_id, exc)
            img = EventImage(event_id=ev.id, image_type=itype, title=title, description=f"Unavailable: {exc}", source="generated", is_available=0)
        db.add(img)
        out.append(img)
    sat = ev.satellite or {}
    ref = sat.get("optical_reference", {})
    for key, title in (("before", "Optical reference — before (NASA GIBS)"), ("after", "Optical reference — after (NASA GIBS)")):
        item = ref.get(key)
        if item:
            db.add(EventImage(event_id=ev.id, image_type=f"optical_{key}", title=title, description=f"{item['provider']} for {item['date']} (external, loaded live; not stored)", url=item["url"], source="nasa_gibs", is_available=1, meta={"external": True, "date": item["date"]}))
    s2 = sat.get("sentinel2", {})
    for key in ("before", "after"):
        for sc in (s2.get(key) or [])[:2]:
            if sc.get("thumbnail") or sc.get("visual"):
                db.add(EventImage(event_id=ev.id, image_type=f"sentinel2_{key}", title=f"Sentinel-2 L2A scene — {key} ({sc.get('datetime', '')[:10]})", description=f"{sc.get('source')} · cloud {sc.get('cloud_cover')}% · {sc.get('id')}",
                                  url=sc.get("thumbnail") or sc.get("visual"), source="sentinel-2", is_available=1, meta={"external": True, "scene": sc}))
    if s2.get("status") in ("no_scenes", "unavailable", "not_searched"):
        db.add(EventImage(event_id=ev.id, image_type="sentinel2", title="Sentinel-2 imagery", description=s2.get("note") or "Satellite imagery unavailable for this event.", source="sentinel-2", is_available=0))
    db.add(EventImage(event_id=ev.id, image_type="thermal_imagery", title="Thermal imagery", description="Thermal imagery unavailable for this event — FIRMS provides point detections, not images; the generated hotspot map is shown instead.", source="none", is_available=0))
    db.flush()
    return out
