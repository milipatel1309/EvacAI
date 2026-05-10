from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import httpx

from .cache import cache_get_json, cache_set_json


USER_AGENT = "EvacAI/0.1 (contact: demo@example.com)"

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometers (WGS84 sphere)."""
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))

# Offline fallback for demo reliability
_OFFLINE_RESOURCES = None

# Map our product categories -> OSM tags to query (multiple tags per category for sparse regions)
TYPE_TO_OVERPASS = {
    "shelter": [
        ('node["amenity"="shelter"]', "shelter"),
        ('way["amenity"="shelter"]', "shelter"),
        ('relation["amenity"="shelter"]', "shelter"),
        ('node["emergency"="shelter"]', "shelter"),
        ('way["emergency"="shelter"]', "shelter"),
        ('relation["emergency"="shelter"]', "shelter"),
    ],
    "hospital": [
        ('node["amenity"="hospital"]', "hospital"),
        ('way["amenity"="hospital"]', "hospital"),
        ('relation["amenity"="hospital"]', "hospital"),
        ('node["healthcare"="hospital"]', "hospital"),
        ('way["healthcare"="hospital"]', "hospital"),
        ('relation["healthcare"="hospital"]', "hospital"),
        ('node["building"="hospital"]', "hospital"),
        ('way["building"="hospital"]', "hospital"),
    ],
    "clinic": [
        ('node["amenity"="clinic"]', "clinic"),
        ('way["amenity"="clinic"]', "clinic"),
        ('relation["amenity"="clinic"]', "clinic"),
        ('node["amenity"="doctors"]', "clinic"),
        ('way["amenity"="doctors"]', "clinic"),
        ('node["healthcare"="clinic"]', "clinic"),
        ('way["healthcare"="clinic"]', "clinic"),
        ('relation["healthcare"="clinic"]', "clinic"),
    ],
    "community_centre": [
        ('node["amenity"="community_centre"]', "community_centre"),
        ('way["amenity"="community_centre"]', "community_centre"),
        ('relation["amenity"="community_centre"]', "community_centre"),
        ('node["leisure"="community_centre"]', "community_centre"),
        ('way["leisure"="community_centre"]', "community_centre"),
    ],
    "food_bank": [
        ('node["social_facility"="food_bank"]', "food_bank"),
        ('way["social_facility"="food_bank"]', "food_bank"),
        ('relation["social_facility"="food_bank"]', "food_bank"),
        ('node["amenity"="social_facility"]["social_facility"="food_bank"]', "food_bank"),
        ('node["amenity"="food_bank"]', "food_bank"),
        ('way["amenity"="food_bank"]', "food_bank"),
    ],
}


def _overpass_query(lat: float, lon: float, radius_m: int, types: list[str]) -> str:
    blocks: list[str] = []
    for t in types:
        for selector, _category in TYPE_TO_OVERPASS.get(t, []):
            blocks.append(f'{selector}(around:{radius_m},{lat},{lon});')

    # If someone passes unknown types, we still return an empty query body.
    body = "\n".join(blocks)
    return f"""
[out:json][timeout:45];
(
{body}
);
out center tags;
"""


def _extract_lat_lon(el: dict[str, Any]) -> tuple[float | None, float | None]:
    if "lat" in el and "lon" in el:
        return float(el["lat"]), float(el["lon"])
    center = el.get("center")
    if isinstance(center, dict) and "lat" in center and "lon" in center:
        return float(center["lat"]), float(center["lon"])
    return None, None


def _infer_category(tags: dict[str, Any]) -> str | None:
    amenity = tags.get("amenity")
    if amenity in {"shelter", "hospital", "clinic", "community_centre", "food_bank"}:
        return str(amenity)
    if tags.get("emergency") == "shelter":
        return "shelter"
    if tags.get("healthcare") == "hospital" or tags.get("building") == "hospital":
        return "hospital"
    if tags.get("healthcare") == "clinic" or amenity == "doctors":
        return "clinic"
    if tags.get("leisure") == "community_centre":
        return "community_centre"
    if tags.get("social_facility") == "food_bank":
        return "food_bank"
    return None


def _load_offline_resources() -> list[dict[str, Any]]:
    global _OFFLINE_RESOURCES
    if _OFFLINE_RESOURCES is not None:
        return _OFFLINE_RESOURCES
    path = Path(__file__).resolve().parents[1] / "demo_data" / "offline_resources.json"
    try:
        _OFFLINE_RESOURCES = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        _OFFLINE_RESOURCES = []
    return _OFFLINE_RESOURCES


async def get_nearby_resources(lat: float, lon: float, radius_km: float, types: list[str]):
    radius_m = int(round(float(radius_km) * 1000))
    # Slightly widen Overpass search so way/relation centers near the edge still match; distance is re-filtered below.
    query_radius_m = min(80_000, int(radius_m * 1.08 + 150))
    norm_types = [t for t in types if t in TYPE_TO_OVERPASS]

    cache_key = f"osm:overpass:{lat:.4f},{lon:.4f}:r={radius_m}:t={','.join(sorted(norm_types))}"
    cached = cache_get_json(cache_key, ttl_seconds=60 * 10)  # 10 min cache
    if cached is not None:
        return {"source": "cache", **cached}

    query = _overpass_query(lat=lat, lon=lon, radius_m=query_radius_m, types=norm_types)
    overpass_urls = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://overpass.openstreetmap.ru/api/interpreter",
    ]
    headers = {"User-Agent": USER_AGENT}

    try:
        last_err: Exception | None = None
        async with httpx.AsyncClient(timeout=50.0, headers=headers, trust_env=False) as client:
            for url in overpass_urls:
                try:
                    r = await client.post(url, data=query.encode("utf-8"))
                    r.raise_for_status()
                    data = r.json()
                    break
                except Exception as e:
                    last_err = e
            else:
                raise last_err or RuntimeError("Overpass failed")
    except Exception as e:
        # Offline fallback: filter bundled resources by distance + type
        offline = []
        for item in _load_offline_resources():
            if item.get("category") not in norm_types:
                continue
            d = haversine_km(lat, lon, float(item["lat"]), float(item["lon"]))
            if d <= radius_km:
                offline.append({**item, "distance_km": round(d, 3)})
        offline.sort(key=lambda x: (x.get("distance_km", 9999), x.get("category", ""), x.get("name", "")))
        note = "Live Overpass query unavailable; using bundled demo data for this area."
        if not offline:
            note += " No demo POIs matched your radius and types; try a larger radius or NYC/Toronto coordinates."
        payload = {
            "items": offline[:40],
            "count": len(offline),
            "radius_km": radius_km,
            "types": norm_types,
            "provider": "offline_demo",
            "note": note,
            "error": str(e),
        }
        return {"source": "offline", **payload}

    items = []
    for el in data.get("elements", []):
        tags = el.get("tags") or {}
        cat = _infer_category(tags)
        if cat is None:
            continue

        el_lat, el_lon = _extract_lat_lon(el)
        if el_lat is None or el_lon is None:
            continue

        distance_km = haversine_km(lat, lon, el_lat, el_lon)
        if distance_km > float(radius_km) + 0.05:
            continue

        name = tags.get("name") or f"Unnamed {cat}"
        items.append(
            {
                "name": name,
                "category": cat,
                "lat": el_lat,
                "lon": el_lon,
                "distance_km": round(distance_km, 3),
                "address": {
                    "street": tags.get("addr:street"),
                    "housenumber": tags.get("addr:housenumber"),
                    "city": tags.get("addr:city"),
                    "state": tags.get("addr:state"),
                    "postcode": tags.get("addr:postcode"),
                    "country": tags.get("addr:country"),
                },
                "phone": tags.get("phone") or tags.get("contact:phone"),
                "website": tags.get("website") or tags.get("contact:website"),
                "osm": {"type": el.get("type"), "id": el.get("id")},
                "source": "OpenStreetMap",
            }
        )

    # Sort and cap for UI
    items.sort(key=lambda x: (x["distance_km"], x["category"], x["name"]))
    payload: dict[str, Any] = {
        "items": items[:40],
        "count": len(items),
        "radius_km": radius_km,
        "types": norm_types,
        "provider": "OpenStreetMap",
    }
    if not items:
        payload["note"] = (
            "No matching tagged facilities in OpenStreetMap within this radius. "
            "Rural areas often have sparse OSM coverage. "
            "Configure MAPBOX_ACCESS_TOKEN or GOOGLE_MAPS_API_KEY for broader POI search, "
            "or increase the search radius."
        )
    cache_set_json(cache_key, payload)
    return {"source": "live", **payload}

