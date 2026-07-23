# B2 Company Data

Documentation: [A0 Documentation Index](./A0_DOC_INDEX.md)

This document describes the sources and scope of structured company data for A-shares and H-shares.

## 1. Data source

Structured company data is retrieved primarily through AKShare.

Rationale:

- AKShare provides a unified interface to numerous A-share and H-share company-data endpoints.
- Structured data is well suited to fast queries for financial statements, financial indicators, dividends, and shareholder information.
- These data can be queried without first downloading and extracting a PDF.

## 2. A-share coverage

Common capabilities include:

- company profiles;
- principal business activities;
- revenue composition;
- balance sheets;
- income statements;
- cash flow statements;
- financial indicators;
- dividends and distributions;
- number of shareholders;
- shareholder and ownership data; and
- share-capital structure and changes.

## 3. H-share coverage

Common capabilities include:

- security profiles;
- company profiles;
- financial statements;
- financial indicators; and
- dividends and distributions.

## 4. Relationship to PDF documents

Structured data is suitable for quickly answering questions such as:

```text
What were Tencent's revenue and net profit in 2025?
What were the major line items in China Merchants Securities' 2025 income statement?
What were Meituan's revenue, gross profit, and net profit in Q1 2026?
```

PDF documents are more suitable for questions such as:

```text
What is the revenue recognition policy?
How did management explain the decline in profit?
How are food-delivery subsidies accounted for?
What does a specific note in the annual report say?
```

## 5. Units

Units depend on the AKShare endpoint and must not be assumed to be yuan in every case.

Before answering, check field names, endpoint documentation, or returned column headers. State the source of the unit explicitly when necessary.

## 6. Caching

Structured query results can be written to SQLite to reduce repeated requests.

The current version supports core structured-data calls for H-shares and writes the results to SQLite for local reuse. Fields, units, and coverage vary across AKShare endpoints, so the endpoint name, returned fields, and reporting basis must still be verified before analysis.

---
**Document created:** 2026-07-03 19:31
**Last modified:** 2026-07-23 16:53
**Last modified model:** Not set (`ANTHROPIC_MODEL` is empty)

