from __future__ import annotations

import re
from datetime import datetime

from ah_disclosure.clients.cninfo_client import CninfoClient
from ah_disclosure.clients.hkex_client import (
    HkexClient,
    get_thread_hkex_client,
    paired_chinese_pdf_url,
)
from ah_disclosure.core.naming import build_document_id, build_pdf_filename
from ah_disclosure.core.paths import get_data_paths
from ah_disclosure.core.time_utils import current_date_yyyymmdd
from ah_disclosure.identity.hkex_stockid_resolver import (
    is_historical_hkex_symbol,
    resolve_hkex_stock_id,
)
from ah_disclosure.pdf.downloader import download_file
from ah_disclosure.pdf.ingest import ingest_pdf
from ah_disclosure.services.source_lookup import build_query_signature, historical_source_ttl_seconds, source_ttl_seconds
from ah_disclosure.storage.sqlite_store import SQLiteStore

HKEX_CACHE_FETCH_ROWS = 500


def _persist_filings(records: list[dict]) -> None:
    store = SQLiteStore()
    for record in records:
        try:
            store.insert_filing(record)
        except Exception:
            pass


def _records_with_local_links(
    store: SQLiteStore,
    signature: str,
    fallback: list[dict],
) -> list[dict]:
    cached = store.get_source_query(signature, include_stale=True)
    return cached["records"] if cached is not None else fallback


def search_a_filings(
    symbol: str,
    category: str = "年报",
    start_date: str = "20200101",
    end_date: str | None = None,
    keyword: str = "",
    max_rows: int = 20,
    prefer_cache: bool = True,
    refresh: bool = False,
    offline: bool = False,
    max_cache_age_seconds: int | None = None,
) -> list[dict]:
    end_date = end_date or current_date_yyyymmdd()
    store = SQLiteStore()
    signature = build_query_signature(
        "CNINFO",
        market="A",
        symbol=symbol,
        category=category,
        keyword=keyword,
        start_date=start_date,
        end_date=end_date,
        max_rows=max_rows,
    )
    if prefer_cache and not refresh:
        cached = store.get_source_query(signature, max_age_seconds=max_cache_age_seconds)
        if cached is not None:
            return cached["records"]
    if offline:
        stale = store.get_source_query(signature, include_stale=True)
        if stale is not None:
            return [{**row, "cache_stale": True} for row in stale["records"]]
        raise RuntimeError(f"Offline source cache miss: {signature}")
    try:
        records = CninfoClient().search_filings(
            symbol=symbol,
            category=category,
            start_date=start_date,
            end_date=end_date,
            keyword=keyword,
            max_rows=max_rows,
        )
        rows = [record.to_dict() for record in records]
    except Exception:
        stale = store.get_source_query(signature, include_stale=True)
        if stale is not None:
            return [{**row, "cache_stale": True} for row in stale["records"]]
        raise
    _persist_filings(rows)
    store.put_source_query(
        signature,
        rows,
        source="CNINFO",
        ttl_seconds=source_ttl_seconds("CNINFO", max_cache_age_seconds),
    )
    return _records_with_local_links(store, signature, rows)


def search_a_annual_report(
    symbol: str,
    report_year: int | None = None,
    start_date: str = "20200101",
    end_date: str | None = None,
    include_summary: bool = False,
    max_rows: int = 10,
    prefer_cache: bool = True,
    refresh: bool = False,
    offline: bool = False,
    max_cache_age_seconds: int | None = None,
) -> list[dict]:
    if (
        max_cache_age_seconds is None
        and report_year is not None
        and report_year <= datetime.now().year - 2
    ):
        max_cache_age_seconds = historical_source_ttl_seconds()
    rows = search_a_filings(
        symbol,
        "年报",
        start_date,
        end_date,
        max_rows=200,
        prefer_cache=prefer_cache,
        refresh=refresh,
        offline=offline,
        max_cache_age_seconds=max_cache_age_seconds,
    )
    if report_year is not None:
        rows = [row for row in rows if str(report_year) in (row.get("title") or "")]
    if not include_summary:
        rows = [row for row in rows if "摘要" not in (row.get("title") or "")]
    return rows[:max_rows]


def download_and_ingest_a_report(symbol: str, report_year: int | None = None, category: str = "年报", start_date: str = "20200101", end_date: str | None = None, output_dir: str | None = None, ingest: bool = True) -> dict:
    if output_dir is None and category == "年报":
        # Keep CLI and MCP annual-report downloads on the same staged,
        # completeness-checked pipeline as H-share reports.
        from ah_disclosure.services.filing_pipeline import ensure_filing_evidence

        return ensure_filing_evidence(
            "年度报告",
            "A",
            symbol,
            "annual_report",
            report_year=report_year,
            language="ZH",
            ingest_if_missing=ingest,
        )
    rows = search_a_filings(symbol, category, start_date, end_date, max_rows=200)
    if report_year is not None:
        rows = [row for row in rows if str(report_year) in (row.get("title") or "")]
    rows = [row for row in rows if "摘要" not in (row.get("title") or "")]
    if not rows:
        return {"ok": False, "error": "No matching A-share filing found."}
    record = rows[0]
    if not record.get("pdf_url"):
        return {"ok": False, "error": "No pdf_url found.", "record": record}
    output_dir = output_dir or str(get_data_paths().raw_cninfo)
    meta = {
        "market": "A",
        "symbol": record.get("symbol"),
        "company_name": record.get("company_name"),
        "document_type": category,
        "report_year": report_year,
        "title": record.get("title"),
        "publish_time": record.get("publish_time"),
        "source": record.get("source"),
        "detail_url": record.get("detail_url"),
        "pdf_url": record.get("pdf_url"),
        "raw_id": record.get("raw_id"),
    }
    document_id = build_document_id(meta, fallback_title=record.get("title") or "a_report")
    downloaded = download_file(record["pdf_url"], output_dir=output_dir, filename=build_pdf_filename(meta))
    result = {"ok": True, "record": record, "download": downloaded, "document_id": document_id}
    if ingest:
        result["ingest"] = ingest_pdf(downloaded["path"], document_id=document_id, meta=meta)
    return result


def search_h_filings(
    hk_code: str,
    hkex_stock_id: str | None = None,
    title_keyword: str = "",
    max_rows: int = 20,
    verify: bool = True,
    lang: str = "EN",
    prefer_cache: bool = True,
    refresh: bool = False,
    offline: bool = False,
    max_cache_age_seconds: int | None = None,
    category: str = "0",
) -> list[dict]:
    requested_rows = max(int(max_rows), 0)
    if requested_rows == 0:
        return []
    store = SQLiteStore()
    signature = build_query_signature(
        "HKEXnews",
        market="H",
        symbol=str(hk_code).zfill(5),
        title_keyword=title_keyword,
        lang=lang.upper(),
        category=category,
    )
    legacy_signature = build_query_signature(
        "HKEXnews",
        market="H",
        symbol=str(hk_code).zfill(5),
        title_keyword=title_keyword,
        max_rows=requested_rows,
        lang=lang.upper(),
        category=category,
    )
    if prefer_cache and not refresh:
        cached = store.get_source_query(signature, max_age_seconds=max_cache_age_seconds)
        if cached is not None:
            records = cached["records"]
            if len(records) >= requested_rows or len(records) < HKEX_CACHE_FETCH_ROWS:
                return records[:requested_rows]
        legacy = store.get_source_query(
            legacy_signature, max_age_seconds=max_cache_age_seconds
        )
        if legacy is not None:
            records = legacy["records"]
            if len(records) < requested_rows:
                store.put_source_query(
                    signature,
                    records,
                    source="HKEXnews",
                    ttl_seconds=source_ttl_seconds("HKEXnews", max_cache_age_seconds),
                )
            return records[:requested_rows]
    if offline:
        stale = store.get_source_query(signature, include_stale=True)
        if stale is None:
            stale = store.get_source_query(legacy_signature, include_stale=True)
        if stale is not None:
            return [
                {**row, "cache_stale": True}
                for row in stale["records"][:requested_rows]
            ]
        raise RuntimeError(f"Offline source cache miss: {signature}")
    resolved = resolve_hkex_stock_id(hk_code, candidate_stock_id=hkex_stock_id, verify=verify)
    stock_id = resolved.get("hkex_stock_id")
    if not stock_id:
        return [{"error": "hkex_stock_id not resolved", "resolver": resolved}]
    try:
        records = get_thread_hkex_client(HkexClient).search_filings(
            stock_id,
            hk_code=resolved.get("symbol"),
            title_keyword=title_keyword,
            max_rows=max(HKEX_CACHE_FETCH_ROWS, requested_rows),
            lang=lang,
            category=category,
        )
        rows = [record.to_dict() for record in records]
    except Exception:
        stale = store.get_source_query(signature, include_stale=True)
        if stale is None:
            stale = store.get_source_query(legacy_signature, include_stale=True)
        if stale is not None:
            return [
                {**row, "cache_stale": True}
                for row in stale["records"][:requested_rows]
            ]
        raise
    resolved_name = resolved.get("company_name") or ""
    for row in rows:
        company_name = str(row.get("company_name") or "").strip()
        if resolved_name and (not company_name or company_name.isdigit()):
            row["company_name"] = resolved_name
    _persist_filings(rows)
    store.put_source_query(
        signature,
        rows,
        source="HKEXnews",
        ttl_seconds=source_ttl_seconds("HKEXnews", max_cache_age_seconds),
    )
    return _records_with_local_links(store, signature, rows)[:requested_rows]


def search_h_annual_report(
    hk_code: str,
    report_year: int | None = None,
    hkex_stock_id: str | None = None,
    max_rows: int = 10,
    lang: str = "EN",
    prefer_cache: bool = True,
    refresh: bool = False,
    offline: bool = False,
    max_cache_age_seconds: int | None = None,
) -> list[dict]:
    if (
        max_cache_age_seconds is None
        and report_year is not None
        and report_year <= datetime.now().year - 2
    ):
        max_cache_age_seconds = historical_source_ttl_seconds()
    is_english = lang.upper().startswith("EN")
    title_keyword = "Annual Report" if is_english else "年報"
    primary_category = "1" if is_historical_hkex_symbol(hk_code) else "0"
    rows = search_h_filings(
        hk_code,
        hkex_stock_id=hkex_stock_id,
        title_keyword=title_keyword,
        max_rows=max_rows,
        verify=bool(hkex_stock_id),
        lang=lang,
        prefer_cache=prefer_cache,
        refresh=refresh,
        offline=offline,
        max_cache_age_seconds=max_cache_age_seconds,
        category=primary_category,
    )
    if not rows and primary_category == "0":
        rows = search_h_filings(
            hk_code,
            hkex_stock_id=hkex_stock_id,
            title_keyword=title_keyword,
            max_rows=max_rows,
            verify=bool(hkex_stock_id),
            lang=lang,
            prefer_cache=prefer_cache,
            refresh=refresh,
            offline=offline,
            max_cache_age_seconds=max_cache_age_seconds,
            category="1",
        )
    # A large, exact annual-report result is normally sufficient. HKEX's title
    # filter occasionally omits special variants, so retain the broad search
    # only for missing, small, or otherwise uncertain filtered results.
    if not any(
        _is_high_confidence_h_annual_report(row, report_year, lang) for row in rows
    ):
        broad_rows = search_h_filings(
            hk_code,
            hkex_stock_id=hkex_stock_id,
            title_keyword="",
            max_rows=max(500, max_rows * 10),
            verify=bool(hkex_stock_id),
            lang=lang,
            prefer_cache=prefer_cache,
            refresh=refresh,
            offline=offline,
            max_cache_age_seconds=max_cache_age_seconds,
        )
        seen_urls = {row.get("pdf_url") or row.get("detail_url") for row in rows}
        rows.extend(
            row
            for row in broad_rows
            if (row.get("pdf_url") or row.get("detail_url")) not in seen_urls
        )
    if report_year is not None:
        exact = [row for row in rows if _matches_h_annual_report_year(row, report_year)]
        if not exact and not is_english:
            fallback_rows = search_h_filings(
                hk_code,
                hkex_stock_id=hkex_stock_id,
                title_keyword="年度報告",
                max_rows=max_rows,
                verify=bool(hkex_stock_id),
                lang=lang,
                prefer_cache=prefer_cache,
                refresh=refresh,
                offline=offline,
                max_cache_age_seconds=max_cache_age_seconds,
            )
            seen_urls = {row.get("pdf_url") or row.get("detail_url") for row in rows}
            rows.extend(
                row
                for row in fallback_rows
                if (row.get("pdf_url") or row.get("detail_url")) not in seen_urls
            )
            exact = [row for row in rows if _matches_h_annual_report_year(row, report_year)]
        if not is_english and (
            not exact or all("海外監管公告" in str(row.get("title") or "") for row in exact)
        ):
            english_rows = search_h_annual_report(
                hk_code,
                report_year=report_year,
                hkex_stock_id=hkex_stock_id,
                max_rows=max_rows,
                lang="EN",
                prefer_cache=prefer_cache,
                refresh=refresh,
                offline=offline,
                max_cache_age_seconds=max_cache_age_seconds,
            )
            if not offline:
                client = get_thread_hkex_client(HkexClient)
                paired_rows = []
                for english_row in english_rows:
                    paired_url = paired_chinese_pdf_url(english_row.get("pdf_url") or "")
                    if not paired_url or not client.pdf_exists(paired_url):
                        continue
                    paired_rows.append(
                        {
                            **english_row,
                            "title": f"{report_year}年年報",
                            "detail_url": paired_url,
                            "pdf_url": paired_url,
                            "raw_id": paired_url.rsplit("/", 1)[-1].rsplit(".", 1)[0],
                        }
                    )
                if paired_rows:
                    exact = paired_rows + exact
                    _persist_filings(paired_rows)
        rows = exact
    return rows[:max_rows]


def download_and_ingest_h_report(hk_code: str, report_year: int | None = None, hkex_stock_id: str | None = None, title_keyword: str = "Annual Report", output_dir: str | None = None, ingest: bool = True, lang: str = "EN") -> dict:
    if output_dir is None:
        # Lazy import avoids a module cycle while keeping CLI and MCP downloads on the
        # same ranked, completeness-checked pipeline.
        from ah_disclosure.services.filing_pipeline import ensure_filing_evidence

        return ensure_filing_evidence(
            "annual report",
            "H",
            hk_code,
            "annual_report",
            report_year=report_year,
            language=lang,
            ingest_if_missing=ingest,
            hkex_stock_id=hkex_stock_id,
        )
    rows = search_h_filings(hk_code, hkex_stock_id=hkex_stock_id, title_keyword=title_keyword, max_rows=20, verify=False, lang=lang)
    rows = [row for row in rows if row.get("pdf_url") or row.get("detail_url")]
    if report_year is not None:
        exact = [row for row in rows if _matches_h_annual_report_year(row, report_year)]
        if not exact:
            return {
                "ok": False,
                "error": f"No exact HK annual report found for year {report_year}.",
                "candidates": rows[:5],
            }
        rows = exact
    if not rows:
        return {"ok": False, "error": "No matching HK filing found."}
    record = rows[0]
    url = record.get("pdf_url") or record.get("detail_url")
    if not isinstance(url, str) or not url:
        return {"ok": False, "error": "Selected HK filing has no downloadable URL."}
    meta = {
        "market": "H",
        "symbol": record.get("symbol"),
        "company_name": record.get("company_name"),
        "document_type": record.get("document_type") or title_keyword,
        "report_year": report_year,
        "title": record.get("title"),
        "publish_time": record.get("publish_time"),
        "source": record.get("source"),
        "detail_url": record.get("detail_url"),
        "pdf_url": url,
        "raw_id": record.get("raw_id"),
    }
    document_id = build_document_id(meta, fallback_title=record.get("title") or "h_report")
    downloaded = download_file(
        url,
        output_dir=output_dir or str(get_data_paths().raw_hkex),
        filename=build_pdf_filename(meta),
    )
    result = {"ok": True, "record": record, "download": downloaded, "document_id": document_id}
    if ingest and downloaded["path"].lower().endswith(".pdf"):
        result["ingest"] = ingest_pdf(downloaded["path"], document_id=document_id, meta=meta)
    return result


def _matches_h_annual_report_year(row: dict, report_year: int) -> bool:
    title = str(row.get("title") or "").upper()
    year = str(report_year)
    english_patterns = [
        rf"\b{re.escape(year)}\s+ANNUAL\s+REPORT\b",
        rf"\bANNUAL\s+REPORT(?:\s+AND\s+ACCOUNTS)?\s+{re.escape(year)}\b",
    ]
    if any(re.search(pattern, title) for pattern in english_patterns):
        return True
    compact_title = re.sub(r"\s+", "", title)
    chinese_digits = str.maketrans("0123456789", "零一二三四五六七八九")
    chinese_year = year.translate(chinese_digits)
    alternate_chinese_year = chinese_year.replace("零", "〇")
    has_year = any(
        token in compact_title for token in (year, chinese_year, alternate_chinese_year)
    )
    has_annual_marker = any(marker in compact_title for marker in ("年報", "年度報告"))
    has_interim_marker = any(marker in compact_title for marker in ("中期", "半年度", "季度"))
    return has_year and has_annual_marker and not has_interim_marker


def _file_size_from_hkex_label(value: object) -> int | None:
    match = re.fullmatch(
        r"\s*([0-9]+(?:\.[0-9]+)?)\s*(KB|MB|GB)\s*",
        str(value or ""),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    multiplier = {"KB": 1024, "MB": 1024**2, "GB": 1024**3}[match.group(2).upper()]
    return int(float(match.group(1)) * multiplier)


def _is_high_confidence_h_annual_report(
    row: dict,
    report_year: int | None,
    lang: str,
) -> bool:
    title = " ".join(str(row.get("title") or "").split())
    folded = title.casefold()
    if any(
        token in folded
        for token in (
            "summary",
            "摘要",
            "notice of publication",
            "notification",
            "reply form",
            "form of proxy",
            "overseas regulatory announcement",
            "海外監管公告",
        )
    ):
        return False
    size = _file_size_from_hkex_label(row.get("file_size_label"))
    if size is None or size < 1024 * 1024:
        return False
    year_pattern = str(report_year) if report_year is not None else r"(?:19|20)\d{2}"
    if lang.upper().startswith("EN"):
        patterns = (
            rf"^(?:fiscal year )?{year_pattern} annual report(?: and accounts)?(?:\s*\([^)]*\))?$",
            rf"^annual report(?: and accounts)? {year_pattern}(?:\s*\([^)]*\))?$",
        )
        return any(re.fullmatch(pattern, folded, flags=re.IGNORECASE) for pattern in patterns)
    compact = re.sub(r"\s+", "", title)
    year_tokens: tuple[str, ...]
    if report_year is None:
        year_tokens = (r"(?:19|20)\d{2}", r"[二〇零一二三四五六七八九]{4}")
    else:
        year = str(report_year)
        chinese_year = year.translate(str.maketrans("0123456789", "零一二三四五六七八九"))
        year_tokens = tuple(re.escape(token) for token in (year, chinese_year, chinese_year.replace("零", "〇")))
    return any(
        re.fullmatch(rf"{year_token}(?:年年報|年報|年度報告)", compact)
        for year_token in year_tokens
    )
