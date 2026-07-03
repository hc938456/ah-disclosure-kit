from __future__ import annotations

import time
from typing import Any

from ah_disclosure.core.cache import read_cache, write_cache
from ah_disclosure.core.config import get_settings
from ah_disclosure.core.time_utils import now_iso
from ah_disclosure.models import CompanyDataResult
from ah_disclosure.providers.akshare_registry import H_INTERFACES, get_akshare_function
from ah_disclosure.providers.dataframe_utils import dataframe_to_records, row_count


def normalize_h_symbol(symbol: str) -> str:
    text = str(symbol).strip().upper().replace("HK", "").replace(".", "")
    return text.zfill(5) if text.isdigit() else text


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
        data["truncated"] = bool(data.get("total_rows") is not None and max_rows is not None and int(data["total_rows"]) > len(rows))
    return CompanyDataResult(**data)


class HCompanyClient:
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

    def call_interface(self, data_type: str, symbol: str, max_rows: int | None = None, **params: Any) -> CompanyDataResult:
        interface = H_INTERFACES.get(data_type, data_type)
        func = get_akshare_function(interface)
        call_params = self._build_params(interface, symbol, dict(params))
        cache_params = {
            "symbol": normalize_h_symbol(symbol),
            "data_type": data_type,
            "interface": interface,
            "call_params": call_params,
        }
        settings = get_settings()
        cached = read_cache("akshare_h", interface, cache_params, settings.akshare_ttl_days)
        if isinstance(cached, dict):
            cached.setdefault("params", {})["cache_hit"] = True
            return _with_row_limit(cached, max_rows)
        try:
            raw = self._call_with_retries(func, call_params)
        except Exception as exc:
            stale = read_cache("akshare_h", interface, cache_params, 3650)
            if isinstance(stale, dict):
                stale.setdefault("params", {})["cache_stale"] = True
                stale["params"]["cache_error"] = f"{type(exc).__name__}: {exc}"
                return _with_row_limit(stale, max_rows)
            return CompanyDataResult(
                "H",
                normalize_h_symbol(symbol),
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
        total_rows = row_count(raw)
        rows, cols = dataframe_to_records(raw, max_rows=None)
        result = CompanyDataResult(
            "H",
            normalize_h_symbol(symbol),
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
        write_cache("akshare_h", interface, cache_params, result.to_dict())
        return _with_row_limit(result.to_dict(), max_rows)

    def _build_params(self, interface: str, symbol: str, params: dict[str, Any]) -> dict[str, Any]:
        code = normalize_h_symbol(symbol)
        if interface == "stock_financial_hk_report_em":
            statement = params.pop("statement", params.pop("symbol_type", "资产负债表"))
            indicator = params.pop("indicator", "年度")
            return {"stock": code, "symbol": statement, "indicator": indicator, **params}
        if interface == "stock_financial_hk_analysis_indicator_em":
            return {"symbol": code, "indicator": params.pop("indicator", "年度"), **params}
        return {"symbol": code, **params}

    def get_company_profile(self, symbol: str, **params: Any) -> dict[str, Any]:
        return self.call_interface("company_profile", symbol, **params).to_dict()

    def get_security_profile(self, symbol: str, **params: Any) -> dict[str, Any]:
        return self.call_interface("security_profile", symbol, **params).to_dict()

    def get_financial_statements(self, symbol: str, statement: str = "all", indicator: str = "年度", **params: Any) -> dict[str, Any]:
        mapping = {
            "balance": "资产负债表",
            "income": "利润表",
            "profit": "利润表",
            "cashflow": "现金流量表",
            "cash_flow": "现金流量表",
        }
        if statement == "all":
            return {
                "market": "H",
                "symbol": normalize_h_symbol(symbol),
                "statements": {
                    name: self.call_interface("financial_statement", symbol, statement=name, indicator=indicator, **params).to_dict()
                    for name in ["资产负债表", "利润表", "现金流量表"]
                },
            }
        return self.call_interface(
            "financial_statement", symbol, statement=mapping.get(statement, statement), indicator=indicator, **params
        ).to_dict()

    def get_financial_indicators(self, symbol: str, **params: Any) -> dict[str, Any]:
        return self.call_interface("financial_indicators", symbol, **params).to_dict()

    def get_dividends(self, symbol: str, **params: Any) -> dict[str, Any]:
        return self.call_interface("dividends", symbol, **params).to_dict()
