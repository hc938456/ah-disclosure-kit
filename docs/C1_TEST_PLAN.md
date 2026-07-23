# C1 Test Plan

Documentation navigation: [A0 Documentation Index](./A0_DOC_INDEX.md)

This document describes the automated, live-source, and pre-release testing procedures for the current version of `ah-disclosure-kit`. The v1.0 test counts in the D1 document are retained for historical traceability only.

## 1. Unit Tests

Run from the Kit root directory:

```powershell
python -m pytest -q
```

Current v1.1.2 release-candidate test result:

```text
294 passed
```

### 1.1 Post-Ingest Live Question-Answering Acceptance

Use local annual reports and prospectuses already written to `pages.jsonl` and SQLite, and run them through a fresh MCP `stdio` process:

```powershell
python scripts\run_qa_acceptance.py
```

Test definitions are stored in `tests/qa_acceptance_cases.json`. They cover management biographies, revenue amounts, revenue recognition, R&D capitalization, segment analysis, customer concentration, actual financing receipts and payments, indirect-method cash-flow tie-outs, A/H cross-checks, key audit matters, share-based payments, IPO use of proceeds, clinical risks, control structures, business models, unit economics, cash burn, related-party transactions, effective tax rate, DuPont analysis, operating working capital, fixed-asset roll-forwards, cash capex, and provisional ROIC. Acceptance must also verify target semantics, target documents, `analysis_run_id`, analysis continuation, page expansion, deterministic calculations, explicit analysis-assumption labels, and exception blocking.

The final Round 8 live test on 2026-07-14 passed `29/29` scenarios, `8/8` protocol checks, and `7/7` management-analysis calculation checks. The full warm-index run took approximately `15.19 seconds`, averaging about `0.43 seconds` per scenario, with the slowest scenario taking about `1.06 seconds`. The test fixed an issue in which long natural-language queries stopped after finding a small number of exact FTS matches and failed to add high-coverage pages matching partial terms. After the fix, exact results are preserved while bounded trigram/substring search supplements recall without relying on additional business-specific keywords. Management-analysis transformation tests also require every variable with `source_type=assumption` to be returned explicitly through `assumption_based` and `assumption_variables`; assumptions must never be presented as values disclosed in the filing.

## 2. Basic Command Tests

Display server information:

```powershell
python -m ah_disclosure.cli server-info
```

Resolve an H-share code:

```powershell
python -m ah_disclosure.cli resolve --market H --symbol 00700
```

Retrieve an A-share company profile:

```powershell
ah-disclosure a profile --symbol 600519
```

## 3. Live End-to-End Tests

Test at least one A-share company and one H-share company.

A-share test:

```powershell
ah-disclosure a report --symbol 600519 --year 2024 --download --ingest
ah-disclosure local search --query "revenue recognition"
```

H-share test:

```powershell
ah-disclosure h report --symbol 00700 --year 2024 --download --ingest
ah-disclosure local search --query "revenue recognition"
```

## 4. Key Acceptance Criteria

- Downloading only the PDF must not generate `pages.jsonl`, `document.md`, or `full_text.txt`.
- Downloading and analyzing must generate `meta.json`, `pages.jsonl`, `quality_report.json`, and SQLite FTS.
- When SQLite FTS returns no matches for Chinese keywords, substring fallback must remain available.
- Cleaning a document or company dataset must update both the filesystem and SQLite indexes.
- Rules in the Skill must remain consistent with the documentation under `docs`.
- The package version, `VERSION` file, and changelog must agree.
- A repeated query for the same source must not access CNINFO or HKEXnews on the second run.
- `refresh=true` must force access to the remote source, while `offline=true` must prevent all remote requests.
- An old `pages.jsonl` must not be reused after the PDF hash changes.
- After finding a direct PDF for an H-share prospectus, the process must stop issuing further keyword queries.
- H-share annual-report candidate selection must exclude short announcements, publication notices, and summaries, and validate key sections in English, Simplified Chinese, and Traditional Chinese.
- H-share annual-report years must support Arabic numerals and Chinese-number year-title variants representing 2025.
- A Simplified Chinese A-share annual report must not rank an English version or an "H-share announcement" candidate first.
- Annual-report and prospectus candidates must enter staging first and move to `raw/` only after structure and identity validation succeeds.
- A staged candidate that fails validation must be deleted before ingest; an indeterminate candidate must move to `staging/review/`.
- When ingest is required after validation, it must reuse the same page extraction instead of parsing the entire PDF again.
- A short H-share code must not be considered matched merely because an isolated digit happens to appear in the document body.
- Cache audits must remain read-only and identify duplicates, unreferenced files, residual staged files, and structurally abnormal files.
- Pages with font-encoding failures and many control characters must be classified as low quality; when an old index returns no matches, the result must set `requires_ocr` instead of silently concluding that no relevant disclosure exists.
- Layout control characters in readable tables must not trigger OCR; low-text pages without scanned-image characteristics must not trigger OCR; image-based scanned pages must still trigger OCR; lower-quality OCR output must not overwrite native text.
- A Traditional Chinese H-share prospectus must prioritize the official listing document through the "Global Offering" title and return evidence using Traditional Chinese accounting-policy, business-segment, and revenue-disaggregation terms.
- `prepare_filing` must ensure that neither cached nor cold paths call EvidencePacket, while preserving the original default behavior of `ensure_filing_evidence`.
- `batch prepare` must support CSV, JSON, and JSONL; preserve input order; enforce concurrency limits; resume from checkpoints; and isolate per-item failures. It must not call EvidencePacket or the analysis workflow.
- `batch prepare --summary-only --output ...` must write complete results to the file while omitting the full validation payload from terminal output.
- After installing the lightweight core wheel, version, help, and server-information commands must run without implicitly importing AKShare or MCP during CLI startup. The corresponding features must remain available after installing optional dependencies.
- GitHub Actions must run Windows/Linux multi-version tests on `main`, pull requests, and `v*` version tags, and build both sdist and wheel artifacts. Workflow permissions must be read-only for repository contents.
- When the annual-report year is omitted, the latest version must be selected by the fiscal year in the title, including `Fiscal Year YYYY Annual Report`; if multiple candidates for the same latest year remain tied, the result must remain ambiguous.
- With `PYTHONIOENCODING=cp936`, the CLI must still output Chinese text, bullets, and curly quotation marks, and write UTF-8 bytes to stdout.
- Concurrent multithreaded ingest of large files must not produce SQLite write-lock conflicts; every document's page count and FTS index must remain complete.
- A US-style annual report using `Notes to Consolidated Financial Statements` must pass completeness validation while still requiring core sections such as the auditor's report, balance sheet, and income statement.
- When multiple Chinese query terms do not form a continuous phrase, substring fallback must rank the revenue table by keyword coverage rather than allowing purchasing or cost pages with repeated product names to displace it.

Performance retest baseline, using five companies in each test category:

| Scenario | Average cold path | Average warm path | Warm-path HTTP requests |
|---|---:|---:|---:|
| A-share prospectus | 0.457 seconds | 0.038 seconds | 0 |
| H-share prospectus | 5.685 seconds | 0.034 seconds | 0 |
| A-share annual report | 0.421 seconds | 0.046 seconds | 0 |
| H-share annual report | 6.846 seconds | 0.046 seconds | 0 |

The cold-path total for 20 files was `67.049 seconds` with 32 HTTP requests. Repeating the run on the warm path took `0.820 seconds` with 0 HTTP requests. Both runs achieved a `20/20` success rate. Before the change, the same cold-path measurement was `165.917 seconds`; this run reduced it by approximately `59.6%`.

Live H-share annual-report test on 2026-07-11: the 2025 English and Traditional Chinese annual reports of WuXi Biologics, Xinyi Solar, Sunny Optical Technology, Zijin Mining, Jiangxi Copper, Hong Kong Exchanges and Clearing, SMIC, China Mobile, POP MART, Great Wall Motor, Geely Automobile, and BYD Company all passed, for a `12/12` result. Cold downloads and completeness scans of the English reports took `105.294 seconds` in total. All Traditional Chinese tests passed after fixing compatibility with title-year formats.

Live A-share annual-report test on 2026-07-11: the 2025 Simplified Chinese annual reports of COSCO SHIPPING Energy Transportation, Wanhua Chemical, Rongsheng Petrochemical, Hengli Petrochemical, Yangnong Chemical, Inovance Technology, Fenghua Advanced Technology, Luxshare Precision, SMIC, and GigaDevice all passed, for a `10/10` result. Cold downloads and completeness scans took `11.943 seconds` in total.

Revenue-model and accounting-policy regression test on 2026-07-11: completeness checks passed for all 22 annual reports. Accounting-policy queries returned body-text evidence, page numbers, and official source links for `22/22` documents. Natural-language revenue-model queries automatically selected the financial-analysis strategy and returned revenue-disaggregation or business-segment evidence for `22/22` documents; the batch search took `5.585 seconds`. Offline source queries and cache reuse for the same document set also succeeded for `22/22` documents without issuing remote requests.

Post-run optimization review on 2026-07-11: completeness rules were strengthened to require simultaneous identification of the auditor's report, notes to the financial statements, statement of financial position, and income statement. All 22 live annual reports still passed, and a simulated long-form annual-results announcement was correctly rejected. Revenue-model search no longer mixed expense and cost evidence into the results. The high-level workflow can now find local documents automatically without an explicit `document_id`. Offline batch execution for all 22 companies skipped source lookup, download, and PDF scanning, taking `3.510 seconds` in total, or approximately `160 milliseconds` per company.

HKEX annual-report recall review on 2026-07-11: HKEX title filtering could miss complete bound editions with title suffixes, so H-share annual-report queries now merge title-filtered results with all company announcements. In the HSBC Holdings test, the system correctly selected the 377-page `Annual Report and Accounts 2025 (with employee share plans)`, published on 2026-03-27, from four candidates and excluded two two-page publication notices. After remote refresh, the final links for the 12 H-share companies listed above matched the original download links, for `12/12` accuracy.

China Mobile Chinese-version review: the 215-page `Overseas Regulatory Announcement 2025 Annual Report` is substantively the annual report for A-share code 600941 and is not the H-share Traditional Chinese annual report. The 171-page `2025 Annual Report` is the Traditional Chinese counterpart to the English H-share annual report. The H-share annual-report workflow now rejects the `Overseas Regulatory Announcement` document variant even when all required financial sections are present.

POP MART prospectus review: of two HKEX documents titled `GLOBAL OFFERING`, the nine-page file was an offering announcement, while the 632-page file was the formal prospectus. Prospectus validation now requires a sufficient page count and recognizes core sections covering the prospectus/global offering, risk factors, business, financial information, and the accountants' report. The nine-page announcement receives status `rejected_short_document`, while the 632-page formal prospectus receives status `complete`.

Local-cache audit review: the audit identified two groups of byte-identical files, one logical duplicate group for HSBC, and four unreferenced files among 65 original PDFs. Body-text scans of 49 PDFs with identifiable document types found that two two-page HSBC publication notices were not complete annual reports. Company, stock-code, and year identity validation passed for `23/23` parsed annual reports and prospectuses. The old index for HSBC's 377-page annual report also identified page 363 as having font-encoding text corruption; EvidencePacket returns `requires_ocr=true` instead of treating zero matches as evidence that no disclosure exists. The audit did not delete any files automatically.

Additional-batch review: the latest English annual reports for JD.com, Xiaomi, Qifu Technology, Trip.com Group, East Buy, Alibaba Health, JD Health, Kuaishou, China Merchants Bank, and ICBC, plus the MOMENTA-W prospectus, passed structure, identity, and text-quality validation for an `11/11` result. A same-title 611 KB MOMENTA formal notice was 11 pages long; after cold download it received status `rejected_short_document` and was removed from staging. The 450-page formal prospectus passed validation for all five core-section categories. Live caches for the ten annual reports correctly selected the latest version when no year was specified, including the `Fiscal Year 2026 Annual Report` for Alibaba Health.

Independent empty-directory review on 2026-07-11: Wanhua Chemical's 2025 annual report (229 pages), JD Health's 2025 annual report (170 pages), and the MOMENTA-W prospectus (450 pages) all completed cold lookup from official sources, staged download, structure validation, identity validation, and formal ingestion. The 11-page MOMENTA formal notice was rejected and deleted before ingest. JD Health's complete offline ingest and indexing took `3.04 seconds`; reusing the same document from the local index then took `0.11 seconds` without querying a remote source. Ruff, Mypy, Python compilation, and all `99 passed` automated tests succeeded.

Post-reset end-to-end review on 2026-07-12: five 2025 A-share annual reports from China Construction Bank, ICBC, Agricultural Bank of China, China Mobile, and Bank of China; four 2025 H-share annual reports from Tencent Holdings, ICBC, China Mobile, and China Construction Bank; Alibaba's H-share Fiscal Year 2026 annual report; and the MOMENTA-W and China Resources New Energy prospectuses all completed download, structure and identity validation, and ingest, for a `12/12` result. The complete library contained 12 documents and 12 PDFs, evenly split between A-share and H-share documents, with zero items remaining in staging. The test fixed an A-share candidate fallback that incorrectly admitted H-share announcements, and a false missing-section result for bank annual reports that used only the title "Income Statement." The final automated-test result was `102 passed`.

Independent HKEX performance review on 2026-07-12: before optimization, CNOOC's cold path took `18.31 seconds`, including `10.57 seconds` for source lookup, `6.34 seconds` for download, and `1.13 seconds` for validation. After adding conditional fallback to all announcements, a forced refresh of the same source reduced lookup time to `2.02 seconds`; the existing PDF was not downloaded again, and total time fell to `2.57 seconds`. In an independent temporary-directory test, PetroChina's 300-page annual report completed first-time stock-ID resolution, a single title-based source query, a 7.30 MB download, and validation in `11.44 seconds`; the test data was then deleted. Refreshing the source restores existing local PDF paths. The high-level document cache verifies PDF SHA-256 values and SQLite page counts. Ruff, Mypy, Python compilation, and all `110 passed` automated tests succeeded.

Final v1.1.0 review on 2026-07-13: the full automated-test result was `164 passed`. Duplicate batch tasks ran only once, aliases resolving to the same security code were processed serially, and the actual concurrency count was reported correctly. Connection failures used a 10-second connection timeout and no more than two attempts. Live source refreshes for China Merchants Bank's A-share report and Tencent Holdings' H-share report took approximately `1.67 seconds` and `2.22 seconds`, respectively, and selected the correct annual reports. Both sdist and wheel builds passed in a clean Python 3.14 environment. The lightweight wheel installed only requests- and BeautifulSoup-related dependencies; the CLI did not import AKShare, pandas, MCP, or PDF components before they were needed, and the default data directory used the operating system's user-data directory. Round 5 cold-path downloading, validation, and ingest succeeded for all 12 live files, taking approximately `139.65 seconds` in total. Re-running the same 12 files offline with `--summary-only` succeeded for `12/12`, with an internal batch time of approximately `0.30 seconds`; complete results were retained in a JSON file containing `output_path`. The standard compatible installation included PDF, company-data, and MCP capabilities but did not install the layout model used only for enhanced Markdown. The final library had 214 PDFs aligned with 214 SQLite index entries, with no duplicates, orphans, missing files, staged files, or review-pending files. Full-body audits passed for `214/214` documents and reused `pages.jsonl` files with matching SHA values and page counts. After optimization, the default cache audit took approximately `0.83 seconds` internally and did not need to hash any uniquely sized files. Ruff, Mypy, Python compilation, and dependency-integrity checks all passed.

Round 6 post-reset review on 2026-07-13: after clearing PDFs, parsed results, SQLite indexes, and source caches, 12 files completed official-source lookup, download, structure and identity validation, and ingest. The set comprised 2025 annual reports for Bank of Ningbo, Piotech, Bloomage Biotechnology, Techtronic Industries, Xinyi Solar, and GDS Holdings; the A-share and H-share annual reports of Weichai Power; and prospectuses for Dameng Data, UGREEN, Lens Technology, and Sanhua Intelligent Controls. The first batch completed `11/12` in approximately `144.15 seconds`, with no recurrence of SQLite lock conflicts. GDS Holdings' 374-page annual report was incorrectly rejected because the US-style notes title omitted `the`; after the rule was fixed, it passed in approximately `16.94 seconds`. The final warm-cache rerun of the full manifest succeeded for `12/12`, with an internal time of approximately `0.88 seconds`. The 12 PDFs matched 12 index entries, with zero missing or orphaned files. After improving long Chinese-query search, the UGREEN prospectus returned the 2023 five-category product-revenue table directly even when evidence was limited to two pages. An additional independent pre-release review covered dynamic query dates, checkpoint contents and parameter validation, HTTP and streaming-download retries, concurrent same-name downloads, trigram-index migration, SQLite file-handle release, cross-platform path case rules, and HKEX HEAD fallback. The final result was `180 passed` automated tests; Ruff, Mypy, Python compilation, sdist/wheel builds, and installation in a clean virtual environment all passed.

External-site response times fluctuate. Performance acceptance should prioritize the number of remote requests rather than absolute elapsed time alone.

## 5. Complex Financial Question-Answering Stress Tests

Complex question answering must preserve the following division of responsibilities: the LLM decomposes claims and identifies the accounting basis; the Kit retrieves source text; the LLM reviews the evidence; Decimal-based code performs deterministic tie-outs; and the LLM explains differences. Keyword matches must not be treated as conclusions, and LLM mental arithmetic must not replace deterministic recalculation.

| ID | Scenario | Required evidence | Deterministic check |
|---|---|---|---|
| CF01 | Indirect-method CFO tie-out | Net profit, non-cash adjustments, working-capital movements, CFO | `Net profit + adjustments + working-capital movements = CFO` |
| CF02 | H-share profit before tax to CFO | Profit before tax, cash generated from operations, interest received, income tax paid | Tie out in two stages; do not mix in net profit after tax |
| CF03 | Three cash-flow activities to ending cash | CFO, CFI, CFF, FX, opening cash, and ending cash | `Opening cash + CFO + CFI + CFF + FX = ending cash` |
| FIN01 | Actual debt-financing amount | Proceeds and repayments from borrowings, bonds, and short-term financing | Report gross proceeds, gross repayments, and net principal cash flow separately |
| FIN02 | Total financing cash flow | Debt, leases, interest, dividends, repurchases, and non-controlling-interest transactions | Sum all financing cash items to CFF; do not look only at net borrowings |
| FIN03 | Financing-liability roll-forward | Opening balance, financing cash flows, FX, fair value, other non-cash movements, closing balance | `opening + cash + FX + FV + other = closing` |
| FIN04 | Lease-liability roll-forward | Lease payments, new leases, terminations, disposals, interest, and FX | Non-cash lease additions must not enter CFF but must enter the liability roll-forward |
| FIN05 | Interest expense versus cash paid | P&L interest expense, operating-cash interest, financing-cash interest, and lease interest | Calculate unpaid/accrued and other differences; do not equate expense with cash paid |
| FIN06 | Dividends declared versus paid | Opening dividends payable, declarations, payments, and closing dividends payable | Distinguish equity movements, liability recognition, and cash-flow timing |
| AH01 | A/H cash-movement tie-out | Two A/H reports, units, and exchange-rate presentation | Search jointly with `filters.document_ids` and standardize units of currency and thousands |
| WC01 | Operating cash positive despite a loss | Loss, impairment and depreciation, and movements in receivables, inventories, and payables | Quantify the respective contributions of non-cash adjustments and working capital; qualitative explanation alone is prohibited |
| NEG01 | Reverse test for incorrect classification | Non-cash leases or debt conversion | Deliberately including the item in cash flow must return `discrepancy` |

The live stress test on 2026-07-14 used the 2025 A/H annual reports of COSCO SHIPPING Holdings, Mengniu Dairy, and Zhongsheng Group. All ten cross-page/cross-report retrieval scenarios obtained the target pages. The indirect-method, financing-cash-flow, financing-liability, lease-liability, interest-cash difference, and A/H unit tie-outs all passed. Multi-document claims used `filters.document_ids` to restrict searches explicitly to no more than eight local files while sharing page and character budgets across the entire claim. Zhongsheng Group's net borrowing cash flow differed from the financing-liability table's cash movement by RMB 18,884 thousand, so the program returned `discrepancy`. Supplemental retrieval found the policy for recognizing net transaction costs and amortizing them under the effective-interest method, but the report did not disclose the composition of the difference separately. The evidence gap therefore remained open and no unsupported explanation was imposed. A subsequent architecture review added declarative calculation chains, a time-limited evidence registry keyed by `analysis_run_id`, rejection of fabricated `evidence_id` values, binding of each variable's original figure to its evidence page, and blocking of completion when calculations fail. The dedicated complex-finance suite passed `42/42`, and the full suite reported `231 passed`.

Pre-GitHub-release review on 2026-07-14: fixes covered document-ID path traversal and root-directory deletion risks, protection for shared PDF references, incorrect reuse of download-source identities, downgrade handling for future SQLite schemas, inconsistencies among page/FTS/trigram indexes, stale table artifacts and failure states, ingest-cache failure to backfill artifacts on demand, analysis-run context mismatches, lost cross-claim evidence, circular calculation plans, and zero-budget boundaries. Quality checks for no-match cases were reduced from at most 100000 pages to a 64-page sample. Targeted low-level regression tests, Ruff, and Mypy passed. The full automated suite reported `288 passed` in that round and reached `294 passed` after Skill packaging and installation validation were added.

## 6. Network-Test Notes

Live data-source tests depend on external sources including CNINFO, HKEXnews, AKShare, and Eastmoney. Tests may fail when the network is unavailable, interfaces are rate-limited, or upstream fields change.

When a failure occurs, distinguish among:

- A local-code bug.
- An unavailable upstream website.
- A change to data-source interface fields.
- No corresponding document for the company code or year.

---
**Document created:** 2026-07-03 19:31

**Last modified:** 2026-07-23 16:53

**Last modified model:** Not set (`ANTHROPIC_MODEL` is empty)
