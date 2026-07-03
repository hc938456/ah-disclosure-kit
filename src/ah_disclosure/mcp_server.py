from __future__ import annotations

from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:  # allows local smoke tests before optional dependency install
    class FastMCP:  # type: ignore[no-redef]
        def __init__(self, name: str) -> None:
            self.name = name
        def tool(self):
            def decorator(func):
                return func
            return decorator
        def run(self, transport: str = "stdio") -> None:
            raise RuntimeError("The 'mcp' package is required to run the MCP server. Install with: pip install mcp")

from ah_disclosure import __version__
from ah_disclosure.core.naming import build_document_id, build_pdf_filename
from ah_disclosure.core.paths import get_data_dir, get_data_paths
from ah_disclosure.identity.resolver import resolve_company as _resolve_company
from ah_disclosure.identity.hkex_stockid_resolver import HkexStockIdResolver
from ah_disclosure.pdf.downloader import download_file
from ah_disclosure.pdf.ingest import ingest_pdf as _ingest_pdf
from ah_disclosure.providers.akshare_registry import list_supported_interfaces
from ah_disclosure.services.company_data_service import (
    get_business_info,
    get_capital_actions,
    get_company_profile,
    get_dividends,
    get_financial_indicators,
    get_financial_statements,
    get_governance_esg,
    get_shareholders,
)
from ah_disclosure.services.disclosure_service import (
    download_and_ingest_a_report,
    download_and_ingest_h_report,
    search_a_filings,
    search_a_annual_report,
    search_h_annual_report,
    search_h_filings,
)
from ah_disclosure.services.dossier_service import build_company_dossier, compare_structured_data_with_report
from ah_disclosure.services.evidence_service import get_evidence_packet
from ah_disclosure.services.local_search_service import (
    cleanup_local_company,
    cleanup_local_document,
    get_document_meta,
    get_document_pages,
    list_local_documents,
    reconcile_local_document_index,
    search_local_document_text,
)
from ah_disclosure.services.prospectus_service import (
    download_and_ingest_prospectus,
    search_a_offering_documents,
    search_prospectus,
)
from ah_disclosure.services.query_router import route_query as _route_query

mcp = FastMCP("ah-disclosure")


@mcp.tool()
def server_info() -> dict[str, Any]:
    """Return ah-disclosure server information."""
    return {
        "name": "ah-disclosure",
        "version": __version__,
        "data_dir": str(get_data_dir()),
        "supported_interfaces": list_supported_interfaces(),
    }


@mcp.tool()
def list_capabilities() -> dict[str, Any]:
    """List high-level capabilities and token governance policy."""
    return {
        "structured_data": ["company_profile", "financials", "dividends", "shareholders", "capital_actions", "governance_esg"],
        "filings": ["CNINFO A-share", "HKEXnews H-share"],
        "prospectus": ["A IPO", "A offering documents", "H listing documents"],
        "pdf": ["download", "download-only", "ingest", "pages.jsonl", "SQLite FTS", "optional full_text.txt", "optional document.md"],
        "cleanup": ["cleanup_document", "cleanup_company", "reconcile_local_index"],
        "token_governance": ["query_router", "evidence_packet", "accounting_policy_strategy", "financial_analysis_strategy", "context_budget"],
        "unsupported": ["complete structured full-year Hong Kong IPO/new-listing company list"],
    }


@mcp.tool()
def resolve_company(symbol: str, market: str | None = None) -> dict[str, Any]:
    """Resolve A/H company identity."""
    result = _resolve_company(symbol, market)
    return result.to_dict() if hasattr(result, "to_dict") else result


@mcp.tool()
def resolve_hkex_stock_id(hk_code: str, candidate_stock_id: str | None = None, company_name: str | None = None, verify: bool = True) -> dict[str, Any]:
    """Resolve/cache HKEX internal stockId for a Hong Kong stock code."""
    return HkexStockIdResolver().resolve(hk_code, candidate_stock_id=candidate_stock_id, company_name=company_name, verify=verify)


@mcp.tool()
def search_filings(market: str, symbol: str, category: str = "年报", keyword: str = "", start_date: str = "20200101", end_date: str = "20261231", max_rows: int = 20, hkex_stock_id: str | None = None, lang: str = "EN") -> list[dict[str, Any]]:
    """Search filings for A/H market."""
    if market.upper().startswith("H"):
        return search_h_filings(symbol, hkex_stock_id=hkex_stock_id, title_keyword=keyword, max_rows=max_rows, lang=lang)
    return search_a_filings(symbol=symbol, category=category, keyword=keyword, start_date=start_date, end_date=end_date, max_rows=max_rows)


@mcp.tool()
def search_annual_report(market: str, symbol: str, year: int | None = None, max_rows: int = 10, hkex_stock_id: str | None = None, lang: str = "EN") -> list[dict[str, Any]]:
    """Search annual reports. A uses CNINFO; H uses HKEXnews."""
    if market.upper().startswith("H"):
        return search_h_annual_report(symbol, report_year=year, hkex_stock_id=hkex_stock_id, max_rows=max_rows, lang=lang)
    return search_a_annual_report(symbol, report_year=year, max_rows=max_rows)


@mcp.tool()
def download_and_ingest_filing(record: dict[str, Any], ingest: bool = True) -> dict[str, Any]:
    """Download a filing record and optionally ingest it. Accepts a record from search tools."""
    market = (record.get("market") or "").upper()
    url = record.get("pdf_url") or record.get("detail_url")
    if not url:
        return {"ok": False, "error": "record has no pdf_url/detail_url", "record": record}
    paths = get_data_paths()
    output_dir = paths.raw_hkex if market.startswith("H") else paths.raw_cninfo if market.startswith("A") else paths.raw_manual
    meta = {
        "market": record.get("market"),
        "symbol": record.get("symbol"),
        "company_name": record.get("company_name"),
        "document_type": record.get("document_type"),
        "title": record.get("title"),
        "publish_time": record.get("publish_time"),
        "source": record.get("source"),
        "detail_url": record.get("detail_url"),
        "pdf_url": url,
        "raw_id": record.get("raw_id"),
    }
    document_id = build_document_id(meta, fallback_title=record.get("title") or "filing")
    downloaded = download_file(url, output_dir=output_dir, filename=build_pdf_filename(meta))
    result: dict[str, Any] = {"ok": True, "record": record, "download": downloaded, "document_id": document_id}
    if ingest and str(downloaded.get("path", "")).lower().endswith(".pdf"):
        result["ingest"] = _ingest_pdf(downloaded["path"], document_id=document_id, meta=meta)
    return result


@mcp.tool()
def download_and_ingest_report(market: str, symbol: str, year: int | None = None, hkex_stock_id: str | None = None, ingest: bool = True, lang: str = "EN") -> dict[str, Any]:
    """Search and download annual report for A/H market; ingest controls local text index creation."""
    if market.upper().startswith("H"):
        title_keyword = "Annual Report" if lang.upper().startswith("EN") else "年報"
        return download_and_ingest_h_report(symbol, report_year=year, hkex_stock_id=hkex_stock_id, title_keyword=title_keyword, ingest=ingest, lang=lang)
    return download_and_ingest_a_report(symbol, report_year=year, ingest=ingest)


@mcp.tool()
def download_report_tool(market: str, symbol: str, year: int | None = None, hkex_stock_id: str | None = None, lang: str = "EN") -> dict[str, Any]:
    """Search and download annual report only; does not ingest or create parsed artifacts."""
    return download_and_ingest_report(market, symbol, year=year, hkex_stock_id=hkex_stock_id, ingest=False, lang=lang)


@mcp.tool()
def search_prospectus_tool(market: str = "A", company_keyword: str = "", symbol: str = "", board: str = "all", max_rows: int = 20, hkex_stock_id: str | None = None, lang: str = "EN") -> list[dict[str, Any]]:
    """Search A/H prospectus, listing, and offering documents."""
    return search_prospectus(market, symbol=symbol or None, company_keyword=company_keyword, board=board, max_rows=max_rows, hkex_stock_id=hkex_stock_id, lang=lang)


@mcp.tool()
def search_offering_documents(market: str = "A", symbol: str = "", keyword: str = "募集说明书", max_rows: int = 20, lang: str = "EN") -> list[dict[str, Any]]:
    """Search offering/refinancing documents. A-share uses CNINFO; H-share uses HKEXnews filing search."""
    if market.upper().startswith("H"):
        return search_h_filings(symbol, title_keyword=keyword, max_rows=max_rows, verify=False, lang=lang)
    return search_a_offering_documents(symbol=symbol, keyword=keyword, max_rows=max_rows)


@mcp.tool()
def download_and_ingest_prospectus_tool(pdf_url: str, title: str = "prospectus", meta: dict[str, Any] | None = None, ingest: bool = True) -> dict[str, Any]:
    """Download a prospectus PDF URL; ingest controls local text index creation."""
    return download_and_ingest_prospectus(pdf_url=pdf_url, title=title, meta=meta, ingest=ingest)


@mcp.tool()
def download_prospectus_tool(pdf_url: str, title: str = "prospectus", meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Download prospectus PDF only; does not ingest or create parsed artifacts."""
    return download_and_ingest_prospectus(pdf_url=pdf_url, title=title, meta=meta, ingest=False)


@mcp.tool()
def get_company_profile_tool(market: str, symbol: str, max_rows: int | None = 200) -> dict[str, Any]:
    """Get A/H company profile via structured data provider."""
    return get_company_profile(market, symbol, max_rows=max_rows)


@mcp.tool()
def get_business_info_tool(market: str, symbol: str, max_rows: int | None = 200) -> dict[str, Any]:
    """Get business description/composition. H-share falls back to company profile when no dedicated wrapper is available."""
    return get_business_info(market, symbol, max_rows=max_rows)


@mcp.tool()
def get_financial_statements_tool(market: str, symbol: str, statement: str = "all", max_rows: int | None = 200) -> dict[str, Any]:
    """Get financial statements. statement=balance/income/cashflow/all."""
    return get_financial_statements(market, symbol, statement=statement, max_rows=max_rows)


@mcp.tool()
def get_financial_indicators_tool(market: str, symbol: str, max_rows: int | None = 200) -> dict[str, Any]:
    """Get financial indicators via AKShare-backed provider."""
    return get_financial_indicators(market, symbol, max_rows=max_rows)


@mcp.tool()
def get_dividends_tool(market: str, symbol: str, max_rows: int | None = 200) -> dict[str, Any]:
    """Get dividend history via AKShare-backed provider."""
    return get_dividends(market, symbol, max_rows=max_rows)


@mcp.tool()
def get_shareholders_tool(market: str, symbol: str, data_type: str = "shareholder_count", max_rows: int | None = 200) -> dict[str, Any]:
    """Get shareholder-related data. H-share may require filings when no structured wrapper is available."""
    return get_shareholders(market, symbol, data_type=data_type, max_rows=max_rows)


@mcp.tool()
def get_capital_actions_tool(market: str, symbol: str, data_type: str = "repurchase", max_rows: int | None = 200) -> dict[str, Any]:
    """Get capital action data such as repurchase/refinancing/dividends."""
    return get_capital_actions(market, symbol, data_type=data_type, max_rows=max_rows)


@mcp.tool()
def get_governance_esg_tool(market: str, symbol: str, data_type: str = "esg", max_rows: int | None = 200) -> dict[str, Any]:
    """Get governance/ESG/corporate event data. H-share may require filings when no structured wrapper is available."""
    return get_governance_esg(market, symbol, data_type=data_type, max_rows=max_rows)


@mcp.tool()
def ingest_pdf_tool(
    pdf_path: str,
    document_id: str | None = None,
    mode: str = "auto",
    build_vector_index: bool = False,
    write_full_text: bool = False,
    write_markdown: bool = False,
    extract_tables: bool = False,
    ocr: str = "auto",
    ocr_lang: str = "chi_sim+eng",
    overwrite: bool = False,
) -> dict[str, Any]:
    """Ingest local PDF into pages.jsonl and SQLite FTS; OCR/full_text/document.md are opt-in."""
    return _ingest_pdf(
        pdf_path,
        document_id=document_id,
        mode=mode,
        build_vector_index_opt=build_vector_index,
        write_full_text=write_full_text,
        write_markdown=write_markdown,
        extract_tables_opt=extract_tables,
        ocr=ocr,
        ocr_lang=ocr_lang,
        overwrite=overwrite,
    )


@mcp.tool()
def list_local_documents_tool(limit: int = 50) -> list[dict[str, Any]]:
    """List locally ingested documents."""
    return list_local_documents(limit)


@mcp.tool()
def search_local_document_text_tool(query: str, document_id: str | None = None, limit: int = 8) -> list[dict[str, Any]]:
    """Search local SQLite FTS document pages."""
    return search_local_document_text(query, document_id, limit)


@mcp.tool()
def get_document_pages_tool(document_id: str, pages: list[int] | None = None) -> list[dict[str, Any]]:
    """Get local document pages by page numbers."""
    return get_document_pages(document_id, pages)


@mcp.tool()
def get_document_meta_tool(document_id: str) -> dict[str, Any]:
    """Get local document metadata."""
    return get_document_meta(document_id)


@mcp.tool()
def cleanup_document_tool(document_id: str, delete_pdf: bool = True, delete_parsed: bool = True, dry_run: bool = False) -> dict[str, Any]:
    """Delete one local document and synchronize parsed files plus SQLite indexes."""
    return cleanup_local_document(document_id, delete_pdf=delete_pdf, delete_parsed=delete_parsed, dry_run=dry_run)


@mcp.tool()
def cleanup_company_tool(market: str, symbol: str, delete_pdfs: bool = True, delete_parsed: bool = True, delete_company_cache: bool = False, dry_run: bool = False) -> dict[str, Any]:
    """Delete local documents for one company and optionally company-level SQLite caches."""
    return cleanup_local_company(market, symbol, delete_pdfs=delete_pdfs, delete_parsed=delete_parsed, delete_company_cache=delete_company_cache, dry_run=dry_run)


@mcp.tool()
def reconcile_local_index_tool(dry_run: bool = False) -> dict[str, Any]:
    """Remove SQLite records whose PDF or parsed directory has been deleted outside the tool."""
    return reconcile_local_document_index(dry_run=dry_run)


@mcp.tool()
def route_query(query: str) -> dict[str, Any]:
    """Route query to lowest-cost path."""
    return _route_query(query)


@mcp.tool()
def get_evidence_packet_tool(query: str, market: str | None = None, symbol: str | None = None, document_id: str | None = None, max_pages: int = 8, max_chars: int = 12000, strategy: str = "auto", include_retrieval_plan: bool = False) -> dict[str, Any]:
    """Return bounded EvidencePacket for low-token analysis. Full retrieval plan is opt-in."""
    return get_evidence_packet(query, market=market, symbol=symbol, document_id=document_id, max_pages=max_pages, max_chars=max_chars, strategy=strategy, include_retrieval_plan=include_retrieval_plan)


@mcp.tool()
def build_company_dossier_tool(market: str, symbol: str, query: str | None = None) -> dict[str, Any]:
    """Build a concise company dossier with structured data and optional evidence."""
    return build_company_dossier(market, symbol, query)


@mcp.tool()
def compare_structured_data_with_report_tool(market: str, symbol: str, query: str, document_id: str | None = None) -> dict[str, Any]:
    """Build structured data + EvidencePacket for report cross-validation."""
    return compare_structured_data_with_report(market, symbol, query, document_id)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
