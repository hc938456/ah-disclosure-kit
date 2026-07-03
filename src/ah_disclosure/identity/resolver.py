from __future__ import annotations

from ah_disclosure.identity.a_symbol_resolver import resolve_a_symbol
from ah_disclosure.identity.h_symbol_resolver import resolve_h_symbol


def resolve_company(symbol: str, market: str | None = None) -> dict:
    text = str(symbol).strip()
    if market:
        return resolve_h_symbol(text) if market.upper().startswith("H") else resolve_a_symbol(text)
    if text.upper().startswith("HK") or (text.isdigit() and len(text) == 5):
        return resolve_h_symbol(text)
    return resolve_a_symbol(text)
