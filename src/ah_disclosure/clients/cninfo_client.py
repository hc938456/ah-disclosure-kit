from __future__ import annotations

import math
import json
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin

import requests

from ah_disclosure.core.config import get_settings
from ah_disclosure.core.file_utils import replace_file_with_retry
from ah_disclosure.core.paths import get_data_paths
from ah_disclosure.core.time_utils import current_date_yyyymmdd
from ah_disclosure.models import FilingRecord

CNINFO_BASE = "https://www.cninfo.com.cn"
CNINFO_STATIC_BASE = "https://static.cninfo.com.cn/"
CNINFO_QUERY_URL = f"{CNINFO_BASE}/new/hisAnnouncement/query"
CNINFO_TOP_SEARCH_URL = f"{CNINFO_BASE}/new/information/topSearch/query"
CNINFO_STOCK_URLS = {
    "沪深京": f"{CNINFO_BASE}/new/data/szse_stock.json",
    "港股": f"{CNINFO_BASE}/new/data/hke_stock.json",
}
COLUMN_MAP = {"沪深京": "szse", "港股": "hke"}
CATEGORY_MAP = {
    "年报": "category_ndbg_szsh",
    "半年报": "category_bndbg_szsh",
    "一季报": "category_yjdbg_szsh",
    "三季报": "category_sjdbg_szsh",
    "首发": "category_sf_szsh",
    "中介报告": "category_zj_szsh",
    "董事会": "category_dshgg_szsh",
    "股东大会": "category_gddh_szsh",
    "公司债": "category_gszq_szsh",
    "可转债": "category_kzzq_szsh",
    "其他融资": "category_qtrz_szsh",
    "补充更正": "category_bcgz_szsh",
}
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Referer": f"{CNINFO_BASE}/new/commonUrl/pageOfSearch?url=disclosure/list/search",
    "Accept": "application/json, text/plain, */*",
}


class CninfoSourceLookupError(RuntimeError):
    """Raised when a CNINFO source request fails before results are available."""

    code = "cninfo_source_lookup_error"
    source = "CNINFO"

    def __init__(
        self,
        message: str,
        *,
        operation: str,
        budget_seconds: float,
    ) -> None:
        super().__init__(message)
        self.operation = operation
        self.budget_seconds = float(budget_seconds)


class CninfoLookupTimeoutError(CninfoSourceLookupError, TimeoutError):
    """Raised when a CNINFO source lookup exhausts its bounded network budget."""

    code = "cninfo_source_lookup_timeout"


def _org_map_cache_path() -> Path:
    return get_data_paths().cache_resolver / "cninfo_org_map.json"


def _read_org_map_cache() -> dict[str, str]:
    path = _org_map_cache_path()
    max_age = get_settings().resolver_ttl_days * 86400
    if not path.exists() or time.time() - path.stat().st_mtime > max_age:
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {str(key): str(value) for key, value in payload.items() if key and value}
    except Exception:
        return {}


def _write_org_map_cache(mapping: dict[str, str]) -> None:
    path = _org_map_cache_path()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    replace_file_with_retry(tmp, path)


def _date(value: str) -> str:
    text = str(value).strip()
    if re.fullmatch(r"\d{8}", text):
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    raise ValueError(f"Date must be YYYYMMDD or YYYY-MM-DD: {value!r}")


def _clean(text: Any) -> str:
    raw = "" if text is None else str(text)
    raw = re.sub(r"</?em>", "", raw, flags=re.I)
    raw = re.sub(r"<[^>]+>", "", raw)
    return re.sub(r"\s+", " ", raw).strip()


def _time(value: Any) -> str:
    if not value:
        return ""
    try:
        import pandas as pd

        ts = pd.to_datetime(value, unit="ms", utc=True, errors="raise")
        return ts.tz_convert("Asia/Shanghai").tz_localize(None).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(value)


def _pdf_url(adjunct_url: str | None) -> str | None:
    if not adjunct_url:
        return None
    if adjunct_url.startswith("http://static.cninfo.com.cn/"):
        return "https://" + adjunct_url.removeprefix("http://")
    if adjunct_url.startswith(("http://", "https://")):
        return adjunct_url
    return urljoin(CNINFO_STATIC_BASE, adjunct_url.lstrip("/"))


def _detail_url(symbol: str, announcement_id: str, org_id: str, publish_time: str) -> str:
    return (
        f"{CNINFO_BASE}/new/disclosure/detail?stockCode={symbol}"
        f"&announcementId={announcement_id}&orgId={org_id}&announcementTime={quote(publish_time, safe='')}"
    )


class CninfoClient:
    def __init__(
        self,
        timeout: float | None = None,
        lookup_budget: float | None = None,
    ) -> None:
        settings = get_settings()
        self.timeout = float(
            settings.cninfo_request_timeout_seconds if timeout is None else timeout
        )
        self.lookup_budget = float(
            settings.cninfo_lookup_budget_seconds
            if lookup_budget is None
            else lookup_budget
        )
        if self.timeout <= 0:
            raise ValueError("CNINFO request timeout must be greater than zero")
        if self.lookup_budget <= 0:
            raise ValueError("CNINFO lookup budget must be greater than zero")
        self._deadline: float | None = None
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _timeout_for_request(self, operation: str) -> float:
        if self._deadline is None:
            return self.timeout
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise CninfoLookupTimeoutError(
                f"CNINFO source lookup exceeded its {self.lookup_budget:g}s internal "
                f"budget before {operation}.",
                operation=operation,
                budget_seconds=self.lookup_budget,
            )
        return min(self.timeout, max(remaining, 0.01))

    def _request(self, operation: str, method: Any, url: str, **kwargs: Any) -> Any:
        timeout = self._timeout_for_request(operation)
        try:
            response = method(url, timeout=timeout, **kwargs)
            response.raise_for_status()
        except requests.Timeout as exc:
            raise CninfoLookupTimeoutError(
                f"CNINFO timed out during {operation}; the request was bounded to "
                f"{timeout:g}s and the complete lookup budget is {self.lookup_budget:g}s.",
                operation=operation,
                budget_seconds=self.lookup_budget,
            ) from exc
        except requests.RequestException as exc:
            raise CninfoSourceLookupError(
                f"CNINFO request failed during {operation} "
                f"({type(exc).__name__}). Check network and proxy availability.",
                operation=operation,
                budget_seconds=self.lookup_budget,
            ) from exc
        if self._deadline is not None and time.monotonic() > self._deadline:
            raise CninfoLookupTimeoutError(
                f"CNINFO source lookup exceeded its {self.lookup_budget:g}s internal "
                f"budget during {operation}.",
                operation=operation,
                budget_seconds=self.lookup_budget,
            )
        return response

    def _response_json(self, response: Any, operation: str) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise CninfoSourceLookupError(
                f"CNINFO returned invalid JSON during {operation}.",
                operation=operation,
                budget_seconds=self.lookup_budget,
            ) from exc

    @lru_cache(maxsize=32)
    def get_stock_org_map(self, market: str = "沪深京") -> dict[str, str]:
        if market == "沪深京":
            cached = _read_org_map_cache()
            if cached:
                return cached
        resp = self._request(
            "stock-code resolver",
            self.session.get,
            CNINFO_STOCK_URLS[market],
        )
        mapping = {
            str(item.get("code")): str(item.get("orgId"))
            for item in self._response_json(resp, "stock-code resolver").get(
                "stockList", []
            )
            if item.get("code") and item.get("orgId")
        }
        if market == "沪深京":
            _write_org_map_cache(mapping)
        return mapping

    def lookup_stock_org_id(self, symbol: str) -> str | None:
        code = str(symbol).strip()
        resp = self._request(
            "stock-code fallback resolver",
            self.session.post,
            CNINFO_TOP_SEARCH_URL,
            data={"keyWord": code, "maxNum": "10"},
        )
        rows = self._response_json(resp, "stock-code fallback resolver")
        for item in rows if isinstance(rows, list) else []:
            if str(item.get("code") or "").strip() == code and item.get("orgId"):
                org_id = str(item["orgId"])
                mapping = self.get_stock_org_map()
                mapping[code] = org_id
                _write_org_map_cache(mapping)
                return org_id
        return None

    def search_filings(
        self,
        symbol: str = "",
        category: str = "年报",
        keyword: str = "",
        start_date: str = "20200101",
        end_date: str | None = None,
        market: str = "沪深京",
        max_rows: int = 20,
        page_size: int = 30,
        max_pages: int | None = None,
    ) -> list[FilingRecord]:
        previous_deadline = self._deadline
        lookup_deadline = time.monotonic() + self.lookup_budget
        self._deadline = (
            min(previous_deadline, lookup_deadline)
            if previous_deadline is not None
            else lookup_deadline
        )
        try:
            stock_item = ""
            if symbol:
                org_id = self.get_stock_org_map(market).get(str(symbol).strip())
                if not org_id and market == "沪深京":
                    org_id = self.lookup_stock_org_id(str(symbol).strip())
                if not org_id:
                    raise ValueError(f"Cannot resolve CNINFO orgId for symbol={symbol!r}")
                stock_item = f"{symbol},{org_id}"
            end_date = end_date or current_date_yyyymmdd()
            payload = {
                "pageNum": "1",
                "pageSize": str(page_size),
                "column": COLUMN_MAP.get(market, "szse"),
                "tabName": "fulltext",
                "plate": "",
                "stock": stock_item,
                "searchkey": keyword or "",
                "secid": "",
                "category": CATEGORY_MAP.get(
                    category,
                    category if category.startswith("category_") else "",
                ),
                "trade": "",
                "seDate": f"{_date(start_date)}~{_date(end_date)}",
                "sortName": "",
                "sortType": "",
                "isHLtitle": "true",
            }
            first = self._post(payload)
            total = int(first.get("totalAnnouncement") or 0)
            if total <= 0:
                return []
            pages = math.ceil(total / page_size)
            if max_pages is not None:
                pages = min(pages, max_pages)
            records: list[FilingRecord] = []
            for page in range(1, pages + 1):
                payload["pageNum"] = str(page)
                data = first if page == 1 else self._post(payload)
                for item in data.get("announcements", []) or []:
                    records.append(self._normalize(item, category))
                    if len(records) >= max_rows:
                        return records
            return records
        finally:
            self._deadline = previous_deadline

    def _post(self, payload: dict[str, str]) -> dict[str, Any]:
        resp = self._request(
            "announcement query",
            self.session.post,
            CNINFO_QUERY_URL,
            data=payload,
        )
        return self._response_json(resp, "announcement query")

    def _normalize(self, item: dict[str, Any], category: str) -> FilingRecord:
        symbol = str(item.get("secCode") or "")
        name = str(item.get("secName") or "")
        title = _clean(item.get("announcementTitle"))
        publish_time = _time(item.get("announcementTime"))
        announcement_id = str(item.get("announcementId") or "")
        org_id = str(item.get("orgId") or "")
        adjunct_url = str(item.get("adjunctUrl") or "") or None
        pdf = _pdf_url(adjunct_url)
        detail = _detail_url(symbol, announcement_id, org_id, publish_time) if symbol and announcement_id and org_id else None
        return FilingRecord(
            market="A",
            symbol=symbol,
            company_name=name,
            title=title,
            publish_time=publish_time,
            document_type=category,
            source="CNINFO",
            detail_url=detail,
            pdf_url=pdf,
            raw_id=announcement_id or None,
        )
