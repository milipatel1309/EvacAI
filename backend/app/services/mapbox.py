from __future__ import annotations

import math
import os
from typing import Any
from urllib.parse import quote

import httpx

from .cache import cache_get_json, cache_set_json
from .resources import haversine_km

# Token must allow Mapbox HTTP APIs used by this app:
#   - Search Box API: `/search/searchbox/v1/forward`, `/category/{id}` (nearby POI for /api/resources)
#   - Geocoding API: `/geocoding/v5/mapbox.places/...` (/api/geocode + legacy POI fallback)
# Create or edit tokens under Mapbox Account → Tokens; ensure URL restrictions (if any) allow
# `api.mapbox.com`. Public `pk.*` tokens usually include these products if not over-restricted.
MAPBOX_ACCESS_TOKEN = os.environ.get("MAPBOX_ACCESS_TOKEN", "").strip()


def mapbox_enabled() -> bool:
    return bool(MAPBOX_ACCESS_TOKEN)


def _bbox_around(lon: float, lat: float, radius_km: float) -> str:
    """min_lon,min_lat,max_lon,max_lat for Search Box `bbox` (docs: no antimeridian cross)."""
    r = float(radius_km) * 1.12
    dlat = r / 111.0
    cos_lat = max(0.2, abs(math.cos(math.radians(lat))))
    dlon = r / (111.0 * cos_lat)
    return f"{lon - dlon},{lat - dlat},{lon + dlon},{lat + dlat}"


def _within_radius_km(
    ref_lat: float, ref_lon: float, flat: float, flon: float, radius_km: float
) -> tuple[bool, float]:
    d_km = haversine_km(ref_lat, ref_lon, flat, flon)
    # Slight slack for POI centroid vs entrance.
    if d_km > float(radius_km) * 1.05 + 0.35:
        return False, d_km
    return True, d_km


def _feature_to_item(
    feature: dict[str, Any],
    category: str,
    ref_lat: float,
    ref_lon: float,
    radius_km: float,
) -> dict[str, Any] | None:
    geom = feature.get("geometry") or {}
    coords = geom.get("coordinates")
    flon: float | None
    flat: float | None
    flon, flat = None, None
    if isinstance(coords, (list, tuple)) and len(coords) >= 2:
        try:
            flon, flat = float(coords[0]), float(coords[1])
        except (TypeError, ValueError):
            pass
    if flon is None or flat is None:
        props = feature.get("properties") or {}
        pc = props.get("coordinates") if isinstance(props.get("coordinates"), dict) else {}
        try:
            flon = float(pc["longitude"])
            flat = float(pc["latitude"])
        except (KeyError, TypeError, ValueError):
            return None
    ok, d_km = _within_radius_km(ref_lat, ref_lon, flat, flon, radius_km)
    if not ok:
        return None
    props = feature.get("properties") or {}
    mid = props.get("mapbox_id") or feature.get("id")
    name = props.get("name_preferred") or props.get("name")
    addr_raw = props.get("full_address") or props.get("place_formatted")
    return {
        "name": name,
        "category": category,
        "lat": flat,
        "lon": flon,
        "distance_km": round(d_km, 3),
        "address": {"raw": addr_raw},
        "phone": None,
        "website": None,
        "mapbox": {"id": mid},
        "source": "Mapbox",
    }


def _geocode_feature_to_item(
    f: dict[str, Any],
    category: str,
    ref_lat: float,
    ref_lon: float,
    radius_km: float,
) -> dict[str, Any] | None:
    center = f.get("center") or []
    if len(center) != 2:
        return None
    flon, flat = float(center[0]), float(center[1])
    ok, d_km = _within_radius_km(ref_lat, ref_lon, flat, flon, radius_km)
    if not ok:
        return None
    return {
        "name": f.get("text") or f.get("place_name"),
        "category": category,
        "lat": flat,
        "lon": flon,
        "distance_km": round(d_km, 3),
        "address": {"raw": f.get("place_name")},
        "phone": None,
        "website": None,
        "mapbox": {"id": f.get("id")},
        "source": "Mapbox",
    }


# Mapbox Search Box canonical category IDs per product category (try in order).
# Discover IDs: GET https://api.mapbox.com/search/searchbox/v1/list/category?language=en
# Unknown IDs yield 404/422 — we skip those silently.
_CATEGORY_TO_SEARCHBOX_CATEGORIES: dict[str, list[str]] = {
    "shelter": ["homeless_shelter", "shelter", "social_services"],
    "clinic": ["medical_clinic", "doctors", "urgent_care"],
    "hospital": ["hospital", "emergency_room"],
    "food_bank": ["food_bank", "food_pantry", "charitable_organization", "social_services"],
    "community_centre": [
        "community_center",
        "cultural_center",
        "civic_center",
        "event_venue",
        "recreation_center",
    ],
}

# Text queries for Search Box `/forward` (types=poi) and Geocoding v5 fallback.
_CATEGORY_TO_QUERIES: dict[str, list[str]] = {
    "shelter": [
        "emergency shelter",
        "homeless shelter",
        "family shelter",
        "shelter",
    ],
    "clinic": [
        "walk in clinic",
        "urgent care",
        "community health clinic",
        "medical clinic",
        "health clinic",
    ],
    "hospital": ["hospital", "emergency room", "medical center", "trauma center"],
    "food_bank": ["food bank", "food pantry", "community food"],
    "community_centre": [
        "community center",
        "community centre",
        "recreation center",
        "neighborhood center",
    ],
}


async def mapbox_geocode(query: str) -> dict[str, Any]:
    """
    Forward geocoding for any address/ZIP/postal code/city.
    """
    if not MAPBOX_ACCESS_TOKEN:
        return {"source": "error", "results": [], "error": "MAPBOX_ACCESS_TOKEN is not set"}

    qnorm = query.strip()
    cache_key = f"mapbox:geocode:q={qnorm.lower()}"
    cached = cache_get_json(cache_key, ttl_seconds=60 * 60 * 24)
    if cached is not None:
        return {"source": "cache", "provider": "mapbox", "results": cached}

    url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{quote(qnorm)}.json"
    params = {
        "access_token": MAPBOX_ACCESS_TOKEN,
        "limit": 5,
        # Forward geocode full strings (ZIP + state + country), not typeahead keystrokes.
        "autocomplete": "false",
    }

    async with httpx.AsyncClient(timeout=20.0, trust_env=True) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()

    feats = data.get("features") or []
    results = []
    for f in feats[:5]:
        center = f.get("center") or []
        if len(center) != 2:
            continue
        lon, lat = center[0], center[1]
        results.append(
            {
                "display_name": f.get("place_name"),
                "lat": float(lat),
                "lon": float(lon),
                "place_id": f.get("id"),
                "types": f.get("place_type") or [],
                "provider": "mapbox",
            }
        )

    cache_set_json(cache_key, results)
    return {"source": "live", "provider": "mapbox", "results": results}


async def mapbox_nearby_resources(lat: float, lon: float, radius_km: float, categories: list[str]) -> dict[str, Any]:
    """
    Nearby POIs via Mapbox Search Box API (`/category`, `/forward`) with Geocoding v5 fallback.

    Search Box is Mapbox's supported POI surface (Geocoding `types=poi` alone is sparse for
    generic keywords). We merge category + text forward results, dedupe, then haversine-filter
    by ``radius_km``.
    """
    if not MAPBOX_ACCESS_TOKEN:
        return {
            "source": "error",
            "provider": "mapbox",
            "items": [],
            "count": 0,
            "error": "MAPBOX_ACCESS_TOKEN is not set",
        }

    cats = [c for c in categories if c in _CATEGORY_TO_QUERIES]
    cache_key = f"mapbox:nearby:lat={lat:.4f}:lon={lon:.4f}:r={radius_km:.1f}:c={','.join(sorted(cats))}"
    cached = cache_get_json(cache_key, ttl_seconds=60 * 10)
    if cached is not None:
        return {"source": "cache", "provider": "mapbox", **cached}

    proximity = f"{lon},{lat}"
    bbox = _bbox_around(lon, lat, radius_km)
    base_params: dict[str, Any] = {
        "access_token": MAPBOX_ACCESS_TOKEN,
        "proximity": proximity,
        "bbox": bbox,
        "language": "en",
    }

    items: list[dict[str, Any]] = []

    def _count_for(cat_key: str) -> int:
        return sum(1 for it in items if it.get("category") == cat_key)

    async with httpx.AsyncClient(timeout=35.0, trust_env=True) as client:
        for cat in cats:
            # 1) Category browse (up to 25 POIs; strongest for hospitals etc.)
            for canon in _CATEGORY_TO_SEARCHBOX_CATEGORIES.get(cat, []):
                url = f"https://api.mapbox.com/search/searchbox/v1/category/{quote(canon)}"
                params = {
                    **base_params,
                    "limit": 25,
                }
                r = await client.get(url, params=params)
                if r.status_code in (400, 404, 422):
                    continue
                r.raise_for_status()
                data = r.json()
                for f in data.get("features") or []:
                    it = _feature_to_item(f, cat, lat, lon, radius_km)
                    if it:
                        items.append(it)

            # 2) Forward text + types=poi (limit 10 per request)
            for q in _CATEGORY_TO_QUERIES[cat]:
                url = "https://api.mapbox.com/search/searchbox/v1/forward"
                params = {
                    **base_params,
                    "q": q,
                    "types": "poi",
                    "limit": 10,
                }
                r = await client.get(url, params=params)
                r.raise_for_status()
                data = r.json()
                for f in data.get("features") or []:
                    props = f.get("properties") or {}
                    if props.get("feature_type") != "poi":
                        continue
                    it = _feature_to_item(f, cat, lat, lon, radius_km)
                    if it:
                        items.append(it)

            # 3) Geocoding v5 POI fallback only if this category is still thin
            if _count_for(cat) >= 3:
                continue
            for q in _CATEGORY_TO_QUERIES[cat]:
                gurl = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{quote(q)}.json"
                params = {
                    "access_token": MAPBOX_ACCESS_TOKEN,
                    "limit": 10,
                    "types": "poi",
                    "proximity": proximity,
                    "autocomplete": "false",
                }
                r = await client.get(gurl, params=params)
                r.raise_for_status()
                data = r.json()
                for f in data.get("features") or []:
                    it = _geocode_feature_to_item(f, cat, lat, lon, radius_km)
                    if it:
                        items.append(it)

    seen: set[tuple[Any, ...]] = set()
    deduped: list[dict[str, Any]] = []
    for it in items:
        mid = (it.get("mapbox") or {}).get("id")
        if mid:
            key = (it.get("category"), mid)
        else:
            key = (
                it.get("category"),
                (it.get("name") or "").strip().lower(),
                round(float(it["lat"]), 5),
                round(float(it["lon"]), 5),
            )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(it)

    deduped.sort(
        key=lambda x: (
            x.get("distance_km") is None,
            x.get("distance_km") or 1e9,
            x.get("category", ""),
            x.get("name", "") or "",
        )
    )
    payload: dict[str, Any] = {
        "items": deduped[:40],
        "count": len(deduped),
        "radius_km": radius_km,
        "types": cats,
    }
    if not deduped:
        payload["note"] = (
            "No Mapbox POI results within this radius for the selected categories "
            "(Search Box + geocoding fallbacks). Try a larger radius, fewer filters, "
            "or use OpenStreetMap by unsetting MAPBOX_ACCESS_TOKEN."
        )
    cache_set_json(cache_key, payload)
    return {"source": "live", "provider": "mapbox", **payload}
