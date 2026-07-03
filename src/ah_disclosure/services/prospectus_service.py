from __future__ import annotations

from ah_disclosure.clients.eastmoney_ipo_client import EastmoneyIpoClient
from ah_disclosure.core.naming import build_document_id, build_pdf_filename
from ah_disclosure.core.paths import get_data_paths
from ah_disclosure.pdf.downloader import download_file
from ah_disclosure.pdf.ingest import ingest_pdf
from ah_disclosure.services.disclosure_service import search_a_filings, search_h_filings

H_PROSPECTUS_TITLE_KEYWORDS = ["Global Offering", "Prospectus", "Listing Document", "招股章程", "上市文件"]


def search_a_ipo_prospectus(company_keyword: str = "", board: str = "all", status_keyword: str = "", max_rows: int = 20) -> list[dict]:
    return [record.to_dict() for record in EastmoneyIpoClient().search_ipo_prospectus(company_keyword, board, status_keyword, max_rows)]


def search_a_listed_company_prospectus(symbol: str, start_date: str = "19900101", end_date: str = "20261231", max_rows: int = 20) -> list[dict]:
    rows = search_a_filings(symbol=symbol, category="首发", start_date=start_date, end_date=end_date, keyword="招股", max_rows=100)
    return [row for row in rows if any(k in (row.get("title") or "") for k in ["招股说明书", "招股意向书", "上市公告书", "首发"] )][:max_rows]


def search_a_offering_documents(symbol: str, keyword: str = "募集说明书", start_date: str = "20000101", end_date: str = "20261231", max_rows: int = 20) -> list[dict]:
    rows: list[dict] = []
    for category in ["可转债", "公司债", "增发", "配股", "其他融资"]:
        try:
            rows.extend(search_a_filings(symbol=symbol, category=category, start_date=start_date, end_date=end_date, keyword=keyword, max_rows=50))
        except Exception:
            pass
    return rows[:max_rows]


def _is_h_code(value: str | None) -> bool:
    text = str(value or "").strip().upper().replace("HK", "").replace(".", "")
    return text.isdigit() and len(text) <= 5


def _dedupe_records(rows: list[dict]) -> list[dict]:
    seen: set[str] = set()
    result: list[dict] = []
    for row in rows:
        key = str(row.get("pdf_url") or row.get("detail_url") or row.get("title") or row)
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def search_h_prospectus(symbol: str | None = None, company_keyword: str = "", max_rows: int = 20, hkex_stock_id: str | None = None, lang: str = "EN") -> list[dict]:
    if not symbol and not hkex_stock_id:
        return [
            {
                "error": "H prospectus search requires symbol or hkex_stock_id.",
                "reason": "HKEXnews prospectus/listing-document search is company-code scoped; broad company-name search is intentionally disabled to avoid slow and unreliable full-market scans.",
                "company_keyword": company_keyword,
                "hint": "Provide the Hong Kong stock code, for example market='H', symbol='03690'.",
            }
        ]

    search_symbol = str(symbol or "").strip()
    title_keywords = H_PROSPECTUS_TITLE_KEYWORDS
    if company_keyword and any(token.casefold() in company_keyword.casefold() for token in H_PROSPECTUS_TITLE_KEYWORDS):
        title_keywords = [company_keyword, *[kw for kw in H_PROSPECTUS_TITLE_KEYWORDS if kw.casefold() != company_keyword.casefold()]]

    rows: list[dict] = []
    for keyword in title_keywords:
        try:
            rows.extend(
                search_h_filings(
                    search_symbol,
                    hkex_stock_id=hkex_stock_id,
                    title_keyword=keyword,
                    max_rows=max_rows,
                    verify=bool(search_symbol),
                    lang=lang,
                )
            )
        except Exception as exc:
            rows.append({"error": f"{type(exc).__name__}: {exc}", "title_keyword": keyword})
        rows = _dedupe_records(rows)
        if len(rows) >= max_rows:
            break
    return rows[:max_rows]


def search_prospectus(market: str, symbol: str | None = None, company_keyword: str = "", max_rows: int = 20, **kwargs) -> list[dict]:
    hkex_stock_id = kwargs.pop("hkex_stock_id", None)
    lang = kwargs.pop("lang", "EN")
    if market.upper().startswith("A"):
        if symbol:
            return search_a_listed_company_prospectus(symbol, max_rows=max_rows)
        if company_keyword:
            listed_rows = search_a_filings(symbol="", category="首发", keyword=company_keyword, max_rows=max_rows)
            if listed_rows:
                return [row for row in listed_rows if any(k in (row.get("title") or "") for k in ["招股说明书", "招股意向书", "上市公告书", "首发"])][:max_rows]
        board = kwargs.get("board", "all")
        status_keyword = kwargs.get("status_keyword", "")
        return search_a_ipo_prospectus(company_keyword=company_keyword, board=board, status_keyword=status_keyword, max_rows=max_rows)
    return search_h_prospectus(symbol=symbol, company_keyword=company_keyword, max_rows=max_rows, hkex_stock_id=hkex_stock_id, lang=lang)


def download_and_ingest_prospectus(pdf_url: str, title: str = "prospectus", meta: dict | None = None, ingest: bool = True) -> dict:
    meta_full = {"document_type": "prospectus", "title": title, **(meta or {})}
    document_id = build_document_id(meta_full, fallback_title=title)
    paths = get_data_paths()
    market = str(meta_full.get("market") or "").upper()
    source = str(meta_full.get("source") or "").lower()
    url_text = str(pdf_url).lower()
    if market.startswith("H") or "hkex" in source or "hkexnews" in url_text:
        output_dir = paths.raw_hkex
    elif "cninfo" in source or "cninfo.com.cn" in url_text:
        output_dir = paths.raw_cninfo
    else:
        output_dir = paths.raw_eastmoney
    downloaded = download_file(pdf_url, output_dir=output_dir, filename=build_pdf_filename(meta_full, fallback_title=title))
    result = {"document_id": document_id, "download": downloaded}
    if ingest:
        result["ingest"] = ingest_pdf(downloaded["path"], document_id=document_id, meta=meta_full)
    return result
