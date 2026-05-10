"""Optional IBM Cloud Object Storage — archive AI plan JSON (ibm_boto3)."""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

IBM_COS_ENDPOINT = os.environ.get("IBM_COS_ENDPOINT", "").strip().rstrip("/")
IBM_COS_BUCKET = os.environ.get("IBM_COS_BUCKET", "").strip()
IBM_COS_API_KEY = os.environ.get("IBM_COS_API_KEY", "").strip() or os.environ.get(
    "IBM_CLOUD_API_KEY", ""
).strip()
IBM_COS_RESOURCE_INSTANCE_ID = os.environ.get("IBM_COS_RESOURCE_INSTANCE_ID", "").strip()


def cos_configured() -> bool:
    return bool(IBM_COS_ENDPOINT and IBM_COS_BUCKET and IBM_COS_API_KEY and IBM_COS_RESOURCE_INSTANCE_ID)


def plan_object_key(prefix: str = "crisis-plans") -> str:
    return f"{prefix}/{int(time.time() * 1000)}.json"


def _put_object_sync(key: str, body: bytes) -> None:
    import ibm_boto3
    from ibm_botocore.client import Config

    client = ibm_boto3.client(
        "s3",
        ibm_api_key_id=IBM_COS_API_KEY,
        ibm_service_instance_id=IBM_COS_RESOURCE_INSTANCE_ID,
        config=Config(signature_version="oauth"),
        endpoint_url=IBM_COS_ENDPOINT,
    )
    client.put_object(Bucket=IBM_COS_BUCKET, Key=key, Body=body, ContentType="application/json")


async def upload_plan_json(*, key: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not cos_configured():
        return {"source": "skipped", "reason": "IBM COS env vars not set"}

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    try:
        await asyncio.to_thread(_put_object_sync, key, body)
    except Exception as e:
        return {"source": "error", "provider": "ibm-cos", "error": str(e)}

    return {"source": "live", "provider": "ibm-cos", "key": key, "bytes": len(body)}
