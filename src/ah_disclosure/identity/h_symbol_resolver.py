from __future__ import annotations


def normalize_h_symbol(symbol: str) -> str:
    text = str(symbol).strip().upper().replace("HK", "").replace(".", "")
    return text.zfill(5) if text.isdigit() else text


def resolve_h_symbol(symbol: str) -> dict:
    return {"market": "H", "symbol": normalize_h_symbol(symbol), "exchange": "HKEX", "input": symbol}
