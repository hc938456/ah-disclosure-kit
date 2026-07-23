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
            raise RuntimeError(
                "The 'mcp' package is required to run the MCP server. "
                "Install ah-disclosure-kit with the 'mcp' extra."
            )

from ah_disclosure.core.naming import (
    build_document_id,
    build_pdf_filename,
    infer_report_year,
    normalize_document_type,
)
from ah_disclosure.core.paths import get_data_paths
from ah_disclosure.identity.resolver import resolve_company as _resolve_company
from ah_disclosure.identity.hkex_stockid_resolver import HkexStockIdResolver
from ah_disclosure.pdf.downloader import download_file
from ah_disclosure.pdf.ingest import ingest_pdf as _ingest_pdf
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
from ah_disclosure.services.cache_audit_service import audit_local_pdf_cache
from ah_disclosure.services.analysis_service import (
    continue_llm_analysis,
    execute_llm_analysis_plan,
    prepare_llm_analysis,
)
from ah_disclosure.services.calculation_service import verify_analysis_calculations
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
from ah_disclosure.services.filing_pipeline import ensure_filing_evidence, find_filing_source
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
from ah_disclosure.services.server_info_service import get_server_info

mcp = FastMCP("ah-disclosure")


@mcp.tool()
def server_info() -> dict[str, Any]:
    """Return ah-disclosure server information."""
    return get_server_info()


@mcp.tool()
def list_capabilities() -> dict[str, Any]:
    """List high-level capabilities and token governance policy."""
    return {
        "structured_data": ["company_profile", "financials", "dividends", "shareholders", "capital_actions", "governance_esg"],
        "filings": ["CNINFO A-share", "HKEXnews H-share"],
        "source_cache": ["local-first", "TTL", "refresh", "offline", "stale fallback"],
        "prospectus": ["A IPO", "A offering documents", "H listing documents"],
        "pdf": ["download", "download-only", "ingest", "pages.jsonl", "SQLite FTS", "optional full_text.txt", "optional document.md"],
        "cleanup": ["audit_local_pdf_cache", "cleanup_document", "cleanup_company", "reconcile_local_index"],
        "batch_cli": ["CSV", "JSON", "JSONL", "controlled concurrency", "checkpoint resume"],
        "token_governance": ["query_router", "evidence_packet", "accounting_policy_strategy", "financial_analysis_strategy", "context_budget"],
        "llm_analysis": ["provider-neutral planning contract", "dynamic claim retrieval", "provider-neutral parallel worker work units", "evidence review", "bounded follow-up retrieval", "evidence-linked decimal calculations", "declarative calculation graph", "bounded evidence registry"],
        "high_level_tools": ["find_filing_source", "ensure_filing_evidence"],
        "unsupported": ["complete structured full-year Hong Kong IPO/new-listing company list"],
    }


@mcp.tool()
def resolve_company(symbol: str, market: str | None = None) -> dict[str, Any]:
    """Resolve A/H company identity."""
    result = _resolve_company(symbol, market)
    return result.to_dict() if hasattr(result, "to_dict") else result


@mcp.tool()
def resolve_hkex_stock_id(hk_code: str, candidate_stock_id: str | None = None, company_name: str | None = None, verify: bool = True, refresh: bool = False) -> dict[str, Any]:
    """Resolve/cache HKEX internal stockId for a Hong Kong stock code."""
    return HkexStockIdResolver().resolve(hk_code, candidate_stock_id=candidate_stock_id, company_name=company_name, verify=verify, refresh=refresh)


@mcp.tool()
def search_filings(market: str, symbol: str, category: str = "年报", keyword: str = "", start_date: str = "20200101", end_date: str | None = None, max_rows: int = 20, hkex_stock_id: str | None = None, lang: str = "EN", prefer_cache: bool = True, refresh: bool = False, offline: bool = False, max_cache_age_seconds: int | None = None) -> list[dict[str, Any]]:
    """Search filings for A/H market."""
    if market.upper().startswith("H"):
        return search_h_filings(symbol, hkex_stock_id=hkex_stock_id, title_keyword=keyword, max_rows=max_rows, lang=lang, prefer_cache=prefer_cache, refresh=refresh, offline=offline, max_cache_age_seconds=max_cache_age_seconds)
    return search_a_filings(symbol=symbol, category=category, keyword=keyword, start_date=start_date, end_date=end_date, max_rows=max_rows, prefer_cache=prefer_cache, refresh=refresh, offline=offline, max_cache_age_seconds=max_cache_age_seconds)


@mcp.tool()
def search_annual_report(market: str, symbol: str, year: int | None = None, max_rows: int = 10, hkex_stock_id: str | None = None, lang: str = "EN", prefer_cache: bool = True, refresh: bool = False, offline: bool = False, max_cache_age_seconds: int | None = None) -> list[dict[str, Any]]:
    """Search annual reports. A uses CNINFO; H uses HKEXnews."""
    if market.upper().startswith("H"):
        return search_h_annual_report(symbol, report_year=year, hkex_stock_id=hkex_stock_id, max_rows=max_rows, lang=lang, prefer_cache=prefer_cache, refresh=refresh, offline=offline, max_cache_age_seconds=max_cache_age_seconds)
    return search_a_annual_report(symbol, report_year=year, max_rows=max_rows, prefer_cache=prefer_cache, refresh=refresh, offline=offline, max_cache_age_seconds=max_cache_age_seconds)


@mcp.tool()
def download_and_ingest_filing(record: dict[str, Any], ingest: bool = True) -> dict[str, Any]:
    """Download a filing record and optionally ingest it. Accepts a record from search tools."""
    market = (record.get("market") or "").upper()
    document_type = normalize_document_type(record.get("document_type"), record.get("title"))
    symbol = str(record.get("symbol") or "").strip()
    if document_type in {"annual_report", "prospectus"} and market and symbol:
        year_value = infer_report_year(
            record.get("title"), record.get("publish_time"), record.get("report_year")
        )
        validated = ensure_filing_evidence(
            query=str(record.get("title") or document_type),
            market=market,
            symbol=symbol,
            document_type=document_type,
            report_year=int(year_value) if str(year_value or "").isdigit() else None,
            language=record.get("language"),
            company_name=record.get("company_name"),
            ingest_if_missing=ingest,
        )
        validated["requested_record"] = record
        validated["validated_pipeline"] = True
        return validated
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
def search_prospectus_tool(market: str = "A", company_keyword: str = "", symbol: str = "", board: str = "all", max_rows: int = 20, hkex_stock_id: str | None = None, lang: str = "EN", prefer_cache: bool = True, refresh: bool = False, offline: bool = False, max_cache_age_seconds: int | None = None) -> list[dict[str, Any]]:
    """Search A/H prospectus, listing, and offering documents."""
    return search_prospectus(market, symbol=symbol or None, company_keyword=company_keyword, board=board, max_rows=max_rows, hkex_stock_id=hkex_stock_id, lang=lang, prefer_cache=prefer_cache, refresh=refresh, offline=offline, max_cache_age_seconds=max_cache_age_seconds)


@mcp.tool()
def find_filing_source_tool(market: str, symbol: str, document_type: str, report_year: int | None = None, language: str | None = None, max_rows: int = 10, prefer_cache: bool = True, refresh: bool = False, offline: bool = False, max_cache_age_seconds: int | None = None, hkex_stock_id: str | None = None, company_name: str | None = None) -> dict[str, Any]:
    """Find filing PDF sources without downloading or ingesting the document."""
    return find_filing_source(market, symbol, document_type, report_year=report_year, language=language, max_rows=max_rows, prefer_cache=prefer_cache, refresh=refresh, offline=offline, max_cache_age_seconds=max_cache_age_seconds, hkex_stock_id=hkex_stock_id, company_name=company_name)


@mcp.tool()
def ensure_filing_evidence_tool(query: str, market: str, symbol: str, document_type: str, report_year: int | None = None, language: str | None = None, document_id: str | None = None, max_pages: int = 8, max_chars: int = 12000, strategy: str = "auto", prefer_cache: bool = True, refresh_source: bool = False, offline: bool = False, ingest_if_missing: bool = True, ocr: str = "auto", hkex_stock_id: str | None = None, company_name: str | None = None) -> dict[str, Any]:
    """Resolve a filing locally first, then download/ingest only when evidence is required."""
    return ensure_filing_evidence(query, market, symbol, document_type, report_year=report_year, language=language, document_id=document_id, max_pages=max_pages, max_chars=max_chars, strategy=strategy, prefer_cache=prefer_cache, refresh_source=refresh_source, offline=offline, ingest_if_missing=ingest_if_missing, ocr=ocr, hkex_stock_id=hkex_stock_id, company_name=company_name)


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
def audit_local_pdf_cache_tool(scan_content: bool = False) -> dict[str, Any]:
    """Read-only audit for duplicate, unreferenced, staged, missing, or structurally suspicious PDFs."""
    return audit_local_pdf_cache(scan_content=scan_content)


@mcp.tool()
def route_query(query: str) -> dict[str, Any]:
    """Route query to lowest-cost path."""
    return _route_query(query)


@mcp.tool()
def get_evidence_packet_tool(query: str, market: str | None = None, symbol: str | None = None, document_id: str | None = None, max_pages: int = 8, max_chars: int = 12000, strategy: str = "auto", include_retrieval_plan: bool = False) -> dict[str, Any]:
    """Return bounded EvidencePacket for low-token analysis. Full retrieval plan is opt-in."""
    return get_evidence_packet(query, market=market, symbol=symbol, document_id=document_id, max_pages=max_pages, max_chars=max_chars, strategy=strategy, include_retrieval_plan=include_retrieval_plan)


@mcp.tool()
def prepare_llm_analysis_tool(query: str, market: str | None = None, symbol: str | None = None, document_id: str | None = None, max_claims: int = 12, max_queries_per_claim: int = 8) -> dict[str, Any]:
    """Return the JSON contract an external LLM uses to plan arbitrary filing analysis."""
    return prepare_llm_analysis(
        query,
        market=market,
        symbol=symbol,
        document_id=document_id,
        max_claims=max_claims,
        max_queries_per_claim=max_queries_per_claim,
    )


@mcp.tool()
def execute_llm_analysis_plan_tool(query: str, analysis_plan: dict[str, Any], market: str | None = None, symbol: str | None = None, document_id: str | None = None, max_pages_per_claim: int = 6, max_chars_per_claim: int = 8000, max_total_chars: int = 48000, round_no: int = 1) -> dict[str, Any]:
    """Execute an LLM-authored claim plan against local ingest indexes for evidence review."""
    return execute_llm_analysis_plan(
        query,
        analysis_plan,
        market=market,
        symbol=symbol,
        document_id=document_id,
        max_pages_per_claim=max_pages_per_claim,
        max_chars_per_claim=max_chars_per_claim,
        max_total_chars=max_total_chars,
        round_no=round_no,
    )


@mcp.tool()
def continue_llm_analysis_tool(query: str, analysis_plan: dict[str, Any], evidence_review: dict[str, Any], market: str | None = None, symbol: str | None = None, document_id: str | None = None, current_round: int = 1, max_rounds: int = 2, max_pages_per_claim: int = 6, max_chars_per_claim: int = 8000, max_total_chars: int = 48000, prior_analysis_result: dict[str, Any] | None = None, prior_analysis_id: str | None = None) -> dict[str, Any]:
    """Process LLM evidence gaps with bounded retrieval and scoped full-page expansion."""
    return continue_llm_analysis(
        query,
        analysis_plan,
        evidence_review,
        market=market,
        symbol=symbol,
        document_id=document_id,
        current_round=current_round,
        max_rounds=max_rounds,
        max_pages_per_claim=max_pages_per_claim,
        max_chars_per_claim=max_chars_per_claim,
        max_total_chars=max_total_chars,
        prior_analysis_result=prior_analysis_result,
        prior_analysis_id=prior_analysis_id,
    )


@mcp.tool()
def verify_analysis_calculations_tool(calculations: list[dict[str, Any]], allowed_evidence_ids: list[str] | None = None, evidence_catalog: dict[str, str] | None = None) -> dict[str, Any]:
    """Safely execute evidence-linked Decimal formulas and tolerance checks."""
    return verify_analysis_calculations(
        calculations,
        allowed_evidence_ids=set(allowed_evidence_ids) if allowed_evidence_ids is not None else None,
        evidence_catalog=evidence_catalog,
    )


@mcp.tool()
def build_company_dossier_tool(market: str, symbol: str, query: str | None = None) -> dict[str, Any]:
    """Build a concise company dossier with structured data and optional evidence."""
    return build_company_dossier(market, symbol, query or "")


@mcp.tool()
def compare_structured_data_with_report_tool(market: str, symbol: str, query: str, document_id: str | None = None) -> dict[str, Any]:
    """Build structured data + EvidencePacket for report cross-validation."""
    return compare_structured_data_with_report(market, symbol, query, document_id)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
