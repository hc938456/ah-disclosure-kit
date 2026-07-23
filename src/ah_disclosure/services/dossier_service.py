from __future__ import annotations

from typing import Any

from ah_disclosure.services.company_data_service import get_company_profile, get_dividends, get_financial_indicators, get_financial_statements
from ah_disclosure.services.evidence_service import get_evidence_packet
from ah_disclosure.services.financial_query import requested_financial_statement
from ah_disclosure.services.query_router import route_query

UNSUPPORTED_ROUTES = {"unsupported_hk_ipo_annual_list"}


def _fetch_into(target: dict, key: str, func, market: str, symbol: str, **params) -> None:
    try:
        target[key] = func(market, symbol, **params)
    except Exception as exc:
        target[key] = {"error": str(exc)}


def build_company_dossier(market: str, symbol: str, query: str = "", document_id: str | None = None) -> dict:
    dossier: dict[str, Any] = {"market": market, "symbol": symbol, "evidence": None}
    route = route_query(query)["route"] if query else "default"
    if route in UNSUPPORTED_ROUTES:
        dossier["unsupported"] = True
        dossier["route"] = route
        dossier["evidence"] = get_evidence_packet(query, market=market, symbol=symbol, document_id=document_id, include_structured_data=False) if query else None
        return dossier
    if route == "structured_financials":
        result_key, statement = requested_financial_statement(query) or ("income_statement", "income")
        _fetch_into(dossier, result_key, get_financial_statements, market, symbol, statement=statement, max_rows=80)
        _fetch_into(dossier, "financial_indicators", get_financial_indicators, market, symbol, max_rows=80)
    elif route == "structured_profile":
        _fetch_into(dossier, "profile", get_company_profile, market, symbol, max_rows=80)
    elif route == "structured_company_data":
        _fetch_into(dossier, "dividends", get_dividends, market, symbol, max_rows=80)
    else:
        for key, func in [("profile", get_company_profile), ("financial_indicators", get_financial_indicators), ("dividends", get_dividends)]:
            _fetch_into(dossier, key, func, market, symbol)
    if query:
        dossier["evidence"] = get_evidence_packet(query, market=market, symbol=symbol, document_id=document_id, include_structured_data=False)
    return dossier


def compare_structured_data_with_report(market: str, symbol: str, query: str, document_id: str | None = None) -> dict:
    structured = build_company_dossier(market, symbol, query)
    structured.pop("evidence", None)
    return {
        "market": market,
        "symbol": symbol,
        "structured": structured,
        "evidence": get_evidence_packet(query, market=market, symbol=symbol, document_id=document_id, include_structured_data=False),
    }
