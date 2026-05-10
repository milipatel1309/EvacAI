from __future__ import annotations

import json
from pathlib import Path
import re

import httpx

from .cache import cache_get_json, cache_set_json


USER_AGENT = "EvacAI/0.1 (contact: demo@example.com)"

_OFFLINE = None
_ZIP_RE = re.compile(r"^\d{5}(?:-\d{4})?$")
# US ZIP embedded in "93292 California USA" (Mapbox/Nominatim sometimes return nothing on cloud hosts).
_ZIP_EMBEDDED_RE = re.compile(r"(?:^|[\s,])(\d{5})(?:-\d{4})?(?:\s|$|,)", re.I)
_CA_POSTAL_RE = re.compile(r"^[ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z][ ]?\d[ABCEGHJ-NPRSTV-Z]\d$", re.I)


def _offline_geocode(query: str):
    global _OFFLINE
    # Reload-friendly: keep in-memory cache but allow updates without restart
    path = Path(__file__).resolve().parents[1] / "demo_data" / "offline_geocode.json"
    try:
        _OFFLINE = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        _OFFLINE = _OFFLINE or []

    q = query.strip().lower()
    hits = []
    for item in _OFFLINE:
        key = (item.get("q") or "").strip().lower()
        if key and (key in q or q in key):
            hits.append(
                {
                    "display_name": item.get("display_name"),
                    "lat": float(item["lat"]),
                    "lon": float(item["lon"]),
                    "type": "offline",
                    "class": "offline",
                }
            )
    return hits[:5]


async def _geocode_zippopotam(country: str, code: str):
    url = f"https://api.zippopotam.us/{country}/{code}"
    async with httpx.AsyncClient(
        timeout=15.0,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        trust_env=False,
    ) as client:
        r = await client.get(url)
        r.raise_for_status()
        data = r.json()

    places = data.get("places") or []
    results = []
    for p in places[:5]:
        display = p.get("place name") or p.get("place name".title())
        state = p.get("state abbreviation") or p.get("state")
        post_code = data.get("post code") or code
        results.append(
            {
                "display_name": f"{display}, {state} {post_code}, {country.upper()}",
                "lat": float(p["latitude"]),
                "lon": float(p["longitude"]),
                "type": "postcode",
                "class": "boundary",
            }
        )
    return results


async def _geocode_photon(query: str):
    """Komoot Photon (OSM) — often works when Nominatim returns [] from cloud IPs."""
    url = "https://photon.komoot.io/api/"
    params = {"q": query, "limit": 5}
    async with httpx.AsyncClient(timeout=20.0, headers={"User-Agent": USER_AGENT}, trust_env=False) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()

    out = []
    for f in (data.get("features") or [])[:5]:
        geom = f.get("geometry") or {}
        coords = geom.get("coordinates") or []
        if len(coords) < 2:
            continue
        lon, lat = float(coords[0]), float(coords[1])
        props = f.get("properties") or {}
        parts = [
            props.get("name"),
            props.get("street"),
            props.get("city"),
            props.get("state"),
            props.get("country"),
        ]
        display = ", ".join(str(p) for p in parts if p)
        if not display:
            display = query
        out.append(
            {
                "display_name": display,
                "lat": lat,
                "lon": lon,
                "type": props.get("type"),
                "class": "place",
            }
        )
    return out


async def _geocode_maps_co(query: str):
    """
    Backup geocoder (also OSM-backed) that sometimes works when Nominatim blocks.
    """
    url = "https://geocode.maps.co/search"
    params = {"q": query}
    async with httpx.AsyncClient(timeout=20.0, headers={"User-Agent": USER_AGENT}, trust_env=False) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()

    results = []
    for item in data[:5]:
        results.append(
            {
                "display_name": item.get("display_name"),
                "lat": float(item["lat"]),
                "lon": float(item["lon"]),
                "type": item.get("type"),
                "class": item.get("class"),
            }
        )
    return results


async def geocode_nominatim(query: str):
    """
    Lightweight geocoder for demo. Prefer caching to respect Nominatim usage.
    """
    cache_key = f"nominatim:q={query.strip().lower()}"
    cached = cache_get_json(cache_key, ttl_seconds=60 * 60 * 24)
    if cached is not None and len(cached) > 0:
        return {"source": "cache", "results": cached}

    q = query.strip()
    # Fast-path: US ZIP + Canada postal codes (exact or embedded in a longer query).
    try:
        if _ZIP_RE.match(q):
            results = await _geocode_zippopotam("us", q[:5])
            if results:
                cache_set_json(cache_key, results)
                return {"source": "live", "results": results, "provider": "zippopotam"}

        if not _ZIP_RE.match(q):
            mzip = _ZIP_EMBEDDED_RE.search(q)
            if mzip and ("canada" not in q.lower()):
                results = await _geocode_zippopotam("us", mzip.group(1))
                if results:
                    cache_set_json(cache_key, results)
                    return {"source": "live", "results": results, "provider": "zippopotam"}

        if _CA_POSTAL_RE.match(q):
            norm = q.replace(" ", "").upper()
            results = await _geocode_zippopotam("ca", norm)
            if results:
                cache_set_json(cache_key, results)
                return {"source": "live", "results": results, "provider": "zippopotam"}
    except Exception:
        # fall through to other providers
        pass

    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": query, "format": "jsonv2", "limit": 5, "addressdetails": 1}
    headers = {"User-Agent": USER_AGENT}

    try:
        async with httpx.AsyncClient(timeout=20.0, headers=headers, trust_env=False) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        # Backup provider
        try:
            results = await _geocode_maps_co(query)
            if results:
                cache_set_json(cache_key, results)
                return {
                    "source": "live",
                    "results": results,
                    "provider": "maps.co",
                    "note": "Primary geocoder blocked; used backup provider.",
                }
        except Exception:
            pass

        offline = _offline_geocode(query)
        if offline:
            return {"source": "offline", "results": offline, "note": "Live geocoding unavailable; using demo fallback."}
        return {"source": "error", "results": [], "error": str(e)}

    results = []
    for item in data:
        results.append(
            {
                "display_name": item.get("display_name"),
                "lat": float(item["lat"]),
                "lon": float(item["lon"]),
                "type": item.get("type"),
                "class": item.get("class"),
            }
        )

    if not results:
        for fn, pname in ((_geocode_maps_co, "maps.co"), (_geocode_photon, "photon")):
            try:
                alt = await fn(q)
                if alt:
                    cache_set_json(cache_key, alt)
                    return {
                        "source": "live",
                        "results": alt,
                        "provider": pname,
                        "note": f"OpenStreetMap Nominatim returned no results; used {pname}.",
                    }
            except Exception:
                continue
        offline = _offline_geocode(q)
        if offline:
            return {"source": "offline", "results": offline, "note": "Live geocoding returned no hits; using demo fallback."}
        return {
            "source": "live",
            "results": [],
            "provider": "nominatim",
            "note": "No geocoding results. On cloud hosts, add MAPBOX_ACCESS_TOKEN (Render env) for reliable address search.",
        }

    cache_set_json(cache_key, results)
    return {"source": "live", "results": results, "provider": "nominatim"}

