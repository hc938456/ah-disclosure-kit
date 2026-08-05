# Troubleshooting

## Tool or environment failure

1. Call `server_info` and verify version and data directory.
2. Confirm the MCP server name is `ah_disclosure` and starts `python -m ah_disclosure.mcp_server`.
3. Confirm the package and required extras are installed in the Python interpreter used by MCP.
4. Restart Codex after MCP or Skill configuration changes.

## Timeout or unexpectedly slow source preparation

1. Inspect `execution_info` first. A CNINFO `source_lookup_timeout` is already bounded below the host limit and has already triggered one automatic cache probe.
2. If `source_timeout_recovered=true`, use the returned source candidate and continue from download. Do not refresh it immediately.
3. If recovery failed, or the host timed out before returning structured status, query cached/local state with `list_local_documents_tool` and `find_filing_source_tool` using `refresh=false`.
4. Resume from the first missing stage: download, cache-ready ingest, or evidence retrieval. For a pipeline-linked annual-report PDF, preserve filing metadata by calling `download_and_ingest_report` with the same identity and `ingest=true`; use `ingest_pdf_tool` for a user-provided local PDF.
5. If no source is cached, perform one refreshed source-only lookup. Do not download in the same call. The CNINFO defaults are 10 seconds per request and a 40-second lookup budget; adjust `[network]` only for a known environment constraint.
6. For `source_lookup_error`, verify network and proxy availability. The Kit respects configured proxies and does not silently bypass them.
7. If the refreshed source-only lookup also fails, report a likely external-source problem. Otherwise treat the original timeout as a combined-pipeline or transient-request failure.

## Empty, wrong, or incomplete evidence

- Verify `document_id`, company, year, language, consolidation scope, and index page count.
- Search accounting and business synonyms in the filing's language.
- Expand fixed sections, full located pages, and adjacent pages.
- Check `requires_ocr`, extraction fallback, and extraction-failure fields.
- Treat substantial extracted character volume with zero required-section matches as a possible font-map or text-layer failure, not proof that the sections are absent.
- Do not treat retrieval failure as absence of disclosure.
- For wrong or short documents, review title, category, size, page count, identity, year, language, and required sections; preserve ambiguity when necessary.

## HKEX Chinese text-layer failure

1. Verify the company, code, year, filing type, page count, and official HKEXnews URL.
2. Look for readable headings and accounting terms in extracted text, not only a high character count.
3. Locate the same official English filing before manually re-downloading or forcing full-document OCR.
4. Use the English filing for analysis when identity matches and its text layer passes validation; answer in the user's requested language and disclose the source-language switch.
5. Use OCR only when no reliable official alternate-language text layer exists or Chinese page-level text is required.

## Cache, index, or calculation inconsistency

- Audit before cleanup and compare PDF hash, parsed metadata, `pages.jsonl`, and SQLite page counts.
- Use reconcile or cleanup with dry-run before changing state.
- For calculations, verify evidence IDs, signs, units, precision, periods, and consolidation scope.
- Split dense formulas into auditable steps and report unresolved differences instead of forcing a pass.

---
**Document created:** 2026-07-22 18:56
**Last modified:** 2026-07-30 00:37
**Last modified model:** OpenAI GPT
