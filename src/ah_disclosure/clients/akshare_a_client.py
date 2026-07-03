from __future__ import annotations

import time
from typing import Any

import requests

from ah_disclosure.core.cache import read_cache, write_cache
from ah_disclosure.core.config import get_settings
from ah_disclosure.core.time_utils import now_iso
from ah_disclosure.models import CompanyDataResult
from ah_disclosure.providers.akshare_registry import A_INTERFACES, get_akshare_function
from ah_disclosure.providers.dataframe_utils import dataframe_to_records, row_count


ALL_MARKET_CODE_INTERFACES = {
    "stock_repurchase_em",
    "stock_esg_hz_sina",
}

DIRECT_FILTER_INTERFACES = {
    "stock_repurchase_em",
    "stock_esg_hz_sina",
}


def normalize_a_symbol(symbol: str, with_exchange: bool = False, exchange: str | None = None) -> str:
    code = str(symbol).strip().upper().replace("SH", "").replace("SZ", "")
    if not with_exchange:
        return code
    if exchange:
        return f"{exchange.upper()}{code}"
    return f"SH{code}" if code.startswith(("6", "9")) else f"SZ{code}"


def _with_row_limit(payload: dict[str, Any], max_rows: int | None) -> CompanyDataResult:
    data = {**payload}
    rows = list(data.get("rows") or [])
    data["columns"] = list(data.get("columns") or [])
    data["params"] = dict(data.get("params") or {})
    if max_rows is not None and len(rows) > max_rows:
        data["rows"] = rows[:max_rows]
        data["returned_rows"] = max_rows
        data["truncated"] = True
    else:
        data["rows"] = rows
        data["returned_rows"] = len(rows)
        total_rows = data.get("total_rows")
        data["truncated"] = bool(total_rows is not None and max_rows is not None and int(total_rows) > len(rows))
    return CompanyDataResult(**data)


class ACompanyClient:
    source = "AKShare"

    def _call_with_retries(self, func, call_params: dict[str, Any], attempts: int = 2) -> Any:
        last_exc: Exception | None = None
        for attempt in range(attempts):
            try:
                return func(**call_params)
            except Exception as exc:
                last_exc = exc
                if attempt + 1 < attempts:
                    time.sleep(1.5 * (attempt + 1))
        if last_exc:
            raise last_exc
        raise RuntimeError("AKShare call failed without an exception.")

    def _stock_repurchase_filtered(self, symbol: str) -> list[dict[str, Any]]:
        code = normalize_a_symbol(symbol)
        url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
        params = {
            "sortColumns": "UPD,DIM_DATE,DIM_SCODE",
            "sortTypes": "-1,-1,-1",
            "pageSize": "50",
            "pageNumber": "1",
            "reportName": "RPTA_WEB_GETHGLIST_NEW",
            "columns": "ALL",
            "source": "WEB",
            "filter": f'(DIM_SCODE="{code}")',
        }
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        return list(((data.get("result") or {}).get("data") or []))

    def _stock_esg_filtered(self, symbol: str) -> list[dict[str, Any]]:
        code = normalize_a_symbol(symbol)
        dotted_code = f"{code}.SH" if code.startswith(("6", "9")) else f"{code}.SZ"
        url = "https://global.finance.sina.com.cn/api/openapi.php/EsgService.getHzEsgStocks"
        page = 1
        total_pages = 1
        matches: list[dict[str, Any]] = []
        while page <= total_pages:
            resp = requests.get(url, params={"p": str(page), "num": "100"}, timeout=20)
            resp.raise_for_status()
            payload = ((resp.json().get("result") or {}).get("data") or {})
            if page == 1:
                total = int(payload.get("total") or 0)
                total_pages = max(1, (total + 99) // 100)
            for row in payload.get("data") or []:
                if str(row.get("symbol") or "").upper() == dotted_code:
                    matches.append(
                        {
                            "日期": row.get("date"),
                            "股票代码": row.get("symbol"),
                            "交易市场": row.get("market"),
                            "股票名称": row.get("name"),
                            "ESG评分": row.get("esg_score"),
                            "ESG等级": row.get("esg_score_grade"),
                            "环境": row.get("e_score"),
                            "环境等级": row.get("e_score_grade"),
                            "社会": row.get("s_score"),
                            "社会等级": row.get("s_score_grade"),
                            "公司治理": row.get("g_score"),
                            "公司治理等级": row.get("g_score_grade"),
                        }
                    )
            if matches:
                return matches
            page += 1
        return matches

    def call_interface(self, data_type: str, symbol: str, max_rows: int | None = None, **params: Any) -> CompanyDataResult:
        interface = A_INTERFACES.get(data_type, data_type)
        func = None if interface in DIRECT_FILTER_INTERFACES else get_akshare_function(interface)
        call_params = self._build_params(interface, symbol, dict(params))
        cache_params = {
            "symbol": normalize_a_symbol(symbol),
            "data_type": data_type,
            "interface": interface,
            "call_params": call_params,
        }
        settings = get_settings()
        cached = read_cache("akshare_a", interface, cache_params, settings.akshare_ttl_days)
        if isinstance(cached, dict):
            cached.setdefault("params", {})["cache_hit"] = True
            return _with_row_limit(cached, max_rows)
        try:
            if interface == "stock_repurchase_em":
                raw = self._stock_repurchase_filtered(symbol)
            elif interface == "stock_esg_hz_sina":
                raw = self._stock_esg_filtered(symbol)
            else:
                raw = self._call_with_retries(func, call_params)
        except Exception as exc:
            stale = read_cache("akshare_a", interface, cache_params, 3650)
            if isinstance(stale, dict):
                stale.setdefault("params", {})["cache_stale"] = True
                stale["params"]["cache_error"] = f"{type(exc).__name__}: {exc}"
                return _with_row_limit(stale, max_rows)
            return CompanyDataResult(
                "A",
                normalize_a_symbol(symbol),
                data_type,
                interface,
                self.source,
                now_iso(),
                [{"error": f"{type(exc).__name__}: {exc}"}],
                ["error"],
                {**call_params, "error": f"{type(exc).__name__}: {exc}"},
                total_rows=0,
                returned_rows=1,
                truncated=False,
            )
        if interface in ALL_MARKET_CODE_INTERFACES:
            raw = self._filter_all_market_rows(raw, symbol)
        total_rows = row_count(raw)
        rows, cols = dataframe_to_records(raw, max_rows=None)
        result = CompanyDataResult(
            "A",
            normalize_a_symbol(symbol),
            data_type,
            interface,
            self.source,
            now_iso(),
            rows,
            cols,
            call_params,
            total_rows=total_rows,
            returned_rows=len(rows),
            truncated=False,
        )
        write_cache("akshare_a", interface, cache_params, result.to_dict())
        return _with_row_limit(result.to_dict(), max_rows)

    def _filter_all_market_rows(self, raw: Any, symbol: str) -> Any:
        code = normalize_a_symbol(symbol)
        exchange_code = normalize_a_symbol(symbol, with_exchange=True)
        dotted_code = f"{code}.SH" if code.startswith(("6", "9")) else f"{code}.SZ"
        targets = {code, exchange_code, dotted_code}

        def value_matches(value: Any) -> bool:
            text = str(value).strip().upper()
            return text in targets

        try:
            import pandas as pd

            if isinstance(raw, pd.DataFrame):
                mask = raw.apply(lambda row: any(value_matches(value) for value in row), axis=1)
                return raw.loc[mask].copy()
        except Exception:
            return raw
        if isinstance(raw, list):
            return [row for row in raw if isinstance(row, dict) and any(value_matches(value) for value in row.values())]
        return raw

    def _build_params(self, interface: str, symbol: str, params: dict[str, Any]) -> dict[str, Any]:
        code = normalize_a_symbol(symbol)
        exch = normalize_a_symbol(symbol, with_exchange=True)
        if interface in {
            "stock_balance_sheet_by_report_em",
            "stock_profit_sheet_by_report_em",
            "stock_cash_flow_sheet_by_report_em",
            "stock_zygc_em",
        }:
            return {"symbol": exch, **params}
        if interface == "stock_financial_analysis_indicator":
            start_year = params.pop("start_year", None)
            if start_year is not None:
                params["start_year"] = str(start_year)
            return {"symbol": code, **params}
        if interface in {
            "stock_hold_num_cninfo",
            "stock_gdfx_free_holding_detail_em",
            "stock_repurchase_em",
            "stock_hold_management_detail_em",
            "stock_gddh_em",
            "stock_esg_hz_sina",
            "stock_zdhtmx_em",
            "stock_yjbb_em",
            "stock_yjkb_em",
            "stock_yjyg_em",
        }:
            return params
        return {"symbol": code, **params}

    def get_company_profile(self, symbol: str, **params: Any) -> dict[str, Any]:
        return self.call_interface("company_profile", symbol, **params).to_dict()

    def get_business_info(self, symbol: str, composition: bool = True, **params: Any) -> dict[str, Any]:
        key = "business_composition" if composition else "business_description"
        return self.call_interface(key, symbol, **params).to_dict()

    def get_financial_statements(self, symbol: str, statement: str = "all", **params: Any) -> dict[str, Any]:
        mapping = {
            "balance": "balance_sheet",
            "income": "income_statement",
            "profit": "income_statement",
            "cashflow": "cashflow_statement",
            "cash_flow": "cashflow_statement",
        }
        if statement == "all":
            return {
                "market": "A",
                "symbol": normalize_a_symbol(symbol),
                "statements": {
                    "balance": self.call_interface("balance_sheet", symbol, **params).to_dict(),
                    "income": self.call_interface("income_statement", symbol, **params).to_dict(),
                    "cashflow": self.call_interface("cashflow_statement", symbol, **params).to_dict(),
                },
            }
        return self.call_interface(mapping.get(statement, statement), symbol, **params).to_dict()

    def get_financial_indicators(self, symbol: str, **params: Any) -> dict[str, Any]:
        return self.call_interface("financial_indicators", symbol, **params).to_dict()

    def get_dividends(self, symbol: str, **params: Any) -> dict[str, Any]:
        return self.call_interface("dividends", symbol, **params).to_dict()

    def get_shareholders(self, symbol: str, data_type: str = "shareholder_count", **params: Any) -> dict[str, Any]:
        return self.call_interface(data_type, symbol, **params).to_dict()

    def get_capital_actions(self, symbol: str, data_type: str = "repurchase", **params: Any) -> dict[str, Any]:
        return self.call_interface(data_type, symbol, **params).to_dict()

    def get_governance_esg(self, symbol: str, data_type: str = "esg", **params: Any) -> dict[str, Any]:
        return self.call_interface(data_type, symbol, **params).to_dict()
