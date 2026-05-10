"""IBM Cloud IAM — bearer token for watsonx / COS (API key grant)."""

from __future__ import annotations

import os
import httpx

from .cache import cache_get_json, cache_set_json

IBM_CLOUD_API_KEY = os.environ.get("IBM_CLOUD_API_KEY", "").strip() or os.environ.get(
    "WATSONX_API_KEY", ""
).strip()

IAM_URL = os.environ.get("IBM_IAM_URL", "https://iam.cloud.ibm.com/identity/token")


def ibm_api_key_configured() -> bool:
    return bool(IBM_CLOUD_API_KEY)


async def get_iam_access_token() -> str:
    """Exchange API key for IAM access token (cached ~50 minutes)."""
    if not IBM_CLOUD_API_KEY:
        raise RuntimeError("IBM_CLOUD_API_KEY (or WATSONX_API_KEY) is not set")

    cache_key = "ibm:iam:access_token"
    cached = cache_get_json(cache_key, ttl_seconds=50 * 60)
    if isinstance(cached, dict) and cached.get("token"):
        return str(cached["token"])

    async with httpx.AsyncClient(timeout=30.0, trust_env=True) as client:
        r = await client.post(
            IAM_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            data={
                "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
                "apikey": IBM_CLOUD_API_KEY,
            },
        )
        r.raise_for_status()
        data = r.json()

    token = data.get("access_token")
    if not token:
        raise RuntimeError("IAM response missing access_token")

    cache_set_json(cache_key, {"token": token})
    return str(token)
