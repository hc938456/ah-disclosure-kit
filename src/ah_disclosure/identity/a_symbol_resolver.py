from __future__ import annotations

from ah_disclosure.identity.bse_symbol_resolver import canonicalize_bse_symbol


def normalize_a_symbol(symbol: str) -> str:
    return (
        str(symbol)
        .strip()
        .upper()
        .replace("SH", "")
        .replace("SZ", "")
        .replace("BJ", "")
        .replace(".", "")
    )


def resolve_a_symbol(
    symbol: str,
    *,
    refresh: bool = False,
    offline: bool = False,
) -> dict:
    code = normalize_a_symbol(symbol)
    if code.startswith(("4", "8", "920")):
        exchange = "BSE"
        bse_identity = canonicalize_bse_symbol(code, refresh=refresh, offline=offline)
        code = str(bse_identity["symbol"])
    elif code.startswith(("6", "9")):
        exchange = "SSE"
        bse_identity = {}
    else:
        exchange = "SZSE"
        bse_identity = {}
    return {
        "market": "A",
        "symbol": code,
        "exchange": exchange,
        "input": symbol,
        **bse_identity,
    }
