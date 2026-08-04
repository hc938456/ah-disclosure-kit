---
name: ah-disclosure
description: Retrieve structured A/H company data and download, ingest, search, audit, and analyze A-share and H-share disclosure documents through the ah_disclosure MCP server. Use for company profiles and business information, financial statements and indicators, dividends, shareholders, capital actions, governance/ESG, CNINFO or HKEXnews annual and interim reports, prospectuses, listing documents, local PDF evidence, accounting policies, management-analysis transformations, financial statement tie-outs, effective tax rate, working capital, cash flow, financing, and ROE/ROIC.
---

# A/H Disclosure

Use `ah_disclosure` as the deterministic backend. Let the LLM interpret flexible questions and design claims; let the Kit locate filings, ingest, retrieve bounded evidence, calculate, reconcile, detect conflicts, and block unsupported completion.

## Core rules

1. Distinguish structured data, source lookup, download only, download plus ingest, simple evidence retrieval, and complex analysis.
2. Do not ingest when the user only requests a URL or PDF download.
3. Bind analysis to company, market, filing type, report period, language, and `document_id`.
4. Treat search hits as candidates until page, table, headers, units, scope, and comparative period are reviewed.
5. Use deterministic calculation tools for arithmetic and tie-outs; do not rely on LLM mental arithmetic.
6. Separate disclosed facts, verified calculations, management reclassifications, and `⚠️ Inference`.
7. Never return `sufficient` with unresolved gaps or present a failed tie-out as complete.
8. Use cleanup tools with dry-run instead of manually deleting PDFs, parsed artifacts, or SQLite rows.
9. CNINFO source lookups are internally bounded and automatically probe source cache after timeout or network failure. Treat `source_lookup_timeout`, `source_lookup_error`, or a host timeout as a failed stage; inspect `execution_info` and resume from the first missing stage instead of repeating a monolithic call.

## Route the request

- Source or candidate only: use `find_filing_source_tool`.
- Annual-report download only: use `download_report_tool`; do not ingest.
- Annual-report download plus ingest: reuse an exact ready local document when available. On a cold start, use `find_filing_source_tool` → `download_report_tool` → cache-ready `download_and_ingest_report` with `ingest=true`. Never start with or repeat the combined call after a timeout.
- Prospectus or listing document: use `search_prospectus_tool`, then `download_prospectus_tool` for download only or `download_and_ingest_prospectus_tool` when ingest is required.
- Local PDF ingest: use `ingest_pdf_tool`.
- Structured company facts: use `get_company_profile_tool`, `get_financial_statements_tool`, `get_financial_indicators_tool`, `get_dividends_tool`, `get_shareholders_tool`, `get_capital_actions_tool`, or `get_governance_esg_tool` according to the requested dataset.
- Business descriptions or composition: use `get_business_info_tool`.
- Multi-source overview: use `build_company_dossier_tool`; use `compare_structured_data_with_report_tool` only for an explicit provider-versus-filing comparison.
- Inspect existing local documents: use `list_local_documents_tool`, then `get_document_meta_tool` when details are needed.
- Filing not yet ready for analysis: use the staged preparation path below. Use `ensure_filing_evidence_tool` only when a cache-ready one-call path is appropriate.
- Already-ingested filing, simple question: use `get_evidence_packet_tool` with `strategy="accounting_policy"` or `strategy="financial_analysis"` when the intent is clear.
- Clipped page or multi-page table: use `get_document_pages_tool`.
- Complex, multi-claim, or non-standard question: use the analysis protocol below.
- Installation, data-directory, or version uncertainty: call `server_info`.

Read [Operations.md](references/Operations.md) for source, validation, ingest, OCR, cache, batch, and cleanup decisions.

## Prepare a filing without blind waits

1. Check exact local readiness by company, market, filing type, year, language, and `document_id`.
2. If no ready document exists, locate the official source without downloading.
3. Download and validate the selected filing without ingesting.
4. Once the PDF and validation cache are ready, call `download_and_ingest_report` with the same identity and `ingest=true` so filing metadata is preserved, then retrieve evidence.
5. After a CNINFO timeout, first inspect `execution_info.source_timeout_recovered`; the Kit has already probed source cache. After a host or combined-stage timeout, check source cache and local artifacts, then resume at the first incomplete stage instead of restarting the workflow.

Keep answer language separate from filing language. For HKEX analysis, when a Chinese PDF has substantial extracted text but zero required-section matches, garbled or unusable evidence, or a broken text layer, try the same official English filing before OCR or manual diagnosis. Preserve company, code, year, filing type, and official-source identity, and disclose the language switch.

## Analyze complex questions

1. Call `prepare_llm_analysis_tool`.
2. Have the LLM define independent claims, dynamic multilingual queries, evidence requirements, dependencies, formulas, units, and completion criteria.
3. Call `execute_llm_analysis_plan_tool`.
4. Review each claim as `sufficient`, `partial`, `insufficient`, or `conflicting`.
5. Use `continue_llm_analysis_tool` for missing evidence and `get_document_pages_tool` for clipped evidence.
6. Call `verify_analysis_calculations_tool` with evidence-linked inputs.
7. Answer only claims that pass the completion gates.

Read [Analysis_Protocol.md](references/Analysis_Protocol.md) before multi-round analysis or finalizing evidence-backed conclusions. Read [Financial_Analysis.md](references/Financial_Analysis.md) for cash flow, financing, ETR, management balance sheet, DuPont, ROIC, equity incentives, or cross-document reconciliation.

## Divide responsibilities

```text
LLM: interpret intent, define claims and accounting scope, review evidence,
     explain differences, label inference, and write the answer

Kit: locate and validate filings, ingest and index pages, retrieve evidence,
     calculate and reconcile, preserve IDs, detect conflicts, and enforce gates
```

Use subagents only after the evidence snapshot is stable and claims are independent. Keep evidence IDs, formal calculations, status gating, conflict resolution, and final synthesis with the main agent.

## Diagnose failures

Read [Troubleshooting.md](references/Troubleshooting.md) when tools are unavailable, evidence is empty, OCR is required, the wrong filing is selected, indexes disagree, or calculations fail.

---
**Document created:** 2026-07-22 18:33
**Last modified:** 2026-07-30 00:37
**Last modified model:** OpenAI GPT
