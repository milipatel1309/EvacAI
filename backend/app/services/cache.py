from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any


def _default_cache_dir() -> Path:
    # Keep cache inside project for easy demo + portability
    return Path(os.environ.get("CRISIS_CACHE_DIR", ".cache"))


def _key_to_path(key: str) -> Path:
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return _default_cache_dir() / f"{h}.json"


def cache_get_json(key: str, ttl_seconds: int) -> Any | None:
    path = _key_to_path(key)
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None

    age = time.time() - stat.st_mtime
    if age > ttl_seconds:
        return None

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def cache_set_json(key: str, value: Any) -> None:
    cache_dir = _default_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)

    path = _key_to_path(key)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

