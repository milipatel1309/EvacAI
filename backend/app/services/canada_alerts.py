"""Environment Canada weather alerts via MSC GeoMet OGC API (weather-alerts collection)."""

from __future__ import annotations

from typing import Any, Optional

import httpx

from .cache import cache_get_json, cache_set_json

USER_AGENT = "EvacAI/0.1 (contact: demo@example.com)"

GEOMET_ITEMS = "https://api.weather.gc.ca/collections/weather-alerts/items"

# Approximate WGS84 bboxes (min_lon, min_lat, max_lon, max_lat) for filtering.
CANADA_BBOX = (-141.0, 41.65, -52.0, 83.8)

PROVINCE_BBOX: dict[str, tuple[float, float, float, float]] = {
    "ON": (-95.2, 41.7, -74.0, 57.0),
    "QC": (-79.8, 45.0, -57.0, 62.6),
    "BC": (-139.1, 48.3, -114.0, 60.0),
    "AB": (-120.0, 49.0, -110.0, 60.0),
    "MB": (-102.1, 49.0, -89.0, 60.0),
    "SK": (-110.1, 49.0, -101.4, 60.0),
    "NS": (-66.4, 43.4, -59.7, 47.0),
    "NB": (-69.1, 44.6, -63.7, 48.1),
    "PE": (-64.5, 45.9, -61.9, 47.1),
    "NL": (-67.9, 46.6, -52.5, 60.5),
    "NT": (-136.5, 59.5, -102.0, 78.8),
    "NU": (-102.0, 51.0, -61.3, 83.2),
    "YT": (-141.0, 59.7, -123.7, 69.7),
}


def _prop(props: dict, *keys: str) -> str:
    for k in keys:
        v = props.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def _next_href(links: Any) -> Optional[str]:
    if not isinstance(links, list):
        return None
    for link in links:
        if not isinstance(link, dict):
            continue
        rel = (link.get("rel") or "").lower()
        if rel == "next":
            href = link.get("href")
            if isinstance(href, str) and href.startswith("http"):
                return href
    return None


def _feature_to_alert(feat: dict[str, Any], area_hint: str) -> dict[str, Any]:
    props = feat.get("properties") or {}
    if not isinstance(props, dict):
        props = {}

    headline = _prop(props, "headline_en", "headline", "name")
    event = _prop(props, "alert_type_en", "alert_type", "event_en", "event") or headline or "Weather alert"
    desc = _prop(props, "description_en", "description", "details_en", "details")
    area = _prop(props, "area_en", "area", "zones_en", "location_en", "location") or area_hint

    effective = _prop(props, "date_effective", "effective", "date_issued", "issued")
    expires = _prop(props, "date_expiry", "expires", "expiry")
    severity = _prop(props, "severity_en", "severity") or None
    status = _prop(props, "status_en", "status") or None

    fid = feat.get("id")
    web = ""
    if isinstance(fid, str) and fid.startswith("http"):
        web = fid
    else:
        for link in feat.get("links") or []:
            if isinstance(link, dict) and (link.get("rel") or "").lower() in ("canonical", "alternate"):
                h = link.get("href")
                if isinstance(h, str) and h.startswith("http"):
                    web = h
                    break
    if not web:
        web = "https://weather.gc.ca/warnings/index_e.html"

    return {
        "event": event,
        "headline": headline or event,
        "description": desc,
        "severity": severity,
        "urgency": status,
        "certainty": None,
        "instruction": None,
        "effective": effective or None,
        "expires": expires or None,
        "senderName": "Environment Canada",
        "web": web,
        "areaDesc": area,
        "country": "CA",
        "provider": "ECCC",
    }


async def _geomet_collect(
    bbox: tuple[float, float, float, float],
    max_features: int,
    per_page: int = 80,
    max_pages: int = 4,
) -> tuple[list[dict[str, Any]], int]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/geo+json, application/json",
    }
    features: list[dict[str, Any]] = []
    total_matched = 0
    url: Optional[str] = GEOMET_ITEMS
    params: dict[str, Any] = {
        "lang": "en",
        "limit": min(per_page, max_features),
        "bbox": ",".join(str(x) for x in bbox),
    }
    pages = 0

    async with httpx.AsyncClient(timeout=60.0, headers=headers, trust_env=True) as client:
        while url and pages < max_pages and len(features) < max_features:
            if pages == 0:
                r = await client.get(url, params=params)
            else:
                r = await client.get(url)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict) and data.get("type") == "FeatureCollection":
                total_matched = int(data.get("numberMatched") or data.get("numberReturned") or 0)
                batch = data.get("features") or []
                if isinstance(batch, list):
                    for feat in batch:
                        if isinstance(feat, dict):
                            features.append(feat)
                            if len(features) >= max_features:
                                break
                nxt = _next_href(data.get("links"))
                url = nxt if len(features) < max_features else None
            else:
                break
            pages += 1

    return features, total_matched or len(features)


async def get_canada_alerts_province(province_code: str, limit: int = 40):
    code = province_code.strip().upper()
    bbox = PROVINCE_BBOX.get(code)
    if not bbox:
        return {
            "source": "error",
            "provider": "ECCC",
            "alerts": [],
            "count": 0,
            "scope": "region",
            "province": code,
            "error": f"Unknown province code: {code}",
        }

    cache_key = f"eccc:geomet:prov:{code}:{limit}"
    cached = cache_get_json(cache_key, ttl_seconds=120)
    if cached is not None:
        return {"source": "cache", **cached}

    try:
        raw_feats, nmatch = await _geomet_collect(bbox, max_features=limit)
    except Exception as e:
        return {
            "source": "error",
            "provider": "ECCC",
            "alerts": [],
            "count": 0,
            "scope": "region",
            "province": code,
            "error": str(e),
        }

    alerts = [_feature_to_alert(f, code) for f in raw_feats][:limit]
    payload = {
        "alerts": alerts,
        "count": nmatch,
        "returned": len(alerts),
        "scope": "region",
        "province": code,
        "country": "CA",
        "provider": "ECCC",
    }
    cache_set_json(cache_key, payload)
    return {"source": "live", **payload}


async def get_canada_alerts_national(max_total: int = 60):
    cache_key = f"eccc:geomet:ca:{max_total}"
    cached = cache_get_json(cache_key, ttl_seconds=180)
    if cached is not None:
        return {"source": "cache", **cached}

    try:
        raw_feats, nmatch = await _geomet_collect(CANADA_BBOX, max_features=max_total)
    except Exception as e:
        return {
            "source": "error",
            "provider": "ECCC",
            "alerts": [],
            "count": 0,
            "scope": "national",
            "country": "CA",
            "error": str(e),
        }

    alerts = [_feature_to_alert(f, "Canada") for f in raw_feats][:max_total]
    payload = {
        "alerts": alerts,
        "count": nmatch,
        "returned": len(alerts),
        "scope": "national",
        "country": "CA",
        "provider": "ECCC",
    }
    cache_set_json(cache_key, payload)
    return {"source": "live", **payload}


async def get_canada_alerts_point(lat: float, lon: float, pad_deg: float = 1.2, limit: int = 35):
    """Alerts whose features intersect a small bbox around the point."""
    min_lon = max(-180.0, lon - pad_deg)
    max_lon = min(180.0, lon + pad_deg)
    min_lat = max(-90.0, lat - pad_deg)
    max_lat = min(90.0, lat + pad_deg)
    bbox = (min_lon, min_lat, max_lon, max_lat)

    cache_key = f"eccc:geomet:pt:{lat:.3f}:{lon:.3f}:{pad_deg}"
    cached = cache_get_json(cache_key, ttl_seconds=120)
    if cached is not None:
        return {"source": "cache", **cached}

    try:
        raw_feats, nmatch = await _geomet_collect(bbox, max_features=limit)
    except Exception as e:
        return {
            "source": "error",
            "provider": "ECCC",
            "alerts": [],
            "count": 0,
            "scope": "point",
            "error": str(e),
        }

    alerts = [_feature_to_alert(f, f"{lat:.3f},{lon:.3f}") for f in raw_feats][:limit]
    payload = {
        "alerts": alerts,
        "count": nmatch,
        "returned": len(alerts),
        "scope": "point",
        "country": "CA",
        "provider": "ECCC",
    }
    cache_set_json(cache_key, payload)
    return {"source": "live", **payload}
