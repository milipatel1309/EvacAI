from __future__ import annotations

import json
from pathlib import Path

import httpx

from .cache import cache_get_json, cache_set_json


USER_AGENT = "EvacAI/0.1 (contact: demo@example.com)"

_OFFLINE_ALERTS = None


def _offline_alerts_payload():
    global _OFFLINE_ALERTS
    if _OFFLINE_ALERTS is not None:
        return _OFFLINE_ALERTS
    path = Path(__file__).resolve().parents[1] / "demo_data" / "offline_alerts_us.json"
    try:
        _OFFLINE_ALERTS = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        _OFFLINE_ALERTS = {"alerts": [], "count": 0}
    return _OFFLINE_ALERTS


async def get_nws_alerts(lat: float, lon: float):
    """
    Live US alerts from NWS.
    Docs: https://www.weather.gov/documentation/services-web-api
    Endpoint: /alerts/active?point={lat},{lon}
    """
    cache_key = f"nws:alerts:point={lat:.4f},{lon:.4f}"
    cached = cache_get_json(cache_key, ttl_seconds=60)  # 1 min cache for "live" feel
    if cached is not None:
        return {"source": "cache", **cached}

    url = "https://api.weather.gov/alerts/active"
    params = {"point": f"{lat},{lon}"}
    headers = {"User-Agent": USER_AGENT, "Accept": "application/geo+json"}

    try:
        async with httpx.AsyncClient(timeout=20.0, headers=headers, trust_env=False) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        payload = _offline_alerts_payload()
        return {
            "source": "offline",
            **payload,
            "note": "Live NWS alerts unavailable; using demo fallback.",
            "error": str(e),
        }

    alerts = []
    for feature in data.get("features", [])[:20]:
        props = feature.get("properties") or {}
        alerts.append(
            {
                "event": props.get("event"),
                "severity": props.get("severity"),
                "urgency": props.get("urgency"),
                "certainty": props.get("certainty"),
                "headline": props.get("headline"),
                "description": props.get("description"),
                "instruction": props.get("instruction"),
                "effective": props.get("effective"),
                "expires": props.get("expires"),
                "senderName": props.get("senderName"),
                "web": props.get("web"),
            }
        )

    payload = {"alerts": alerts, "count": len(alerts), "scope": "point"}
    cache_set_json(cache_key, payload)
    return {"source": "live", **payload}


def _features_to_alerts(features: list, limit: int) -> list[dict]:
    alerts = []
    for feature in features[:limit]:
        props = feature.get("properties") or {}
        alerts.append(
            {
                "event": props.get("event"),
                "severity": props.get("severity"),
                "urgency": props.get("urgency"),
                "certainty": props.get("certainty"),
                "headline": props.get("headline"),
                "description": props.get("description"),
                "instruction": props.get("instruction"),
                "effective": props.get("effective"),
                "expires": props.get("expires"),
                "senderName": props.get("senderName"),
                "web": props.get("web"),
                "areaDesc": props.get("areaDesc"),
            }
        )
    return alerts


def _parse_next_url(link_header: str | None) -> str | None:
    if not link_header:
        return None
    # Link: <url>; rel="next", ...
    for part in link_header.split(","):
        part = part.strip()
        if 'rel="next"' in part or "rel='next'" in part:
            start = part.find("<")
            end = part.find(">")
            if start != -1 and end != -1:
                return part[start + 1 : end]
    return None


async def get_nws_alerts_state(state_code: str):
    """
    Active alerts for a US state (NWS `area` parameter, e.g. NJ, CA).
    """
    code = state_code.strip().upper()
    cache_key = f"nws:alerts:area={code}"
    cached = cache_get_json(cache_key, ttl_seconds=120)
    if cached is not None:
        return {"source": "cache", **cached}

    url = "https://api.weather.gov/alerts/active"
    params = {"area": code}
    headers = {"User-Agent": USER_AGENT, "Accept": "application/geo+json"}

    try:
        async with httpx.AsyncClient(timeout=45.0, headers=headers, trust_env=False) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        payload = _offline_alerts_payload()
        return {
            "source": "offline",
            **payload,
            "scope": "state",
            "state": code,
            "note": "Live NWS alerts unavailable; using demo fallback.",
            "error": str(e),
        }

    features = data.get("features") or []
    alerts = _features_to_alerts(features, 80)
    payload = {
        "alerts": alerts,
        "count": len(features),
        "returned": len(alerts),
        "scope": "state",
        "state": code,
    }
    cache_set_json(cache_key, payload)
    return {"source": "live", **payload}


async def get_nws_alerts_national(max_returned: int = 80, max_pages: int = 3):
    """
    Nationwide active alerts (NWS `/alerts/active` with pagination via Link: rel="next").
    Response can be large; we cap what we return for UI performance.
    """
    cache_key = f"nws:alerts:national:max={max_returned}:pages={max_pages}"
    cached = cache_get_json(cache_key, ttl_seconds=120)
    if cached is not None:
        return {"source": "cache", **cached}

    headers = {"User-Agent": USER_AGENT, "Accept": "application/geo+json"}
    all_features: list = []
    next_url: str | None = "https://api.weather.gov/alerts/active"
    pages = 0

    try:
        async with httpx.AsyncClient(timeout=60.0, headers=headers, trust_env=False) as client:
            while next_url and pages < max_pages and len(all_features) < max_returned:
                r = await client.get(next_url)
                r.raise_for_status()
                data = r.json()
                feats = data.get("features") or []
                for feat in feats:
                    all_features.append(feat)
                    if len(all_features) >= max_returned:
                        break
                pages += 1
                next_url = _parse_next_url(r.headers.get("Link")) if len(all_features) < max_returned else None
    except Exception as e:
        payload = _offline_alerts_payload()
        return {
            "source": "offline",
            **payload,
            "scope": "national",
            "note": "Live NWS national alerts unavailable; using demo fallback.",
            "error": str(e),
        }

    total_seen = len(all_features)
    alerts = _features_to_alerts(all_features, max_returned)
    payload = {
        "alerts": alerts,
        "count": total_seen,
        "returned": len(alerts),
        "scope": "national",
        "pages_fetched": pages,
    }
    cache_set_json(cache_key, payload)
    return {"source": "live", **payload}

