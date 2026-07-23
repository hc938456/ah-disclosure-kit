from __future__ import annotations

import uuid

from ah_disclosure.clients.eastmoney_ipo_client import EastmoneyIpoClient
from ah_disclosure.core.naming import build_document_id, build_pdf_filename
from ah_disclosure.core.paths import get_data_paths
from ah_disclosure.identity.hkex_stockid_resolver import (
    is_historical_hkex_stock_id,
    is_historical_hkex_symbol,
)
from ah_disclosure.pdf.candidate_files import discard_staged_candidate, move_staged_candidate
from ah_disclosure.pdf.downloader import download_file
from ah_disclosure.pdf.completeness import validate_prospectus_pages
from ah_disclosure.pdf.ingest import ingest_pdf
from ah_disclosure.pdf.identity import validate_document_identity
from ah_disclosure.pdf.text_extract import extract_pages
from ah_disclosure.services.disclosure_service import search_a_filings, search_h_filings
from ah_disclosure.services.source_lookup import historical_source_ttl_seconds

H_PROSPECTUS_TITLE_KEYWORDS = [
    "Global Offering",
    "Offering",
    "Prospectus",
    "Listing Document",
    "Introduction",
]
H_PROSPECTUS_TITLE_KEYWORDS_ZH = [
    "全球發售",
    "發售",
    "招股章程",
    "上市文件",
    "以介紹方式",
]


def search_a_ipo_prospectus(
    company_keyword: str = "",
    symbol: str | None = None,
    board: str = "all",
    status_keyword: str = "",
    max_rows: int = 20,
) -> list[dict]:
    rows = [
        record.to_dict()
        for record in EastmoneyIpoClient().search_ipo_prospectus(
            company_keyword=company_keyword,
            board=board,
            status_keyword=status_keyword,
            max_rows=max_rows,
            symbol=symbol,
        )
    ]
    for row in rows:
        if row.get("publish_date") and not row.get("publish_time"):
            row["publish_time"] = row["publish_date"]
    return rows


def search_a_listed_company_prospectus(
    symbol: str,
    start_date: str = "19900101",
    end_date: str | None = None,
    max_rows: int = 20,
    prefer_cache: bool = True,
    refresh: bool = False,
    offline: bool = False,
    max_cache_age_seconds: int | None = None,
) -> list[dict]:
    if max_cache_age_seconds is None:
        max_cache_age_seconds = historical_source_ttl_seconds()
    rows = search_a_filings(
        symbol=symbol,
        category="首发",
        start_date=start_date,
        end_date=end_date,
        keyword="招股",
        max_rows=100,
        prefer_cache=prefer_cache,
        refresh=refresh,
        offline=offline,
        max_cache_age_seconds=max_cache_age_seconds,
    )
    return [row for row in rows if any(k in (row.get("title") or "") for k in ["招股说明书", "招股意向书", "上市公告书", "首发"] )][:max_rows]


def search_a_offering_documents(symbol: str, keyword: str = "募集说明书", start_date: str = "20000101", end_date: str | None = None, max_rows: int = 20) -> list[dict]:
    rows: list[dict] = []
    errors: list[dict] = []
    for category in ["可转债", "公司债", "增发", "配股", "其他融资"]:
        try:
            rows.extend(search_a_filings(symbol=symbol, category=category, start_date=start_date, end_date=end_date, keyword=keyword, max_rows=50))
        except Exception as exc:
            errors.append(
                {
                    "error": f"{type(exc).__name__}: {exc}",
                    "source": "CNINFO",
                    "symbol": symbol,
                    "category": category,
                    "keyword": keyword,
                }
            )
    return (rows if rows else errors)[:max_rows]


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


def _h_prospectus_priority(row: dict) -> tuple[int, int]:
    category = " ".join(
        str(row.get("category") or row.get("document_type") or "").casefold().split()
    )
    if (
        ("listing documents" in category and "offer for subscription" in category)
        or ("上市文件" in category and "發售以供認購" in category)
    ):
        category_rank = 0
    elif "listing documents" in category or "上市文件" in category:
        category_rank = 1
    elif any(
        keyword in category
        for keyword in ("formal notice", "announcements and notices", "正式通告", "公告及通告")
    ):
        category_rank = 3
    else:
        category_rank = 2
    pdf_rank = 0 if str(row.get("pdf_url") or "").lower().endswith(".pdf") else 1
    return category_rank, pdf_rank


def search_h_prospectus(
    symbol: str | None = None,
    company_keyword: str = "",
    max_rows: int = 20,
    hkex_stock_id: str | None = None,
    lang: str = "EN",
    prefer_cache: bool = True,
    refresh: bool = False,
    offline: bool = False,
    max_cache_age_seconds: int | None = None,
) -> list[dict]:
    if max_cache_age_seconds is None:
        max_cache_age_seconds = historical_source_ttl_seconds()
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
    title_keywords = (
        H_PROSPECTUS_TITLE_KEYWORDS_ZH
        if str(lang or "EN").upper().startswith("ZH")
        else H_PROSPECTUS_TITLE_KEYWORDS
    )
    if company_keyword and any(token.casefold() in company_keyword.casefold() for token in H_PROSPECTUS_TITLE_KEYWORDS):
        title_keywords = [company_keyword, *[kw for kw in H_PROSPECTUS_TITLE_KEYWORDS if kw.casefold() != company_keyword.casefold()]]

    rows: list[dict] = []
    historical_security = (
        bool(search_symbol) and is_historical_hkex_symbol(search_symbol)
    ) or is_historical_hkex_stock_id(hkex_stock_id)
    categories = ("1",) if historical_security else ("0",)
    for category in categories:
        for keyword in title_keywords:
            try:
                rows.extend(
                    search_h_filings(
                        search_symbol,
                        hkex_stock_id=hkex_stock_id,
                        title_keyword=keyword,
                        max_rows=max_rows,
                        verify=bool(hkex_stock_id),
                        lang=lang,
                        prefer_cache=prefer_cache,
                        refresh=refresh,
                        offline=offline,
                        max_cache_age_seconds=max_cache_age_seconds,
                        category=category,
                    )
                )
            except Exception as exc:
                rows.append(
                    {
                        "error": f"{type(exc).__name__}: {exc}",
                        "title_keyword": keyword,
                        "category": category,
                    }
                )
            rows = _dedupe_records(rows)
            direct_pdfs = [
                row
                for row in rows
                if str(row.get("pdf_url") or "").lower().endswith(".pdf")
            ]
            listing_packages = [
                row
                for row in rows
                if str(row.get("detail_url") or "").lower().endswith((".htm", ".html"))
                and "listing" in str(row.get("category") or "").casefold()
            ]
            if direct_pdfs or listing_packages or len(rows) >= max_rows:
                break
        if direct_pdfs or listing_packages or len(rows) >= max_rows:
            break
    rows.sort(key=_h_prospectus_priority)
    return rows[:max_rows]


def search_prospectus(market: str, symbol: str | None = None, company_keyword: str = "", max_rows: int = 20, **kwargs) -> list[dict]:
    hkex_stock_id = kwargs.pop("hkex_stock_id", None)
    lang = kwargs.pop("lang", "EN")
    prefer_cache = kwargs.pop("prefer_cache", True)
    refresh = kwargs.pop("refresh", False)
    offline = kwargs.pop("offline", False)
    max_cache_age_seconds = kwargs.pop("max_cache_age_seconds", None)
    if market.upper().startswith("A"):
        if symbol:
            listed_rows = search_a_listed_company_prospectus(
                symbol,
                max_rows=max_rows,
                prefer_cache=prefer_cache,
                refresh=refresh,
                offline=offline,
                max_cache_age_seconds=max_cache_age_seconds,
            )
            if listed_rows or not company_keyword or offline:
                return listed_rows
            board = "bj" if str(symbol).startswith(("8", "9")) else kwargs.get("board", "all")
            ipo_rows = search_a_ipo_prospectus(
                company_keyword=company_keyword,
                symbol=symbol,
                board=board,
                status_keyword=kwargs.get("status_keyword", ""),
                max_rows=max_rows,
            )
            if not ipo_rows and board != "all":
                ipo_rows = search_a_ipo_prospectus(
                    company_keyword=company_keyword,
                    symbol=symbol,
                    board="all",
                    status_keyword=kwargs.get("status_keyword", ""),
                    max_rows=max_rows,
                )
            if not ipo_rows and str(symbol).startswith(("8", "9")):
                ipo_rows = [
                    record.to_dict()
                    for record in EastmoneyIpoClient().search_bse_listed_prospectus(
                        symbol,
                        company_keyword,
                        max_rows=max_rows,
                    )
                ]
                for row in ipo_rows:
                    if row.get("publish_date") and not row.get("publish_time"):
                        row["publish_time"] = row["publish_date"]
            for row in ipo_rows:
                row["company_name"] = company_keyword
                row["title"] = f"{company_keyword} 招股说明书"
            return ipo_rows
        if company_keyword:
            listed_rows = search_a_filings(symbol="", category="首发", keyword=company_keyword, max_rows=max_rows)
            if listed_rows:
                return [row for row in listed_rows if any(k in (row.get("title") or "") for k in ["招股说明书", "招股意向书", "上市公告书", "首发"])][:max_rows]
        board = kwargs.get("board", "all")
        status_keyword = kwargs.get("status_keyword", "")
        return search_a_ipo_prospectus(
            company_keyword=company_keyword,
            board=board,
            status_keyword=status_keyword,
            max_rows=max_rows,
        )
    return search_h_prospectus(
        symbol=symbol,
        company_keyword=company_keyword,
        max_rows=max_rows,
        hkex_stock_id=hkex_stock_id,
        lang=lang,
        prefer_cache=prefer_cache,
        refresh=refresh,
        offline=offline,
        max_cache_age_seconds=max_cache_age_seconds,
    )


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
    filename = build_pdf_filename(meta_full, fallback_title=title)
    downloaded = download_file(
        pdf_url,
        output_dir=paths.staging_downloads / uuid.uuid4().hex,
        filename=filename,
    )
    downloaded["staged"] = True
    pages = extract_pages(downloaded["path"], ocr="auto" if ingest else "off")
    validation = validate_prospectus_pages(downloaded["path"], pages)
    identity = validate_document_identity(
        pages,
        expected_year=meta_full.get("report_year"),
        expected_company_name=meta_full.get("company_name"),
        expected_symbol=meta_full.get("symbol"),
    )
    validation["identity"] = identity
    if validation.get("complete") is True and not identity["passed"]:
        validation["complete"] = None
        validation["status"] = "needs_review_identity_mismatch"
    result = {
        "ok": validation.get("complete") is True,
        "document_id": document_id,
        "download": downloaded,
        "document_validation": validation,
    }
    if validation.get("complete") is False:
        result["disposition"] = (
            "deleted_staging"
            if discard_staged_candidate(downloaded, paths.staging_downloads)
            else "retained_existing_file"
        )
        result["error"] = "Downloaded PDF is not a complete prospectus."
        return result
    if validation.get("complete") is None:
        downloaded = move_staged_candidate(
            downloaded,
            paths.staging / "review",
            filename,
            pdf_url,
            paths.staging_downloads,
        )
        result["download"] = downloaded
        result["disposition"] = "needs_review"
        validation["path"] = downloaded["path"]
        result["error"] = "Downloaded prospectus requires OCR or manual review."
        return result
    downloaded = move_staged_candidate(
        downloaded,
        output_dir,
        filename,
        pdf_url,
        paths.staging_downloads,
    )
    result["download"] = downloaded
    result["disposition"] = "accepted"
    validation["path"] = downloaded["path"]
    if ingest:
        result["ingest"] = ingest_pdf(
            downloaded["path"],
            document_id=document_id,
            meta=meta_full,
            pre_extracted_pages=pages,
        )
    return result
