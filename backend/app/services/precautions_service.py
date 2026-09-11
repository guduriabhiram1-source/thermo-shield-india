"""Recommended precautions by incident type and risk level - general decision-support guidance only."""
from __future__ import annotations

from ..models import ThermalEvent

DISCLAIMER = "General decision-support guidance only. Follow authorized emergency services and professional fire-safety instructions."

BASE = {
    "INDUSTRIAL_FIRE": ["Alert appropriate emergency/fire authorities and the facility control room", "Follow facility emergency procedures", "Avoid smoke-affected areas; keep upwind where possible",
                        "Monitor wind direction continuously and update the exposure zone", "Protect nearby personnel and residents; prepare shelter-in-place advice",
                        "Keep emergency access routes and hydrants clear", "Use appropriate PPE (SCBA, heat-resistant gear) for trained responders only"],
    "PERSISTENT_INDUSTRIAL_HEAT": ["Notify the facility operator to confirm the heat source is a normal process", "Compare against the site's expected thermal signature and permitted operations",
                                   "Keep monitoring for sudden FRP increases that may indicate an upset condition", "No public action required unless escalation is confirmed"],
    "WILDFIRE": ["Avoid fire zones; do not attempt to cross the fire front", "Follow official evacuation instructions from forest / district authorities", "Monitor smoke and protect vulnerable people (children, elderly, respiratory patients)",
                 "Monitor fire spread direction relative to wind and settlements", "Keep livestock and vehicles away from downwind grassland and cropland"],
    "AGRICULTURAL_BURN": ["Verify with local agriculture / revenue officials whether burning is authorised", "Advise residents downwind to limit outdoor exposure during peak smoke",
                          "Watch for spread into adjacent fields, orchards or settlements", "Ensure burning is not close to power lines, roads or fodder storage"],
    "GAS_FLARE": ["Notify the responsible operator to confirm routine flaring", "Monitor for abnormal flare behaviour (sudden FRP jumps, smoke, multiple stacks)", "Check for escalation to nearby process units or storage",
                  "Maintain appropriate exclusion zones around the flare stack"],
    "REFINERY_ACTIVITY": ["Notify the refinery control room to confirm the observed thermal activity", "Check for concurrent flare, furnace and tank-farm signatures", "Maintain exclusion zones; keep non-essential personnel away from process areas",
                          "Monitor wind direction for potential downwind exposure of townships", "Escalate to industrial-fire precautions if intensity rises sharply"],
    "POWER_PLANT_ACTIVITY": ["Confirm with the plant operator that the signature matches normal boiler / stack operation", "Check coal-yard and ash-pond areas for spontaneous combustion if the hotspot is off the main block",
                             "Monitor for growth in spatial extent, which would be atypical for normal operation"],
    "MINING_ACTIVITY": ["Notify the mine operator and the authorised mine safety officer", "Treat persistent hotspots on coal seams as possible seam fires; restrict access to subsidence-prone ground",
                        "Monitor for smoke and toxic gases near settlements and haul roads"],
    "OTHER_THERMAL_SOURCE": ["Request local verification (police / fire station / revenue officials) of the hotspot location", "Check for waste dumps, brick kilns or landfills known to smoulder in the area",
                             "Monitor for growth or persistence before escalating"],
    "UNKNOWN": ["Treat as unverified: request field verification before any public action", "Continue satellite monitoring for recurrence", "Cross-check with the next satellite overpass and local reports"],
}
RISK_EXTRA = {
    "CRITICAL": ["Escalate to the district emergency operations centre and state disaster management authority", "Pre-position ambulances and fire tenders near the downwind settlements listed in this report",
                 "Issue public advisory for the potentially exposed areas through authorised channels"],
    "HIGH": ["Inform district administration and local fire services", "Prepare an evacuation contingency for downwind settlements", "Increase monitoring frequency (every satellite pass)"],
    "MEDIUM": ["Inform local authorities; continue enhanced monitoring", "Prepare public advisory templates in case of escalation"],
    "MODERATE": ["Continue routine monitoring; verify with facility / local officials"],
    "LOW": ["Routine monitoring only"],
}


def recommend_precautions(ev: ThermalEvent) -> dict:
    cls = ev.classification if ev.classification in BASE else "UNKNOWN"
    pop = (ev.exposure or {}).get("population", {}).get("exposed_estimate") or 0
    weather_note = "Wind data is a model analysis / reanalysis value, not a site measurement" if (ev.weather or {}).get("available") else "Weather data was unavailable for this assessment; wind-dependent guidance could not be evaluated"
    return {"classification": cls, "risk_level": ev.risk_level, "general": list(BASE[cls]), "risk_specific": list(RISK_EXTRA.get(ev.risk_level, [])),
            "population": ["Advise potentially exposed population to keep windows closed and limit outdoor activity if smoke is visible"] if pop > 5000 else [],
            "limitations": ["Classification and exposure are AI / model estimates from satellite data", weather_note,
                            "Population figures are Census 2011 reference values / OSM tags, not current headcounts", "Field verification by authorised personnel is required before operational decisions"],
            "disclaimer": DISCLAIMER}
