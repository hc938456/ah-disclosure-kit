# Analysis protocol

## Plan and execute

For each claim define identity and scope, multilingual queries, required evidence, table or section types, dependencies, formulas, units, and completion criteria. Do not encode a growing catalog of user wording into permanent keyword rules.

Execute with bounded page and character budgets. Review every candidate for the correct filing, period, page, table, column, headers, units, accounting or management definition, sign convention, comparative period, and conflicts.

## Status and continuation

Assign exactly one status per claim:

- `sufficient`: required evidence is complete and no material gap remains;
- `partial`: useful evidence exists but required fields or pages are missing;
- `insufficient`: available evidence cannot support the claim;
- `conflicting`: credible sources disagree or definitions differ.

Never combine `sufficient` with unresolved gaps. Use follow-up queries for missing evidence and page expansion for evidence already located but clipped. Preserve stable evidence IDs and the same analysis-run chain across rounds. Stop at bounded limits and report the remaining gap.

## Calculate and reconcile

- Bind each input to an allowed evidence ID.
- Use Decimal calculations and derive tolerances from disclosed precision when possible.
- Verify totals, percentages, roll-forwards, signs, periods, units, and cross-claim bridges.
- Report formulas, inputs, result, expected result, tolerance, and residual difference.
- Treat a failed or under-evidenced calculation as a blocking gap, not a result to explain away.

## Output and completion gates

For each material conclusion retain company/code, market, filing type, report period, language, `document_id`, official URL, page/evidence ID, currency/unit, and whether it is disclosed, calculated, reclassified, or inferred.

Lead with the answer, then include only the calculations, evidence, definitions, caveats, and unresolved differences required to audit it. Do not finalize when filing identity is uncertain, period or unit is missing, the table is clipped, credible evidence conflicts, OCR quality is inadequate, or a deterministic tie-out fails outside tolerance.

Keep these distinctions explicit:

- filing evidence versus external provider data;
- disclosed metric versus management metric;
- expense versus cash payment;
- current-period movement versus ending balance;
- accounting policy versus business model;
- candidate evidence versus reviewed evidence.

---
**Document created:** 2026-07-22 18:56
**Last modified:** 2026-07-23 17:02
**Last modified model:** Not set (`ANTHROPIC_MODEL` is empty)
