from __future__ import annotations

import json
from pathlib import Path

from ah_disclosure.clients.hkex_client import HkexClient
from ah_disclosure.core.paths import get_data_paths
from ah_disclosure.identity.h_symbol_resolver import normalize_h_symbol


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
    _cache_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_hkex_stock_id(
    hk_code: str,
    candidate_stock_id: str | None = None,
    company_keyword: str = "",
    verify: bool = True,
) -> dict:
    code = normalize_h_symbol(hk_code)
    cache = _load_map()
    if code in cache and not candidate_stock_id:
        return {**cache[code], "cache_hit": True}
    cached = cache.get(code) if isinstance(cache.get(code), dict) else None
    discovered: dict | None = None
    if not candidate_stock_id:
        try:
            discovered = HkexClient().lookup_stock(code)
        except Exception as exc:
            return {
                "symbol": code,
                "hkex_stock_id": None,
                "verified": False,
                "cache_hit": False,
                "error": f"HKEX stockId auto discovery failed: {exc}",
            }
        if not discovered or not discovered.get("hkex_stock_id"):
            return {
                "symbol": code,
                "hkex_stock_id": None,
                "verified": False,
                "cache_hit": False,
                "error": "HKEX stockId was not found by HKEX prefix search.",
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
            verification = HkexClient().verify_stock_id(str(candidate_stock_id), hk_code=code, company_keyword=company_keyword)
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
        cache[code] = {k: v for k, v in result.items() if k != "records_sample"}
        _save_map(cache)
    return result


def set_hkex_stock_id(hk_code: str, hkex_stock_id: str, company_keyword: str = "", verify: bool = True) -> dict:
    """Manually set/cache an HKEX stockId mapping, optionally validating it first."""
    return resolve_hkex_stock_id(hk_code, candidate_stock_id=hkex_stock_id, company_keyword=company_keyword, verify=verify)


class HkexStockIdResolver:
    """Small object wrapper for MCP/server code."""

    def resolve(self, hk_code: str, candidate_stock_id: str | None = None, company_name: str | None = None, verify: bool = True) -> dict:
        return resolve_hkex_stock_id(hk_code, candidate_stock_id=candidate_stock_id, company_keyword=company_name or "", verify=verify)
