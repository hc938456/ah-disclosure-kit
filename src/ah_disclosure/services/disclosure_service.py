from __future__ import annotations

import re

from ah_disclosure.clients.cninfo_client import CninfoClient
from ah_disclosure.clients.hkex_client import HkexClient
from ah_disclosure.core.naming import build_document_id, build_pdf_filename
from ah_disclosure.core.paths import get_data_paths
from ah_disclosure.identity.hkex_stockid_resolver import resolve_hkex_stock_id
from ah_disclosure.pdf.downloader import download_file
from ah_disclosure.pdf.ingest import ingest_pdf
from ah_disclosure.storage.sqlite_store import SQLiteStore


def _persist_filings(records: list[dict]) -> None:
    store = SQLiteStore()
    for record in records:
        try:
            store.insert_filing(record)
        except Exception:
            pass


def search_a_filings(
    symbol: str,
    category: str = "年报",
    start_date: str = "20200101",
    end_date: str = "20261231",
    keyword: str = "",
    max_rows: int = 20,
) -> list[dict]:
    records = CninfoClient().search_filings(symbol=symbol, category=category, start_date=start_date, end_date=end_date, keyword=keyword, max_rows=max_rows)
    rows = [record.to_dict() for record in records]
    _persist_filings(rows)
    return rows


def search_a_annual_report(symbol: str, report_year: int | None = None, start_date: str = "20200101", end_date: str = "20261231", include_summary: bool = False, max_rows: int = 10) -> list[dict]:
    rows = search_a_filings(symbol, "年报", start_date, end_date, max_rows=200)
    if report_year is not None:
        rows = [row for row in rows if str(report_year) in (row.get("title") or "")]
    if not include_summary:
        rows = [row for row in rows if "摘要" not in (row.get("title") or "")]
    return rows[:max_rows]


def download_and_ingest_a_report(symbol: str, report_year: int | None = None, category: str = "年报", start_date: str = "20200101", end_date: str = "20261231", output_dir: str | None = None, ingest: bool = True) -> dict:
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


def search_h_filings(hk_code: str, hkex_stock_id: str | None = None, title_keyword: str = "", max_rows: int = 20, verify: bool = True, lang: str = "EN") -> list[dict]:
    resolved = resolve_hkex_stock_id(hk_code, candidate_stock_id=hkex_stock_id, verify=verify)
    stock_id = resolved.get("hkex_stock_id")
    if not stock_id:
        return [{"error": "hkex_stock_id not resolved", "resolver": resolved}]
    records = HkexClient().search_filings(stock_id, hk_code=resolved.get("symbol"), title_keyword=title_keyword, max_rows=max_rows, lang=lang)
    rows = [record.to_dict() for record in records]
    resolved_name = resolved.get("company_name") or ""
    for row in rows:
        company_name = str(row.get("company_name") or "").strip()
        if resolved_name and (not company_name or company_name.isdigit()):
            row["company_name"] = resolved_name
    _persist_filings(rows)
    return rows


def search_h_annual_report(hk_code: str, report_year: int | None = None, hkex_stock_id: str | None = None, max_rows: int = 10, lang: str = "EN") -> list[dict]:
    title_keyword = "Annual Report" if lang.upper().startswith("EN") else "年報"
    rows = search_h_filings(hk_code, hkex_stock_id=hkex_stock_id, title_keyword=title_keyword, max_rows=max_rows, verify=True, lang=lang)
    if report_year is not None:
        exact = [row for row in rows if _matches_h_annual_report_year(row, report_year)]
        rows = exact
    return rows[:max_rows]


def download_and_ingest_h_report(hk_code: str, report_year: int | None = None, hkex_stock_id: str | None = None, title_keyword: str = "Annual Report", output_dir: str | None = None, ingest: bool = True, lang: str = "EN") -> dict:
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
    downloaded = download_file(url, output_dir=output_dir or str(get_data_paths().raw_hkex), filename=build_pdf_filename(meta))
    result = {"ok": True, "record": record, "download": downloaded, "document_id": document_id}
    if ingest and downloaded["path"].lower().endswith(".pdf"):
        result["ingest"] = ingest_pdf(downloaded["path"], document_id=document_id, meta=meta)
    return result


def _matches_h_annual_report_year(row: dict, report_year: int) -> bool:
    title = str(row.get("title") or "").upper()
    year = str(report_year)
    patterns = [
        rf"\b{re.escape(year)}\s+ANNUAL\s+REPORT\b",
        rf"\bANNUAL\s+REPORT\s+{re.escape(year)}\b",
        rf"{re.escape(year)}\s*年報",
        rf"年報\s*{re.escape(year)}",
    ]
    return any(re.search(pattern, title) for pattern in patterns)
