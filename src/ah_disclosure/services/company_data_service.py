from __future__ import annotations

from ah_disclosure.clients.akshare_a_client import ACompanyClient
from ah_disclosure.clients.akshare_h_client import HCompanyClient
from ah_disclosure.storage.sqlite_store import SQLiteStore


def _persist(result: dict) -> dict:
    try:
        SQLiteStore().insert_company_data(result)
    except Exception:
        pass
    return result


def get_company_profile(market: str, symbol: str, **params) -> dict:
    result = HCompanyClient().get_company_profile(symbol, **params) if market.upper().startswith("H") else ACompanyClient().get_company_profile(symbol, **params)
    return _persist(result)


def get_business_info(market: str, symbol: str, **params) -> dict:
    if market.upper().startswith("H"):
        return get_company_profile(market, symbol, **params)
    return _persist(ACompanyClient().get_business_info(symbol, **params))


def get_financial_statements(market: str, symbol: str, statement: str = "all", **params) -> dict:
    result = HCompanyClient().get_financial_statements(symbol, statement=statement, **params) if market.upper().startswith("H") else ACompanyClient().get_financial_statements(symbol, statement=statement, **params)
    return _persist(result)


def get_financial_indicators(market: str, symbol: str, **params) -> dict:
    result = HCompanyClient().get_financial_indicators(symbol, **params) if market.upper().startswith("H") else ACompanyClient().get_financial_indicators(symbol, **params)
    return _persist(result)


def get_dividends(market: str, symbol: str, **params) -> dict:
    result = HCompanyClient().get_dividends(symbol, **params) if market.upper().startswith("H") else ACompanyClient().get_dividends(symbol, **params)
    return _persist(result)


def get_shareholders(market: str, symbol: str, **params) -> dict:
    if market.upper().startswith("H"):
        return {"market": "H", "symbol": symbol, "data_type": "shareholders", "error": "HK shareholder wrappers are not exposed yet; use filings if needed."}
    return _persist(ACompanyClient().get_shareholders(symbol, **params))


def get_capital_actions(market: str, symbol: str, **params) -> dict:
    if market.upper().startswith("H"):
        return get_dividends(market, symbol, **params)
    return _persist(ACompanyClient().get_capital_actions(symbol, **params))


def get_governance_esg(market: str, symbol: str, **params) -> dict:
    if market.upper().startswith("H"):
        return {"market": "H", "symbol": symbol, "data_type": "governance_esg", "error": "HK governance/ESG wrapper is not exposed yet."}
    return _persist(ACompanyClient().get_governance_esg(symbol, **params))
