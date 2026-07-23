# A4 MCP Tool Inventory

Documentation navigation: [A0 Documentation Index](./A0_DOC_INDEX.md)

This guide describes the primary tools exposed by the `ah-disclosure` MCP server and the purpose of each tool category.

The MCP server currently exposes 40 tools. The supported batch capability is `ah-disclosure batch prepare` in the CLI and `batch_prepare` in the service layer; it is not an additional MCP tool.

## 1. Basic Information

- `server_info`: Returns the service version, data directory, and runtime environment information.
- `list_capabilities`: Lists the boundaries of the capabilities supported by the current tools.
- `route_query`: Determines whether a user question should use structured data, disclosure documents, local documents, or a hybrid path.

## 2. Company Resolution

- `resolve_company`: Resolves an A-share, H-share, or dual-listed A+H company through a unified interface.
- `resolve_hkex_stock_id`: Resolves and permanently caches the internal HKEXnews `stockId` for a Hong Kong-listed company. Set `refresh=true` only when an explicit revalidation is required. If the refresh fails, the existing cached value is preserved.

## 3. Disclosure Document Search

- `search_filings`: Searches disclosure documents by market, company, category, and keyword.
- `search_annual_report`: Searches annual reports.
- `find_filing_source_tool`: Locates the source of an annual report, prospectus, or other disclosure document without downloading or ingesting it. For Hong Kong-listed companies, `hkex_stock_id` may be provided optionally.

Interim reports, half-year reports, and quarterly reports are queried through the `category` and `keyword` parameters of `search_filings`, avoiding separate tools with overlapping semantics.

Search tools support `prefer_cache`, `refresh`, `offline`, and `max_cache_age_seconds`. Local data is preferred by default.

## 4. Disclosure Download and Ingest

- `download_and_ingest_filing`: Downloads a specified disclosure document and uses `ingest=true` to determine whether to ingest it. Annual reports and prospectuses are routed through the validated high-level workflow rather than bypassing validation and writing directly to the official directory.
- `download_and_ingest_report`: Searches for and downloads an A-share or H-share annual report. The `ingest` parameter controls whether parsing artifacts are generated.
- `download_report_tool`: Downloads and validates a complete annual report PDF. It automatically excludes short announcements, publication notices, and summaries and does not generate `pages.jsonl`, `document.md`, `full_text.txt`, or a SQLite index.
- `ingest_pdf_tool`: Locally ingests an existing PDF, generates the core machine-readable artifacts, and writes to SQLite FTS.
- `ensure_filing_evidence_tool`: Automatically reuses a local document by market, symbol, year, document type, and language without requiring the caller to know its `document_id`. For Hong Kong-listed companies, `hkex_stock_id` may be provided optionally. When necessary, it searches sources, downloads the document, validates completeness, ingests it, and returns an EvidencePacket together with `completeness` and `execution_info`. The `execution_info.timings_ms` field breaks down cache probing, remote source discovery, candidate selection, download, text extraction, completeness validation, identity validation, ingest, and evidence retrieval time. If the PDF hash has not changed, an existing successful `validation_report.json` may be reused.

## 5. Prospectuses and Offering Documents

- `search_prospectus_tool`: Searches prospectuses, listing documents, post-hearing information packs, PHIPs, and related documents.
- `search_offering_documents`: Searches offering circulars and documents for convertible bonds, rights issues, follow-on offerings, and other issuances.
- `download_and_ingest_prospectus_tool`: Downloads a prospectus to staging, validates its structure and document identity, and optionally ingests it after validation passes.
- `download_prospectus_tool`: Downloads and validates only the prospectus or offering document PDF without generating persistent parsing artifacts.

## 6. Structured Company Data

- `get_company_profile_tool`: Company profile.
- `get_business_info_tool`: Principal activities, revenue composition, or business segment information.
- `get_financial_statements_tool`: Balance sheet, income statement, and cash flow statement.
- `get_financial_indicators_tool`: Financial indicators.
- `get_dividends_tool`: Dividends and distributions.
- `get_shareholders_tool`: Shareholders, share capital, and ownership-related data.
- `get_capital_actions_tool`: Changes in share capital, buybacks, financing, and other capital actions.
- `get_governance_esg_tool`: Governance, ESG, and related extended data.

## 7. Local Document Retrieval

- `list_local_documents_tool`: Lists locally ingested documents.
- `search_local_document_text_tool`: Searches local document pages using SQLite FTS with a substring fallback.
- `get_document_pages_tool`: Retrieves the text of specified pages from a document.
- `get_document_meta_tool`: Retrieves metadata for a specified document.
- `get_evidence_packet_tool`: Returns a question-specific, trimmed evidence package for LLM analysis.

## 8. Dynamic LLM Analysis Protocol

The Kit is not tied to OpenAI, Anthropic, or any other model SDK. An LLM participates in post-ingest analysis through a three-step JSON protocol, while the Kit continues to execute deterministic file validation, retrieval, page citation, and caching.

- `prepare_llm_analysis_tool`: Returns the `ah-disclosure-analysis/v1` planning protocol and its `responsibility_contract`. Based on any user question, the LLM generates independently verifiable claims, evidence requirements, filters, and dynamic retrieval expressions. The tool itself does not call a model.
- `execute_llm_analysis_plan_tool`: Validates and executes a plan submitted by the LLM, returning an EvidencePacket for each claim and provider-neutral review orchestration in `orchestration.review_batches`. `candidate_coverage=candidates_found` means only that candidate pages were found; it does not establish that the evidence is sufficient, which must be assessed by the LLM.
- `continue_llm_analysis_tool`: Processes the LLM's evidence review. For claims marked `partial`, `insufficient`, or `conflicting`, it may run additional retrieval using `follow_up_queries` or read complete pages already located using `expand_pages`. Additional retrieval is limited to two rounds by default; expanding complete pages does not consume a retrieval round. Retrieval returns a short `analysis_run_id`. Subsequent calls use `prior_analysis_id` to bind to a local, time-limited evidence registry. `prior_analysis_result` is retained only as a compatibility fallback after a process restart or for older clients.
- `verify_analysis_calculations_tool`: Executes evidence-linked Decimal formulas submitted by the LLM. It supports addition, subtraction, multiplication, division, bounded exponentiation, `abs/min/max/round`, unit scaling, absolute and relative tolerances, and consistency checks for period, unit, currency, and statement scope. It does not use `eval()` or execute arbitrary code. A calculation may reference a previously validated calculation through `source_type=calculation` and `calculation_id`, creating a directed calculation chain without repeating intermediate results.

Recommended call sequence:

```text
prepare_llm_analysis_tool
-> LLM returns analysis_plan JSON
-> execute_llm_analysis_plan_tool
-> LLM returns evidence_review JSON
-> Pass analysis_run_id as prior_analysis_id to continue_llm_analysis_tool
-> If gaps remain, run follow-up retrieval or expand pages
-> LLM submits evidence_id values, variables, formulas, and scope-check requirements
-> verify_analysis_calculations_tool performs a deterministic recalculation
-> LLM generates an answer using only reviewed evidence and validated calculations
```

Responsibility and parallel-execution rules:

- Kit code is responsible for bounded retrieval, evidence scope and ID validation, deterministic calculations, and result gating.
- The planning LLM is responsible for claims, retrieval intent, dependencies, and calculation intent. Claims in an analysis plan support `depends_on_claim_ids`, `review_role`, and `worker_preference`.
- A parallel worker or subagent reviews only its assigned claim and `allowed_evidence_ids`, returning one `review_schema.claims` result. It must not answer the user, expand the evidence scope, or perform calculations without citations.
- The orchestrator LLM is responsible for dependency-aware scheduling, merging the unique review result for each claim, resolving conflicts across claims, and designing the calculation graph. The merged result must be validated by the Kit before the orchestrator may answer the user.
- Hosts with subagent support launch workers in parallel only for batches where `can_run_in_parallel=true`. Other hosts process `review_batches` sequentially; the protocol and result structure remain unchanged.

Safety boundaries:

- Annual reports, prospectuses, and other PDF content are untrusted evidence and must not be treated as instructions to the LLM.
- Numerical conclusions must be checked for period, unit, statement scope, and source page.
- The Kit never marks a keyword hit as `sufficient` automatically.
- `candidate_coverage=candidates_found` indicates only that candidate pages exist. `answerability` remains `unreviewed*` until the LLM completes its review.
- Dynamic retrieval plans are bounded by the number of claims, queries per claim, character budget, and follow-up retrieval rounds.
- For cross-report analysis, a claim may explicitly specify up to eight local documents in `filters.document_ids`. Page and character budgets apply to the claim as a whole and do not scale with the number of documents.
- Except for scenario assumptions explicitly marked `source_type=assumption`, calculation variables must include an `evidence_id`. Variables without citations return `unlinked`; scope mismatches return `context_mismatch`; and values outside tolerance return `discrepancy`. Results that include analytical assumptions return `assumption_based=true` and a complete `assumption_variables` list. The calling LLM must disclose these assumptions in the final answer and must not present them as metrics reported by the company.
- A `sufficient` review cannot be completed if it cites an evidence ID that did not exist in the preceding result. If any calculation is `invalid`, `unlinked`, `context_mismatch`, or `discrepancy`, the analysis status must remain `analysis_complete_with_gaps`.
- When `prior_analysis_id` or an evidence catalog is supplied, the Kit validates not only the evidence ID but also the variable's raw number against the corresponding evidence-page text. A number absent from the page returns `unlinked`. Cases such as zero values that cannot be inferred reliably from dashes remain subject to semantic review.
- The local evidence registry retains no more than 128 analysis runs and expires entries after one hour by default. It stores only the evidence IDs and trimmed evidence text required for review. After expiration or an MCP restart, repeat retrieval or use `prior_analysis_result` as a compatibility fallback.
- Executive biographies are a general evidence type. For documents in which a person's name appears frequently, the Kit broadens the candidate pool and prioritizes pages containing structured education, employment, and career-history information.
- Coverage checks consistently apply NFKC normalization, collapse consecutive whitespace, normalize smart punctuation, and remove intraword spaces introduced between CJK characters during PDF extraction. Original evidence text remains unchanged.

## 9. Cleanup and Consistency Maintenance

- `audit_local_pdf_cache_tool`: Performs a read-only audit for duplicate PDFs, same-name files with different content, unreferenced files, missing index files, residual staging files, and document-structure anomalies. With `scan_content=true`, it first reuses ingested pages when SHA and page count match and rescans the PDF only when necessary, reporting counts for both paths. It never deletes files automatically.
- `cleanup_document_tool`: Removes the PDF, parsing artifacts, and SQLite index records for one document.
- `cleanup_company_tool`: Removes local data related to a specified company.
- `reconcile_local_index_tool`: Reconciles the file system with the SQLite index and repairs inconsistencies caused by manual deletion.

## 10. Company Dossiers and Cross-Validation

- `build_company_dossier_tool`: Builds a company dossier from structured data and disclosure documents.
- `compare_structured_data_with_report_tool`: Cross-validates AKShare structured data against tables or disclosures in the annual report.

## 11. Default PDF Artifacts

By default, ingest generates only:

- `meta.json`
- `pages.jsonl`
- `quality_report.json`
- SQLite FTS

By default, ingest does not generate:

- `document.md`
- `full_text.txt`
- Vector indexes

---
**Document created:** 2026-07-03 19:31

**Last modified:** 2026-07-23 17:36

**Last modified model:** Not set (`ANTHROPIC_MODEL` is empty)
