from __future__ import annotations

import json
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from ah_disclosure.core.file_utils import replace_file_with_retry
from ah_disclosure.core.paths import get_data_paths


BSE_CODE_MAPPING_URL = "https://www.bse.cn/service/code_mapping.html"


def _cache_path() -> Path:
    return get_data_paths().cache_resolver / "bse_code_map.json"


def _read_cache() -> dict[str, str] | None:
    path = _cache_path()
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    mapping = payload.get("legacy_to_current") if isinstance(payload, dict) else None
    if not isinstance(mapping, dict):
        return None
    return {str(key): str(value) for key, value in mapping.items()}


def _write_cache(mapping: dict[str, str]) -> None:
    target = _cache_path()
    temporary = target.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {
                "source": BSE_CODE_MAPPING_URL,
                "legacy_to_current": mapping,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    replace_file_with_retry(temporary, target)


def _fetch_mapping() -> dict[str, str]:
    response = requests.get(
        BSE_CODE_MAPPING_URL,
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.bse.cn/"},
        timeout=20,
    )
    response.raise_for_status()
    response.encoding = "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")
    mapping: dict[str, str] = {}
    for row in soup.find_all("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all(("td", "th"))]
        codes = [value for value in cells if value.isdigit() and len(value) == 6]
        current = [value for value in codes if value.startswith("920")]
        legacy = [value for value in codes if not value.startswith("920")]
        if legacy and current:
            mapping[legacy[-1]] = current[-1]
    if not mapping:
        raise RuntimeError("BSE code mapping page did not contain any old/new code pairs.")
    return mapping


def get_bse_code_mapping(
    *,
    refresh: bool = False,
    offline: bool = False,
) -> tuple[dict[str, str], bool]:
    cached = _read_cache()
    if not refresh:
        if cached is not None:
            return cached, True
    if offline:
        return cached or {}, bool(cached)
    try:
        mapping = _fetch_mapping()
    except (requests.RequestException, RuntimeError):
        if cached is not None:
            return cached, True
        raise
    _write_cache(mapping)
    return mapping, False


def canonicalize_bse_symbol(
    symbol: str,
    *,
    refresh: bool = False,
    offline: bool = False,
) -> dict[str, object]:
    code = str(symbol).strip().upper().replace("BJ", "").replace(".", "")
    if code.startswith("920"):
        return {
            "symbol": code,
            "input_symbol": symbol,
            "alias_resolved": False,
            "mapping_cache_hit": True,
        }
    mapping, cache_hit = get_bse_code_mapping(refresh=refresh, offline=offline)
    canonical = mapping.get(code, code)
    return {
        "symbol": canonical,
        "input_symbol": symbol,
        "legacy_symbol": code if canonical != code else None,
        "alias_resolved": canonical != code,
        "mapping_cache_hit": cache_hit,
    }
