"""Reverse geocode lat/lon → ISO 3166-1 alpha-2 country code (US, CA, …)."""

from __future__ import annotations

import os
from typing import Optional

import httpx

from .cache import cache_get_json, cache_set_json

USER_AGENT = "EvacAI/0.1 (contact: demo@example.com)"
MAPBOX_ACCESS_TOKEN = os.environ.get("MAPBOX_ACCESS_TOKEN", "").strip()


async def country_code_from_latlon(lat: float, lon: float) -> Optional[str]:
    """
    Returns uppercased ISO country code, e.g. US, CA.
    """
    cache_key = f"reverse:country:{lat:.4f}:{lon:.4f}"
    cached = cache_get_json(cache_key, ttl_seconds=60 * 60 * 24)
    if isinstance(cached, dict) and cached.get("country_code"):
        return str(cached["country_code"])

    if MAPBOX_ACCESS_TOKEN:
        try:
            url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{lon},{lat}.json"
            params = {"access_token": MAPBOX_ACCESS_TOKEN, "types": "country", "limit": 1}
            async with httpx.AsyncClient(timeout=15.0, trust_env=True) as client:
                r = await client.get(url, params=params)
                r.raise_for_status()
                data = r.json()
            feats = data.get("features") or []
            if feats:
                short = (feats[0].get("properties") or {}).get("short_code") or ""
                short = short.strip().upper()
                if len(short) == 2:
                    cache_set_json(cache_key, {"country_code": short})
                    return short
        except Exception:
            pass

    url = "https://nominatim.openstreetmap.org/reverse"
    params = {"lat": lat, "lon": lon, "format": "json", "addressdetails": 1}
    headers = {"User-Agent": USER_AGENT}
    try:
        async with httpx.AsyncClient(timeout=15.0, headers=headers, trust_env=True) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception:
        return None

    addr = data.get("address") or {}
    cc = (addr.get("country_code") or "").strip().upper()
    if len(cc) == 2:
        cache_set_json(cache_key, {"country_code": cc})
        return cc
    return None


async def canada_province_code_from_latlon(lat: float, lon: float) -> Optional[str]:
    """Best-effort CA province/territory 2-letter code (ON, BC, …)."""
    cache_key = f"reverse:ca_prov:{lat:.4f}:{lon:.4f}"
    cached = cache_get_json(cache_key, ttl_seconds=60 * 60 * 24)
    if isinstance(cached, dict) and cached.get("province_code"):
        return str(cached["province_code"])

    url = "https://nominatim.openstreetmap.org/reverse"
    params = {"lat": lat, "lon": lon, "format": "json", "addressdetails": 1}
    headers = {"User-Agent": USER_AGENT}
    try:
        async with httpx.AsyncClient(timeout=15.0, headers=headers, trust_env=True) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception:
        return None

    addr = data.get("address") or {}
    iso = addr.get("ISO3166-2-lvl4") or addr.get("ISO3166-2-lvl3") or ""
    if isinstance(iso, str) and iso.upper().startswith("CA-"):
        code = iso.split("-", 1)[-1].strip().upper()
        if len(code) == 2:
            cache_set_json(cache_key, {"province_code": code})
            return code

    # Fallback: map common province names
    prov = (addr.get("state") or addr.get("province") or "").strip().lower()
    name_to_code = {
        "ontario": "ON",
        "quebec": "QC",
        "british columbia": "BC",
        "alberta": "AB",
        "manitoba": "MB",
        "saskatchewan": "SK",
        "nova scotia": "NS",
        "new brunswick": "NB",
        "prince edward island": "PE",
        "newfoundland and labrador": "NL",
        "northwest territories": "NT",
        "nunavut": "NU",
        "yukon": "YT",
    }
    code = name_to_code.get(prov)
    if code:
        cache_set_json(cache_key, {"province_code": code})
        return code
    return None
