"""Structured demo action plan when IBM watsonx is unavailable or errors.

Keeps the same JSON shape as live watsonx output so clients render consistently.
"""

from __future__ import annotations

from typing import Any, Optional

from .ibm_watsonx import PLAN_SECTION_TITLES

_OFFICIAL_SOURCES = [
    "https://www.cdc.gov/extreme-heat/index.html",
    "https://www.redcross.org/get-help/how-to-prepare-for-emergencies.html",
    "https://www.canada.ca/en/health-canada/services/environmental-workplace-health/heat.html",
    "https://www.weather.gov/safety/flood",
]

_SCENARIO_LABEL = {
    "general": "general emergency preparedness",
    "heatwave": "extreme heat",
    "flood": "flooding",
    "wildfire_smoke": "wildfire smoke and poor air quality",
    "power_outage": "power outages",
    "winter_storm": "winter storms and extreme cold",
    "hurricane": "hurricanes and tropical systems",
}


def _clip(s: str, max_len: int) -> str:
    t = s.strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 1].rstrip() + "…"


def _scenario_content(scenario: str) -> dict[str, list[str]]:
    s = (scenario or "general").strip().lower()
    if s == "heatwave":
        return {
            "now": [
                "Slow down activity; seek shade, fans, or air conditioning when possible.",
                "Drink water regularly; avoid alcohol and heavy exertion during peak heat.",
                "Check on infants, older adults, neighbors, and anyone without reliable cooling.",
            ],
            "kit": [
                "Extra drinking water (about 1 gallon per person per day)",
                "Electrolyte drinks or oral rehydration supplies",
                "Battery-powered fan, cooling towels, sun protection",
                "A 7-day supply of prescription medications if possible",
            ],
            "evac": [
                "Evacuate if local officials order it or if indoor heat becomes unsafe and you have a safer place.",
                "Take ID, medications, chargers, cash cards, and pet supplies; avoid flooded or washed-out roads.",
            ],
            "support": [
                "Cooling centers, urgent care or ER for heat illness, shelters if you lose housing cooling.",
            ],
        }
    if s == "flood":
        return {
            "now": [
                "Move to higher ground; avoid walking or driving through flood water.",
                "Monitor official alerts and local emergency instructions.",
                "Turn around if you encounter water over a road (\"Turn Around Don't Drown\").",
            ],
            "kit": [
                "Waterproof bags for documents and phones",
                "Drinking water and non-perishable food",
                "Flashlight, whistle, first aid kit, and spare clothes",
                "Rubber boots and gloves if you must move through shallow water",
            ],
            "evac": [
                "Leave early if advised; take essentials and pets if safe to do so.",
                "Know multiple routes; bridges and low crossings are often first to fail.",
            ],
            "support": [
                "Shelters, local emergency management, and hospitals for injuries or illness.",
            ],
        }
    if s == "wildfire_smoke":
        return {
            "now": [
                "Stay indoors with windows closed when smoke is heavy; use clean air spaces if available.",
                "Run a HEPA air cleaner if you have one; avoid vacuuming (stirs particles).",
                "Limit outdoor exercise; watch for breathing difficulty or chest tightness.",
            ],
            "kit": [
                "N95 or KN95 masks rated for fine particles (if available and fit well)",
                "Spare medications for asthma or heart/lung conditions",
                "Goggles and saline rinse supplies for eye/nose irritation",
            ],
            "evac": [
                "Evacuate immediately if ordered; wildfires move quickly.",
                "Pack go-bags, documents, and pet carriers; follow designated evacuation routes.",
            ],
            "support": [
                "Medical care for smoke-related symptoms, community centers for clean air, shelters if displaced.",
            ],
        }
    if s == "power_outage":
        return {
            "now": [
                "Unplug sensitive electronics to avoid surges when power returns.",
                "Keep refrigerator/freezer closed; use flashlights instead of candles when possible.",
                "Check on anyone using medical devices that need electricity; have a backup plan.",
            ],
            "kit": [
                "Battery or hand-crank radio, flashlights, spare batteries",
                "Non-perishable food and manual can opener",
                "Blankets, warm layers, and charged power banks",
                "Cash in small bills (card readers may be down)",
            ],
            "evac": [
                "Leave if home becomes unsafe (temperature, medical need, or structural risk).",
                "Take medications, water, and chargers; know nearby warming/cooling locations.",
            ],
            "support": [
                "Hospitals and clinics for medical emergencies, shelters, food banks if outages are prolonged.",
            ],
        }
    if s == "winter_storm":
        return {
            "now": [
                "Limit travel; if you must drive, keep an emergency kit in the vehicle.",
                "Stay dry; watch for frostbite and hypothermia signs.",
                "Prevent carbon monoxide risk: never run generators or grills indoors or in garages.",
            ],
            "kit": [
                "Warm layers, gloves, hats, blankets, and hand warmers",
                "Shovel, sand or cat litter for traction, ice scraper",
                "High-energy food and water; backup heat plan that is ventilated safely",
            ],
            "evac": [
                "Evacuate only when safe routes exist; inform someone of your plan.",
                "Take medications, documents, and a phone charger; expect delays.",
            ],
            "support": [
                "Warming shelters, roadside assistance, hospitals for cold injuries.",
            ],
        }
    if s == "hurricane":
        return {
            "now": [
                "Follow evacuation orders early; fuel vehicles and charge devices before winds rise.",
                "Secure outdoor items; move valuables to higher levels if flooding is possible.",
                "Stay off roads during high winds and storm surge.",
            ],
            "kit": [
                "Water, non-perishable food, and a manual can opener",
                "Waterproof document pouch, cash, batteries, first aid kit",
                "Whistle, tarps, and basic tools for temporary repairs after the storm",
            ],
            "evac": [
                "Use official evacuation routes; do not drive through flood water.",
                "Plan for pets; confirm shelter rules if you must leave home.",
            ],
            "support": [
                "Emergency shelters, Red Cross / local aid, hospitals for injuries.",
            ],
        }
    # general
    return {
        "now": [
            "Stay informed through official local alerts and trusted local media.",
            "Confirm a household communication plan and a meeting place if separated.",
            "Charge phones; conserve battery if outages are possible.",
        ],
        "kit": [
            "Water and non-perishable food for several days",
            "First aid kit, flashlight, batteries, whistle",
            "Copies of important documents in a waterproof bag",
            "Cash, chargers, and any daily medications",
        ],
        "evac": [
            "Leave if authorities tell you to, or if staying becomes unsafe.",
            "Take go-bags, medications, ID, and pet supplies; use mapped routes away from hazards.",
        ],
        "support": [
            "Local shelters, hospitals, food banks, and community centers.",
        ],
    }


def _build_risk_summary(
    *,
    location_display: str,
    scenario: str,
    lat: float,
    lon: float,
    alerts_summary: Optional[str],
    weather_summary: Optional[str],
    resources_summary: Optional[str],
    risk_summary: Optional[str],
) -> str:
    label = _SCENARIO_LABEL.get((scenario or "general").strip().lower(), _SCENARIO_LABEL["general"])
    lines: list[str] = [
        f"You are planning for {label} near {location_display} (coordinates {lat:.4f}, {lon:.4f}). "
        "This demo plan summarizes practical steps using the context you provided; it is not a substitute for official instructions."
    ]
    if alerts_summary and alerts_summary.strip():
        lines.append(f"Alert context: {_clip(alerts_summary, 420)}")
    if weather_summary and weather_summary.strip():
        lines.append(f"Weather context: {_clip(weather_summary, 280)}")
    if risk_summary and risk_summary.strip():
        lines.append(f"Risk model context: {_clip(risk_summary, 280)}")
    if resources_summary and resources_summary.strip():
        lines.append(f"Nearby resources context: {_clip(resources_summary, 240)}")
    return " ".join(lines)


def _nearby_support(resources_summary: Optional[str], template_support: list[str]) -> list[str]:
    out: list[str] = []
    if resources_summary and resources_summary.strip():
        out.append(
            "Use the facilities you found in Step 4 (shelters, clinics, hospitals, food banks, community centers) "
            f"— summary: {_clip(resources_summary.replace(chr(10), ' '), 320)}"
        )
    out.extend(template_support)
    return out


def build_demo_action_plan(
    *,
    lat: float,
    lon: float,
    location_display: str,
    scenario: str,
    alerts_summary: Optional[str] = None,
    weather_summary: Optional[str] = None,
    resources_summary: Optional[str] = None,
    risk_summary: Optional[str] = None,
    ibm_error_code: Optional[str] = None,
) -> dict[str, Any]:
    """Full `/api/plan`-style payload with ``source: \"demo\"`` and structured ``plan``."""
    tmpl = _scenario_content(scenario)
    risk_block = _build_risk_summary(
        location_display=location_display,
        scenario=scenario,
        lat=lat,
        lon=lon,
        alerts_summary=alerts_summary,
        weather_summary=weather_summary,
        resources_summary=resources_summary,
        risk_summary=risk_summary,
    )
    family = (
        f"I'm safe and tracking { _SCENARIO_LABEL.get((scenario or 'general').strip().lower(), 'the situation') } "
        f"near {location_display}. I'm following official alerts and have a basic kit ready. "
        "How are you doing, and what's your plan if communications drop?"
    )
    official = (
        "Follow instructions from local emergency management, 911 for emergencies, and your national "
        "weather and health agencies (for example NWS in the U.S. or ECCC in Canada). "
        "This app supplements—not replaces—official guidance."
    )
    plan: dict[str, Any] = {
        "risk_summary": risk_block,
        "what_to_do_now": list(tmpl["now"]),
        "emergency_kit": list(tmpl["kit"]),
        "evacuation_guidance": list(tmpl["evac"]),
        "nearby_support": _nearby_support(resources_summary, tmpl["support"]),
        "family_message": family,
        "official_alert_reminder": official,
        "sources": list(_OFFICIAL_SOURCES),
        "warning_signs": [],
        "section_titles": dict(PLAN_SECTION_TITLES),
    }
    payload: dict[str, Any] = {
        "source": "demo",
        "demo_fallback": True,
        "provider": "demo-templates",
        "plan": plan,
        "section_titles": PLAN_SECTION_TITLES,
    }
    if ibm_error_code:
        payload["ibm_error_code"] = ibm_error_code
    return payload
