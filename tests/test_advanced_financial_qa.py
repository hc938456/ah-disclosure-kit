from ah_disclosure.services.analysis_service import (
    continue_llm_analysis,
    execute_llm_analysis_plan,
    prepare_llm_analysis,
)
from ah_disclosure.services.calculation_service import verify_analysis_calculations
from ah_disclosure.storage.sqlite_store import SQLiteStore


def _seed_equity_compensation_document(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    store = SQLiteStore()
    store.upsert_document(
        {
            "document_id": "option_doc",
            "title": "2025 Annual Report",
            "market": "H",
            "symbol": "09999",
        }
    )
    store.upsert_page(
        "option_doc",
        40,
        "Share options outstanding: opening 10,000,000; granted 2,000,000; "
        "exercised 1,500,000; lapsed 500,000; closing 10,000,000.",
    )
    store.upsert_page(
        "option_doc",
        41,
        "Plan A has 2,000,000 options at exercise price RMB10. Plan B has "
        "1,000,000 options at exercise price RMB25.",
    )
    store.upsert_page(
        "option_doc",
        42,
        "Share-based payment expense was RMB130.5 million in 2025 and RMB98.2 "
        "million in 2024. Revenue was RMB21,790.018 million in 2025.",
    )
    store.upsert_page(
        "option_doc",
        43,
        "The options were excluded from diluted EPS because their effect was anti-dilutive.",
    )
    return store


def test_planning_contract_requires_deterministic_arithmetic(monkeypatch, tmp_path):
    _seed_equity_compensation_document(monkeypatch, tmp_path)

    result = prepare_llm_analysis(
        "分析期权变动、股份支付费用及潜在摊薄",
        document_id="option_doc",
    )

    assert any("deterministic calculation" in item for item in result["planner_instructions"])


def test_option_rollforward_retrieval_review_and_calculation(monkeypatch, tmp_path):
    _seed_equity_compensation_document(monkeypatch, tmp_path)
    plan = {
        "claims": [
            {
                "claim_id": "option_rollforward",
                "question": "期权期初、授予、行权、失效和期末数量能否勾稽",
                "evidence_requirements": ["同一计划", "同一期间", "数量单位"],
                "search_queries": ["Share options outstanding opening granted exercised lapsed closing"],
            }
        ]
    }
    evidence = execute_llm_analysis_plan(
        "分析期权滚动表",
        plan,
        document_id="option_doc",
        reconcile=False,
    )
    assert 40 in {item["page_no"] for item in evidence["claim_results"][0]["evidence_references"]}

    review = {
        "claims": [
            {
                "claim_id": "option_rollforward",
                "status": "sufficient",
                "evidence_ids": ["option_rollforward:e1"],
            }
        ],
        "calculations": [
            {
                "calculation_id": "option_closing_reconcile",
                "expression": "opening + granted - exercised - lapsed",
                "variables": [
                    {"name": "opening", "value": 10_000_000, "evidence_id": "option_rollforward:e1"},
                    {"name": "granted", "value": 2_000_000, "evidence_id": "option_rollforward:e1"},
                    {"name": "exercised", "value": 1_500_000, "evidence_id": "option_rollforward:e1"},
                    {"name": "lapsed", "value": 500_000, "evidence_id": "option_rollforward:e1"},
                ],
                "expected_value": 10_000_000,
                "output_unit": "options",
            }
        ],
    }
    completed = continue_llm_analysis(
        "分析期权滚动表",
        plan,
        review,
        document_id="option_doc",
        reconcile=False,
        prior_analysis_result=evidence,
    )

    assert completed["stage"] == "analysis_review_complete"
    assert completed["calculation_summary"]["status"] == "verified"


def test_weighted_option_price_and_expense_intensity_are_not_simple_averages():
    result = verify_analysis_calculations(
        [
            {
                "calculation_id": "weighted_exercise_price",
                "expression": "(count_a * price_a + count_b * price_b) / (count_a + count_b)",
                "variables": [
                    {"name": "count_a", "value": 2_000_000, "evidence_id": "option:e1"},
                    {"name": "price_a", "value": 10, "evidence_id": "option:e1"},
                    {"name": "count_b", "value": 1_000_000, "evidence_id": "option:e1"},
                    {"name": "price_b", "value": 25, "evidence_id": "option:e1"},
                ],
                "expected_value": 15,
            },
            {
                "calculation_id": "expense_revenue_ratio",
                "expression": "share_expense / revenue * 100",
                "variables": [
                    {"name": "share_expense", "value": "130.5", "evidence_id": "expense:e1"},
                    {"name": "revenue", "value": "21790.018", "evidence_id": "expense:e1"},
                ],
                "expected_value": "0.5989",
                "absolute_tolerance": "0.0001",
                "output_unit": "%",
            },
        ]
    )

    assert result["status"] == "verified"
    assert result["results"][0]["calculated_value"] == "15"


def test_conflicting_periods_remain_gaps_instead_of_becoming_an_answer(monkeypatch, tmp_path):
    _seed_equity_compensation_document(monkeypatch, tmp_path)
    plan = {
        "claims": [
            {
                "claim_id": "expense_change",
                "question": "股份支付费用同比变化是多少",
                "search_queries": ["Share-based payment expense"],
            }
        ]
    }
    result = continue_llm_analysis(
        "股份支付费用同比变化是多少",
        plan,
        {
            "claims": [
                {
                    "claim_id": "expense_change",
                    "status": "conflicting",
                    "gaps": ["两个金额的期间口径无法确认一致"],
                }
            ]
        },
        document_id="option_doc",
        reconcile=False,
    )

    assert result["stage"] == "analysis_complete_with_gaps"
    assert result["semantic_status"] == "insufficient"


def test_anti_dilution_question_requires_semantic_review(monkeypatch, tmp_path):
    _seed_equity_compensation_document(monkeypatch, tmp_path)
    plan = {
        "claims": [
            {
                "claim_id": "anti_dilution",
                "question": "期权是否应该计入稀释每股收益",
                "search_queries": ["excluded from diluted EPS anti-dilutive"],
            }
        ]
    }
    result = execute_llm_analysis_plan(
        "期权是否应该计入稀释每股收益",
        plan,
        document_id="option_doc",
        reconcile=False,
    )

    claim = result["claim_results"][0]
    assert 43 in {item["page_no"] for item in claim["evidence_references"]}
    assert claim["answerability"] == "unreviewed"
    assert claim["requires_llm_review"] is True
