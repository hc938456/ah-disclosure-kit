# B3 HKEX

Documentation: [A0 Documentation Index](./A0_DOC_INDEX.md)

This document explains why H-share filing searches require an HKEX `stockId` and defines the current scope of the toolkit.

## 1. H-share codes and HKEX stockId

Many HKEXnews announcement-search URLs use an internal `stockId`.

The HKEX title-filter endpoint cannot be treated unconditionally as a complete candidate set. For example, filtering for `Annual Report` may omit title variants such as `Annual Report and Accounts 2025 (with employee share plans)`. The current workflow first checks the title, reporting year, exclusion terms, and HKEX file size. A clearly identified standard annual report of at least 1 MB proceeds directly to download validation. All announcements for the same company are queried only when the initial result is missing, too small, or uncertain. This preserves recall for unusual titles while avoiding two HKEX requests for most standard annual reports.

HKEX queries with the same stock code, language, and title keyword share one source cache. `max_rows` controls only how many locally cached rows are returned to the caller. The first remote query caches the complete candidate set from the current page, so a request for 20 rows followed by a request for 10 rows does not access HKEX again. Legacy caches keyed by `max_rows` are migrated automatically when the Kit can safely confirm that the result was not truncated.

The mapping from public stock codes to `stockId` values is cached persistently on demand rather than populated by downloading the entire H-share mapping at once. Each worker thread reuses an HKEX HTTP session. Validated cache entries are not revalidated during source searches. Identity mappings are checked again only when `refresh=true` is set explicitly, and the existing record is retained if refresh fails.

An `Overseas Regulatory Announcement` may include an A-share annual report as an attachment. Even if the document is complete, it must not be used as the H-share annual report. The H-share annual-report workflow must classify it as an incorrect document variant and continue searching for the Traditional Chinese version corresponding to the English HKEX annual report.

`stockId` is not the five-digit H-share code.

For example:

```text
H-share code: 00700
HKEX stockId: must be resolved through an HKEX query or the local cache
```

An H-share announcement search therefore usually follows this sequence:

```text
H-share code
-> resolve_hkex_stock_id
-> validate Stock Code / Short Name
-> search_h_filings
-> download
```

## 2. Supported H-share filings

The current version supports:

- annual reports;
- interim reports;
- quarterly results announcements;
- results announcements;
- circulars;
- general announcements;
- prospectuses;
- listing documents; and
- PHIPs / post-hearing information packs.

## 3. Unsupported capability

The current version does not provide a complete, structured list of newly listed H-share IPO companies for a given year to date.

If the user asks:

```text
List all newly listed H-share IPO companies in 2026 year to date.
```

First explain:

```text
ah-disclosure does not currently support a complete, structured list of all new H-share IPOs for an entire year.
```

If the user agrees, compile the list manually from external websites or exchange pages and state clearly that the result comes from external sources rather than local structured ah-disclosure data.

## 4. Scope of prospectus searches

H-share prospectus and listing-document searches operate within the scope of a specific company code.

If the user provides only a company name without an H-share code, ask for the code instead of running a market-wide scan.

---
**Document created:** 2026-07-03 19:31
**Last modified:** 2026-07-23 16:53
**Last modified model:** Not set (`ANTHROPIC_MODEL` is empty)

