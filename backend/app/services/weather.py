from __future__ import annotations

import json
from pathlib import Path

import httpx

from .cache import cache_get_json, cache_set_json


_OFFLINE_WEATHER = None


def _offline_weather_payload():
    global _OFFLINE_WEATHER
    if _OFFLINE_WEATHER is not None:
        return _OFFLINE_WEATHER
    path = Path(__file__).resolve().parents[1] / "demo_data" / "offline_weather.json"
    try:
        _OFFLINE_WEATHER = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        _OFFLINE_WEATHER = {"current": {}, "timezone": None, "timezone_abbreviation": None}
    return _OFFLINE_WEATHER


def _open_meteo_temperature_unit(temp_unit: str) -> str:
    u = (temp_unit or "f").strip().lower()
    if u in ("f", "fahrenheit"):
        return "fahrenheit"
    return "celsius"


def _api_temp_letter(open_meteo_unit: str) -> str:
    return "f" if open_meteo_unit == "fahrenheit" else "c"


def _open_meteo_windspeed_param(open_meteo_temp_unit: str) -> str:
    """Open-Meteo windspeed_unit: kmh | mph | ms | kn. Match US (mph) vs metric (km/h)."""
    return "mph" if open_meteo_temp_unit == "fahrenheit" else "kmh"


def _wind_speed_display_suffix(open_meteo_temp_unit: str) -> str:
    return "mph" if open_meteo_temp_unit == "fahrenheit" else "km/h"


def _weather_debug_note(
    *,
    lat: float,
    lon: float,
    data_source: str,
    timezone: str | None,
    extra: str | None = None,
) -> str:
    tz = timezone or "?"
    bits = [
        f"request lat={lat:.5f} lon={lon:.5f}",
        f"timezone={tz}",
        f"provider=Open-Meteo",
        f"response={data_source}",
    ]
    if extra:
        bits.append(extra)
    return " · ".join(bits)


def _offline_payload_for_unit(open_meteo_unit: str):
    """Offline demo JSON is °C and km/h; convert temps and wind when °F / mph is requested."""
    raw = _offline_weather_payload()
    payload = {
        "current": dict(raw.get("current") or {}),
        "timezone": raw.get("timezone"),
        "timezone_abbreviation": raw.get("timezone_abbreviation"),
    }
    if open_meteo_unit == "fahrenheit":
        cur = payload["current"]
        for key in ("temperature_2m", "apparent_temperature"):
            v = cur.get(key)
            if isinstance(v, (int, float)):
                cur[key] = v * 9.0 / 5.0 + 32.0
        w = cur.get("wind_speed_10m")
        if isinstance(w, (int, float)):
            cur["wind_speed_10m"] = w * 0.621371192237334  # km/h → mph
    return payload


async def get_open_meteo_weather(lat: float, lon: float, *, temp_unit: str = "f"):
    """
    Live weather (no API key) via Open-Meteo.
    https://open-meteo.com/
    """
    om_unit = _open_meteo_temperature_unit(temp_unit)
    letter = _api_temp_letter(om_unit)
    wind_param = _open_meteo_windspeed_param(om_unit)
    wind_suffix = _wind_speed_display_suffix(om_unit)
    cache_key = f"openmeteo:lat={lat:.4f}:lon={lon:.4f}:t={letter}:w={wind_param}:v3"
    cached = cache_get_json(cache_key, ttl_seconds=60 * 5)
    if cached is not None and isinstance(cached, dict):
        tz = cached.get("timezone")
        tz_s = tz if isinstance(tz, str) else None
        note = _weather_debug_note(
            lat=lat,
            lon=lon,
            data_source="cache(≤5m)",
            timezone=tz_s,
        )
        return {
            **cached,
            "source": "cache",
            "temp_unit": letter,
            "wind_speed_unit": wind_suffix,
            "note": note,
        }
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,apparent_temperature,precipitation,rain,showers,weather_code,wind_speed_10m",
        "timezone": "auto",
        "temperature_unit": om_unit,
        "windspeed_unit": wind_param,
    }

    try:
        async with httpx.AsyncClient(
            timeout=20.0,
            headers={"User-Agent": "EvacAI/0.1"},
            trust_env=False,
        ) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        payload = _offline_payload_for_unit(om_unit)
        err_s = str(e)
        note = _weather_debug_note(
            lat=lat,
            lon=lon,
            data_source="offline_fallback",
            timezone=payload.get("timezone") if isinstance(payload.get("timezone"), str) else None,
            extra=f"live_error={err_s[:180]}",
        )
        return {
            "source": "offline",
            "temp_unit": letter,
            "wind_speed_unit": wind_suffix,
            **payload,
            "note": note,
            "error": err_s,
        }

    current = data.get("current") or {}
    payload = {
        "current": current,
        "timezone": data.get("timezone"),
        "timezone_abbreviation": data.get("timezone_abbreviation"),
    }
    cache_set_json(cache_key, payload)
    note = _weather_debug_note(
        lat=lat,
        lon=lon,
        data_source="live",
        timezone=data.get("timezone") if isinstance(data.get("timezone"), str) else None,
    )
    return {"source": "live", "temp_unit": letter, "wind_speed_unit": wind_suffix, "note": note, **payload}

