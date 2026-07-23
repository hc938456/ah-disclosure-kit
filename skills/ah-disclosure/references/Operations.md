# Operations

## Tool routing

| Intent | Primary path | Boundary |
|---|---|---|
| Check version/data directory | `server_info` | Do not infer paths from the working directory |
| Find official filing | `find_filing_source_tool` | Do not download or ingest |
| Download annual report | `download_report_tool` | Do not ingest unless requested |
| Download and ingest annual report | `download_and_ingest_report` | Use only when ingest is explicit or analysis requires it |
| Prospectus/listing document | `search_prospectus_tool` → `download_prospectus_tool` or `download_and_ingest_prospectus_tool` | Match ingest behavior to intent |
| Ingest a local PDF | `ingest_pdf_tool` | Preserve the requested OCR and output boundaries |
| Company profile | `get_company_profile_tool` | Identify provider and as-of context |
| Financial statements | `get_financial_statements_tool` | Preserve statement type, period, currency, and units |
| Financial indicators | `get_financial_indicators_tool` | Preserve provider metric definitions |
| Dividends/shareholders | `get_dividends_tool` / `get_shareholders_tool` | Preserve event date and coverage |
| Capital actions/governance/ESG | `get_capital_actions_tool` / `get_governance_esg_tool` | Keep dataset type explicit |
| Business information | `get_business_info_tool` | Distinguish provider descriptions from filing evidence |
| Multi-source overview | `build_company_dossier_tool` | Keep each source definition visible |
| Provider-versus-filing check | `compare_structured_data_with_report_tool` | Do not silently mix periods or units |
| Inspect local documents | `list_local_documents_tool` → `get_document_meta_tool` | Confirm identity before reuse |
| Analyze filing not ready locally | `ensure_filing_evidence_tool` | Local → cache → official source → download → ingest → evidence |
| Search ingested filing | `get_evidence_packet_tool` | Bind to `document_id` when known |
| Expand located evidence | `get_document_pages_tool` | Recover complete headers, tables, and adjacent pages |
| Provider data cross-check | structured-data tools | Keep provider and filing evidence separate |
| Audit or cleanup | `audit_local_pdf_cache_tool` → `cleanup_document_tool`, `cleanup_company_tool`, or `reconcile_local_index_tool` | Use `dry_run=true` before deletion |

## Evidence strategy

- Use `strategy="accounting_policy"` for recognition, measurement, significant policies, and critical estimates.
- Use `strategy="financial_analysis"` for performance, drivers, cash flow, financing, working capital, and management analysis.
- Use `strategy="auto"` only when the intent does not clearly fit either strategy.
- Retrieve provider data separately when cross-validation is needed; do not contaminate a filing-specific EvidencePacket.

## Source and validation

- Prefer CNINFO for A-share filings and HKEXnews for H-share filings.
- Normalize market, code, fiscal year, filing type, and language before selection.
- Prefer cached source results unless refresh is explicitly requested; refresh is not forced re-download.
- When the user requests offline operation, set `offline=true` and do not fall back to websites or generic web search.
- Preserve equal-score ambiguity instead of silently selecting a filing.
- Validate title, company identity, code, year, language, size, page count, and required sections before promotion from staging.
- Reject release notices, summaries, letters, and other short documents when a full report or prospectus is required.
- The Kit does not provide a complete structured full-year Hong Kong IPO/new-listing company list; label any external discovery source separately.

## Ingest, OCR, and cache

- Ingest only for reading, search, analysis, or an explicit ingest request.
- Core outputs are `meta.json`, `pages.jsonl`, `quality_report.json`, and SQLite indexes.
- Do not generate `document.md` or `full_text.txt` by default.
- Reuse extraction and indexes when PDF hash, metadata, page count, and index counts agree.
- Default to `ocr="auto"`; use native text unless scan-like pages require OCR and OCR materially improves quality.
- Treat `requires_ocr=true` as a retrieval limitation, not proof that disclosure is absent.
- Report whether source cache, PDF, parsed cache, validation, and indexes were reused.

## Batch and cleanup

- Use the formal batch prepare path for multi-company download/validate/ingest requests.
- Deduplicate identical tasks and serialize aliases that resolve to the same file.
- Do not begin analysis automatically after a download/ingest-only batch.
- Audit first, preview cleanup with dry-run, review every affected layer, then execute and reconcile.

---
**Document created:** 2026-07-22 18:56
**Last modified:** 2026-07-23 17:02
**Last modified model:** Not set (`ANTHROPIC_MODEL` is empty)
