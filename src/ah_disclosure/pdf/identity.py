from __future__ import annotations

import re
from typing import Any

from ah_disclosure.models import PdfPage


COMPANY_TOKEN_STOPWORDS = {
    "company",
    "corporation",
    "group",
    "holdings",
    "holding",
    "limited",
    "ltd",
    "inc",
    "plc",
    "股份有限公司",
    "有限公司",
    "集团",
}


def _compact(text: Any) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(text or "").casefold())


def _company_tokens(company_name: str | None) -> list[str]:
    normalized = str(company_name or "").casefold()
    for suffix in ("股份有限公司", "有限公司", "控股集团", "控股集團", "集团", "集團"):
        normalized = normalized.replace(suffix, " ")
    raw_tokens = re.findall(r"[0-9a-z]+|[\u4e00-\u9fff]+", normalized)
    return [
        token
        for token in raw_tokens
        if token not in COMPANY_TOKEN_STOPWORDS and len(_compact(token)) >= 3
    ]


def validate_document_identity(
    pages: list[PdfPage],
    expected_year: int | None = None,
    expected_company_name: str | None = None,
    expected_symbol: str | None = None,
) -> dict[str, Any]:
    text = "\n".join(page.text for page in pages)
    compact_text = _compact(text)
    year_match = None if expected_year is None else str(expected_year) in text
    tokens = _company_tokens(expected_company_name)
    company_match = None if not tokens else any(_compact(token) in compact_text for token in tokens)
    normalized_symbol = str(expected_symbol or "").strip().upper().replace(".HK", "")
    symbol_digits = normalized_symbol.lstrip("0") or normalized_symbol
    symbol_match = None
    if normalized_symbol:
        exact_code = re.search(rf"(?<!\d){re.escape(normalized_symbol)}(?!\d)", text, flags=re.IGNORECASE)
        labeled_code = re.search(
            rf"(?:stock\s*code|股份代[號号]|股票代[碼码]|證券代碼|证券代码)"
            rf"[^0-9]{{0,24}}0*{re.escape(symbol_digits)}(?!\d)",
            text,
            flags=re.IGNORECASE,
        )
        symbol_match = bool(exact_code or labeled_code)

    year_ok = year_match is not False
    issuer_signals = [signal for signal in (company_match, symbol_match) if signal is not None]
    issuer_ok = True if not issuer_signals else any(issuer_signals)
    return {
        "passed": year_ok and issuer_ok,
        "expected_year": expected_year,
        "year_match": year_match,
        "expected_company_name": expected_company_name,
        "company_tokens": tokens,
        "company_match": company_match,
        "expected_symbol": expected_symbol,
        "symbol_match": symbol_match,
    }
