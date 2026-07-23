from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path

from ah_disclosure.clients.hkex_client import HkexClient, get_thread_hkex_client
from ah_disclosure.core.file_utils import replace_file_with_retry
from ah_disclosure.core.paths import get_data_paths
from ah_disclosure.identity.h_symbol_resolver import normalize_h_symbol


# HKEX prefix.do only lists active securities. Keep verified historical mappings
# for delisted/de-SPAC issuers so title search remains available.
HISTORICAL_HKEX_STOCK_IDS = {
    "00011": {
        "hkex_stock_id": "18",
        "company_name": "HANG SENG BANK LIMITED",
    },
    "07836": {
        "hkex_stock_id": "1000145057",
        "company_name": "AQUILA ACQUISITION CORPORATION",
    },
}
_CACHE_WRITE_LOCK = threading.Lock()


def is_historical_hkex_symbol(hk_code: str) -> bool:
    return normalize_h_symbol(hk_code) in HISTORICAL_HKEX_STOCK_IDS


def is_historical_hkex_stock_id(stock_id: str | None) -> bool:
    value = str(stock_id or "")
    return any(
        str(record.get("hkex_stock_id")) == value
        for record in HISTORICAL_HKEX_STOCK_IDS.values()
    )


def _cache_path() -> Path:
    return get_data_paths().cache_resolver / "hkex_stockid_map.json"


def _load_map() -> dict[str, dict]:
    path = _cache_path()
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_map(data: dict[str, dict]) -> None:
    target = _cache_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f"{target.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    replace_file_with_retry(temporary, target)


def _save_record(code: str, record: dict) -> None:
    """Merge one mapping under a process lock so parallel lookups do not lose updates."""
    with _CACHE_WRITE_LOCK:
        latest = _load_map()
        latest[code] = record
        _save_map(latest)


def resolve_hkex_stock_id(
    hk_code: str,
    candidate_stock_id: str | None = None,
    company_keyword: str = "",
    verify: bool = True,
    refresh: bool = False,
) -> dict:
    code = normalize_h_symbol(hk_code)
    cache = _load_map()
    cached = cache.get(code) if isinstance(cache.get(code), dict) else None
    if cached and not candidate_stock_id and not refresh:
        return {**cached, "cache_hit": True}
    if (
        cached
        and candidate_stock_id
        and str(cached.get("hkex_stock_id")) == str(candidate_stock_id)
        and cached.get("verified") is True
        and not refresh
    ):
        return {
            **cached,
            "cache_hit": True,
            "verification_skipped": "verified_cache_match",
        }
    discovered: dict | None = None
    if not candidate_stock_id:
        historical = HISTORICAL_HKEX_STOCK_IDS.get(code)
        lookup_error: Exception | None = None
        if historical:
            discovered = {
                "symbol": code,
                **historical,
                "source": "verified historical HKEX mapping",
            }
        else:
            try:
                discovered = get_thread_hkex_client(HkexClient).lookup_stock(code)
            except Exception as exc:
                lookup_error = exc
        if not discovered or not discovered.get("hkex_stock_id"):
            if cached and cached.get("hkex_stock_id"):
                return {
                    **cached,
                    "cache_hit": True,
                    "refresh_failed": bool(refresh),
                    "refresh_error": str(lookup_error or "HKEX prefix search returned no match"),
                }
            return {
                "symbol": code,
                "hkex_stock_id": None,
                "verified": False,
                "cache_hit": False,
                "error": (
                    f"HKEX stockId auto discovery failed: {lookup_error}"
                    if lookup_error
                    else "HKEX stockId was not found by HKEX prefix search."
                ),
            }
        candidate_stock_id = str(discovered["hkex_stock_id"])
    result = {
        "symbol": code,
        "hkex_stock_id": str(candidate_stock_id),
        "verified": bool(discovered),
        "cache_hit": False,
    }
    if cached and str(cached.get("hkex_stock_id")) == str(candidate_stock_id):
        result.update({k: v for k, v in cached.items() if k not in {"cache_hit", "verified"}})
    if discovered:
        result.update(
            {
                "company_name": discovered.get("company_name"),
                "discovered_by": discovered.get("source"),
            }
        )
    if verify:
        try:
            verification = get_thread_hkex_client(HkexClient).verify_stock_id(
                str(candidate_stock_id),
                hk_code=code,
                company_keyword=company_keyword,
            )
            result.update(verification)
            if discovered and not result.get("verified"):
                result["verified"] = True
                result["verification_note"] = "Verified by exact HKEX prefix.do stock code match; title-search verification did not confirm."
        except Exception as exc:
            result["verification_error"] = str(exc)
            if discovered:
                result["verified"] = True
                result["verification_note"] = "Verified by exact HKEX prefix.do stock code match; title-search verification failed."
    else:
        result["verified"] = bool(discovered)
    if result.get("verified") or not verify:
        _save_record(
            code,
            {k: v for k, v in result.items() if k != "records_sample"},
        )
    return result


def set_hkex_stock_id(hk_code: str, hkex_stock_id: str, company_keyword: str = "", verify: bool = True) -> dict:
    """Manually set/cache an HKEX stockId mapping, optionally validating it first."""
    return resolve_hkex_stock_id(hk_code, candidate_stock_id=hkex_stock_id, company_keyword=company_keyword, verify=verify)


class HkexStockIdResolver:
    """Small object wrapper for MCP/server code."""

    def resolve(self, hk_code: str, candidate_stock_id: str | None = None, company_name: str | None = None, verify: bool = True, refresh: bool = False) -> dict:
        return resolve_hkex_stock_id(
            hk_code,
            candidate_stock_id=candidate_stock_id,
            company_keyword=company_name or "",
            verify=verify,
            refresh=refresh,
        )
