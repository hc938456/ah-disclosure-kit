from __future__ import annotations


def normalize_a_symbol(symbol: str) -> str:
    return str(symbol).strip().upper().replace("SH", "").replace("SZ", "")


def resolve_a_symbol(symbol: str) -> dict:
    code = normalize_a_symbol(symbol)
    exchange = "SSE" if code.startswith(("6", "9")) else "SZSE"
    return {"market": "A", "symbol": code, "exchange": exchange, "input": symbol}
