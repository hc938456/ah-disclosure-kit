from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ah_disclosure.models import FilingRecord

HKEX_TITLE_SEARCH_URL = "https://www1.hkexnews.hk/search/titlesearch.xhtml"
HKEX_STOCK_PREFIX_URL = "https://www1.hkexnews.hk/search/prefix.do"
HKEX_BASE = "https://www1.hkexnews.hk"


class HkexClient:
    def __init__(self, timeout: int = 30) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36",
                "Referer": "https://www.hkexnews.hk/index.htm",
            }
        )

    def search_filings(
        self,
        hkex_stock_id: str,
        hk_code: str | None = None,
        lang: str = "EN",
        category: str = "0",
        title_keyword: str = "",
        max_rows: int = 20,
    ) -> list[FilingRecord]:
        params = {"lang": lang, "market": "SEHK", "stockId": str(hkex_stock_id), "category": str(category)}
        if title_keyword:
            params["title"] = title_keyword
        resp = self.session.get(HKEX_TITLE_SEARCH_URL, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return self.parse_title_search_html(resp.text, hk_code=hk_code, fallback_stock_id=str(hkex_stock_id))[:max_rows]

    def lookup_stock(self, hk_code: str, lang: str = "EN") -> dict[str, Any] | None:
        code = str(hk_code).zfill(5)
        params = {
            "lang": lang,
            "type": "A",
            "name": code,
            "market": "SEHK",
            "callback": "callback",
        }
        resp = self.session.get(HKEX_STOCK_PREFIX_URL, params=params, timeout=self.timeout)
        resp.raise_for_status()
        payload = _parse_jsonp(resp.text)
        matches = payload.get("stockInfo") or []
        for item in matches:
            if str(item.get("code", "")).zfill(5) == code:
                return {
                    "symbol": code,
                    "hkex_stock_id": str(item.get("stockId")),
                    "company_name": item.get("name") or "",
                    "source": "HKEXnews prefix.do",
                }
        return None

    def verify_stock_id(self, hkex_stock_id: str, hk_code: str | None = None, company_keyword: str = "") -> dict[str, Any]:
        records = self.search_filings(hkex_stock_id, hk_code=hk_code, title_keyword="", max_rows=5)
        ok = False
        if records:
            code_match = not hk_code or any((r.symbol or "").lstrip("0") == str(hk_code).lstrip("0") for r in records)
            name_match = not company_keyword or any(company_keyword.lower() in (r.company_name or "").lower() for r in records)
            ok = code_match and name_match
        return {"hkex_stock_id": str(hkex_stock_id), "symbol": hk_code, "verified": ok, "records_sample": [r.to_dict() for r in records[:3]]}

    def parse_title_search_html(self, html: str, hk_code: str | None = None, fallback_stock_id: str | None = None) -> list[FilingRecord]:
        soup = BeautifulSoup(html, "html.parser")
        records: list[FilingRecord] = []
        anchors = []
        for a in soup.find_all("a"):
            href = a.get("href")
            title = a.get_text(" ", strip=True)
            if not href or not title:
                continue
            if any(x in href.lower() for x in ["/listedco/", "/newlistings/", "/news/"]) or href.lower().endswith((".pdf", ".htm", ".html", ".xls", ".xlsx")):
                anchors.append((a, title, urljoin(HKEX_BASE, href)))
        text = soup.get_text("\n", strip=True)
        for i, (_a, title, url) in enumerate(anchors):
            around = title
            # Conservative extraction from surrounding text; HKEX markup changes often.
            code = hk_code or ""
            name = ""
            if not code:
                m = re.search(r"\b(\d{5})\b", text)
                code = m.group(1) if m else ""
            if code:
                m = re.search(re.escape(code) + r"\s+([A-Z0-9\-\. ]{2,40})", text)
                name = (m.group(1).strip() if m else "")
            records.append(
                FilingRecord(
                    market="H",
                    symbol=code,
                    company_name=name,
                    title=title,
                    publish_time=_date_from_hkex_url(url),
                    document_type="HKEX filing",
                    source="HKEXnews",
                    detail_url=url,
                    pdf_url=url if url.lower().endswith(".pdf") else None,
                    raw_id=fallback_stock_id,
                )
            )
        return records


def _parse_jsonp(text: str) -> dict[str, Any]:
    match = re.search(r"^[^(]*\((.*)\)\s*;?\s*$", text, flags=re.S)
    payload = match.group(1) if match else text
    return json.loads(payload)


def _date_from_hkex_url(url: str) -> str:
    match = re.search(r"/((?:19|20)\d{2})/(\d{2})(\d{2})/", str(url or ""))
    if not match:
        return ""
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
