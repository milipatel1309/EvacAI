from __future__ import annotations

import os
from typing import Any

import httpx

from .cache import cache_get_json, cache_set_json
from .resources import haversine_km


GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()


def google_enabled() -> bool:
    return bool(GOOGLE_MAPS_API_KEY)


async def google_geocode(query: str) -> dict[str, Any]:
    if not GOOGLE_MAPS_API_KEY:
        return {
            "source": "error",
            "results": [],
            "error": "GOOGLE_MAPS_API_KEY is not set",
        }

    cache_key = f"google:geocode:q={query.strip().lower()}"
    cached = cache_get_json(cache_key, ttl_seconds=60 * 60 * 24)
    if cached is not None:
        return {"source": "cache", "provider": "google", "results": cached}

    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": query, "key": GOOGLE_MAPS_API_KEY}

    async with httpx.AsyncClient(timeout=20.0, trust_env=True) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()

    status = data.get("status")
    if status != "OK":
        return {"source": "error", "provider": "google", "results": [], "error": status, "details": data.get("error_message")}

    results = []
    for item in (data.get("results") or [])[:5]:
        loc = (item.get("geometry") or {}).get("location") or {}
        results.append(
            {
                "display_name": item.get("formatted_address"),
                "lat": float(loc.get("lat")),
                "lon": float(loc.get("lng")),
                "place_id": item.get("place_id"),
                "types": item.get("types") or [],
                "provider": "google",
            }
        )

    cache_set_json(cache_key, results)
    return {"source": "live", "provider": "google", "results": results}


_CATEGORY_TO_KEYWORD = {
    "shelter": "shelter",
    "clinic": "clinic",
    "hospital": "hospital",
    "food_bank": "food bank",
    "community_centre": "community center",
}


async def google_nearby_places(lat: float, lon: float, radius_km: float, categories: list[str]) -> dict[str, Any]:
    if not GOOGLE_MAPS_API_KEY:
        return {
            "source": "error",
            "provider": "google",
            "items": [],
            "count": 0,
            "error": "GOOGLE_MAPS_API_KEY is not set",
        }

    radius_m = int(max(100, min(50_000, radius_km * 1000)))
    cats = [c for c in categories if c in _CATEGORY_TO_KEYWORD]
    cache_key = f"google:places:lat={lat:.4f}:lon={lon:.4f}:r={radius_m}:c={','.join(sorted(cats))}"
    cached = cache_get_json(cache_key, ttl_seconds=60 * 10)
    if cached is not None:
        return {"source": "cache", "provider": "google", **cached}

    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"

    # Places Nearby Search has limited type taxonomy; keyword works best for these categories.
    items: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=20.0, trust_env=True) as client:
        for cat in cats:
            keyword = _CATEGORY_TO_KEYWORD[cat]
            params = {
                "location": f"{lat},{lon}",
                "radius": radius_m,
                "keyword": keyword,
                "key": GOOGLE_MAPS_API_KEY,
            }
            r = await client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
            status = data.get("status")
            if status not in {"OK", "ZERO_RESULTS"}:
                return {
                    "source": "error",
                    "provider": "google",
                    "items": [],
                    "count": 0,
                    "error": status,
                    "details": data.get("error_message"),
                }

            for p in (data.get("results") or [])[:20]:
                loc = ((p.get("geometry") or {}).get("location")) or {}
                plat = float(loc.get("lat"))
                plon = float(loc.get("lng"))
                d_km = haversine_km(lat, lon, plat, plon)
                if d_km > radius_km:
                    continue
                items.append(
                    {
                        "name": p.get("name"),
                        "category": cat,
                        "lat": plat,
                        "lon": plon,
                        "distance_km": round(d_km, 3),
                        "address": {"raw": p.get("vicinity")},
                        "phone": None,  # requires Place Details API (optional)
                        "website": None,
                        "google": {"place_id": p.get("place_id")},
                        "source": "Google Places",
                    }
                )

    # Deduplicate by place_id
    seen = set()
    deduped = []
    for it in items:
        pid = (it.get("google") or {}).get("place_id")
        if not pid or pid in seen:
            continue
        seen.add(pid)
        deduped.append(it)

    deduped.sort(key=lambda x: (x.get("distance_km") is None, x.get("distance_km") or 1e9, x.get("category", ""), x.get("name", "")))
    payload: dict[str, Any] = {
        "items": deduped[:40],
        "count": len(deduped),
        "radius_km": radius_km,
        "types": cats,
    }
    if not deduped:
        payload["note"] = (
            "No Google Places results within this radius for these keywords. "
            "Try a larger radius or different categories; verify Places API is enabled for your key."
        )
    cache_set_json(cache_key, payload)
    return {"source": "live", "provider": "google", **payload}

