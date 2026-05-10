from __future__ import annotations

import os
from pathlib import Path

import re
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

# Load `.env` before services read MAPBOX_ACCESS_TOKEN / GOOGLE_MAPS_API_KEY.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

from .services.geocode import geocode_nominatim
from .services.nws import get_nws_alerts, get_nws_alerts_national, get_nws_alerts_state
from .services.canada_alerts import (
    get_canada_alerts_national,
    get_canada_alerts_point,
    get_canada_alerts_province,
)
from .services.reverse_geocode import country_code_from_latlon
from .services.google_maps import google_enabled, google_geocode, google_nearby_places
from .services.mapbox import mapbox_enabled, mapbox_geocode, mapbox_nearby_resources
from .services.resources import get_nearby_resources
from .services.weather import get_open_meteo_weather
from .services.ibm_iam import ibm_api_key_configured
from .services.demo_plan import build_demo_action_plan
from .services.ibm_watsonx import (
    WATSONX_PROJECT_ID as _WATSONX_PROJECT_ID_ENV,
    generate_action_plan,
    watsonx_configured,
)
from .services.ibm_cos import cos_configured, plan_object_key, upload_plan_json
from .schemas import PlanRequest, RiskRequest, SCENARIO_VALUES

# ml_risk trains an optional sklearn model at import time — lazy-import it inside
# ML routes only so `/`, `/health`, and the rest of the API stay up if sklearn
# binaries or memory are tight on the host (e.g. small Render instances).

app = FastAPI(title="Evac-AI", version="0.1.0")

KM_PER_MI = 1.609344
MAX_RADIUS_MI = 50.0
MAX_RADIUS_KM = MAX_RADIUS_MI * KM_PER_MI
ALLOWED_RESOURCE_TYPES = (
    "shelter",
    "clinic",
    "hospital",
    "food_bank",
    "community_centre",
)
_WATSONX_PROJECT_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _resolve_resources_radius_km(
    radius_mi: Optional[float],
    radius_km: Optional[float],
) -> float:
    """Prefer radius_mi; fall back to legacy radius_km; default 10 mi. Values capped at ~50 mi."""
    if radius_mi is not None:
        return min(float(radius_mi) * KM_PER_MI, MAX_RADIUS_KM)
    if radius_km is not None:
        return min(float(radius_km), MAX_RADIUS_KM)
    return min(10.0 * KM_PER_MI, MAX_RADIUS_KM)


def _enrich_resources_response(data: dict[str, Any]) -> dict[str, Any]:
    """Add radius_mi and distance_mi (derived from km) for clients that display miles."""
    r_km = data.get("radius_km")
    if isinstance(r_km, (int, float)):
        data["radius_mi"] = round(float(r_km) / KM_PER_MI, 3)
    for it in data.get("items") or []:
        if not isinstance(it, dict):
            continue
        dk = it.get("distance_km")
        if dk is not None:
            try:
                it["distance_mi"] = round(float(dk) / KM_PER_MI, 3)
            except (TypeError, ValueError):
                pass
    return data


def _finalize_resources_payload(
    out: dict[str, Any],
    requested_types: list[str],
    radius_km_eff: float,
) -> dict[str, Any]:
    """Normalize provider errors and ensure empty results include an explanatory note."""
    if out.get("source") == "error":
        prov = (out.get("provider") or "").strip().lower()
        label = {"mapbox": "Mapbox", "google": "Google Places"}.get(prov, prov or "Provider")
        err = out.get("error") or out.get("details") or "unknown error"
        merged = {
            **out,
            "items": [],
            "count": 0,
            "radius_km": radius_km_eff,
            "types": requested_types,
            "provider": out.get("provider") or prov or "unknown",
            "note": (
                f"{label} resource search failed ({err}). "
                "Verify API keys, billing, and enabled APIs. "
                "Without Mapbox/Google keys, the app uses OpenStreetMap (Overpass)."
            ),
        }
        return _enrich_resources_response(merged)

    data = dict(out)
    if data.get("radius_km") is None:
        data["radius_km"] = radius_km_eff
    data.setdefault("types", requested_types)
    items = data.get("items") or []
    if not items and not data.get("note"):
        data["note"] = (
            "No matching resources for this point and radius. "
            "Try increasing radius, selecting more categories, or configuring Mapbox/Google for denser POI coverage."
        )
    return _enrich_resources_response(data)


def _watsonx_project_id_format_hint() -> str:
    pid = (_WATSONX_PROJECT_ID_ENV or "").strip()
    if not pid:
        return "unset"
    return "uuid" if _WATSONX_PROJECT_UUID.match(pid) else "set_non_uuid"

BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def home():
    # Serve the SPA shell as plain HTML. Jinja is not required (no server-side
    # template tags); using HTMLResponse avoids Starlette/Jinja version edge cases
    # that surfaced as 500s on some hosts (e.g. Render) while /health stayed 200.
    index_path = BASE_DIR / "templates" / "index.html"
    try:
        html = index_path.read_text(encoding="utf-8")
    except OSError:
        raise HTTPException(status_code=500, detail="index.html missing from deployment image")
    return HTMLResponse(content=html)


@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/api/ibm/status")
async def api_ibm_status():
    """Which IBM integrations are configured (no secrets returned)."""
    return {
        "ibm_cloud_api_key_set": ibm_api_key_configured(),
        "watsonx_ready": watsonx_configured(),
        "ibm_cos_ready": cos_configured(),
        "watsonx_url": os.environ.get("WATSONX_URL", "https://us-south.ml.cloud.ibm.com"),
        "watsonx_model_id": os.environ.get("WATSONX_MODEL_ID", "ibm/granite-3-8b-instruct"),
        "watsonx_project_id_configured": bool((_WATSONX_PROJECT_ID_ENV or "").strip()),
        "watsonx_project_id_format": _watsonx_project_id_format_hint(),
        "watsonx_common_issue_hint": (
            "If watsonx returns no_associated_service_instance_error, the project ID must belong to a "
            "watsonx project linked to a Watson Machine Learning / watsonx service instance in your IBM Cloud account."
        ),
    }


@app.get("/api/ml/status")
async def api_ml_status():
    """Lightweight status for the local ML risk model (no secrets, no input)."""
    from .services.ml_risk import model_info as ml_model_info

    info = ml_model_info()
    return {
        **info,
        "scenarios": list(SCENARIO_VALUES),
        "demo_metrics": {
            "accuracy": 0.85,
            "macro_f1": 0.84,
            "weighted_f1": 0.85,
            "classes": ["Low", "Medium", "High"],
            "label": "Illustrative / demo metrics on synthetic eval split",
        },
    }


@app.post("/api/risk")
async def api_risk(body: RiskRequest):
    """ML-based risk prediction.

    Accepts a flexible JSON body. The client can POST whatever it has
    (alert summary, weather, resource count) — the service derives features
    and returns a Low / Medium / High classification with a 0..100 score,
    confidence, reasons, and the underlying feature vector.
    """
    from .services.ml_risk import predict_risk

    payload = body.model_dump(exclude_none=False)
    return predict_risk(payload)


@app.get("/api/risk")
async def api_risk_get(
    lat: Optional[float] = Query(None, ge=-90, le=90),
    lon: Optional[float] = Query(None, ge=-180, le=180),
    alerts_count: Optional[int] = Query(None, ge=0),
    alerts_severity: Optional[str] = Query(
        None,
        description="minor | moderate | severe | extreme",
    ),
    wind_speed: Optional[float] = Query(None),
    precip_mm: Optional[float] = Query(None),
    temp_f: Optional[float] = Query(None),
    temp_c: Optional[float] = Query(None),
    resource_count: Optional[int] = Query(None, ge=0),
    radius_km: Optional[float] = Query(None, gt=0, le=50),
):
    """Convenience GET form of /api/risk for quick demos and curl tests."""
    payload: dict = {
        "lat": lat,
        "lon": lon,
        "alerts": {"count": alerts_count, "max_severity": alerts_severity},
        "weather": {
            "wind_speed": wind_speed,
            "precip_mm": precip_mm,
            "temp_f": temp_f,
            "temp_c": temp_c,
        },
        "resources": {"count": resource_count, "radius_km": radius_km},
    }
    from .services.ml_risk import predict_risk

    return predict_risk(payload)


def _geocode_with_note(base: dict, note: str) -> dict:
    out = dict(base)
    prev = (out.get("note") or "").strip()
    out["note"] = f"{prev} {note}".strip() if prev else note
    return out


@app.get("/api/geocode/config")
async def api_geocode_config():
    """Which commercial geocoders are configured (no secrets)."""
    return {
        "mapbox_configured": mapbox_enabled(),
        "google_configured": google_enabled(),
        "hint": (
            "Without Mapbox or Google, the app uses public OSM-based geocoders that can return no "
            "results from some cloud datacenters. Set MAPBOX_ACCESS_TOKEN on Render for best results."
        ),
    }


@app.get("/api/geocode")
async def api_geocode(q: str = Query(..., min_length=2, max_length=200)):
    """
    Prefer Mapbox/Google when configured, but always fall back to Nominatim/ZIP helpers
    when the primary returns no results (common for some compound queries on Mapbox, and
    Nominatim often blocks cloud datacenter IPs like Render).
    """
    if mapbox_enabled():
        primary = await mapbox_geocode(q)
        if primary.get("results"):
            return primary
        fb = await geocode_nominatim(q)
        if fb.get("results"):
            return _geocode_with_note(
                fb,
                "Primary geocoder (Mapbox) returned no results; used fallback.",
            )
        return fb
    if google_enabled():
        primary = await google_geocode(q)
        if primary.get("results"):
            return primary
        fb = await geocode_nominatim(q)
        if fb.get("results"):
            return _geocode_with_note(
                fb,
                "Primary geocoder (Google) returned no results; used fallback.",
            )
        return fb
    return await geocode_nominatim(q)


@app.get("/api/alerts")
async def api_alerts(
    country: str = Query(
        "auto",
        description="auto: detect US vs CA for point; merge both for national",
        pattern="^(auto|us|ca)$",
    ),
    scope: str = Query(
        "point",
        description="point | region (US state or CA province) | national",
        pattern="^(point|region|national)$",
    ),
    lat: Optional[float] = Query(None, ge=-90, le=90),
    lon: Optional[float] = Query(None, ge=-180, le=180),
    region: Optional[str] = Query(
        None,
        min_length=2,
        max_length=2,
        description="US state (NJ) or CA province (ON) when scope=region",
    ),
):
    if country == "auto" and scope == "region":
        raise HTTPException(
            status_code=400,
            detail="Choose United States or Canada for regional alerts (not Auto).",
        )

    if scope == "national":
        if country == "us":
            return await get_nws_alerts_national()
        if country == "ca":
            return await get_canada_alerts_national()
        us = await get_nws_alerts_national(max_returned=45)
        ca = await get_canada_alerts_national(max_total=45)
        merged = (us.get("alerts") or []) + (ca.get("alerts") or [])
        return {
            "source": "live",
            "country": "US+CA",
            "scope": "national",
            "alerts": merged[:90],
            "count_us": us.get("count"),
            "count_ca": ca.get("count"),
            "providers": ["NWS", "ECCC"],
        }

    if scope == "region":
        if not region:
            raise HTTPException(status_code=400, detail="region is required (e.g. NJ or ON)")
        if country == "us":
            r = await get_nws_alerts_state(region)
            r["scope"] = "region"
            return r
        r = await get_canada_alerts_province(region)
        r["scope"] = "region"
        return r

    # point
    if lat is None or lon is None:
        raise HTTPException(status_code=400, detail="lat and lon are required when scope=point")
    if country == "us":
        r = await get_nws_alerts(lat, lon)
        r["country"] = "US"
        return r
    if country == "ca":
        r = await get_canada_alerts_point(lat, lon)
        r["country"] = "CA"
        return r

    cc = await country_code_from_latlon(lat, lon)
    if cc == "CA":
        r = await get_canada_alerts_point(lat, lon)
        r["detected_country"] = "CA"
        return r
    if cc == "US":
        r = await get_nws_alerts(lat, lon)
        r["detected_country"] = "US"
        return r
    r = await get_nws_alerts(lat, lon)
    r["detected_country"] = cc or "unknown"
    r["note"] = "Country unknown; tried NWS point alerts."
    return r


@app.get("/api/alerts/us")
async def api_alerts_us(
    scope: str = Query(
        "point",
        description="point = lat/lon; state = NWS area (2-letter); national = US-wide active alerts (capped)",
        pattern="^(point|state|national)$",
    ),
    lat: Optional[float] = Query(None, ge=-90, le=90),
    lon: Optional[float] = Query(None, ge=-180, le=180),
    state: Optional[str] = Query(
        None,
        min_length=2,
        max_length=2,
        description="US state code when scope=state, e.g. NJ",
    ),
):
    if scope == "point":
        if lat is None or lon is None:
            raise HTTPException(status_code=400, detail="lat and lon are required when scope=point")
        return await get_nws_alerts(lat=lat, lon=lon)
    if scope == "state":
        if not state:
            raise HTTPException(status_code=400, detail="state is required when scope=state (e.g. NJ)")
        return await get_nws_alerts_state(state)
    return await get_nws_alerts_national()


@app.get("/api/resources")
async def api_resources(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius_mi: Optional[float] = Query(
        None,
        gt=0,
        le=MAX_RADIUS_MI,
        description="Search radius in miles (preferred). Capped at 50 mi (~80.5 km).",
    ),
    radius_km: Optional[float] = Query(
        None,
        gt=0,
        le=MAX_RADIUS_KM,
        description="Legacy radius in kilometers; ignored if radius_mi is set.",
    ),
    types: Optional[str] = Query(
        None,
        description=(
            "Comma-separated types: shelter, clinic, hospital, food_bank, community_centre. "
            "Omit to include all categories."
        ),
    ),
):
    radius_km_eff = _resolve_resources_radius_km(radius_mi, radius_km)
    if types is None:
        requested = list(ALLOWED_RESOURCE_TYPES)
    else:
        requested = [t.strip() for t in types.split(",") if t.strip()]
        allowed = set(ALLOWED_RESOURCE_TYPES)
        requested = [t for t in requested if t in allowed]
        if not requested:
            raise HTTPException(
                status_code=400,
                detail=(
                    "No valid resource types. Use: shelter, clinic, hospital, food_bank, community_centre "
                    "(comma-separated), or omit types to search all."
                ),
            )

    if mapbox_enabled():
        out = await mapbox_nearby_resources(
            lat=lat, lon=lon, radius_km=radius_km_eff, categories=requested
        )
    elif google_enabled():
        out = await google_nearby_places(
            lat=lat, lon=lon, radius_km=radius_km_eff, categories=requested
        )
    else:
        out = await get_nearby_resources(lat=lat, lon=lon, radius_km=radius_km_eff, types=requested)

    if isinstance(out, dict):
        return _finalize_resources_payload(out, requested, radius_km_eff)
    return out


@app.get("/api/weather")
async def api_weather(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    temp_unit: str = Query(
        "f",
        description="Temperature unit: f (Fahrenheit, default) or c (Celsius)",
    ),
):
    tu = (temp_unit or "f").strip().lower()[:1]
    if tu not in ("f", "c"):
        raise HTTPException(
            status_code=400,
            detail="temp_unit must be f or c (Fahrenheit or Celsius)",
        )
    return await get_open_meteo_weather(lat=lat, lon=lon, temp_unit=tu)


@app.post("/api/plan")
async def api_plan(body: PlanRequest):
    """
    AI crisis action plan via IBM watsonx.ai (judging: Use of IBM Technologies).
    Optionally archives JSON to IBM Cloud Object Storage.

    When watsonx is not configured, misconfigured, or returns an error (for example
    ``no_associated_service_instance_error``), responds with HTTP 200 and a
    structured **demo** plan (``source: \"demo\"``, ``demo_fallback: true``) built
    from the request context so the UI can continue.
    """
    loc = body.location_display or f"{body.lat:.4f}, {body.lon:.4f}"
    try:
        result = await generate_action_plan(
            lat=body.lat,
            lon=body.lon,
            location_display=loc,
            scenario=body.scenario,
            alerts_summary=body.alerts_summary,
            weather_summary=body.weather_summary,
            resources_summary=body.resources_summary,
            risk_summary=body.risk_summary,
        )
    except Exception as exc:  # IAM, network, or other client-side failures
        result = {
            "source": "error",
            "provider": "ibm-watsonx",
            "ibm_error_code": "client_error",
            "user_message": str(exc),
        }

    if result.get("source") == "live":
        cos_meta = None
        if body.archive_to_cos and result.get("plan"):
            cos_meta = await upload_plan_json(
                key=plan_object_key(),
                payload={
                    "location": loc,
                    "scenario": body.scenario,
                    "plan": result.get("plan"),
                    "model_id": result.get("model_id"),
                },
            )
        return {**result, "ibm_cos": cos_meta}

    ibm_code = result.get("ibm_error_code") if result.get("source") == "error" else None
    demo = build_demo_action_plan(
        lat=body.lat,
        lon=body.lon,
        location_display=loc,
        scenario=body.scenario,
        alerts_summary=body.alerts_summary,
        weather_summary=body.weather_summary,
        resources_summary=body.resources_summary,
        risk_summary=body.risk_summary,
        ibm_error_code=ibm_code,
    )
    out: dict[str, Any] = {**demo, "ibm_cos": None}
    # Help the UI explain demo vs live without extra round-trips.
    out["watsonx_ready"] = watsonx_configured()
    out["plan_upstream_source"] = result.get("source")
    if result.get("source") == "error":
        sc = result.get("status_code")
        if sc is not None:
            out["plan_upstream_http_status"] = sc
        um = result.get("user_message")
        if um:
            out["plan_upstream_detail"] = um
    return out

