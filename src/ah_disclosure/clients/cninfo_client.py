from __future__ import annotations

import math
import re
from functools import lru_cache
from typing import Any
from urllib.parse import quote, urljoin

import requests

from ah_disclosure.models import FilingRecord

CNINFO_BASE = "http://www.cninfo.com.cn"
CNINFO_STATIC_BASE = "http://static.cninfo.com.cn/"
CNINFO_QUERY_URL = f"{CNINFO_BASE}/new/hisAnnouncement/query"
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
    if adjunct_url.startswith(("http://", "https://")):
        return adjunct_url
    return urljoin(CNINFO_STATIC_BASE, adjunct_url.lstrip("/"))


def _detail_url(symbol: str, announcement_id: str, org_id: str, publish_time: str) -> str:
    return (
        f"{CNINFO_BASE}/new/disclosure/detail?stockCode={symbol}"
        f"&announcementId={announcement_id}&orgId={org_id}&announcementTime={quote(publish_time, safe='')}"
    )


class CninfoClient:
    def __init__(self, timeout: int = 30) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    @lru_cache(maxsize=32)
    def get_stock_org_map(self, market: str = "沪深京") -> dict[str, str]:
        resp = self.session.get(CNINFO_STOCK_URLS[market], timeout=self.timeout)
        resp.raise_for_status()
        return {str(item.get("code")): str(item.get("orgId")) for item in resp.json().get("stockList", []) if item.get("code")}

    def search_filings(
        self,
        symbol: str = "",
        category: str = "年报",
        keyword: str = "",
        start_date: str = "20200101",
        end_date: str = "20261231",
        market: str = "沪深京",
        max_rows: int = 20,
        page_size: int = 30,
        max_pages: int | None = None,
    ) -> list[FilingRecord]:
        stock_item = ""
        if symbol:
            org_id = self.get_stock_org_map(market).get(str(symbol).strip())
            if not org_id:
                raise ValueError(f"Cannot resolve CNINFO orgId for symbol={symbol!r}")
            stock_item = f"{symbol},{org_id}"
        payload = {
            "pageNum": "1",
            "pageSize": str(page_size),
            "column": COLUMN_MAP.get(market, "szse"),
            "tabName": "fulltext",
            "plate": "",
            "stock": stock_item,
            "searchkey": keyword or "",
            "secid": "",
            "category": CATEGORY_MAP.get(category, category if category.startswith("category_") else ""),
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

    def _post(self, payload: dict[str, str]) -> dict[str, Any]:
        resp = self.session.post(CNINFO_QUERY_URL, data=payload, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

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
