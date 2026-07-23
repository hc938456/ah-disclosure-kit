from __future__ import annotations

import math
import time
from typing import Any

import requests

from ah_disclosure.core.cache import read_cache, write_cache
from ah_disclosure.core.config import get_settings
from ah_disclosure.identity.bse_symbol_resolver import canonicalize_bse_symbol
from ah_disclosure.models import ProspectusRecord
from ah_disclosure.providers.akshare_registry import IPO_INTERFACES, get_akshare_function
from ah_disclosure.providers.dataframe_utils import dataframe_to_records


def _none(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if value != value:
            return None
    except Exception:
        pass
    text = str(value).strip()
    return text or None


def _row_value(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row:
            return row.get(key)
    return None


class EastmoneyIpoClient:
    source = "Eastmoney via AKShare"

    def search_bse_listed_prospectus(
        self,
        symbol: str,
        company_name: str,
        max_rows: int = 20,
    ) -> list[ProspectusRecord]:
        """Search historical BSE prospectuses through Eastmoney announcements."""
        normalized = str(symbol).strip()
        current_code = str(canonicalize_bse_symbol(normalized)["symbol"])
        url = "https://np-anotice-stock.eastmoney.com/api/security/ann"
        records: list[ProspectusRecord] = []
        # The endpoint occasionally returns an empty first page without total_hits.
        # Start with the safety cap and narrow it only after a non-zero total arrives.
        page_count = 15
        for page_index in range(1, 16):
            if page_index > page_count:
                break
            response = requests.get(
                url,
                params={
                    "sr": "-1",
                    "page_size": "100",
                    "page_index": str(page_index),
                    "ann_type": "A",
                    "client_source": "web",
                    "stock_list": current_code,
                },
                timeout=20,
            )
            response.raise_for_status()
            response.encoding = "utf-8"
            data = response.json().get("data") or {}
            total_hits = int(data.get("total_hits") or 0)
            if total_hits:
                page_count = max(math.ceil(total_hits / 100), 1)
            for row in data.get("list") or []:
                title = str(row.get("title_ch") or row.get("title") or "")
                if "招股说明书" not in title or "摘要" in title:
                    continue
                art_code = str(row.get("art_code") or "")
                if not art_code:
                    continue
                records.append(
                    ProspectusRecord(
                        market="A",
                        symbol=normalized,
                        company_name=company_name,
                        board="北交所",
                        document_type="招股说明书",
                        title=title,
                        publish_date=_none(row.get("notice_date")),
                        source="Eastmoney announcements",
                        source_url=(
                            "https://xinsanban.eastmoney.com/Article/NoticeContent"
                            f"?id={art_code}"
                        ),
                        pdf_url=f"https://pdf.dfcfw.com/pdf/H2_{art_code}_1.pdf",
                    )
                )
                if len(records) >= max_rows:
                    return records
            if records:
                return records
        return records

    def _fetch_rows_for_company(self, company_keyword: str) -> list[dict[str, Any]]:
        func_name = "stock_register_all_em"
        cache_params = {"interface": func_name, "company_keyword": company_keyword}
        settings = get_settings()
        cached = read_cache("eastmoney_ipo", f"{func_name}_company", cache_params, settings.akshare_ttl_days)
        if isinstance(cached, list):
            return cached
        url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
        params = {
            "sortColumns": "UPDATE_DATE,ORG_CODE",
            "sortTypes": "-1,-1",
            "pageSize": "50",
            "pageNumber": "1",
            "reportName": "RPT_IPO_INFOALLNEW",
            "columns": "SECURITY_CODE,STATE,REG_ADDRESS,INFO_CODE,CSRC_INDUSTRY,ACCEPT_DATE,DECLARE_ORG,"
            "PREDICT_LISTING_MARKET,LAW_FIRM,ACCOUNT_FIRM,ORG_CODE,UPDATE_DATE,RECOMMEND_ORG,IS_REGISTRATION",
            "source": "WEB",
            "client": "WEB",
            "filter": f'(DECLARE_ORG like "%{company_keyword}%")',
        }
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        result = (resp.json().get("result") or {})
        rows = list(result.get("data") or [])
        write_cache("eastmoney_ipo", f"{func_name}_company", cache_params, rows)
        return rows

    def _fetch_rows(self, func_name: str) -> list[dict[str, Any]]:
        cache_params = {"interface": func_name}
        settings = get_settings()
        cached = read_cache("eastmoney_ipo", func_name, cache_params, settings.akshare_ttl_days)
        if isinstance(cached, list):
            return cached
        func = get_akshare_function(func_name)
        last_exc: Exception | None = None
        for attempt in range(2):
            try:
                raw = func()
                rows, _ = dataframe_to_records(raw)
                write_cache("eastmoney_ipo", func_name, cache_params, rows)
                return rows
            except Exception as exc:
                last_exc = exc
                if attempt == 0:
                    time.sleep(1.5)
        stale = read_cache("eastmoney_ipo", func_name, cache_params, 3650)
        if isinstance(stale, list):
            return stale
        if last_exc:
            raise last_exc
        raise RuntimeError(f"{func_name} failed without an exception.")

    def search_ipo_prospectus(
        self,
        company_keyword: str = "",
        board: str = "all",
        status_keyword: str = "",
        max_rows: int = 20,
        symbol: str | None = None,
    ) -> list[ProspectusRecord]:
        func_name = IPO_INTERFACES.get(board, board)
        try:
            rows = self._fetch_rows_for_company(company_keyword) if company_keyword and board == "all" else self._fetch_rows(func_name)
        except Exception as exc:
            return [
                ProspectusRecord(
                    market="A",
                    company_name=company_keyword or "",
                    board=board,
                    stage=f"fetch_error: {type(exc).__name__}: {exc}",
                    document_type="招股说明书",
                    title=f"{company_keyword or 'A-share IPO'} 招股说明书".strip(),
                    source=self.source,
                )
            ]
        if company_keyword:
            rows = [r for r in rows if company_keyword.lower() in str(_row_value(r, "企业名称", "DECLARE_ORG") or "").lower()]
        if status_keyword:
            rows = [r for r in rows if status_keyword.lower() in str(_row_value(r, "最新状态", "STATE") or "").lower()]
        records: list[ProspectusRecord] = []
        for row in rows[:max_rows]:
            info_code = _none(_row_value(row, "招股说明书", "INFO_CODE"))
            records.append(
                ProspectusRecord(
                    market="A",
                    company_name=_none(_row_value(row, "企业名称", "DECLARE_ORG")) or "",
                    symbol=symbol,
                    board=_none(_row_value(row, "拟上市地点", "PREDICT_LISTING_MARKET")),
                    stage=_none(_row_value(row, "最新状态", "STATE")),
                    document_type="招股说明书",
                    title=f"{_none(_row_value(row, '企业名称', 'DECLARE_ORG')) or ''} 招股说明书".strip(),
                    publish_date=_none(_row_value(row, "更新日期", "UPDATE_DATE")) or _none(_row_value(row, "受理日期", "ACCEPT_DATE")),
                    status=_none(_row_value(row, "最新状态", "STATE")),
                    sponsor=_none(_row_value(row, "保荐机构", "RECOMMEND_ORG")),
                    law_firm=_none(_row_value(row, "律师事务所", "LAW_FIRM")),
                    accounting_firm=_none(_row_value(row, "会计师事务所", "ACCOUNT_FIRM")),
                    source=self.source,
                    source_url=None,
                    pdf_url=info_code if str(info_code or "").startswith(("http://", "https://")) else f"https://pdf.dfcfw.com/pdf/H2_{info_code}_1.pdf" if info_code else None,
                )
            )
        return records
