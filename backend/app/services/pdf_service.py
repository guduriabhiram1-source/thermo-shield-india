"""Automatic incident PDF (ReportLab) — 13 sections, one per page, every value
labelled OBSERVED / MODEL INFERENCE / ESTIMATE / HUMAN VERIFIED / UNAVAILABLE."""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import REPORTS_DIR
from ..ml.features import CLASS_LABELS
from ..models import EventImage, EventReport, HumanVerification, RiskScore, ThermalEvent
from ..utils.timeutil import ensure_utc, fmt_ist, fmt_utc
from .image_service import generate_event_images

log = logging.getLogger("thermoshield.pdf")

PRIMARY = colors.HexColor("#b91c1c")
DARK = colors.HexColor("#0f172a")
MUTED = colors.HexColor("#475569")
LIGHT = colors.HexColor("#f1f5f9")
FOOTER = "Automated AI/GIS assessment. This report is decision-support information and should be verified by authorized personnel."
_styles = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=_styles["Title"], fontSize=20, textColor=PRIMARY, spaceAfter=4, alignment=TA_CENTER)
H2 = ParagraphStyle("H2", parent=_styles["Heading2"], fontSize=13, textColor=DARK, spaceBefore=6, spaceAfter=6)
H3 = ParagraphStyle("H3", parent=_styles["Heading3"], fontSize=10.5, textColor=PRIMARY, spaceBefore=6, spaceAfter=3)
BODY = ParagraphStyle("Body", parent=_styles["BodyText"], fontSize=9, leading=12)
SMALL = ParagraphStyle("Small", parent=BODY, fontSize=7.5, leading=9.5, textColor=MUTED)
TAG = ParagraphStyle("Tag", parent=BODY, fontSize=8, textColor=colors.white, backColor=PRIMARY, alignment=TA_CENTER)
_ENTITY_RE = re.compile(r"&(?!(amp|lt|gt|nbsp|quot|#\d+);)")
_TAG_RE = re.compile(r"<(?!/?(b|i|u|font|br|super|sub)\b)")
UNAVAILABLE = "Unavailable"


def _safe(text) -> str:
    s = str(text)
    return _TAG_RE.sub("&lt;", _ENTITY_RE.sub("&amp;", s))


def _p(text, style=BODY):
    return Paragraph(_safe(text), style)


def _v(value, fmt="{}", suffix=""):
    return UNAVAILABLE if value is None else fmt.format(value) + suffix


def _table(rows, col_widths=None, header=True, font=8):
    cell_style = ParagraphStyle("c", parent=BODY, fontSize=font, leading=font + 2.5)
    head_style = ParagraphStyle("h", parent=BODY, fontSize=font, leading=font + 2.5, textColor=colors.white)
    data = []
    for ri, r in enumerate(rows):
        if header and ri == 0:
            data.append([Paragraph(f"<b>{_safe(c)}</b>", head_style) for c in r])
        else:
            data.append([c if isinstance(c, Paragraph) else _p(c, cell_style) for c in r])
    t = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)
    style = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
             ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), DARK)]
    t.setStyle(TableStyle(style))
    return t


def _kv(pairs, col_widths=(55 * mm, 115 * mm)):
    return _table([["Field", "Value"]] + [[k, v] for k, v in pairs], col_widths)


def _img(images: dict, key: str, width=170 * mm, max_h=120 * mm):
    img = images.get(key)
    path = img.file_path if img else None
    if path and os.path.exists(path):
        im = Image(path)
        ratio = im.imageHeight / float(im.imageWidth)
        w, h = width, width * ratio
        if h > max_h:
            h, w = max_h, max_h / ratio
        im.drawWidth, im.drawHeight = w, h
        return im
    return _p("Image unavailable for this event", SMALL)


def _legend():
    return _p("<b>Data origin legend:</b> [OBSERVED] satellite / sensor / map data · [MODEL INFERENCE] AI / rule inference · [ESTIMATE] calculated approximation · [HUMAN VERIFIED] analyst information · [UNAVAILABLE] no data from any source", SMALL)


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(15 * mm, 10 * mm, FOOTER)
    canvas.drawRightString(A4[0] - 15 * mm, 10 * mm, f"Page {doc.page}")
    canvas.setFillColor(PRIMARY)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(15 * mm, A4[1] - 12 * mm, "THERMO-SHIELD INDIA — THERMAL INCIDENT REPORT")
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7)
    canvas.drawRightString(A4[0] - 15 * mm, A4[1] - 12 * mm, doc.incident_label)
    canvas.restoreState()


def build_pdf(db: Session, ev: ThermalEvent, generated_by: str = "system") -> EventReport:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    generate_event_images(db, ev)
    images = {i.image_type: i for i in db.execute(select(EventImage).where(EventImage.event_id == ev.id)).scalars().all()}
    risks = list(db.execute(select(RiskScore).where(RiskScore.event_id == ev.id).order_by(RiskScore.computed_at)).scalars().all())
    vers = list(db.execute(select(HumanVerification).where(HumanVerification.event_id == ev.id).order_by(HumanVerification.created_at)).scalars().all())
    file_name = f"ThermoShield_Incident_{ev.incident_id}.pdf"
    path = REPORTS_DIR / file_name
    report = EventReport(event_id=ev.id, incident_id=ev.incident_id, file_name=file_name, file_path=str(path), status="generating", generated_by=generated_by)
    db.add(report)
    db.flush()
    try:
        doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=18 * mm, bottomMargin=16 * mm, title=f"Thermo-Shield India incident report {ev.incident_id}", author="Thermo-Shield India")
        doc.incident_label = f"{ev.incident_id} · {ev.data_status} DATA"
        doc.build(_story(ev, images, risks, vers), onFirstPage=_footer, onLaterPages=_footer)
        report.status = "generated"
        report.file_size = path.stat().st_size
        report.pages = 13
        report.snapshot = {"classification": ev.classification, "risk_score": ev.risk_score, "risk_level": ev.risk_level, "human_status": ev.human_status, "data_status": ev.data_status, "generated_at": datetime.now(timezone.utc).isoformat()}
        for old in db.execute(select(EventReport).where(EventReport.event_id == ev.id, EventReport.id != report.id, EventReport.status == "generated")).scalars().all():
            old.status = "stale"
    except Exception as exc:
        log.exception("PDF generation failed for %s", ev.incident_id)
        report.status = "failed"
        report.error = str(exc)
    db.flush()
    return report


def _story(ev: ThermalEvent, images: dict, risks: list[RiskScore], vers: list[HumanVerification]) -> list:
    s: list = []
    exp = ev.explanation or {}
    expo = ev.exposure or {}
    wind = expo.get("wind", {})
    gis = ev.gis_context or {}
    weather = ev.weather or {}
    label = CLASS_LABELS.get(ev.classification, ev.classification)
    generated = fmt_utc(datetime.now(timezone.utc))
    method = "LightGBM + SHAP" if exp.get("shap_available") else "rule-based attribution (no validated ML model)"

    # 1 cover
    s += [Spacer(1, 18 * mm), _p("THERMO-SHIELD INDIA", H1), _p("THERMAL INCIDENT REPORT", ParagraphStyle("sub", parent=H2, alignment=TA_CENTER, fontSize=15)),
          _p("AI-Powered Thermal Fire &amp; Industrial Heat Intelligence Platform", ParagraphStyle("sub2", parent=SMALL, alignment=TA_CENTER, fontSize=9)), Spacer(1, 6 * mm),
          Paragraph(f"<b>{ev.data_status} DATA</b>", TAG), Spacer(1, 4 * mm)]
    s.append(_kv([
        ("Incident ID", ev.incident_id), ("Report generated", generated), ("Data status", ev.data_status),
        ("Location [OBSERVED]", f"{ev.locality or UNAVAILABLE}, {ev.district or UNAVAILABLE}, {ev.state or UNAVAILABLE}"), ("Coordinates", f"{ev.latitude:.5f}, {ev.longitude:.5f}"),
        ("First observed thermal activity [OBSERVED]", fmt_ist(ev.first_detected_at)), ("Latest observation [OBSERVED]", fmt_ist(ev.last_detected_at)),
        ("Classification [MODEL INFERENCE]", f"{label} ({ev.classification_confidence * 100:.1f}% confidence; {method})"),
        ("Risk score [CALCULATED]", f"{ev.risk_score:.0f}/100 — {ev.risk_level}"), ("Risk momentum", f"{ev.risk_momentum:+.0f} ({ev.risk_trend})"),
        ("AI status", ev.ai_status), ("Human verification status", ev.human_status + (f" — {CLASS_LABELS.get(ev.verified_classification, ev.verified_classification)}" if ev.verified_classification else "")),
        ("Data sources", f"NASA FIRMS ({ev.satellites or 'VIIRS/MODIS'}); GIS: {gis.get('provider', UNAVAILABLE)}; weather: {weather.get('weather_source') or UNAVAILABLE}; population: Census 2011 reference / OSM tags"),
    ]))
    s += [Spacer(1, 6 * mm), _legend(), PageBreak()]

    # 2 summary
    pers = ev.persistence_details or {}
    s += [_p("2. Thermal Event Summary [OBSERVED]", H2), _kv([
        ("First observed thermal activity", f"{fmt_ist(ev.first_detected_at)} ({fmt_utc(ev.first_detected_at)})"), ("Last observation", f"{fmt_ist(ev.last_detected_at)}"),
        ("Duration", f"{ev.duration_hours:.1f} h ({ev.active_days} active day(s))"), ("Detections", f"{ev.detection_count} ({ev.live_detection_count} LIVE)"),
        ("Peak / mean FRP", f"{ev.max_frp:.1f} MW / {ev.mean_frp:.1f} MW"), ("Latest FRP", f"{ev.latest_frp:.1f} MW (growth ×{ev.frp_growth_rate:.2f})"),
        ("Peak brightness temperature", f"{ev.max_brightness:.1f} K"), ("Mean detection confidence", f"{ev.mean_confidence * 100:.0f}%"), ("Night-time detections", f"{ev.night_ratio * 100:.0f}%"),
        ("Satellite / instrument", f"{ev.satellites or UNAVAILABLE} / {ev.instruments or UNAVAILABLE}"), ("Spatial spread", f"{ev.spatial_spread_km:.2f} km"),
        ("Persistence [CALCULATED]", f"{ev.persistence_score:.0f}/100 — {ev.persistence_class}"), ("Persistence summary", pers.get("summary", UNAVAILABLE)), ("Status", f"{ev.status} / {ev.data_status}"),
    ]), PageBreak()]

    # 3 map
    s += [_p("3. Map — hotspot detections, event boundary, surrounding facilities [OBSERVED]", H2), _img(images, "hotspot_map"), Spacer(1, 3 * mm), _img(images, "context_map", max_h=105 * mm), PageBreak()]

    # 4 AI classification
    probs = sorted((exp.get("probabilities") or {}).items(), key=lambda kv: -kv[1])
    s += [_p("4. AI Classification [MODEL INFERENCE]", H2),
          _p(f"<b>Classification:</b> {label} &nbsp;&nbsp; <b>Confidence:</b> {ev.classification_confidence * 100:.1f}% &nbsp;&nbsp; <b>Method:</b> {method} {exp.get('model_version', '')}"),
          _p(f"<b>Uncertainty:</b> {exp.get('uncertainty', UNAVAILABLE)}"), _p(exp.get("method_note", ""), SMALL), Spacer(1, 2 * mm),
          _table([["Class", "Probability"]] + [[CLASS_LABELS.get(c, c), f"{p * 100:.1f}%"] for c, p in probs[:6]], (90 * mm, 40 * mm)), Spacer(1, 3 * mm),
          _p("Why did the AI classify this event?", H3), _p(exp.get("summary", UNAVAILABLE)),
          _table([["Factor", "Contribution"]] + [[r["description"], f"{r['contribution']:+.3f}"] for r in exp.get("rows", [])[:8]], (120 * mm, 40 * mm)),
          _p(exp.get("method", ""), SMALL), Spacer(1, 2 * mm), _img(images, "shap_chart", max_h=80 * mm), PageBreak()]

    # 5 evolution
    evo = ev.evolution or {}
    s += [_p("5. Event Evolution [OBSERVED → CALCULATED]", H2), _p(f"<b>{evo.get('statement', '')}</b>"), _img(images, "frp_chart", max_h=85 * mm),
          _table([["Day", "Detections", "Peak FRP (MW)", "Peak brightness (K)", "Spread (km)", "Night", "Live"]] +
                 [[r["day"], r["detections"], f"{r['max_frp']:.1f}", f"{r['max_brightness']:.0f}", f"{r['spread_km']:.2f}", r["night_detections"], r.get("live_detections", 0)] for r in evo.get("series", [])[:14]]),
          Spacer(1, 3 * mm), _p("Risk momentum [CALCULATED]", H3), _p((ev.risk_change or {}).get("statement", UNAVAILABLE)), _img(images, "risk_chart", max_h=70 * mm)]
    rc = (ev.risk_change or {}).get("reasons") or []
    if rc:
        s.append(_table([["Why did risk change?", "Δ points"]] + [[r["text"], f"{r['delta_points']:+.1f}"] for r in rc], (140 * mm, 30 * mm)))
    s.append(PageBreak())

    # 6 wind & exposure
    s += [_p("6. Wind Conditions [OBSERVED] &amp; Exposure [ESTIMATE]", H2), _kv([
        ("Wind speed", _v(wind.get("speed_kmh"), "{}", " km/h")), ("Wind direction (from)", f"{wind.get('direction_from')} ({wind.get('direction_from_deg')}°)" if wind.get("available") else UNAVAILABLE),
        ("Potential downwind direction", wind.get("downwind") or UNAVAILABLE), ("Weather source / timestamp", f"{weather.get('weather_source') or UNAVAILABLE} / {weather.get('weather_timestamp') or UNAVAILABLE}"),
        ("Estimated hazard radius", _v(expo.get("hazard_radius_km"), "{}", " km")), ("Downwind exposure reach", _v(expo.get("downwind_reach_km"), "{}", " km")),
        ("Exposure level", expo.get("exposure_level", UNAVAILABLE)), ("Model", expo.get("model_note", UNAVAILABLE)),
    ]), _p("Estimated potential exposure based on available wind and geographic data.", SMALL), _img(images, "exposure_map", max_h=105 * mm), PageBreak()]

    # 7 potentially exposed areas
    areas = expo.get("affected_areas", [])
    s += [_p("7. Potentially Exposed Areas [ESTIMATE]", H2), _p("Areas are listed as <i>potentially exposed</i>. No area is confirmed as affected unless field-verified. Names come from the Census gazetteer / OpenStreetMap only."),
          _table([["#", "Area", "Type", "District", "Distance", "Direction", "Downwind", "Exposure"]] +
                 ([[i + 1, a["name"], a["area_type"], a["district"] or "—", f"{a['distance_km']} km", a["direction"], "yes" if a["downwind"] else "no", a["exposure_level"]] for i, a in enumerate(areas[:18])] if areas else [["—", "No potentially exposed area identified in the available datasets", "", "", "", "", "", ""]]),
                 (8 * mm, 55 * mm, 22 * mm, 30 * mm, 17 * mm, 15 * mm, 15 * mm, 18 * mm), font=7),
          Spacer(1, 3 * mm), _img(images, "affected_map", max_h=95 * mm), PageBreak()]

    # 8 population
    pop = expo.get("population", {})
    est = pop.get("exposed_estimate")
    s += [_p("8. Population Exposure [ESTIMATE]", H2),
          _p(f"<b>Potentially exposed population (estimate): {format(est, ',') if est is not None else UNAVAILABLE}</b> &nbsp; (downwind share ≈ {format(pop.get('downwind_estimate'), ',') if pop.get('downwind_estimate') is not None else UNAVAILABLE}; within hazard radius ≈ {format(pop.get('within_hazard_radius'), ',') if pop.get('within_hazard_radius') is not None else UNAVAILABLE})"),
          _p(pop.get("note", ""), SMALL), Spacer(1, 2 * mm),
          _table([["Settlement / area", "Type", "Estimated exposed population"]] + ([[b["name"], b["type"], f"{b['population']:,}"] for b in pop.get("by_settlement", [])[:15]] or [["—", "—", UNAVAILABLE]]), (90 * mm, 35 * mm, 45 * mm)),
          Spacer(1, 3 * mm), _p("By administrative area", H3), _table([["District", "Estimated exposed population"]] + ([[k, f"{v:,}"] for k, v in (pop.get("by_district") or {}).items()] or [["—", UNAVAILABLE]]), (90 * mm, 60 * mm))]
    if pop.get("settlements_without_population_data"):
        s.append(_p("Settlements without population data (listed, not estimated): " + ", ".join(pop["settlements_without_population_data"]), SMALL))
    s.append(PageBreak())

    # 9 industrial / GIS
    rows = [["Category", "Name", "Operator", "Distance", "Direction", "Source"]]
    for key, lab in (("refineries", "Refinery"), ("power_plants", "Power plant"), ("mines", "Mine"), ("gas_facilities", "Gas facility"), ("industrial_facilities", "Industrial / storage")):
        for f in gis.get(key, [])[:3]:
            rows.append([lab, f["name"], f.get("operator", ""), f"{f['distance_km']} km", f["direction"], f.get("source", "")])
    if len(rows) == 1:
        rows.append(["—", "No facility within the search radius in OSM / reference data", "", "", "", ""])
    lc = gis.get("land_cover", {})
    s += [_p("9. Industrial / GIS Context [OBSERVED — OSM + reference data]", H2), _table(rows, (28 * mm, 55 * mm, 35 * mm, 18 * mm, 16 * mm, 22 * mm), font=7), Spacer(1, 3 * mm),
          _kv([("Nearest road", f"{gis['nearest_road']['name']} — {gis['nearest_road']['distance_km']} km" if gis.get("nearest_road") else UNAVAILABLE),
               ("Nearest railway", f"{gis['nearest_railway']['name']} — {gis['nearest_railway']['distance_km']} km" if gis.get("nearest_railway") else UNAVAILABLE),
               ("Nearest residential area", f"{gis['nearest_residential']['name']} — {gis['nearest_residential']['distance_km']} km {gis['nearest_residential']['direction']}" if gis.get("nearest_residential") else UNAVAILABLE),
               ("Land cover", f"{lc.get('label')} [{lc.get('provenance')}]" if lc.get("available") else UNAVAILABLE),
               ("Population density", f"{ev.population_density:.0f} persons/km² [ESTIMATE — {gis.get('density', {}).get('basis', '')}]" if ev.population_density is not None else UNAVAILABLE),
               ("OSM live enrichment", gis.get("osm_live_status", UNAVAILABLE))])]
    ref = gis.get("nearest", {}).get("refineries")
    if ref and ref["distance_km"] <= 10:
        s += [Spacer(1, 3 * mm), _p("Industrial Thermal Incident Assessment — refinery proximity", H3),
              _kv([("Facility name [OBSERVED]", ref["name"]), ("Operator", ref.get("operator") or UNAVAILABLE), ("Facility coordinates", f"{ref['latitude']:.4f}, {ref['longitude']:.4f}"),
                   ("Distance from event", f"{ref['distance_km']} km {ref['direction']}"), ("Thermal activity", f"peak {ev.max_frp:.0f} MW, persistence {ev.persistence_score:.0f}/100"),
                   ("Historical recurrence (12 months)", str(int((ev.features or {}).get("historical_event_count", 0)))), ("Risk", f"{ev.risk_score:.0f}/100 {ev.risk_level}"),
                   ("Wind / downwind", f"{wind.get('direction_from')} → {wind.get('downwind')}" if wind.get("available") else UNAVAILABLE),
                   ("Potential exposure / population", f"{expo.get('exposure_level', UNAVAILABLE)}; {format(est, ',') + ' people (estimate)' if est is not None else 'population unavailable'}")])]
    s.append(PageBreak())

    # 10 images
    sat = ev.satellite or {}
    s2 = sat.get("sentinel2", {})
    s += [_p("10. Thermal / Satellite Images", H2),
          _p("<b>Thermal imagery:</b> Thermal imagery unavailable for this event — FIRMS provides point detections, not images. Generated geospatial evidence is shown instead.", BODY),
          _p(f"<b>Sentinel-2 optical evidence:</b> {s2.get('status', 'unavailable')} — {s2.get('note', '')}", BODY),
          _p(f"<b>Optical reference imagery (NASA GIBS):</b> {sat.get('optical_reference', {}).get('note', '')}", SMALL), _p(sat.get("disclaimer", ""), SMALL), Spacer(1, 3 * mm),
          _img(images, "hotspot_map", width=120 * mm, max_h=95 * mm), _img(images, "exposure_map", width=120 * mm, max_h=95 * mm), PageBreak()]

    # 11 probable cause
    cause = (ev.classifications[-1].probable_cause if ev.classifications else None) or {}
    s += [_p("11. Probable Cause / Thermal Source [MODEL INFERENCE]", H2), _p(f"<b>Probable cause:</b> {cause.get('title', ev.probable_cause or UNAVAILABLE)}"),
          _p(f"<b>Confidence:</b> {(cause.get('confidence', ev.classification_confidence) or 0) * 100:.0f}%"), _p(f"<b>Possible sources considered:</b> {', '.join(cause.get('options', []))}"), _p("Evidence", H3)]
    for e in cause.get("evidence", []):
        s.append(_p(f"• {e['text'] if isinstance(e, dict) else e} [{e.get('provenance', '') if isinstance(e, dict) else ''}]"))
    s += [Spacer(1, 2 * mm), _p(cause.get("wording", "AI inference — requires field verification."), SMALL), _p(f"<b>Verification:</b> {cause.get('verification', ev.human_status)}"), PageBreak()]

    # 12 precautions + limitations
    prec = ev.precautions or {}
    s += [_p("12. Precautions &amp; Limitations", H2), _p(f"Incident type: {label} · Risk level: {ev.risk_level}", SMALL), _p("General guidance", H3)] + [_p(f"• {x}") for x in prec.get("general", [])]
    s += [_p("Risk-level specific", H3)] + [_p(f"• {x}") for x in prec.get("risk_specific", [])]
    if prec.get("population"):
        s += [_p("Population", H3)] + [_p(f"• {x}") for x in prec["population"]]
    s += [_p("Limitations", H3)] + [_p(f"• {x}", SMALL) for x in prec.get("limitations", [])]
    s += [Spacer(1, 3 * mm), _p(prec.get("disclaimer", ""), SMALL), PageBreak()]

    # 13 verification
    s += [_p("13. Human Verification [HUMAN VERIFIED]", H2), _kv([("AI status", f"{ev.ai_status}: {label}"), ("Human status", ev.human_status),
          ("Verified classification", CLASS_LABELS.get(ev.verified_classification, ev.verified_classification) if ev.verified_classification else "— (pending)")])]
    if vers:
        s += [Spacer(1, 3 * mm), _table([["Timestamp", "Analyst", "Action", "Original", "Verified", "Notes"]] +
                                         [[fmt_utc(v.created_at), v.analyst, v.action, CLASS_LABELS.get(v.original_prediction, v.original_prediction), CLASS_LABELS.get(v.verified_classification, v.verified_classification or "—"), v.notes] for v in vers],
                                         (30 * mm, 30 * mm, 18 * mm, 28 * mm, 28 * mm, 46 * mm), font=7)]
    else:
        s.append(_p("No analyst verification recorded yet. The classification above is an unverified AI inference."))
    s += [Spacer(1, 6 * mm), _legend(), Spacer(1, 2 * mm), _p(FOOTER, SMALL)]
    return s
