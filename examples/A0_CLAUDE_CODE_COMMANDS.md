# A0 Claude Code Command Examples

Documentation: [A0 Documentation Index](../docs/A0_DOC_INDEX.md)

## 1. Register the MCP server

```powershell
claude mcp add --transport stdio --scope user ah-disclosure "python -m ah_disclosure.mcp_server"
```

## 2. Common prompts

Download a PDF without ingesting it:

```text
Use ah-disclosure to download Tencent's 2024 annual report. Download the PDF only; do not ingest it.
```

Download and analyze:

```text
Use ah-disclosure to download Meituan's 2025 annual report and Q1 2026 results announcement. Analyze revenue, net profit, segment performance, and management's explanations.
```

Summarize significant accounting policies:

```text
Use ah-disclosure to download and analyze Tencent's 2024 annual report. Summarize significant accounting policies for revenue recognition, cost recognition, impairment of financial assets, capitalization of research and development expenditure, income taxes, and the scope of consolidation. Present each item as "policy content + impact on financial analysis."
```

Analyze share-based compensation:

```text
Use ah-disclosure to download and analyze Meituan's latest annual report. Summarize its share-based compensation arrangements, including plan types, eligible recipients, number of awards granted, exercise prices, vesting schedules, share-based payment expense for the period, and the effect on profit.
```

Analyze pre-IPO financing in a prospectus:

```text
Use ah-disclosure to download and analyze the company's prospectus. Summarize its pre-IPO financing history, including the date of each round, investors, amount raised, principal entry prices, preference-share or special-rights arrangements, and major institutional investors before listing.
```

Analyze major investors disclosed in a prospectus:

```text
Use ah-disclosure to download and analyze the company's prospectus. Summarize the major pre-listing shareholders and institutional investors, including their ownership percentages, investment dates, whether they are core strategic investors, and their potential influence on corporate governance and the timing of future exits.
```

Query structured data:

```text
Use ah-disclosure to query structured data directly without searching PDFs. Tell me Tencent's revenue and net profit for 2025.
```

Search locally ingested PDFs:

```text
Use ah-disclosure to find pages related to revenue recognition, customer incentives, and selling and marketing expenses in the locally ingested Meituan annual report.
```

Require evidence:

```text
Use ah-disclosure to return an EvidencePacket and answer from the evidence pages. List the source file, page numbers, and local PDF path.
```

Prepare a batch without analyzing it:

```text
Use ah-disclosure batch prepare to process the company list I provide. Confirm stock codes, locate sources, download, validate, and ingest the documents in batch. Do not extract an EvidencePacket and do not perform analysis, valuation, or report writing. When complete, summarize each task's status and the elapsed time for every stage.
```

---
**Document created:** 2026-07-03 19:31
**Last modified:** 2026-07-23 16:53
**Last modified model:** Not set (`ANTHROPIC_MODEL` is empty)

