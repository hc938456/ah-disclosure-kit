# Operations

## Tool routing

| Intent | Primary path | Boundary |
|---|---|---|
| Check version/data directory | `server_info` | Do not infer paths from the working directory |
| Find official filing | `find_filing_source_tool` | Do not download or ingest |
| Download annual report | `download_report_tool` | Do not ingest unless requested |
| Download and ingest annual report | Ready cache: `download_and_ingest_report`; cold start: `find_filing_source_tool` → `download_report_tool` → cache-ready `download_and_ingest_report` | Do not place source lookup, download, validation, and ingest in one cold-start call |
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
| Analyze filing not ready locally | Staged preparation, then `get_evidence_packet_tool` | Use `ensure_filing_evidence_tool` only for a cache-ready one-call path |
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
- CNINFO uses a stable `latest` cache key across day changes, a bounded candidate window, a per-request timeout, and a complete lookup budget. The defaults are 10 seconds per request and 40 seconds per lookup; override them under `[network]` only when the environment requires it.
- CNINFO honors configured system proxies. A proxy or network failure returns structured `source_lookup_error` status and probes cache; the Kit does not silently bypass an explicitly configured proxy.
- When the user requests offline operation, set `offline=true` and do not fall back to websites or generic web search.
- Preserve equal-score ambiguity instead of silently selecting a filing.
- Validate title, company identity, code, year, language, size, page count, and required sections before promotion from staging.
- Reject release notices, summaries, letters, and other short documents when a full report or prospectus is required.
- The Kit does not provide a complete structured full-year Hong Kong IPO/new-listing company list; label any external discovery source separately.

## Cold start and timeout recovery

- Define a cold start as no exact ready local document for the requested company, market, filing type, year, and language.
- On a cold start, run these bounded stages: inspect local documents → locate official source → download and validate → cache-ready ingest → retrieve evidence.
- Do not set `refresh=true` unless the user requests a refresh or the source cache is missing, stale, or demonstrably wrong.
- For an internally bounded CNINFO timeout, inspect `execution_info.source_timeout`, `source_timeout_recovered`, `source_cache_hit`, and `timings_ms.cache_recovery`. The Kit already performs one automatic source-cache probe.
- Treat one host timeout as failure of that stage. Do not repeat the same combined call with identical arguments.
- After a timeout, inspect local readiness and cached source results. These read-only checks may run in parallel. Continue from the first missing stage:
  - source cached, no PDF: download;
  - pipeline-linked PDF present, no parsed/indexed document: call cache-ready `download_and_ingest_report` with the same identity and `ingest=true`;
  - user-provided local PDF: use `ingest_pdf_tool`, then verify document identity and metadata before analysis;
  - parsed document ready: retrieve evidence;
  - no reusable state: retry source lookup once without forced refresh, then report the external-source failure.
- Report available `execution_info`, cache hits, and stage timings. Do not attribute a timeout to the exchange unless a direct refreshed source lookup also fails.

## HKEX language fallback

- Keep the user's answer language independent from the filing language used for evidence.
- Start with the requested filing language. If the user did not require verbatim Chinese text, an official English filing may be used for analysis.
- Suspect an unusable text layer when extracted character volume is substantial but required sections have zero matches, evidence is nonsensical, or text-quality/OCR flags conflict with the visible PDF.
- Before OCR or manual re-download, locate the official filing in the alternate language for the same company, code, report year, and filing type.
- Switch only after verifying official HKEXnews identity and disclose the switch. Preserve the original-language official URL when useful.
- Prefer a valid native English text layer over OCR of a Chinese PDF with a broken font map. Use OCR when no reliable official text-layer alternative exists or the user specifically requires Chinese page text.

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
**Last modified:** 2026-07-30 00:37
**Last modified model:** OpenAI GPT
