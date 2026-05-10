"""IBM watsonx.ai — text generation for Evac-AI action plans (hackathon / Devpost story)."""

from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

from .ibm_iam import get_iam_access_token, ibm_api_key_configured

WATSONX_URL = os.environ.get("WATSONX_URL", "https://us-south.ml.cloud.ibm.com").rstrip("/")
WATSONX_PROJECT_ID = os.environ.get("WATSONX_PROJECT_ID", "").strip()
# IBM Granite is a strong "IBM tech" default; override if your project uses another model.
WATSONX_MODEL_ID = os.environ.get(
    "WATSONX_MODEL_ID",
    "ibm/granite-3-8b-instruct",
).strip()
WATSONX_API_VERSION = os.environ.get("WATSONX_API_VERSION", "2023-05-29")

IBM_CLOUD_RESOURCES_URL = "https://cloud.ibm.com/resources"
WATSONX_SETUP_DOCS_URL = (
    "https://dataplatform.cloud.ibm.com/docs/content/wsj/getting-started/welcome-main.html?context=wx"
)


def watsonx_configured() -> bool:
    return ibm_api_key_configured() and bool(WATSONX_PROJECT_ID)


_OFFICIAL_SOURCES = [
    "https://www.cdc.gov/extreme-heat/index.html",
    "https://www.redcross.org/get-help/how-to-prepare-for-emergencies.html",
    "https://www.canada.ca/en/health-canada/services/environmental-workplace-health/heat.html",
    "https://www.weather.gov/safety/flood",
]


_PLAN_SECTION_KEYS = (
    "risk_summary",
    "what_to_do_now",
    "emergency_kit",
    "evacuation_guidance",
    "nearby_support",
    "family_message",
    "official_alert_reminder",
)

# Human-readable titles, kept here so the API and UI agree on labels.
PLAN_SECTION_TITLES: dict[str, str] = {
    "risk_summary": "Risk Summary",
    "what_to_do_now": "What To Do Now",
    "emergency_kit": "Emergency Kit",
    "evacuation_guidance": "Evacuation Guidance",
    "nearby_support": "Nearby Support",
    "family_message": "Family Message",
    "official_alert_reminder": "Official Alert Reminder",
}


def _build_prompt(
    *,
    location: str,
    lat: float,
    lon: float,
    scenario: str,
    alerts_summary: str | None,
    weather_summary: str | None,
    resources_summary: str | None,
    risk_summary: str | None,
) -> str:
    return f"""You are Evac-AI, a public-safety assistant. You are NOT a doctor. Give practical, cautious guidance.

Location: {location} (lat {lat}, lon {lon})
Scenario: {scenario}

Active alerts (if any, may be empty):
{alerts_summary or "None provided."}

Weather snapshot (if any, may be empty):
{weather_summary or "None provided."}

Nearby help / resources (if any, may be empty):
{resources_summary or "None provided."}

ML risk assessment (if any, may be empty):
{risk_summary or "None provided."}

Official sources to cite (use only these URLs in the "sources" array):
{json.dumps(_OFFICIAL_SOURCES)}

Respond with VALID JSON ONLY, no markdown, no commentary, no code fences.
Use this EXACT shape and keys:
{{
  "risk_summary": "2-3 sentence plain-language summary of the current situation and what it means for the user.",
  "what_to_do_now": ["short imperative step", "..."],
  "emergency_kit": ["concrete item or supply", "..."],
  "evacuation_guidance": ["when to evacuate, routes/considerations, what to take", "..."],
  "nearby_support": ["specific kinds of nearby help to use (shelter, clinic, hospital, food bank, community center)", "..."],
  "family_message": "A short text/message (1-3 sentences) the user can copy-paste to family members.",
  "official_alert_reminder": "1-2 sentence reminder to follow official local government / emergency services / NWS / Red Cross instructions.",
  "sources": ["url1", "url2"]
}}

Rules:
- Keep each list item short and actionable (one sentence or fragment).
- If scenario is unclear, give general preparedness steps.
- Do not invent phone numbers or URLs; only use URLs from the list above for "sources".
- The "family_message" must be a single short string, NOT a list.
- The "risk_summary" and "official_alert_reminder" must be single short strings, NOT lists.
"""


def _coerce_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        return s or None
    if isinstance(value, list):
        joined = " ".join(str(v).strip() for v in value if v)
        return joined or None
    return str(value)


def _coerce_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        out: list[str] = []
        for v in value:
            if v is None:
                continue
            s = str(v).strip()
            if s:
                out.append(s)
        return out
    if isinstance(value, str):
        # Sometimes the model returns a single newline-separated string.
        parts = [p.strip(" -•\t") for p in value.splitlines()]
        return [p for p in parts if p]
    return [str(value)]


def _collect_ibm_error_entries(payload: Any) -> list[dict[str, Any]]:
    """Normalize IBM Cloud / watsonx error JSON into a list of dicts with code/message."""
    if payload is None:
        return []
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return []
    if not isinstance(payload, dict):
        return []

    out: list[dict[str, Any]] = []
    raw_errors = payload.get("errors")
    if raw_errors is None:
        err_one = payload.get("error")
        if isinstance(err_one, list):
            raw_errors = err_one
        elif isinstance(err_one, dict):
            raw_errors = [err_one]
        elif isinstance(err_one, str):
            try:
                parsed = json.loads(err_one)
                if isinstance(parsed, list):
                    raw_errors = parsed
                elif isinstance(parsed, dict):
                    raw_errors = [parsed]
            except json.JSONDecodeError:
                raw_errors = [{"message": err_one}]
    if not isinstance(raw_errors, list):
        return out
    for item in raw_errors:
        if isinstance(item, dict):
            out.append(item)
    return out


def _watsonx_error_display(entries: list[dict[str, Any]]) -> tuple[str | None, str | None, list[str]]:
    """Return (ibm_code, short user-facing message, all codes seen)."""
    codes: list[str] = []
    messages: list[str] = []
    for e in entries:
        c = e.get("code") or e.get("errorCode") or e.get("type")
        m = e.get("message") or e.get("reason") or e.get("description")
        if c:
            codes.append(str(c))
        if m:
            messages.append(str(m))

    primary_code = codes[0] if codes else None
    code_set = {c.lower() for c in codes}
    msg_blob = " ".join(messages).lower()

    if "no_associated_service_instance" in code_set or "no_associated_service_instance_error" in code_set:
        return (
            primary_code or "no_associated_service_instance_error",
            (
                "This watsonx project ID is not tied to a Watson Machine Learning / watsonx "
                "service instance in your IBM Cloud account. Create or link a service instance, "
                "then use the project ID from that watsonx environment."
            ),
            codes,
        )
    if "no_associated_service_instance" in msg_blob:
        return (
            primary_code or "no_associated_service_instance_error",
            (
                "IBM Cloud reports that this project is not associated with a watsonx / WML service instance. "
                "Open IBM Cloud → Resources, confirm your watsonx service, and copy the project ID from that setup."
            ),
            codes,
        )

    if codes or messages:
        return (
            primary_code,
            (messages[0] if messages else None),
            codes,
        )
    return None, None, codes


def _normalize_plan(parsed: dict[str, Any] | None) -> dict[str, Any] | None:
    """Coerce model output into the structured 7-section shape.

    Tolerates older keys (immediate_steps, next_24_hours, warning_signs,
    what_to_pack_or_prepare, emergency_guidance) so legacy responses still
    render in the UI.
    """
    if not isinstance(parsed, dict):
        return None

    def first(*keys: str) -> Any:
        for k in keys:
            if k in parsed and parsed[k] not in (None, ""):
                return parsed[k]
        return None

    risk_summary = _coerce_string(
        first("risk_summary", "summary", "overview")
    )
    what_to_do_now = _coerce_list(
        first("what_to_do_now", "immediate_steps", "now")
    )
    emergency_kit = _coerce_list(
        first("emergency_kit", "what_to_pack_or_prepare", "kit", "supplies")
    )
    evacuation_guidance = _coerce_list(
        first("evacuation_guidance", "evacuation", "next_24_hours")
    )
    nearby_support = _coerce_list(
        first("nearby_support", "support", "resources_to_use")
    )
    family_message = _coerce_string(
        first("family_message", "message_to_family", "family")
    )
    official_alert_reminder = _coerce_string(
        first(
            "official_alert_reminder",
            "official_reminder",
            "follow_official",
            "emergency_guidance",
        )
    )
    sources = _coerce_list(first("sources", "citations"))
    warning_signs = _coerce_list(first("warning_signs"))  # legacy passthrough

    return {
        "risk_summary": risk_summary,
        "what_to_do_now": what_to_do_now,
        "emergency_kit": emergency_kit,
        "evacuation_guidance": evacuation_guidance,
        "nearby_support": nearby_support,
        "family_message": family_message,
        "official_alert_reminder": official_alert_reminder,
        "sources": sources,
        "warning_signs": warning_signs,
        "section_titles": PLAN_SECTION_TITLES,
    }


async def generate_action_plan(
    *,
    lat: float,
    lon: float,
    location_display: str,
    scenario: str,
    alerts_summary: str | None = None,
    weather_summary: str | None = None,
    resources_summary: str | None = None,
    risk_summary: str | None = None,
) -> dict[str, Any]:
    if not watsonx_configured():
        return {
            "source": "unavailable",
            "provider": "ibm-watsonx",
            "error": "watsonx not configured",
            "hint": "Set IBM_CLOUD_API_KEY (or WATSONX_API_KEY), WATSONX_PROJECT_ID, and optionally WATSONX_URL / WATSONX_MODEL_ID in .env",
            "section_titles": PLAN_SECTION_TITLES,
        }

    token = await get_iam_access_token()
    url = f"{WATSONX_URL}/ml/v1/text/generation"
    params = {"version": WATSONX_API_VERSION}

    prompt = _build_prompt(
        location=location_display,
        lat=lat,
        lon=lon,
        scenario=scenario,
        alerts_summary=alerts_summary,
        weather_summary=weather_summary,
        resources_summary=resources_summary,
        risk_summary=risk_summary,
    )

    body = {
        "model_id": WATSONX_MODEL_ID,
        "project_id": WATSONX_PROJECT_ID,
        "input": prompt,
        "parameters": {
            "decoding_method": "greedy",
            "max_new_tokens": 1100,
            "min_new_tokens": 80,
        },
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=120.0, trust_env=True) as client:
        r = await client.post(url, params=params, headers=headers, json=body)
        if r.status_code >= 400:
            text = r.text[:8000]
            parsed_body: Any
            try:
                parsed_body = r.json()
            except json.JSONDecodeError:
                parsed_body = None
            entries = _collect_ibm_error_entries(parsed_body if parsed_body is not None else text)
            ibm_code, user_message, all_codes = _watsonx_error_display(entries)
            hint_links = (
                f"IBM Cloud resource list: {IBM_CLOUD_RESOURCES_URL} · "
                f"watsonx setup overview: {WATSONX_SETUP_DOCS_URL}"
            )
            return {
                "source": "error",
                "provider": "ibm-watsonx",
                "status_code": r.status_code,
                "ibm_error_code": ibm_code,
                "user_message": user_message,
                "hint_links": hint_links,
                "error": text[:2000],
                "error_body": parsed_body,
                "ibm_error_codes": all_codes,
                "section_titles": PLAN_SECTION_TITLES,
            }
        data = r.json()

    # watsonx: results[0].generated_text (shape varies slightly by API version)
    text = ""
    results = data.get("results")
    if isinstance(results, list) and results:
        first = results[0]
        if isinstance(first, dict):
            text = str(first.get("generated_text") or first.get("text") or "")
    if not text:
        text = json.dumps(data)[:4000]

    parsed: dict[str, Any] | None = None
    try:
        # Model might wrap JSON in whitespace or extra text — extract first {...}
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            parsed = json.loads(m.group(0))
    except json.JSONDecodeError:
        parsed = None

    normalized = _normalize_plan(parsed)

    return {
        "source": "live",
        "provider": "ibm-watsonx",
        "model_id": WATSONX_MODEL_ID,
        "raw_text": text[:8000],
        "plan": normalized,
        "plan_raw": parsed,
        "section_titles": PLAN_SECTION_TITLES,
    }
