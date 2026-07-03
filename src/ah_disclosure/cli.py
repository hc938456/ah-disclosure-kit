from __future__ import annotations

import argparse
import json

from ah_disclosure import __version__
from ah_disclosure.identity.resolver import resolve_company
from ah_disclosure.identity.hkex_stockid_resolver import resolve_hkex_stock_id
from ah_disclosure.mcp_server import server_info
from ah_disclosure.pdf.ingest import ingest_pdf
from ah_disclosure.services.company_data_service import (
    get_business_info,
    get_company_profile,
    get_dividends,
    get_financial_indicators,
    get_financial_statements,
    get_shareholders,
)
from ah_disclosure.services.disclosure_service import (
    download_and_ingest_a_report,
    download_and_ingest_h_report,
    search_a_annual_report,
    search_a_filings,
    search_h_annual_report,
    search_h_filings,
)
from ah_disclosure.services.dossier_service import build_company_dossier
from ah_disclosure.services.evidence_service import get_evidence_packet
from ah_disclosure.services.local_search_service import (
    cleanup_local_company,
    cleanup_local_document,
    list_local_documents,
    reconcile_local_document_index,
    search_local_document_text,
)
from ah_disclosure.services.prospectus_service import search_a_offering_documents, search_prospectus


def dump(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def _asdict(obj):
    return obj.to_dict() if hasattr(obj, "to_dict") else obj


def _resolve_command(a):
    if a.market == "H":
        return resolve_hkex_stock_id(
            a.symbol,
            candidate_stock_id=a.candidate_stock_id,
            company_keyword=a.company_name,
        )
    return _asdict(resolve_company(a.symbol, a.market))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ah-disclosure")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("server-info").set_defaults(func=lambda a: dump(server_info()))

    p = sub.add_parser("resolve")
    p.add_argument("--market", choices=["A", "H"], default=None)
    p.add_argument("--symbol", required=True)
    p.add_argument("--candidate-stock-id", default=None)
    p.add_argument("--company-name", default="")
    p.set_defaults(func=lambda a: dump(_resolve_command(a)))

    a_cmd = sub.add_parser("a")
    a_sub = a_cmd.add_subparsers(dest="a_cmd", required=True)
    p = a_sub.add_parser("profile"); p.add_argument("--symbol", required=True); p.set_defaults(func=lambda a: dump(get_company_profile("A", a.symbol)))
    p = a_sub.add_parser("business"); p.add_argument("--symbol", required=True); p.set_defaults(func=lambda a: dump(get_business_info("A", a.symbol)))
    p = a_sub.add_parser("financials"); p.add_argument("--symbol", required=True); p.add_argument("--statement", default="all"); p.set_defaults(func=lambda a: dump(get_financial_statements("A", a.symbol, a.statement)))
    p = a_sub.add_parser("indicators"); p.add_argument("--symbol", required=True); p.set_defaults(func=lambda a: dump(get_financial_indicators("A", a.symbol)))
    p = a_sub.add_parser("dividends"); p.add_argument("--symbol", required=True); p.set_defaults(func=lambda a: dump(get_dividends("A", a.symbol)))
    p = a_sub.add_parser("shareholders"); p.add_argument("--symbol", required=True); p.add_argument("--data-type", default="shareholder_count"); p.set_defaults(func=lambda a: dump(get_shareholders("A", a.symbol, data_type=a.data_type)))
    p = a_sub.add_parser("filings"); p.add_argument("--symbol", required=True); p.add_argument("--category", default="年报"); p.add_argument("--keyword", default=""); p.add_argument("--start-date", default="20200101"); p.add_argument("--end-date", default="20261231"); p.add_argument("--max-rows", type=int, default=20); p.set_defaults(func=lambda a: dump(search_a_filings(a.symbol, category=a.category, keyword=a.keyword, start_date=a.start_date, end_date=a.end_date, max_rows=a.max_rows)))
    p = a_sub.add_parser("report"); p.add_argument("--symbol", required=True); p.add_argument("--year", type=int); p.add_argument("--start-date", default="20200101"); p.add_argument("--end-date", default="20261231"); p.add_argument("--download", action="store_true"); p.add_argument("--ingest", action="store_true"); p.set_defaults(func=lambda a: dump(download_and_ingest_a_report(a.symbol, a.year, start_date=a.start_date, end_date=a.end_date, ingest=a.ingest) if a.download else search_a_annual_report(a.symbol, a.year, start_date=a.start_date, end_date=a.end_date)))
    p = a_sub.add_parser("prospectus"); p.add_argument("--symbol"); p.add_argument("--keyword", default=""); p.add_argument("--max-rows", type=int, default=20); p.set_defaults(func=lambda a: dump(search_prospectus("A", symbol=a.symbol, company_keyword=a.keyword, max_rows=a.max_rows)))
    p = a_sub.add_parser("offering"); p.add_argument("--symbol", required=True); p.add_argument("--keyword", default="募集说明书"); p.add_argument("--max-rows", type=int, default=20); p.set_defaults(func=lambda a: dump(search_a_offering_documents(a.symbol, keyword=a.keyword, max_rows=a.max_rows)))

    h_cmd = sub.add_parser("h")
    h_sub = h_cmd.add_subparsers(dest="h_cmd", required=True)
    p = h_sub.add_parser("profile"); p.add_argument("--symbol", required=True); p.set_defaults(func=lambda a: dump(get_company_profile("H", a.symbol)))
    p = h_sub.add_parser("financials"); p.add_argument("--symbol", required=True); p.add_argument("--statement", default="all"); p.set_defaults(func=lambda a: dump(get_financial_statements("H", a.symbol, a.statement)))
    p = h_sub.add_parser("indicators"); p.add_argument("--symbol", required=True); p.set_defaults(func=lambda a: dump(get_financial_indicators("H", a.symbol)))
    p = h_sub.add_parser("dividends"); p.add_argument("--symbol", required=True); p.set_defaults(func=lambda a: dump(get_dividends("H", a.symbol)))
    p = h_sub.add_parser("filings"); p.add_argument("--symbol", required=True); p.add_argument("--hkex-stock-id"); p.add_argument("--keyword", default=""); p.add_argument("--max-rows", type=int, default=20); p.add_argument("--lang", default="EN"); p.set_defaults(func=lambda a: dump(search_h_filings(a.symbol, a.hkex_stock_id, title_keyword=a.keyword, max_rows=a.max_rows, verify=False, lang=a.lang)))
    p = h_sub.add_parser("report"); p.add_argument("--symbol", required=True); p.add_argument("--year", type=int); p.add_argument("--hkex-stock-id"); p.add_argument("--download", action="store_true"); p.add_argument("--ingest", action="store_true"); p.add_argument("--lang", default="EN"); p.set_defaults(func=lambda a: dump(download_and_ingest_h_report(a.symbol, report_year=a.year, hkex_stock_id=a.hkex_stock_id, ingest=a.ingest, lang=a.lang) if a.download else search_h_annual_report(a.symbol, report_year=a.year, hkex_stock_id=a.hkex_stock_id, lang=a.lang)))
    p = h_sub.add_parser("prospectus"); p.add_argument("--symbol", required=True); p.add_argument("--hkex-stock-id"); p.add_argument("--keyword", default=""); p.add_argument("--max-rows", type=int, default=20); p.add_argument("--lang", default="EN"); p.set_defaults(func=lambda a: dump(search_prospectus("H", symbol=a.symbol, company_keyword=a.keyword, max_rows=a.max_rows, hkex_stock_id=a.hkex_stock_id, lang=a.lang)))

    p = sub.add_parser("financials"); p.add_argument("--market", choices=["A", "H"], required=True); p.add_argument("--symbol", required=True); p.add_argument("--statement", default="all"); p.set_defaults(func=lambda a: dump(get_financial_statements(a.market, a.symbol, a.statement)))
    p = sub.add_parser("indicators"); p.add_argument("--market", choices=["A", "H"], required=True); p.add_argument("--symbol", required=True); p.set_defaults(func=lambda a: dump(get_financial_indicators(a.market, a.symbol)))
    p = sub.add_parser("dividends"); p.add_argument("--market", choices=["A", "H"], required=True); p.add_argument("--symbol", required=True); p.set_defaults(func=lambda a: dump(get_dividends(a.market, a.symbol)))

    p = sub.add_parser("prospectus"); p.add_argument("--market", choices=["A", "H"], required=True); p.add_argument("--symbol", default=""); p.add_argument("--keyword", default=""); p.add_argument("--board", default="all"); p.add_argument("--max-rows", type=int, default=20); p.add_argument("--hkex-stock-id"); p.add_argument("--lang", default="EN"); p.set_defaults(func=lambda a: dump(search_prospectus(a.market, symbol=a.symbol or None, company_keyword=a.keyword, board=a.board, max_rows=a.max_rows, hkex_stock_id=a.hkex_stock_id, lang=a.lang)))

    pdf = sub.add_parser("pdf")
    pdf_sub = pdf.add_subparsers(dest="pdf_cmd", required=True)
    p = pdf_sub.add_parser("ingest"); p.add_argument("--pdf-path", required=True); p.add_argument("--mode", default="auto"); p.add_argument("--vector", action="store_true"); p.add_argument("--full-text", action="store_true"); p.add_argument("--markdown", action="store_true"); p.add_argument("--tables", action="store_true"); p.add_argument("--ocr", default="auto"); p.add_argument("--ocr-lang", default="chi_sim+eng"); p.add_argument("--overwrite", action="store_true"); p.set_defaults(func=lambda a: dump(ingest_pdf(a.pdf_path, mode=a.mode, build_vector_index_opt=a.vector, write_full_text=a.full_text, write_markdown=a.markdown, extract_tables_opt=a.tables, ocr=a.ocr, ocr_lang=a.ocr_lang, overwrite=a.overwrite)))

    local = sub.add_parser("local")
    local_sub = local.add_subparsers(dest="local_cmd", required=True)
    p = local_sub.add_parser("search"); p.add_argument("--query", required=True); p.add_argument("--document-id"); p.add_argument("--limit", type=int, default=8); p.set_defaults(func=lambda a: dump(search_local_document_text(a.query, a.document_id, a.limit)))
    p = local_sub.add_parser("list"); p.add_argument("--limit", type=int, default=50); p.set_defaults(func=lambda a: dump(list_local_documents(a.limit)))
    p = local_sub.add_parser("cleanup-document"); p.add_argument("--document-id", required=True); p.add_argument("--keep-pdf", action="store_true"); p.add_argument("--keep-parsed", action="store_true"); p.add_argument("--dry-run", action="store_true"); p.set_defaults(func=lambda a: dump(cleanup_local_document(a.document_id, delete_pdf=not a.keep_pdf, delete_parsed=not a.keep_parsed, dry_run=a.dry_run)))
    p = local_sub.add_parser("cleanup-company"); p.add_argument("--market", choices=["A", "H"], required=True); p.add_argument("--symbol", required=True); p.add_argument("--keep-pdfs", action="store_true"); p.add_argument("--keep-parsed", action="store_true"); p.add_argument("--delete-company-cache", action="store_true"); p.add_argument("--dry-run", action="store_true"); p.set_defaults(func=lambda a: dump(cleanup_local_company(a.market, a.symbol, delete_pdfs=not a.keep_pdfs, delete_parsed=not a.keep_parsed, delete_company_cache=a.delete_company_cache, dry_run=a.dry_run)))
    p = local_sub.add_parser("reconcile"); p.add_argument("--dry-run", action="store_true"); p.set_defaults(func=lambda a: dump(reconcile_local_document_index(dry_run=a.dry_run)))

    p = sub.add_parser("evidence"); p.add_argument("--query", required=True); p.add_argument("--market"); p.add_argument("--symbol"); p.add_argument("--document-id"); p.add_argument("--max-pages", type=int, default=8); p.add_argument("--max-chars", type=int, default=12000); p.add_argument("--strategy", default="auto"); p.add_argument("--retrieval-plan", action="store_true"); p.set_defaults(func=lambda a: dump(get_evidence_packet(a.query, market=a.market, symbol=a.symbol, document_id=a.document_id, max_pages=a.max_pages, max_chars=a.max_chars, strategy=a.strategy, include_retrieval_plan=a.retrieval_plan)))
    p = sub.add_parser("dossier"); p.add_argument("--market", choices=["A", "H"], required=True); p.add_argument("--symbol", required=True); p.add_argument("--query", default=""); p.set_defaults(func=lambda a: dump(build_company_dossier(a.market, a.symbol, a.query)))

    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
