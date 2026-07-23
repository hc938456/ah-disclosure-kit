# Troubleshooting

## Tool or environment failure

1. Call `server_info` and verify version and data directory.
2. Confirm the MCP server name is `ah_disclosure` and starts `python -m ah_disclosure.mcp_server`.
3. Confirm the package and required extras are installed in the Python interpreter used by MCP.
4. Restart Codex after MCP or Skill configuration changes.

## Empty, wrong, or incomplete evidence

- Verify `document_id`, company, year, language, consolidation scope, and index page count.
- Search accounting and business synonyms in the filing's language.
- Expand fixed sections, full located pages, and adjacent pages.
- Check `requires_ocr`, extraction fallback, and extraction-failure fields.
- Do not treat retrieval failure as absence of disclosure.
- For wrong or short documents, review title, category, size, page count, identity, year, language, and required sections; preserve ambiguity when necessary.

## Cache, index, or calculation inconsistency

- Audit before cleanup and compare PDF hash, parsed metadata, `pages.jsonl`, and SQLite page counts.
- Use reconcile or cleanup with dry-run before changing state.
- For calculations, verify evidence IDs, signs, units, precision, periods, and consolidation scope.
- Split dense formulas into auditable steps and report unresolved differences instead of forcing a pass.

---
**Document created:** 2026-07-22 18:56
**Last modified:** 2026-07-23 17:02
**Last modified model:** Not set (`ANTHROPIC_MODEL` is empty)
