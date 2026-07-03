from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from .paths import get_data_paths


def cache_key(provider: str, interface: str, params: dict[str, Any]) -> str:
    payload = json.dumps(params, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
    return f"{provider}_{interface}_{digest}.json"


def get_cache_path(provider: str, interface: str, params: dict[str, Any]) -> Path:
    paths = get_data_paths()
    folder = paths.cache / provider
    folder.mkdir(parents=True, exist_ok=True)
    return folder / cache_key(provider, interface, params)


def read_cache(provider: str, interface: str, params: dict[str, Any], ttl_days: int) -> Any | None:
    path = get_cache_path(provider, interface, params)
    if not path.exists() or time.time() - path.stat().st_mtime > ttl_days * 86400:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_cache(provider: str, interface: str, params: dict[str, Any], payload: Any) -> Path:
    path = get_cache_path(provider, interface, params)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path
