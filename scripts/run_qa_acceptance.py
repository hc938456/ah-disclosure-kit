from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import statistics
import sys
import time
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ROOT / "tests" / "qa_acceptance_cases.json"


def _tool_payload(result: Any) -> dict[str, Any]:
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        if isinstance(structured.get("result"), dict):
            return structured["result"]
        return structured
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if not text:
            continue
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    raise RuntimeError("MCP tool returned no JSON object")


def _claim_plan(case: dict[str, Any]) -> dict[str, Any]:
    document_ids = list(case["document_ids"])
    return {
        "claims": [
            {
                "claim_id": claim["claim_id"],
                "question": claim["question"],
                "depends_on_claim_ids": claim.get("depends_on_claim_ids") or [],
                "review_role": claim.get("review_role") or "financial_evidence_reviewer",
                "worker_preference": claim.get("worker_preference") or "auto",
                "evidence_requirements": [
                    "period, unit, reporting scope and directly supporting source text"
                ],
                "filters": {
                    "document_ids": list(claim.get("document_ids") or document_ids)
                },
                "search_queries": [
                    {"query": query, "evidence_type": "dynamic_llm_query"}
                    for query in claim["queries"]
                ],
            }
            for claim in case["claims"]
        ]
    }


def _evaluate_case(case: dict[str, Any], payload: dict[str, Any], elapsed: float) -> dict[str, Any]:
    failures: list[str] = []
    claim_details: list[dict[str, Any]] = []
    if payload.get("stage") != "evidence_review_required":
        failures.append(f"unexpected stage: {payload.get('stage')}")
    if not payload.get("analysis_run_id"):
        failures.append("analysis_run_id missing")
    all_documents: set[str] = set()
    by_id = {
        item.get("claim_id"): item
        for item in payload.get("claim_results") or []
        if isinstance(item, dict)
    }
    for expected in case["claims"]:
        claim_id = expected["claim_id"]
        actual = by_id.get(claim_id)
        if actual is None:
            failures.append(f"{claim_id}: result missing")
            continue
        packet = actual.get("evidence_packet") or {}
        items = [item for item in packet.get("evidence_items") or [] if isinstance(item, dict)]
        text = re.sub(
            r"\s+",
            " ",
            "\n".join(str(item.get("text") or "") for item in items),
        ).casefold()
        documents = {str(item.get("document_id")) for item in items if item.get("document_id")}
        all_documents.update(documents)
        required_documents = set(expected.get("require_documents") or [])
        missing_claim_documents = required_documents - documents
        if missing_claim_documents:
            failures.append(
                f"{claim_id}: required documents missing: {sorted(missing_claim_documents)}"
            )
        missing_groups: list[list[str]] = []
        for group in expected.get("expected_groups") or []:
            if not any(str(term).casefold() in text for term in group):
                missing_groups.append(group)
        if not items:
            failures.append(f"{claim_id}: no evidence candidates")
        if missing_groups:
            failures.append(f"{claim_id}: missing semantic anchors {missing_groups}")
        claim_details.append(
            {
                "claim_id": claim_id,
                "candidate_pages": [item.get("page_no") for item in items],
                "documents": sorted(documents),
                "missing_groups": missing_groups,
                "truncated": bool(packet.get("truncated")),
            }
        )
    if case.get("require_all_documents"):
        missing_documents = set(case["document_ids"]) - all_documents
        if missing_documents:
            failures.append(f"cross-document evidence missing: {sorted(missing_documents)}")
    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "status": "passed" if not failures else "failed",
        "elapsed_seconds": round(elapsed, 4),
        "failures": failures,
        "claims": claim_details,
        "analysis_run_id": payload.get("analysis_run_id"),
    }


async def _protocol_guardrails(session: ClientSession, seed: dict[str, Any]) -> list[dict[str, Any]]:
    source_claim = (seed.get("claim_results") or [{}])[0]
    claim_id = source_claim.get("claim_id") or "claim"
    plan = {
        "claims": [
            {
                "claim_id": claim_id,
                "question": source_claim.get("question") or "guardrail claim",
                "filters": source_claim.get("filters") or {},
                "search_queries": source_claim.get("search_queries") or ["revenue"],
            }
        ]
    }
    isolated_seed = _tool_payload(
        await session.call_tool(
            "execute_llm_analysis_plan_tool",
            {
                "query": "protocol isolated guardrail seed",
                "analysis_plan": plan,
            },
        )
    )
    run_id = isolated_seed.get("analysis_run_id")
    claim = (isolated_seed.get("claim_results") or [{}])[0]
    evidence_refs = claim.get("evidence_references") or []
    evidence_id = (evidence_refs[0] if evidence_refs else {}).get("evidence_id")
    checks: list[dict[str, Any]] = []

    valid_review = {
        "claims": [
            {
                "claim_id": claim_id,
                "status": "sufficient",
                "evidence_ids": [evidence_id] if evidence_id else [],
            }
        ]
    }
    result = _tool_payload(
        await session.call_tool(
            "continue_llm_analysis_tool",
            {
                "query": "protocol valid semantic review",
                "analysis_plan": plan,
                "evidence_review": valid_review,
                "prior_analysis_id": run_id,
            },
        )
    )
    checks.append(
        {
            "name": "valid_review_reuses_registry_context",
            "passed": result.get("stage") == "analysis_review_complete",
            "stage": result.get("stage"),
        }
    )

    fake_review = {
        "claims": [
            {
                "claim_id": claim_id,
                "status": "sufficient",
                "evidence_ids": [f"{claim_id}:fabricated"],
            }
        ]
    }
    result = _tool_payload(
        await session.call_tool(
            "continue_llm_analysis_tool",
            {
                "query": "guardrail fabricated evidence",
                "analysis_plan": plan,
                "evidence_review": fake_review,
                "prior_analysis_id": run_id,
            },
        )
    )
    checks.append(
        {
            "name": "fabricated_evidence_is_blocked",
            "passed": result.get("stage") == "analysis_complete_with_gaps"
            and bool(result.get("validation_errors")),
            "stage": result.get("stage"),
            "validation_errors": result.get("validation_errors"),
        }
    )

    if evidence_id:
        evidence_item = ((claim.get("evidence_packet") or {}).get("evidence_items") or [{}])[0]
        source_text = str(evidence_item.get("text") or "")
        numeric_matches = re.findall(r"(?<!\w)[+-]?\d[\d,]*(?:\.\d+)?(?!\w)", source_text)
        source_number = numeric_matches[0] if numeric_matches else None
        if source_number:
            positive_calculation = {
                **valid_review,
                "calculations": [
                    {
                        "calculation_id": "evidence_bound_identity",
                        "expression": "reported_value",
                        "variables": [
                            {
                                "name": "reported_value",
                                "value": source_number,
                                "evidence_id": evidence_id,
                            }
                        ],
                        "expected_value": source_number,
                    }
                ],
            }
            result = _tool_payload(
                await session.call_tool(
                    "continue_llm_analysis_tool",
                    {
                        "query": "protocol valid evidence-bound calculation",
                        "analysis_plan": plan,
                        "evidence_review": positive_calculation,
                        "prior_analysis_id": run_id,
                    },
                )
            )
            checks.append(
                {
                    "name": "source_number_binding_and_calculation_complete",
                    "passed": result.get("stage") == "analysis_review_complete"
                    and (result.get("calculation_summary") or {}).get("status") == "verified",
                    "stage": result.get("stage"),
                    "calculation_status": (result.get("calculation_summary") or {}).get("status"),
                }
            )

            discrepancy_review = {
                **valid_review,
                "calculations": [
                    {
                        "calculation_id": "deliberate_discrepancy",
                        "expression": "reported_value + 1",
                        "variables": [
                            {
                                "name": "reported_value",
                                "value": source_number,
                                "evidence_id": evidence_id,
                            }
                        ],
                        "expected_value": source_number,
                        "absolute_tolerance": 0,
                    }
                ],
            }
            result = _tool_payload(
                await session.call_tool(
                    "continue_llm_analysis_tool",
                    {
                        "query": "protocol discrepancy gate",
                        "analysis_plan": plan,
                        "evidence_review": discrepancy_review,
                        "prior_analysis_id": run_id,
                    },
                )
            )
            checks.append(
                {
                    "name": "calculation_discrepancy_blocks_completion",
                    "passed": result.get("stage") == "analysis_complete_with_gaps"
                    and (result.get("calculation_summary") or {}).get("status")
                    == "discrepancy",
                    "stage": result.get("stage"),
                    "calculation_status": (result.get("calculation_summary") or {}).get("status"),
                }
            )

        bad_number_review = {
            "claims": [
                {
                    "claim_id": claim_id,
                    "status": "sufficient",
                    "evidence_ids": [evidence_id],
                }
            ],
            "calculations": [
                {
                    "calculation_id": "fabricated_source_number",
                    "expression": "reported_value",
                    "variables": [
                        {
                            "name": "reported_value",
                            "value": "9876543210123456789",
                            "evidence_id": evidence_id,
                        }
                    ],
                    "expected_value": "9876543210123456789",
                }
            ],
        }
        result = _tool_payload(
            await session.call_tool(
                "continue_llm_analysis_tool",
                {
                    "query": "guardrail fabricated source number",
                    "analysis_plan": plan,
                    "evidence_review": bad_number_review,
                    "prior_analysis_id": run_id,
                },
            )
        )
        checks.append(
            {
                "name": "number_absent_from_source_is_blocked",
                "passed": result.get("stage") == "analysis_complete_with_gaps"
                and (result.get("calculation_summary") or {}).get("status") == "unlinked",
                "stage": result.get("stage"),
                "calculation_status": (result.get("calculation_summary") or {}).get("status"),
            }
        )

        page_no = evidence_item.get("page_no")
        document_id = evidence_item.get("document_id")
        if page_no and document_id:
            expansion_review = {
                "claims": [
                    {
                        "claim_id": claim_id,
                        "status": "partial",
                        "evidence_ids": [evidence_id],
                        "gaps": ["need the complete source page"],
                        "expand_pages": [
                            {"document_id": document_id, "page_numbers": [page_no]}
                        ],
                    }
                ]
            }
            result = _tool_payload(
                await session.call_tool(
                    "continue_llm_analysis_tool",
                    {
                        "query": "protocol explicit page expansion",
                        "analysis_plan": plan,
                        "evidence_review": expansion_review,
                        "prior_analysis_id": run_id,
                    },
                )
            )
            checks.append(
                {
                    "name": "explicit_page_expansion_returns_new_review_round",
                    "passed": result.get("stage") == "expanded_evidence_review_required"
                    and bool(result.get("analysis_run_id")),
                    "stage": result.get("stage"),
                }
            )

        follow_up_review = {
            "claims": [
                {
                    "claim_id": claim_id,
                    "status": "partial",
                    "evidence_ids": [evidence_id],
                    "gaps": ["need a focused corroborating page"],
                    "follow_up_queries": [
                        {"query": "财务负责人 首席财务官", "evidence_type": "biography"}
                    ],
                }
            ]
        }
        result = _tool_payload(
            await session.call_tool(
                "continue_llm_analysis_tool",
                {
                    "query": "protocol focused follow-up",
                    "analysis_plan": plan,
                    "evidence_review": follow_up_review,
                    "prior_analysis_id": run_id,
                },
            )
        )
        checks.append(
            {
                "name": "partial_review_triggers_focused_follow_up",
                "passed": result.get("stage") == "follow_up_evidence_review_required"
                and bool(result.get("analysis_run_id")),
                "stage": result.get("stage"),
            }
        )

    result = _tool_payload(
        await session.call_tool(
            "continue_llm_analysis_tool",
            {
                "query": "protocol expired context",
                "analysis_plan": plan,
                "evidence_review": valid_review,
                "prior_analysis_id": "qa-nonexistent-analysis-run",
            },
        )
    )
    checks.append(
        {
            "name": "unknown_analysis_context_is_blocked",
            "passed": result.get("stage") == "analysis_complete_with_gaps"
            and any(
                "unknown or expired" in str(error)
                for error in result.get("validation_errors") or []
            ),
            "stage": result.get("stage"),
        }
    )
    return checks


async def _management_calculation_checks(session: ClientSession) -> list[dict[str, Any]]:
    cases = [
        {
            "name": "effective_tax_rate_bridge",
            "expected_status": "verified",
            "calculations": [
                {
                    "calculation_id": "etr_bridge",
                    "expression": "base + non_taxable + non_deductible + prior + rd + losses + utilized + concession + rate_change + jurisdictions",
                    "variables": [
                        {"name": "base", "value": 1_814_227, "evidence_id": "tax:p171"},
                        {"name": "non_taxable", "value": -104_148, "evidence_id": "tax:p171"},
                        {"name": "non_deductible", "value": 563_605, "evidence_id": "tax:p171"},
                        {"name": "prior", "value": -90_231, "evidence_id": "tax:p171"},
                        {"name": "rd", "value": -138_491, "evidence_id": "tax:p171"},
                        {"name": "losses", "value": 371_654, "evidence_id": "tax:p171"},
                        {"name": "utilized", "value": -4_376, "evidence_id": "tax:p171"},
                        {"name": "concession", "value": -740_460, "evidence_id": "tax:p171"},
                        {"name": "rate_change", "value": 3_812, "evidence_id": "tax:p171"},
                        {"name": "jurisdictions", "value": -151_912, "evidence_id": "tax:p171"},
                    ],
                    "expected_value": 1_523_680,
                }
            ],
        },
        {
            "name": "mda_effective_tax_rate_discrepancy",
            "expected_status": "discrepancy",
            "calculations": [
                {
                    "calculation_id": "etr",
                    "expression": "tax / pbt * 100",
                    "variables": [
                        {"name": "tax", "value": 1_523_680, "evidence_id": "income:p108"},
                        {"name": "pbt", "value": 7_256_907, "evidence_id": "income:p108"},
                    ],
                    "expected_value": "21.6",
                    "absolute_tolerance": "0.05",
                }
            ],
        },
        {
            "name": "three_factor_dupont",
            "expected_status": "verified",
            "calculations": [
                {
                    "calculation_id": "dupont_roe",
                    "expression": "(profit / revenue) * (revenue / average_assets) * (average_assets / average_equity) * 100",
                    "variables": [
                        {"name": "profit", "value": 5_733_227, "evidence_id": "income:p108"},
                        {"name": "revenue", "value": 21_790_018, "evidence_id": "income:p108"},
                        {"name": "average_assets", "value": "60337086.5", "evidence_id": "balance:p110-111"},
                        {"name": "average_equity", "value": "49258456.5", "evidence_id": "balance:p111"},
                    ],
                    "expected_value": "11.6391",
                    "absolute_tolerance": "0.0001",
                }
            ],
        },
        {
            "name": "operating_working_capital_gap",
            "expected_status": "discrepancy",
            "calculations": [
                {
                    "calculation_id": "nwc_cashflow_gap",
                    "expression": "cashflow_effect + balance_sheet_increase",
                    "variables": [
                        {"name": "cashflow_effect", "value": -1_740_021, "evidence_id": "cashflow:p115"},
                        {"name": "balance_sheet_increase", "value": 1_779_783, "evidence_id": "balance:p110"},
                    ],
                    "expected_value": 0,
                    "absolute_tolerance": 1,
                }
            ],
        },
        {
            "name": "ppe_rollforward",
            "expected_status": "verified",
            "calculations": [
                {
                    "calculation_id": "ppe_cost",
                    "expression": "opening + additions + transfer + held_for_sale + disposals + fx",
                    "variables": [
                        {"name": "opening", "value": 30_608_816, "evidence_id": "ppe:p177"},
                        {"name": "additions", "value": 3_996_335, "evidence_id": "ppe:p177"},
                        {"name": "transfer", "value": -16_061, "evidence_id": "ppe:p177"},
                        {"name": "held_for_sale", "value": -1_237_459, "evidence_id": "ppe:p177"},
                        {"name": "disposals", "value": -895_081, "evidence_id": "ppe:p177"},
                        {"name": "fx", "value": 871_519, "evidence_id": "ppe:p177"},
                    ],
                    "expected_value": 33_328_069,
                }
            ],
        },
        {
            "name": "cash_capex_is_not_accounting_additions",
            "expected_status": "discrepancy",
            "calculations": [
                {
                    "calculation_id": "capex_gap",
                    "expression": "accounting_additions - cash_capex",
                    "variables": [
                        {"name": "accounting_additions", "value": 3_996_335, "evidence_id": "ppe:p177"},
                        {"name": "cash_capex", "value": 3_685_115, "evidence_id": "cashflow:p116"},
                    ],
                    "expected_value": 0,
                }
            ],
        },
        {
            "name": "management_assumption_provenance",
            "expected_status": "calculated",
            "expected_assumption_based": True,
            "calculations": [
                {
                    "calculation_id": "provisional_nopat",
                    "expression": "ebit * (1 - tax_rate)",
                    "variables": [
                        {"name": "ebit", "value": 7_399_966, "evidence_id": "income:p108"},
                        {"name": "tax_rate", "value": "0.2099627293", "source_type": "assumption"},
                    ],
                }
            ],
        },
    ]
    checks: list[dict[str, Any]] = []
    for case in cases:
        payload = _tool_payload(
            await session.call_tool(
                "verify_analysis_calculations_tool",
                {"calculations": case["calculations"]},
            )
        )
        expected_assumption = case.get("expected_assumption_based")
        passed = payload.get("status") == case["expected_status"]
        if expected_assumption is not None:
            passed = passed and payload.get("assumption_based") is expected_assumption
        checks.append(
            {
                "name": case["name"],
                "passed": passed,
                "status": payload.get("status"),
                "assumption_based": payload.get("assumption_based"),
            }
        )
    return checks


async def run(cases_path: Path, output_path: Path) -> int:
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "ah_disclosure.mcp_server"],
        env={
            **os.environ,
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
        },
    )
    results: list[dict[str, Any]] = []
    first_payload: dict[str, Any] | None = None
    started = time.perf_counter()
    async with stdio_client(params) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            tool_names = {tool.name for tool in (await session.list_tools()).tools}
            required_tools = {
                "prepare_llm_analysis_tool",
                "execute_llm_analysis_plan_tool",
                "continue_llm_analysis_tool",
                "verify_analysis_calculations_tool",
            }
            missing_tools = sorted(required_tools - tool_names)
            if missing_tools:
                raise RuntimeError(f"MCP tools missing after restart: {missing_tools}")
            for case in cases:
                case_started = time.perf_counter()
                payload = _tool_payload(
                    await session.call_tool(
                        "execute_llm_analysis_plan_tool",
                        {
                            "query": case["question"],
                            "analysis_plan": _claim_plan(case),
                            "max_pages_per_claim": 8,
                            "max_chars_per_claim": 12000,
                            "max_total_chars": 72000,
                        },
                    )
                )
                if first_payload is None:
                    first_payload = payload
                result = _evaluate_case(case, payload, time.perf_counter() - case_started)
                results.append(result)
                marker = "PASS" if result["status"] == "passed" else "FAIL"
                print(f"[{marker}] {result['case_id']} ({result['elapsed_seconds']:.3f}s)")
                for failure in result["failures"]:
                    print(f"  - {failure}")
            guardrails = await _protocol_guardrails(session, first_payload or {})
            management_calculations = await _management_calculation_checks(session)
    elapsed = time.perf_counter() - started
    passed = sum(item["status"] == "passed" for item in results)
    latencies = [float(item["elapsed_seconds"]) for item in results]
    report = {
        "suite": "post-ingest financial filing QA acceptance",
        "transport": "fresh MCP stdio process",
        "case_count": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "pass_rate": round(passed / len(results), 4) if results else 0,
        "elapsed_seconds": round(elapsed, 4),
        "latency_seconds": {
            "mean": round(statistics.mean(latencies), 4) if latencies else 0,
            "median": round(statistics.median(latencies), 4) if latencies else 0,
            "max": round(max(latencies), 4) if latencies else 0,
        },
        "guardrails": guardrails,
        "management_calculations": management_calculations,
        "results": results,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("case_count", "passed", "failed", "pass_rate", "elapsed_seconds", "latency_seconds", "guardrails", "management_calculations")}, ensure_ascii=False, indent=2))
    print(f"Report: {output_path}")
    return (
        0
        if report["failed"] == 0
        and all(item["passed"] for item in guardrails)
        and all(item["passed"] for item in management_calculations)
        else 1
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real post-ingest QA acceptance through MCP stdio.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / ".test-results" / "qa_acceptance.json",
    )
    args = parser.parse_args()
    return asyncio.run(run(args.cases, args.output))


if __name__ == "__main__":
    raise SystemExit(main())
