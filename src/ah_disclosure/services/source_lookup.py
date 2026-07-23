from __future__ import annotations

import json
from typing import Any

from ah_disclosure.core.config import get_settings


def build_query_signature(source: str, **params: Any) -> str:
    normalized = {
        key: str(value).strip() if value is not None else ""
        for key, value in sorted(params.items())
    }
    payload = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{source.strip().casefold()}|{payload}"


def source_ttl_seconds(source: str, max_cache_age_seconds: int | None = None) -> int:
    if max_cache_age_seconds is not None:
        return max(int(max_cache_age_seconds), 0)
    settings = get_settings()
    days = settings.hkex_ttl_days if source.upper().startswith("HKEX") else settings.cninfo_ttl_days
    return max(int(days), 0) * 86400


def historical_source_ttl_seconds() -> int:
    return max(int(get_settings().historical_filing_ttl_days), 0) * 86400
