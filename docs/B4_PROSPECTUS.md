# B4 Prospectuses and Listing Documents

Documentation: [A0 Documentation Index](./A0_DOC_INDEX.md)

This document describes the search paths for prospectuses, listing documents, hearing materials, and securities offering documents.

## 1. A-share IPO-stage documents

A-share IPO review status, queue status, listing-preparation guidance, and prospectus indexes are retrieved primarily through relevant AKShare and Eastmoney endpoints.

Typical questions include:

```text
What stage has a company reached in the IPO process?
Where can I find the IPO prospectus?
Who are the sponsor, accountants, and legal counsel?
```

## 2. Historical offering documents for listed A-share companies

Historical prospectuses, listing announcements, and securities offering documents for listed companies are retrieved primarily through CNINFO.

Common search concepts include:

- prospectus;
- listing announcement;
- securities offering document;
- convertible corporate bond offering document;
- rights issue prospectus;
- non-public offering; and
- offering to specific investors.

## 3. H-share prospectuses and listing documents

H-share prospectuses, listing documents, PHIPs, and post-hearing information packs are retrieved primarily through HKEXnews.

Important considerations:

- Searches usually require an H-share code or HKEX `stockId`.
- A market-wide scan based only on a company name is not recommended.
- Results should include the source URL, local PDF path, publication date, and document title.
- HKEX may use the same `GLOBAL OFFERING` title for both an offering announcement and the formal prospectus, so title alone is not sufficient for selection.
- The workflow should inspect the HKEX document category and file size. `Listing Documents - [Offer for Subscription]` takes precedence over `Announcements and Notices - [Formal Notice]`.
- A formal prospectus must pass page-count and core-section validation, including the prospectus or global offering, risk factors, business, financial information, and accountants' report sections.
- For Traditional Chinese H-share prospectuses, the search should prioritize the Traditional Chinese term for "global offering," then fall back to terms for "prospectus," "listing document," and relevant English keywords. Within Chinese listing-document categories, `Listing Documents - [Offer for Subscription]` takes precedence over `Announcements and Notices - [Formal Notice]`.
- Analysis of a Traditional Chinese prospectus should search concurrently for the Traditional Chinese equivalents of "revenue recognition," "significant accounting policies," "segment information," "revenue disaggregation," and "principal products and services." This prevents an empty evidence package caused by script differences after the correct document has been downloaded.
- The document body must also match the target company or stock code and the expected year, preventing a structurally complete document for another issuer from entering the production cache.
- A short offering announcement should be marked `rejected_short_document`, after which the workflow should continue to the next candidate.

## 4. Download and ingest

A-share securities offering documents are queried by category: convertible bonds, corporate bonds, follow-on offerings, rights issues, and other financing. If any category returns a formal document, the result retains only document candidates. If every category fails because of source errors, the workflow returns a structured error containing the source, category, and error type. An upstream timeout must not be interpreted as "no document found."

For download-only requests:

```text
download_prospectus_tool
-> download to staging
-> validate structure and document identity
-> save to raw/ after validation passes
-> return the path and URL
```

For requests that include analysis:

```text
download_and_ingest_prospectus_tool
-> stage and validate the PDF
-> move it to raw/ after validation passes
-> reuse pages extracted during validation for ingest
-> SQLite FTS
-> EvidencePacket
-> LLM analysis
```

---
**Document created:** 2026-07-03 19:31
**Last modified:** 2026-07-23 16:53
**Last modified model:** Not set (`ANTHROPIC_MODEL` is empty)

