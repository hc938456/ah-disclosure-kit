# D1 Development Plan v1.0

> Archive note: This document preserves the finalized v1.0 design, test counts, and follow-up ideas for historical traceability only. For the actual behavior of v1.1.0 and later versions, refer to the README, the A/B/C documentation series, and the CHANGELOG.

Documentation navigation: [A0 Documentation Index](./A0_DOC_INDEX.md)

File version: v1.0

Development finalized: 2026-07-03 15:44

Project name: `ah-disclosure-kit`

Python package name: `ah_disclosure`

MCP server name: `ah-disclosure`

Skill name: `ah-disclosure`

CLI command: `ah-disclosure`

## 1. Project Scope

`ah-disclosure-kit` is a non-trading workspace for A-share and H-share company data and disclosure documents.

Primary objectives:

- Retrieve A/H-share company profiles and structured financial data.
- Find and download original A-share and H-share disclosure PDFs.
- Find and download prospectuses, listing documents, and offering circulars.
- Parse and search PDFs locally.
- Provide LLMs with traceable, token-efficient EvidencePackets.

Explicitly out of scope:

- Real-time market quotes.
- Candlestick and intraday charts.
- Order books.
- Technical indicators.
- Short-term market sentiment.
- Trading recommendations.

## 2. Data Source Design

| Use case | Preferred source | Description |
|---|---|---|
| Structured A-share company data | AKShare | Company profiles, financial statements, financial indicators, dividends, shareholders, and related data |
| Structured H-share company data | AKShare | Company profiles, financial statements, indicators, dividends, and related data |
| Original A-share announcement PDFs | CNINFO | Annual reports, interim reports, quarterly reports, and general announcements |
| Original H-share announcement PDFs | HKEXnews | Annual reports, interim reports, circulars, and results announcements |
| A-share IPO/prospectus index | AKShare / Eastmoney | IPO-stage information, sponsors, and related data |
| Historical A-share prospectuses/offering circulars | CNINFO | Historical documents for listed companies |
| H-share prospectuses/listing documents | HKEXnews | Requires an H-share stock code or HKEX stockId |

## 3. Default PDF Processing Strategy

Downloading a PDF alone does not trigger parsing.

Ingest runs only when the user requests analysis, reading, search, summarization, or evidence.

By default, ingest generates only:

- `meta.json`
- `pages.jsonl`
- `quality_report.json`
- SQLite FTS

By default, ingest does not generate:

- `document.md`
- `full_text.txt`
- Vector indexes
- Full-document OCR

## 4. Local Question-Answering Workflow

```text
User question
-> Determine the market, company, document type, and task type
-> Use either structured data or the disclosure-document path
-> If PDF evidence is required, first check for existing local parsed artifacts
-> Search SQLite FTS with keywords and synonyms
-> Fall back to Chinese/general substring search
-> Read relevant pages and adjacent pages
-> Assemble an EvidencePacket
-> Have the LLM answer only from the evidence packet
```

## 5. Naming Convention

PDFs, parsed directories, and `document_id` values should use stable names whenever possible:

```text
MARKET_SYMBOL_YEAR_DOCUMENTTYPE_LANGUAGE_SHORTNAME
```

Examples:

```text
A_600519_2024_annual_report_ZH_KWEICHOW_MOUTAI.pdf
H_00700_2024_annual_report_EN_TENCENT.pdf
H_03690_2026_q1_results_announcement_EN_MEITUAN-W.pdf
```

## 6. Data Directory

Default data root:

```text
data/ah_disclosure
```

For production use, set a fixed location through the following environment variable:

```text
AH_DISCLOSURE_DATA_DIR
```

Directory structure:

```text
raw/       Original PDFs
parsed/    PDF parsing artifacts
index/     SQLite search database
cache/     API cache
logs/      Logs
```

## 7. Cleanup Rules

Do not manually delete an individual PDF or parsed directory without updating SQLite.

Use:

- `cleanup_document_tool`
- `cleanup_company_tool`
- `reconcile_local_index_tool`

These tools keep `raw/`, `parsed/`, and SQLite FTS consistent.

## 8. Known Limitations

- A complete structured list of all new H-share IPO companies for a full year is not supported.
- H-share prospectus searches are scoped by company code and do not perform slow market-wide scans.
- Some H-share structured-data interfaces still require stronger caching, retries, and field normalization.
- OCR remains available as a local capability but is not triggered across entire documents by default.
- Vector embeddings are disabled by default.

## 9. v1.0 Acceptance Status

Completed:

- Python package and CLI.
- MCP server.
- Skill.
- Structured A/H-share data paths.
- CNINFO A-share disclosure-document path.
- HKEXnews H-share disclosure-document path.
- Prospectus and offering-document paths.
- PDF downloading, parsing, and SQLite FTS.
- Chinese-search substring fallback.
- Cleanup and index-consistency tools.
- Chinese documentation suite.

Final unit-test result:

```text
44 passed
```

## 10. Follow-up Recommendations

The following historical recommendations were proposed when v1.0 was finalized; some were completed in v1.1.0:

- Further strengthen caching and retries for H-share structured data.
- Add table-extraction quality assessment.
- Add optional local embeddings to improve recall.
- Provide a one-click Windows installation script.
- Provide a Docker distribution environment.
- Expand the real-data regression test suite.

---
**Document created:** 2026-07-03 19:31

**Last modified:** 2026-07-23 17:36

**Last modified model:** Not set (`ANTHROPIC_MODEL` is empty)
