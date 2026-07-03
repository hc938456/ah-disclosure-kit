from __future__ import annotations

from ah_disclosure.services.company_data_service import get_company_profile, get_financial_indicators, get_financial_statements
from ah_disclosure.services.financial_query import requested_financial_statement, wants_financial_indicators
from ah_disclosure.services.local_search_service import LocalSearchService
from ah_disclosure.services.query_router import route_query

UNSUPPORTED_ROUTE_MESSAGES = {
    "unsupported_hk_ipo_annual_list": "ah-disclosure does not support complete structured full-year Hong Kong IPO/new-listing company lists. Use external sources only after stating this capability boundary.",
}


def _structured_payload_for_query(query: str, route: str, market: str, symbol: str) -> dict | None:
    q = str(query or "").casefold()
    if route == "structured_profile":
        return {"profile": get_company_profile(market, symbol)}
    if route == "structured_financials":
        payload: dict = {}
        requested_statement = requested_financial_statement(q)
        if requested_statement:
            result_key, statement = requested_statement
            payload[result_key] = get_financial_statements(market, symbol, statement=statement, max_rows=80)
        if wants_financial_indicators(q):
            payload["financial_indicators"] = get_financial_indicators(market, symbol, max_rows=80)
        if not payload:
            payload["income_statement"] = get_financial_statements(market, symbol, statement="income", max_rows=80)
        return payload
    return None


def get_evidence_packet(query: str, market: str | None = None, symbol: str | None = None, document_id: str | None = None, max_pages: int = 8, max_chars: int = 12000, include_structured_data: bool = True, strategy: str = "auto", include_retrieval_plan: bool = False) -> dict:
    route = route_query(query)
    if route["route"] in UNSUPPORTED_ROUTE_MESSAGES:
        return {
            "query": query,
            "route": route["route"],
            "market": market,
            "symbol": symbol,
            "evidence_items": [],
            "token_estimate": 1,
            "max_chars": max_chars,
            "truncated": False,
            "unsupported": True,
            "message": UNSUPPORTED_ROUTE_MESSAGES[route["route"]],
        }
    structured = None
    if include_structured_data and market and symbol and route["route"].startswith("structured"):
        try:
            structured = _structured_payload_for_query(query, route["route"], market, symbol)
        except Exception as exc:
            structured = {"error": str(exc)}
    packet = LocalSearchService().evidence_packet(query, market=market, symbol=symbol, document_id=document_id, max_pages=max_pages, max_chars=max_chars, structured_data=structured, strategy=strategy, include_retrieval_plan=include_retrieval_plan)
    packet["route"] = route["route"]
    return packet
