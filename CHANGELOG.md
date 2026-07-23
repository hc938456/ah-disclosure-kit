# Changelog

Documentation index: [A0 Documentation Index](./docs/A0_DOC_INDEX.md)

## v1.1.2

This release internationalizes the GitHub documentation and public Skill metadata into English while retaining `README.zh-CN.md`.

- Updated the GitHub About description, Website link, and Topics for international discoverability.
- Functional behavior is unchanged; this release is documentation and public metadata only.
- Validated with 294 tests, Ruff, Mypy, Python compilation, and sdist/wheel package builds.

## v1.1.1

This release unified GitHub `main`, the local Kit, the Codex Skill installation path, and the published Release assets.

- Changed the default GitHub README to English and provided a complete Simplified Chinese version.
- Updated the default Codex user-level Skill directory to `%USERPROFILE%\.agents\skills\ah-disclosure`, consistent with current Codex discovery rules.
- Removed the unnecessary `type = "stdio"` field from the Codex stdio MCP example and added end-to-end MCP and Skill acceptance steps.
- Clarified the current Python environment, optional `.venv`, Tesseract fallback behavior, and Skill target-directory overwrite behavior in the installation guide.
- Unified the bilingual READMEs, installation documents, version files, sdist, wheel, and full ZIP under `v1.1.1`.

## v1.1.0

This release primarily optimized PDF source resolution and repeated-query performance.

Release-candidate update date: 2026-07-14

- Completed pre-release security and consistency review for document-ID path boundaries, on-demand cache enhancement, analysis-run context binding, cross-claim calculations, download-source identity, SQLite index consistency, and table-failure cleanup; the package test count follows the final review record in `docs/C1_TEST_PLAN.md`.
- Removed unused Camelot, OpenCV, ChromaDB, and sentence-transformers dependencies; table extraction now declares only the actually used pdfplumber dependency, and the vector interface explicitly describes an external-backend inventory instead of presenting placeholder files as generated embedding indexes.
- Passed 294 automated tests, Ruff, Mypy, Python compilation, and sdist/wheel build verification for the final release candidate.
- Changed the default end date for A-share announcements, annual reports, prospectuses, and financing-document queries to the current system date, eliminating the fixed `20261231` cutoff that would omit new announcements after 2027.
- Added input-file SHA-256, effective run-parameter, and schema-version validation to checkpoints; reuse of stale results is rejected when same-path input content or key OCR and other parameters change.
- Extended PDF download retries to HTTP 408/425/429/5xx and streaming interruptions, honoring `Retry-After`; added per-target file locks and unique temporary files to prevent concurrent collisions; MD5 and SHA-256 are now computed during download writes without rereading the entire file.
- Changed SQLite connections to explicit commit, rollback, and close handling, fixing a Windows issue where database files could remain locked after use; schema initialization now runs once per database path, and page and FTS writes use batch execution.
- Added a SQLite trigram index to accelerate Chinese substring search; existing databases migrate automatically to schema v3. A 3,000-page local performance smoke test returned results in approximately 20 milliseconds.
- Changed batch progress callbacks to maintain an incremental completed-item list; a 5,000-item no-I/O performance smoke test took approximately 15 milliseconds, avoiding resorting and copying all results after every item.
- Added Range GET and PDF-header validation as fallbacks when HKEX PDF HEAD requests are unavailable, reducing false negatives for valid Chinese paired documents.
- Split GitHub Actions into quality checks, a cross-platform test matrix, a complete-extras smoke test, and a single release build, avoiding repeated Ruff, Mypy, and build execution across eight matrix jobs.
- `--stop-on-error` now preserves the checkpoint when not all tasks have been processed, allowing a later `--resume` to continue the remaining tasks; a complete batch still removes the checkpoint automatically.
- Serialized SQLite full-text index writes within a process while keeping reads and download parsing parallel, eliminating occasional `database is locked` errors during large-file concurrent ingest.
- Made Hong Kong annual-report completeness validation compatible with the US-style `Notes to Consolidated Financial Statements` heading instead of incorrectly requiring `the`; the 374-page 2025 annual report of GDS Holdings passed in live testing.
- For long Chinese questions, the substring fallback first searches the full sentence, then recalls at most 16 keywords and ranks results by keyword coverage; financial analysis reserves two priority evidence slots for the user's original question, allowing Ugreen Technology and Dameng Data prospectuses to return the revenue table directly.
- Completed a sixth-round test of 12 real files from an empty data directory, including download, structural and identity validation, and ingest. The first batch completed 11 files in approximately 144.15 seconds and exposed the GDS Holdings title-compatibility issue; after the fix, the single-item path passed in approximately 16.94 seconds, and the final warm-cache rerun completed internally in approximately 0.88 seconds with `12/12` cache hits.
- Added `--summary-only` to the batch CLI; when `--output` is specified, complete results continue to be written to JSON while the terminal can show only overall statistics and per-item status, reducing context usage for large validation batches.
- Split the base installation into `company-data` and `mcp` optional dependencies; the lightweight core no longer forces installation of AKShare, pandas, openpyxl, or MCP, while one-step installation still provides the commonly used `pdf,company-data,mcp` capability set by default.
- Split enhanced Markdown layout conversion into a separate `layout` optional dependency; ordinary PDF ingest no longer installs PyMuPDF4LLM or its layout-model dependencies, reducing default installation size and time.
- Changed package license metadata to the standard SPDX expression, removing the deprecation warning from newer setuptools versions.
- Added Pillow and pytesseract to the `dev` optional dependencies used directly by tests, and removed the tests' unnecessary pandas dependency, ensuring GitHub Actions can run the full suite in a clean environment after dependency splitting.
- Changed `requirements.txt` to reference the common extras in `pyproject.toml`, preventing the legacy dependency list from reinstalling removed layout-model packages or drifting from the package definition.
- Added GitHub homepage, repository, Issue, and changelog links to wheel metadata; updated the README and environment-variable example to the formal release wording.
- Complete batch-result JSON now includes its own `output_path`, matching the command return value.
- Added version-tag and manual triggers, minimal read-only permissions, job timeouts, and independent sdist and wheel builds to GitHub Actions; split builds also avoid the Windows Python 3.14 nested-isolation-environment issue.
- Unified CNINFO query, detail-page, and PDF-download endpoints under HTTPS instead of plaintext HTTP, reducing the risk of public disclosure files being modified in transit.
- Removed directly unused httpx and lxml from the lightweight core; MCP and AKShare installation still brings in the required versions through their corresponding extras, making basic source-query installation faster.
- The default cache audit now filters duplicate candidates by file size before computing SHA-256; full-text audits still hash every file, so duplicate-detection accuracy is unchanged.
- Fixed the default data directory after wheel installation falling under the Python `Lib` directory; source workspaces continue to use the project data directory, while wheels use the operating-system user-data directory. `AH_DISCLOSURE_DATA_DIR` still has highest priority.
- Added complete duplicate-input reuse and normalized file-task locks to batch jobs, avoiding concurrent writes to the same file from duplicate rows or security-code aliases; `effective_workers` now reports the actual thread count.
- Set download connections to a 10-second connection timeout, a 60-second read timeout, and at most two attempts, reducing long-tail waits caused by invalid links.
- Changed CLI service information to use a lightweight module, avoiding early loading of the full MCP runtime for ordinary CLI commands.
- A-share financing-file multi-category searches now return a structured error when all sources fail instead of silently presenting a source failure as no result.
- Added rate-limited atomic writes for large-batch checkpoints while preserving completion-result and resume semantics.
- Added a GitHub Actions matrix for Windows/Linux and Python 3.11/3.12/3.13/3.14, with separate jobs for Ruff, Mypy, complete-extras smoke testing, and release-package builds.
- Content audits reuse `pages.jsonl` when the PDF SHA-256 and indexed page count match; only files with missing or inconsistent caches are rescanned, and reuse and scan counts are reported separately.
- PDF SHA computation in local-cache audits now uses up to four threads; 202 files were reduced from approximately 2.51 seconds to approximately 1.00 second in live testing, while full-text structural validation remains per-document.
- When no year is explicitly specified for a batch annual-report request, the top-level `report_year` is populated with the actual latest selected report year instead of remaining `null`.
- Unified UTF-8 configuration for CLI startup and JSON output, fixing `UnicodeEncodeError` on Windows GBK/CP936 terminals when output contains bullets, curly quotes, or other Unicode characters; the MCP stdio protocol remains independent.
- Unified the A-share annual-report default download entry point with the staging, structural-validation, and identity-validation pipeline instead of bypassing it and writing directly to the formal directory.
- Relative `data_dir` paths are now resolved from the project root, avoiding multiple data directories when MCP starts from different working directories.
- The installation script now reads the expected version from `VERSION` instead of hard-coding an old version number.
- Fixed null handling when EvidencePacket document metadata is missing, and unified the final file path in top-level `document_id`, `local_pdf_path`, and validation results.
- Aligned MCP function documentation with the actual exposed names item by item; half-year and quarterly reports now explicitly use the common `search_filings` entry point.
- Independent empty-directory cold-path validation passed for A-share annual reports, H-share annual reports, and H-share prospectuses; failed short announcements are deleted before ingest. Ruff, Mypy, and 99 automated tests all passed.
- The A-share annual-report download pipeline now hard-rejects `H-share announcement`, `Hong Kong announcement`, and `H-share announcement` candidates, preventing fallback to an H-share version after an initial A-share validation failure.
- Added standalone `income statement`, `profit and loss statement`, and equivalent localized heading variants commonly used by banks, so Agricultural Bank of China and Bank of China A-share formal annual reports are no longer falsely classified as missing an income statement.
- All 12 real-file regression tests after resetting the data directory passed: five A-share annual reports, five H-share annual reports, and two prospectuses completed validation and ingest; the full library had no leftover staging files, and the automated test count increased to 102.
- Changed H-share annual-report fallback to conditional full HKEX-announcement execution: when the year and standard title are explicit and the file is at least 1 MB, only title search runs; missing, undersized, or uncertain results still retain full-announcement recall for special consolidated reports such as HSBC Holdings.
- Fixed `refresh_source=true` obtaining the same URL without restoring the local path, which caused an existing PDF to be downloaded again; both A-share and H-share source refreshes now restore `local_pdf_path` and `document_id` from SQLite.
- Added PDF SHA-256 and SQLite page-count validation to high-level document-cache reuse, preventing stale evidence reuse when a PDF is replaced or the index is missing pages.
- Propagated `hkex_stock_id` through H-share annual-report source resolution, download, EvidencePacket, and MCP high-level tools, eliminating cases where a public parameter was ignored by the high-level pipeline.
- A forced-refresh live test for CNOOC reduced total time from `10.57 seconds` to `2.02 seconds` without redownloading the PDF; an independent cold-path test for PetroChina took `11.44 seconds`. Ruff, Mypy, and 110 automated tests all passed.
- The formal Kit added `ah-disclosure batch prepare`, supporting CSV, JSON, and JSONL batch input, controlled concurrency, checkpoint resume, offline mode, and staged result summaries; single-file downloads and existing MCP interfaces remain unchanged.
- Persisted annual-report and prospectus completeness-validation results by `document_id + SHA-256 + security code + file type`; when an explicitly refreshed source points to an unchanged PDF, the already validated result is reused without re-extracting the whole PDF.
- HKEX clients now reuse HTTP sessions by worker thread, reducing repeated TLS connections during batch queries; permanent `stockId` mapping adds an explicit `refresh` entry point and preserves the old cache when refresh fails.
- Added single-page `pypdf` fallback counts, completely failed extraction-page counts, and issue counts to PDF quality reports, allowing batch audits without relying on terminal logs.
- Set the formal batch command's hard concurrency limit to four and report requested and effective concurrency; `stop-on-error` explicitly runs single-threaded.
- Reuse verified and permanently cached HKEX `stockId` values directly in later title searches instead of repeating identity-validation requests for the same mapping.
- Changed PDF text extraction to tolerate failures page by page; when PyMuPDF fails on one page, only that page falls back to pypdf, and OCR failures preserve native text instead of reparsing the entire PDF from page one.
- Added `text_extraction`, `completeness_check`, and `identity_check` to `execution_info.timings_ms` while retaining the compatible aggregate `validation` timing.
- Added a 30-second SQLite `busy_timeout` to support controlled concurrent writes from the formal batch command.
- When ingest parsing cache and SQLite page indexes are consistent, ingest updates only document metadata instead of deleting and rebuilding the entire FTS page index; missing indexes or page-count mismatches still trigger automatic repair.
- Changed concurrent HKEX mapping-cache writes to merge under a per-record lock, preventing multiple H-share identity-resolution operations in one process from overwriting one another.
- Added the general `prepare_filing` interface for source resolution, download, validation, and ingest, explicitly excluding EvidencePacket creation; the formal batch CLI reuses this interface without duplicating download or validation logic.
- Fixed missed source resolution for Traditional Chinese H-share prospectuses by prioritizing `Global Offering` and recognizing Chinese listing-document categories; formal prospectus source resolution for Luxshare Precision changed from a failure at approximately 47.59 seconds to success at approximately 8.13 seconds.
- Added Traditional Chinese search terms for accounting policies, business segments, and revenue disaggregation; offline evidence search across Luxshare Precision's 515-page prospectus returns eight relevant evidence pages in approximately 184 milliseconds.
- Fixed PDF table-layout control characters causing false `ocr="auto"` decisions: the MiniMax 716-page prospectus dropped from 120 mistakenly OCR-processed pages to zero, completeness validation remained successful, and extraction-plus-validation time decreased from approximately 172.73 seconds to approximately 1.46 seconds.
- Automatic OCR now combines readable-phrase checks with page-image ratios and replaces native text only when OCR quality is higher, avoiding degradation of readable tables.
- Preserved high-level file-processing timings for `cache_lookup`, `remote_lookup`, and `selection` source-resolution stages, enabling accurate bottleneck identification.
- Fixed specified annual-report or prospectus analysis being routed through external structured financial data; `ensure_filing_evidence` now returns only target-PDF evidence, preventing disclosure-period and post-listing data contamination.
- Added short lock retries to Windows atomic file replacement, preventing cache rebuild, download persistence, or index-write failures when antivirus or indexing processes briefly hold a file.
- Passed the Zhipu prospectus real-download, 504-page completeness-validation, ingest, and cache-reuse tests; the full automated-test count at that stage was `120 passed`.
- HKEX source-cache identity no longer includes `max_rows`; remote candidates are cached once and truncated locally according to the caller's request, eliminating duplicate remote requests when the Zhipu prospectus was first queried with 20 rows and then with 10.
- Added cache probing, remote-query, and candidate-selection stage timings to high-level source resolution, and now correctly honors cached zero-result responses, preventing repeated queries for files that have not been published or do not exist.
- Added local `filing_sources` and `source_queries` caches with zero-result caching, TTL, forced refresh, and offline mode.
- Added `find_filing_source_tool` to locate links without downloading or ingesting.
- Added `ensure_filing_evidence_tool` to resolve sources locally first, perform required downloads and ingest, and return an EvidencePacket.
- H-share prospectus resolution now stops immediately after finding a direct PDF instead of serially querying every keyword in the fallback plan.
- Persisted CNINFO security-code mappings and filled missing `orgId` values through the official top-search endpoint.
- Changed HKEX announcement `raw_id` to the document identifier in the announcement URL instead of incorrectly using the company `stockId`.
- Validate PDF SHA-256 before reusing ingest caches; inconsistent hashes, old metadata without a hash, or corrupted caches trigger reparsing.
- Changed `meta.json`, `quality_report.json`, and `pages.jsonl` to atomic writes.
- Added the final URL, redirect chain, and bounded retries for download results.
- When the same normalized filename maps to different source URLs, automatically add a source suffix to prevent incorrect reuse of another PDF.
- Added completeness validation for H-share annual-report candidates using exact titles, page counts, file sizes, and key sections in English and Traditional Chinese, automatically excluding short announcements, release notices, and summaries.
- H-share Chinese annual-report search now supports four localized title forms: `2025 Annual Report` in Simplified Chinese metadata, `2025 Annual Report` in Traditional Chinese metadata, the Chinese fiscal-year report form, and the full-width-numeral report form.
- A-share annual-report candidates are selected by target language; Chinese requests lower the priority of English versions and H-share announcement candidates.
- Added source-cache, CNINFO-fallback, HKEX-early-stop, hash-rebuild, and high-level-tool tests.
- Reduced the total cold-path time for 20 real source resolutions from 165.917 seconds to 67.049 seconds, a decrease of approximately 59.6%.
- The same 20 source resolutions on the warm path took 0.820 seconds, with a 20/20 success rate and zero HTTP requests.
- All 12 H-share 2025 annual reports in English and Traditional Chinese passed completeness validation in live testing, for a 12/12 success rate.
- All 10 A-share 2025 Chinese annual reports passed completeness validation in live testing, for a 10/10 success rate.
- Fixed incorrect routing of questions about revenue models, revenue sources, and business segments to structured financial-statement data.
- Changed financial-analysis retrieval to use general bilingual segment and revenue-disaggregation keywords instead of company-specific business terms.
- Real annual-report regression tests for revenue models and accounting policies across 22 A/H-share companies passed with a 22/22 success rate.
- Simplified the revenue-model query plan to use business-segment and revenue-disaggregation searches without mixing in expense and cost pages.
- Annual-report completeness validation now requires the audit report, notes to the financial statements, statement of financial position, and income statement core sections to coexist, reducing the risk of mistaking an annual-results announcement for a full annual report.
- `ensure_filing_evidence_tool` can automatically match local documents by market, security code, year, type, and language without a pre-supplied `document_id`.
- `offline=true` now fails directly when the local PDF is missing instead of attempting a download.
- Added source-query, download, completeness-validation, ingest, and evidence-retrieval stage timings to `execution_info.timings_ms`.
- Reduced offline batch evidence retrieval for 22 ingested annual reports to 3.510 seconds, averaging approximately 160 milliseconds per company.
- Merged HKEX title-filter results with all company announcements for H-share annual-report queries, avoiding misses caused by suffixes on complete consolidated versions.
- Applied a shorter ordinary source-cache lifetime to the latest report year, preventing an earlier release notice from masking a later complete annual report.
- `refresh_source=true` now bypasses the local document cache and rechecks the official source.
- In HSBC Holdings testing, selected a 377-page complete annual report from four candidates while excluding two 2-page release notices; all refreshed links for the 12 H-share companies matched their original download links.
- Source-query caches now dynamically restore the local PDF path and document ID for a URL, allowing files with source suffixes to be fully reused offline.
- H-share annual-report processing rejects A-share annual reports found inside `overseas regulatory announcements`, preventing an A-share version from being incorrectly named as an H-share Chinese annual report.
- Added prospectus completeness validation using page counts and core sections such as risk factors, business, financial information, and the accountants' report to distinguish a formal prospectus from a same-title issue announcement.
- In Pop Mart testing, rejected a 9-page announcement and accepted the 632-page formal prospectus among two files with the same `GLOBAL OFFERING` title.
- Direct prospectus downloads now also return `document_validation`; incomplete files are prohibited from entering ingest.
- HKEX parsers preserve the file category and page-displayed file size, allowing formal listing documents to be distinguished from same-title formal notices before download.
- Annual-report and prospectus candidates are first downloaded to staging; only candidates that pass structural and document-identity validation enter the formal `raw/` directory. Failed candidates are deleted before ingest, and candidates that cannot be classified enter `staging/review/`.
- Completeness validation and ingest reuse the same per-page extraction, avoiding duplicate parsing of the same PDF.
- Document-identity validation checks the year, company name, and labeled security code, and fixes false matches where a short H-share code is accidentally found in unrelated body text.
- Unified annual-report and prospectus handling in `download_and_ingest_filing` with the validated high-level pipeline, eliminating the direct-write bypass into the formal directory.
- Added read-only `audit_local_pdf_cache_tool` to check duplicate, unreferenced, missing-index, leftover-staging, and abnormal-text PDFs without deleting anything automatically.
- Added control-character and garbled-text detection to PDF text-quality reports, fixing cases where large character counts but unsearchable text were still classified as high quality; empty searches against old indexes now return a `requires_ocr` hint.
- When an annual-report year is omitted, choose the latest version by the fiscal year in the title, supporting `Fiscal Year YYYY Annual Report` while retaining ambiguity protection for tied candidates from the same latest year.
- Unified UTF-8 handling for CLI startup and JSON output, fixing Windows GBK/CP936 terminal `UnicodeEncodeError` for bullets, curly quotes, and other Unicode characters; MCP stdio remains independent.
- Unified the A-share annual-report default download entry point with staging, structural validation, and identity validation instead of bypassing the pipeline and writing directly to the formal directory.
- Resolve relative `data_dir` paths against the project root, avoiding multiple data directories when MCP starts from different working directories.
- The installation script reads the expected version from `VERSION` instead of hard-coding an old version number.
- Fixed null boundaries when EvidencePacket document metadata is missing and unified the final file path across top-level `document_id`, `local_pdf_path`, and validation results.
- Aligned MCP function documentation and actual exposed names item by item; half-year and quarterly reports explicitly use the common `search_filings` entry point.
- Independent empty-directory cold-path validation passed for A-share annual reports, H-share annual reports, and H-share prospectuses; failed short notices are deleted before ingest. Ruff, Mypy, and 99 automated tests all passed.
- The A-share annual-report download pipeline hard-rejects H-share and Hong Kong announcement candidates, preventing fallback to an H-share version after an A-share validation failure.
- Added standalone income-statement heading variants commonly used by banks, so Agricultural Bank of China and Bank of China A-share formal annual reports are no longer falsely classified as missing an income statement.
- All 12 real-file regression tests after resetting the data directory passed: five A-share annual reports, five H-share annual reports, and two prospectuses completed validation and ingest; the full library had no staging leftovers, and the automated test count increased to 102.
- H-share annual reports now conditionally execute the full HKEX-announcement fallback: when year and standard title are explicit and the file is at least 1 MB, only title search runs; missing, undersized, or uncertain results retain full-announcement recall for special consolidated reports such as HSBC Holdings.
- Fixed `refresh_source=true` returning the same URL without restoring the local path, which caused an existing PDF to be downloaded again; both A-share and H-share source refreshes now restore `local_pdf_path` and `document_id` from SQLite.
- Added PDF SHA-256 and SQLite page-count checks to high-level document-cache reuse, preventing stale evidence reuse when a PDF is replaced or the index is missing pages.
- Propagated `hkex_stock_id` through H-share annual-report source resolution, download, EvidencePacket, and high-level MCP tools, eliminating cases where a public parameter was ignored by the high-level pipeline.
- A forced-refresh live test for CNOOC reduced total time from `10.57 seconds` to `2.02 seconds` without redownloading the PDF; an independent cold-path test for PetroChina took `11.44 seconds`. Ruff, Mypy, and 110 automated tests all passed.

## v1.0.0

Finalized: 2026-07-03 15:44

This was the first stable release prepared for public use.

Highlights:

- Established the project name as `ah-disclosure-kit`.
- Established the Skill name as `ah-disclosure`.
- Established the MCP server name as `ah-disclosure`.
- Supports non-trading company-data queries for A-shares and H-shares.
- Supports downloading original A-share CNINFO announcements and annual-report PDFs.
- Supports downloading original HKEXnews announcements, annual reports, circulars, and results-announcement PDFs.
- Supports querying and downloading A-share and H-share prospectuses, listing documents, and offering circulars.
- Supports local PDF parsing and generation of `meta.json`, `pages.jsonl`, and `quality_report.json`.
- Supports SQLite FTS full-text search with Chinese-keyword substring fallback retrieval.
- Supports the EvidencePacket workflow, avoiding direct delivery of an entire PDF or full-text Markdown document to the LLM.
- Clarified that downloaded PDFs are not parsed automatically by default; ingest runs only when the user requests reading, analysis, or search.
- Clarified that `document.md` and `full_text.txt` are not generated by default.
- OCR remains local, on demand, and triggered by low text quality; full-library OCR is not enabled by default.
- Vector embedding is not enabled by default.
- Cleaned up the documentation system, with all Markdown body text converted to English and organized by category.

## v0.1.0

Internal development draft.

Highlights:

- Initialized the Python package, CLI, MCP server, and Skill.
- Connected AKShare, CNINFO, HKEXnews, and Eastmoney IPO-related paths.
- Established the PDF ingest, SQLite FTS, local-search, and test skeletons.

---
**Document created:** 2026-07-03 19:31

**Last modified:** 2026-07-23 17:12

**Last modified model:** Not set (`ANTHROPIC_MODEL` is empty)
