import json

from ah_disclosure.services.analysis_service import (
    ANALYSIS_PROTOCOL,
    continue_llm_analysis,
    execute_llm_analysis_plan,
    normalize_evidence_text,
    prepare_llm_analysis,
)
from ah_disclosure.storage.sqlite_store import SQLiteStore


def _seed_document(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    store = SQLiteStore()
    store.upsert_document(
        {
            "document_id": "doc1",
            "title": "Flexible Filing",
            "market": "A",
            "symbol": "000001",
        }
    )
    store.upsert_page(
        "doc1",
        4,
        "2025年度合并营业收入为123,456万元，单位为人民币万元。",
    )
    store.upsert_page(
        "doc1",
        19,
        "客户签收商品并取得控制权时确认收入，技术服务按照履约进度确认收入。",
    )
    store.upsert_page(
        "doc1",
        20,
        "履约进度采用已发生成本占预计总成本的比例确定。",
    )


def test_prepare_llm_analysis_returns_provider_neutral_contract(monkeypatch, tmp_path):
    _seed_document(monkeypatch, tmp_path)

    result = prepare_llm_analysis("请分析这家公司的商业化质量", document_id="doc1")

    assert result["protocol"] == ANALYSIS_PROTOCOL
    assert result["stage"] == "planning_required"
    assert result["scope"]["document_meta"]["title"] == "Flexible Filing"
    assert "claims" in result["analysis_plan_schema"]
    claim_schema = result["analysis_plan_schema"]["claims"][0]
    assert "depends_on_claim_ids" in claim_schema
    assert claim_schema["worker_preference"] == "auto | parallel_worker | orchestrator"
    assert "kit_code" in result["responsibility_contract"]
    assert "orchestrating_llm" in result["responsibility_contract"]
    assert all("OpenAI" not in instruction for instruction in result["planner_instructions"])


def test_execute_plan_emits_parallel_worker_batches_for_independent_claims(
    monkeypatch, tmp_path
):
    _seed_document(monkeypatch, tmp_path)
    plan = {
        "claims": [
            {
                "claim_id": "amount",
                "question": "确认收入金额",
                "search_queries": ["营业收入"],
                "review_role": "financial_statement_reviewer",
            },
            {
                "claim_id": "policy",
                "question": "确认收入政策",
                "search_queries": ["控制权"],
                "review_role": "accounting_policy_reviewer",
            },
            {
                "claim_id": "conclusion",
                "question": "结合金额和政策形成分析",
                "search_queries": ["营业收入"],
                "depends_on_claim_ids": ["amount", "policy"],
                "worker_preference": "orchestrator",
            },
        ]
    }

    result = execute_llm_analysis_plan(
        "分析收入规模与确认模式",
        plan,
        document_id="doc1",
        reconcile=False,
    )

    orchestration = result["orchestration"]
    assert orchestration["protocol"] == "ah-disclosure-worker-plan/v1"
    assert orchestration["provider_neutral"] is True
    assert orchestration["recommended_mode"] == "parallel_workers"
    assert orchestration["analysis_run_id"] == result["analysis_run_id"]
    assert orchestration["expected_review_claim_ids"] == ["amount", "policy", "conclusion"]
    first_batch = orchestration["review_batches"][0]
    assert first_batch["can_run_in_parallel"] is True
    assert {unit["claim_id"] for unit in first_batch["work_units"]} == {
        "amount",
        "policy",
    }
    assert all(
        unit["input_selector"]["json_pointer"].startswith("/claim_results/")
        for unit in first_batch["work_units"]
    )
    assert all(
        unit["constraints"]["may_answer_user"] is False
        for unit in first_batch["work_units"]
    )
    second_unit = orchestration["review_batches"][1]["work_units"][0]
    assert second_unit["claim_id"] == "conclusion"
    assert second_unit["recommended_executor"] == "orchestrator"
    assert set(second_unit["depends_on_work_units"]) == {
        "review:amount",
        "review:policy",
    }


def test_execute_plan_reports_invalid_worker_dependencies(monkeypatch, tmp_path):
    _seed_document(monkeypatch, tmp_path)
    result = execute_llm_analysis_plan(
        "分析收入",
        {
            "claims": [
                {
                    "claim_id": "amount",
                    "question": "确认收入",
                    "search_queries": ["营业收入"],
                    "depends_on_claim_ids": ["amount", "missing"],
                }
            ]
        },
        document_id="doc1",
        reconcile=False,
    )

    errors = " ".join(result["validation_errors"])
    assert "claim cannot depend on itself" in errors
    assert "unknown dependency missing" in errors
    assert result["orchestration"]["recommended_mode"] == "single_orchestrator"


def test_review_rejects_missing_duplicate_and_unsupported_worker_outputs(
    monkeypatch, tmp_path
):
    _seed_document(monkeypatch, tmp_path)
    plan = {
        "claims": [
            {"claim_id": "amount", "question": "确认金额", "search_queries": ["营业收入"]},
            {"claim_id": "policy", "question": "确认政策", "search_queries": ["控制权"]},
        ]
    }
    prior = execute_llm_analysis_plan(
        "分析收入",
        plan,
        document_id="doc1",
        reconcile=False,
    )

    missing = continue_llm_analysis(
        "分析收入",
        plan,
        {"claims": [{"claim_id": "amount", "status": "sufficient"}]},
        document_id="doc1",
        prior_analysis_id=prior["analysis_run_id"],
        reconcile=False,
    )
    duplicate = continue_llm_analysis(
        "分析收入",
        plan,
        {
            "claims": [
                {"claim_id": "amount", "status": "sufficient"},
                {"claim_id": "amount", "status": "sufficient"},
            ]
        },
        document_id="doc1",
        prior_analysis_id=prior["analysis_run_id"],
        reconcile=False,
    )
    unsupported = continue_llm_analysis(
        "分析收入",
        plan,
        {
            "claims": [
                {"claim_id": "amount", "status": "approved"},
                {"claim_id": "policy", "status": "sufficient"},
            ]
        },
        document_id="doc1",
        prior_analysis_id=prior["analysis_run_id"],
        reconcile=False,
    )

    assert missing["stage"] == "invalid_review"
    assert "missing review claim_ids: policy" in " ".join(missing["validation_errors"])
    assert duplicate["stage"] == "invalid_review"
    assert "duplicate review claim_id: amount" in " ".join(duplicate["validation_errors"])
    assert unsupported["stage"] == "invalid_review"
    assert "unsupported review status: approved" in " ".join(
        unsupported["validation_errors"]
    )


def test_execute_dynamic_plan_uses_llm_queries_without_fixed_question_keywords(monkeypatch, tmp_path):
    _seed_document(monkeypatch, tmp_path)
    plan = {
        "claims": [
            {
                "claim_id": "scale",
                "question": "量化公司在目标期间的经营规模",
                "evidence_requirements": ["期间", "单位", "合并口径"],
                "search_queries": ["123,456万元"],
            },
            {
                "claim_id": "transfer",
                "question": "判断履约结果如何进入财务报表",
                "search_queries": [
                    {"query": "客户签收商品并取得控制权", "evidence_type": "accounting_policy"},
                    {"query": "已发生成本占预计总成本", "evidence_type": "accounting_policy"},
                ],
            },
        ]
    }

    result = execute_llm_analysis_plan(
        "这家公司的商业化质量怎么样",
        plan,
        document_id="doc1",
        reconcile=False,
    )

    assert result["stage"] == "evidence_review_required"
    assert [claim["claim_id"] for claim in result["claim_results"]] == ["scale", "transfer"]
    assert result["claim_results"][0]["candidate_coverage"] == "candidates_found"
    assert result["claim_results"][0]["evidence_references"][0]["page_no"] == 4
    assert result["claim_results"][0]["evidence_references"][0]["evidence_id"] == "scale:e1"
    policy_pages = {
        ref["page_no"] for ref in result["claim_results"][1]["evidence_references"]
    }
    assert {19, 20}.issubset(policy_pages)
    assert result["claim_results"][0]["requires_llm_review"] is True


def test_execute_plan_does_not_claim_semantic_sufficiency_from_a_hit(monkeypatch, tmp_path):
    _seed_document(monkeypatch, tmp_path)
    plan = {
        "claims": [
            {
                "claim_id": "amount",
                "question": "确认金额",
                "search_queries": ["营业收入"],
            }
        ]
    }

    result = execute_llm_analysis_plan(
        "金额是多少",
        plan,
        document_id="doc1",
        reconcile=False,
    )

    claim = result["claim_results"][0]
    assert claim["candidate_coverage"] == "candidates_found"
    assert "sufficient" not in claim["candidate_coverage"]
    assert result["stage"] == "evidence_review_required"


def test_continue_analysis_only_runs_llm_requested_gaps(monkeypatch, tmp_path):
    _seed_document(monkeypatch, tmp_path)
    plan = {
        "claims": [
            {"claim_id": "amount", "question": "确认金额", "search_queries": ["营业收入"]},
            {"claim_id": "policy", "question": "确认模式", "search_queries": ["控制权"]},
        ]
    }
    review = {
        "claims": [
            {"claim_id": "amount", "status": "sufficient", "evidence_ids": ["e1"]},
            {
                "claim_id": "policy",
                "status": "partial",
                "gaps": ["缺少进度计量方法"],
                "follow_up_queries": ["已发生成本占预计总成本"],
            },
        ]
    }

    result = continue_llm_analysis(
        "收入表现如何",
        plan,
        review,
        document_id="doc1",
        current_round=1,
        max_rounds=2,
        reconcile=False,
    )

    assert result["stage"] == "follow_up_evidence_review_required"
    assert result["round_no"] == 2
    assert [claim["claim_id"] for claim in result["claim_results"]] == ["policy", "amount"]
    assert result["claim_results"][0]["evidence_references"][0]["page_no"] == 20
    assert result["claim_results"][1]["evidence_references"] == []


def test_continue_analysis_stops_at_round_limit(monkeypatch, tmp_path):
    _seed_document(monkeypatch, tmp_path)

    result = continue_llm_analysis(
        "任意问题",
        {"claims": [{"claim_id": "c1", "question": "待验证结论"}]},
        {
            "claims": [
                {
                    "claim_id": "c1",
                    "status": "insufficient",
                    "follow_up_queries": ["missing disclosure"],
                }
            ]
        },
        document_id="doc1",
        current_round=2,
        max_rounds=2,
        reconcile=False,
    )

    assert result["stage"] == "analysis_complete_with_gaps"
    assert result["semantic_status"] == "insufficient"
    assert "blocked by max_rounds" in " ".join(result["validation_errors"])


def test_invalid_plan_is_rejected_without_search(monkeypatch, tmp_path):
    _seed_document(monkeypatch, tmp_path)

    result = execute_llm_analysis_plan(
        "任意问题",
        {"claims": []},
        document_id="doc1",
        reconcile=False,
    )

    assert result["stage"] == "invalid_plan"
    assert result["claim_results"] == []


def test_biography_intent_ranks_content_rich_page_for_frequent_name(monkeypatch, tmp_path):
    _seed_document(monkeypatch, tmp_path)
    store = SQLiteStore()
    for page_no in range(1, 14):
        store.upsert_page("doc1", page_no, f"Alex Example executive roster item page {page_no}.")
    store.upsert_page(
        "doc1",
        39,
        "Alex Example, aged 45, obtained a master's degree in finance. "
        "Prior to joining the company, Alex worked at an accounting firm and served as finance director.",
    )

    result = execute_llm_analysis_plan(
        "What is the finance leader's professional background?",
        {
            "claims": [
                {
                    "claim_id": "bio",
                    "question": "Retrieve the complete biography and career history",
                    "search_queries": ["Alex Example"],
                }
            ]
        },
        document_id="doc1",
        max_pages_per_claim=1,
        reconcile=False,
    )

    claim = result["claim_results"][0]
    assert claim["search_queries"][0]["evidence_type"] == "biography"
    assert claim["evidence_references"][0]["page_no"] == 39


def test_review_can_expand_full_pages_without_spending_follow_up_round(monkeypatch, tmp_path):
    _seed_document(monkeypatch, tmp_path)
    store = SQLiteStore()
    full_text = "Education continued on this page.\nMaster’s degree in finance and accounting."
    store.upsert_page("doc1", 21, full_text)
    plan = {
        "claims": [
            {"claim_id": "bio", "question": "Retrieve biography", "search_queries": ["Education"]}
        ]
    }
    review = {
        "claims": [
            {
                "claim_id": "bio",
                "status": "partial",
                "gaps": ["education continuation"],
                "expand_pages": [{"page_numbers": [21]}],
            }
        ]
    }

    result = continue_llm_analysis(
        "Who is the finance leader?",
        plan,
        review,
        document_id="doc1",
        current_round=2,
        max_rounds=2,
        reconcile=False,
    )

    assert result["stage"] == "expanded_evidence_review_required"
    assert result["round_no"] == 2
    item = result["claim_results"][0]["evidence_packet"]["evidence_items"][0]
    assert item["source_type"] == "expanded_page"
    assert item["page_no"] == 21
    assert item["text"] == full_text


def test_evidence_text_normalization_handles_pdf_whitespace_and_unicode_punctuation():
    source = "University of International\nBusiness and Economics — Master’s degree"
    expected = "university of international business and economics - master's degree"

    assert normalize_evidence_text(source, casefold=True) == expected


def test_evidence_text_normalization_compacts_cjk_layout_breaks_only_for_matching():
    source = "履约进度按航 次已航行天数占航行总天数确定"

    assert "航次已航行天数" in normalize_evidence_text(source)
    assert normalize_evidence_text("金额 期间", compact_cjk=False) == "金额 期间"


def test_candidates_never_mark_a_claim_answerable_before_llm_review(monkeypatch, tmp_path):
    _seed_document(monkeypatch, tmp_path)

    result = execute_llm_analysis_plan(
        "What is the undisclosed 2027 forecast?",
        {
            "claims": [
                {
                    "claim_id": "forecast",
                    "question": "Verify whether a 2027 forecast is disclosed",
                    "search_queries": ["2027"],
                }
            ]
        },
        document_id="doc1",
        reconcile=False,
    )

    claim = result["claim_results"][0]
    assert claim["answerability"].startswith("unreviewed")
    assert claim["requires_llm_review"] is True
    assert result["semantic_status"] == "unreviewed"


def test_continue_analysis_executes_review_calculations(monkeypatch, tmp_path):
    _seed_document(monkeypatch, tmp_path)
    plan = {
        "claims": [
            {"claim_id": "amount", "question": "确认金额", "search_queries": ["营业收入"]}
        ]
    }
    review = {
        "claims": [
            {"claim_id": "amount", "status": "sufficient", "evidence_ids": ["amount:e1"]}
        ],
        "calculations": [
            {
                "calculation_id": "unit_conversion",
                "expression": "reported * 10000",
                "variables": [
                    {"name": "reported", "value": "123456", "unit": "万元", "evidence_id": "amount:e1"}
                ],
                "expected_value": "1234560000",
                "output_unit": "元",
            }
        ],
    }

    prior = execute_llm_analysis_plan(
        "收入是多少",
        plan,
        document_id="doc1",
        reconcile=False,
    )

    result = continue_llm_analysis(
        "收入是多少",
        plan,
        review,
        document_id="doc1",
        reconcile=False,
        prior_analysis_id=prior["analysis_run_id"],
    )

    assert result["stage"] == "analysis_review_complete"
    assert result["calculation_summary"]["status"] == "verified"
    assert result["calculation_summary"]["provenance_status"] == "checked"


def test_complete_review_requires_the_actual_prior_analysis_result(monkeypatch, tmp_path):
    _seed_document(monkeypatch, tmp_path)
    plan = {"claims": [{"claim_id": "amount", "question": "金额", "search_queries": ["营业收入"]}]}

    result = continue_llm_analysis(
        "金额",
        plan,
        {"claims": [{"claim_id": "amount", "status": "sufficient", "evidence_ids": ["amount:e1"]}]},
        document_id="doc1",
        reconcile=False,
    )

    assert result["stage"] == "analysis_complete_with_gaps"
    assert "prior_analysis_result is required" in " ".join(result["validation_errors"])


def test_review_rejects_fabricated_evidence_ids(monkeypatch, tmp_path):
    _seed_document(monkeypatch, tmp_path)
    plan = {"claims": [{"claim_id": "amount", "question": "金额", "search_queries": ["营业收入"]}]}
    prior = execute_llm_analysis_plan("金额", plan, document_id="doc1", reconcile=False)

    result = continue_llm_analysis(
        "金额",
        plan,
        {
            "claims": [
                {"claim_id": "amount", "status": "sufficient", "evidence_ids": ["amount:e999"]}
            ]
        },
        document_id="doc1",
        reconcile=False,
        prior_analysis_result=prior,
    )

    assert result["stage"] == "analysis_complete_with_gaps"
    assert "not present in prior analysis result" in " ".join(result["validation_errors"])


def test_calculation_discrepancy_blocks_analysis_completion(monkeypatch, tmp_path):
    _seed_document(monkeypatch, tmp_path)
    plan = {"claims": [{"claim_id": "amount", "question": "金额", "search_queries": ["营业收入"]}]}
    prior = execute_llm_analysis_plan("金额", plan, document_id="doc1", reconcile=False)
    result = continue_llm_analysis(
        "金额",
        plan,
        {
            "claims": [
                {"claim_id": "amount", "status": "sufficient", "evidence_ids": ["amount:e1"]}
            ],
            "calculations": [
                {
                    "calculation_id": "bad_tieout",
                    "expression": "reported",
                    "variables": [
                        {"name": "reported", "value": 100, "evidence_id": "amount:e1"}
                    ],
                    "expected_value": 90,
                }
            ],
        },
        document_id="doc1",
        reconcile=False,
        prior_analysis_result=prior,
    )

    assert result["stage"] == "analysis_complete_with_gaps"
    assert result["calculation_summary"]["status"] == "unlinked"
    assert result["calculation_summary"]["results"][0]["arithmetic_status"] == "discrepancy"


def test_execute_plan_supports_explicit_multi_document_scope(monkeypatch, tmp_path):
    _seed_document(monkeypatch, tmp_path)
    store = SQLiteStore()
    store.upsert_document({"document_id": "doc2", "title": "H-share filing"})
    store.upsert_page("doc2", 8, "Revenue was RMB123,456 thousand in 2025.")

    result = execute_llm_analysis_plan(
        "勾稽A股和H股收入",
        {
            "claims": [
                {
                    "claim_id": "cross_listing",
                    "question": "勾稽两份报告的收入",
                    "filters": {"document_ids": ["doc1", "doc2"]},
                    "search_queries": ["123,456"],
                }
            ]
        },
        max_pages_per_claim=6,
        reconcile=False,
    )

    refs = result["claim_results"][0]["evidence_references"]
    assert {ref["document_id"] for ref in refs} == {"doc1", "doc2"}


def test_explicit_document_scope_rejects_other_claim_documents(monkeypatch, tmp_path):
    _seed_document(monkeypatch, tmp_path)

    result = execute_llm_analysis_plan(
        "test scope",
        {
            "claims": [
                {
                    "claim_id": "scope",
                    "question": "scope",
                    "filters": {"document_ids": ["outside_doc"]},
                    "search_queries": ["营业收入"],
                }
            ]
        },
        document_id="doc1",
        reconcile=False,
    )

    assert any("outside the explicitly scoped document" in item for item in result["validation_errors"])
    assert {ref["document_id"] for ref in result["claim_results"][0]["evidence_references"]} == {"doc1"}


def test_total_character_budget_is_fairly_reserved_for_remaining_claims(monkeypatch, tmp_path):
    _seed_document(monkeypatch, tmp_path)
    plan = {
        "claims": [
            {"claim_id": f"claim_{index}", "question": "收入", "search_queries": ["收入"]}
            for index in range(3)
        ]
    }

    result = execute_llm_analysis_plan(
        "分析收入",
        plan,
        document_id="doc1",
        max_chars_per_claim=1000,
        max_total_chars=1200,
        reconcile=False,
    )

    assert result["budget"]["allocation_strategy"] == "fair_share_remaining_claims"
    allocations = [item["budget_allocation"]["allocated_chars"] for item in result["claim_results"]]
    assert allocations[0] == 400
    assert all(value > 0 for value in allocations)
    assert sum(item["budget_allocation"]["used_chars"] for item in result["claim_results"]) <= 1200
    assert all(item["candidate_coverage"] != "budget_exhausted" for item in result["claim_results"])


def test_page_expansion_preserves_prior_evidence_ids(monkeypatch, tmp_path):
    _seed_document(monkeypatch, tmp_path)
    plan = {"claims": [{"claim_id": "amount", "question": "金额", "search_queries": ["营业收入"]}]}
    prior = execute_llm_analysis_plan("金额", plan, document_id="doc1", reconcile=False)
    prior_ref = prior["claim_results"][0]["evidence_references"][0]

    result = continue_llm_analysis(
        "金额",
        plan,
        {
            "claims": [
                {
                    "claim_id": "amount",
                    "status": "partial",
                    "evidence_ids": [prior_ref["evidence_id"]],
                    "gaps": ["需要政策页"],
                    "expand_pages": [{"document_id": "doc1", "page_numbers": [19]}],
                }
            ]
        },
        document_id="doc1",
        prior_analysis_id=prior["analysis_run_id"],
        reconcile=False,
    )

    refs = result["claim_results"][0]["evidence_references"]
    by_page = {ref["page_no"]: ref["evidence_id"] for ref in refs}
    assert by_page[prior_ref["page_no"]] == prior_ref["evidence_id"]
    assert by_page[19] != prior_ref["evidence_id"]


def test_sufficient_review_with_gaps_is_blocked(monkeypatch, tmp_path):
    _seed_document(monkeypatch, tmp_path)
    plan = {"claims": [{"claim_id": "amount", "question": "金额", "search_queries": ["营业收入"]}]}
    prior = execute_llm_analysis_plan("金额", plan, document_id="doc1", reconcile=False)
    evidence_id = prior["claim_results"][0]["evidence_references"][0]["evidence_id"]

    result = continue_llm_analysis(
        "金额",
        plan,
        {
            "claims": [
                {
                    "claim_id": "amount",
                    "status": "sufficient",
                    "evidence_ids": [evidence_id],
                    "gaps": ["期间尚未确认"],
                }
            ]
        },
        document_id="doc1",
        prior_analysis_id=prior["analysis_run_id"],
        reconcile=False,
    )

    assert result["stage"] == "analysis_complete_with_gaps"
    assert "cannot contain unresolved gaps" in " ".join(result["validation_errors"])


def test_evidence_facts_detect_cross_page_numeric_conflict(monkeypatch, tmp_path):
    _seed_document(monkeypatch, tmp_path)
    plan = {"claims": [{"claim_id": "revenue", "question": "收入", "search_queries": ["收入"]}]}
    prior = execute_llm_analysis_plan(
        "收入",
        plan,
        document_id="doc1",
        max_pages_per_claim=3,
        reconcile=False,
    )
    evidence_ids = [
        ref["evidence_id"] for ref in prior["claim_results"][0]["evidence_references"]
    ]
    assert len(evidence_ids) >= 2

    result = continue_llm_analysis(
        "收入",
        plan,
        {
            "claims": [
                {
                    "claim_id": "revenue",
                    "status": "sufficient",
                    "evidence_ids": evidence_ids,
                    "evidence_facts": [
                        {"fact_key": "revenue", "value": 123456, "period": "2025 FY", "unit": "万元", "scope": "consolidated", "evidence_id": evidence_ids[0]},
                        {"fact_key": "revenue", "value": 123455, "period": "2025 FY", "unit": "万元", "scope": "consolidated", "evidence_id": evidence_ids[1]},
                    ],
                }
            ]
        },
        document_id="doc1",
        prior_analysis_id=prior["analysis_run_id"],
        reconcile=False,
    )

    assert result["stage"] == "analysis_complete_with_gaps"
    assert result["detected_conflicts"][0]["fact_key"] == "revenue"


def test_evidence_facts_do_not_conflict_across_different_periods(monkeypatch, tmp_path):
    _seed_document(monkeypatch, tmp_path)
    plan = {"claims": [{"claim_id": "revenue", "question": "收入", "search_queries": ["收入"]}]}
    prior = execute_llm_analysis_plan(
        "收入",
        plan,
        document_id="doc1",
        max_pages_per_claim=3,
        reconcile=False,
    )
    evidence_ids = [
        ref["evidence_id"] for ref in prior["claim_results"][0]["evidence_references"]
    ]

    result = continue_llm_analysis(
        "收入",
        plan,
        {
            "claims": [
                {
                    "claim_id": "revenue",
                    "status": "sufficient",
                    "evidence_ids": evidence_ids,
                    "evidence_facts": [
                        {"fact_key": "revenue", "value": 123456, "period": "2025 FY", "unit": "万元", "scope": "consolidated", "evidence_id": evidence_ids[0]},
                        {"fact_key": "revenue", "value": 100000, "period": "2024 FY", "unit": "万元", "scope": "consolidated", "evidence_id": evidence_ids[1]},
                    ],
                }
            ]
        },
        document_id="doc1",
        prior_analysis_id=prior["analysis_run_id"],
        reconcile=False,
    )

    assert result["stage"] == "analysis_review_complete"
    assert "detected_conflicts" not in result


def test_dependency_cycle_has_no_executable_review_units(monkeypatch, tmp_path):
    _seed_document(monkeypatch, tmp_path)
    result = execute_llm_analysis_plan(
        "循环依赖",
        {
            "claims": [
                {"claim_id": "a", "question": "A", "depends_on_claim_ids": ["b"]},
                {"claim_id": "b", "question": "B", "depends_on_claim_ids": ["a"]},
            ]
        },
        document_id="doc1",
        reconcile=False,
    )

    assert result["stage"] == "invalid_plan"
    assert result["claim_results"] == []
    assert result["orchestration"]["review_batches"] == []
    assert result["orchestration"]["cycle_claim_ids"] == ["a", "b"]
    assert any("dependency cycle" in error for error in result["validation_errors"])


def test_analysis_run_id_rejects_query_plan_and_scope_mismatches(monkeypatch, tmp_path):
    _seed_document(monkeypatch, tmp_path)
    plan = {
        "claims": [
            {"claim_id": "amount", "question": "金额", "search_queries": ["营业收入"]}
        ]
    }
    prior = execute_llm_analysis_plan("金额", plan, document_id="doc1", reconcile=False)
    review = {
        "claims": [
            {"claim_id": "amount", "status": "sufficient", "evidence_ids": ["amount:e1"]}
        ]
    }

    mismatches = [
        ("另一个问题", plan, "doc1"),
        (
            "金额",
            {"claims": [{"claim_id": "amount", "question": "不同计划"}]},
            "doc1",
        ),
        ("金额", plan, "another-document"),
    ]
    for query, candidate_plan, document_id in mismatches:
        result = continue_llm_analysis(
            query,
            candidate_plan,
            review,
            document_id=document_id,
            reconcile=False,
            prior_analysis_id=prior["analysis_run_id"],
        )
        assert result["stage"] == "invalid_analysis_context"
        assert "does not match" in " ".join(result["validation_errors"])


def test_expired_run_id_accepts_matching_result_fallback(monkeypatch, tmp_path):
    import ah_disclosure.services.analysis_registry as registry

    _seed_document(monkeypatch, tmp_path)
    plan = {
        "claims": [
            {"claim_id": "amount", "question": "金额", "search_queries": ["营业收入"]}
        ]
    }
    prior = execute_llm_analysis_plan("金额", plan, document_id="doc1", reconcile=False)
    with registry._LOCK:
        registry._RUNS.clear()
        registry._TOTAL_BYTES = 0

    result = continue_llm_analysis(
        "金额",
        plan,
        {
            "claims": [
                {"claim_id": "amount", "status": "sufficient", "evidence_ids": ["amount:e1"]}
            ]
        },
        document_id="doc1",
        reconcile=False,
        prior_analysis_id=prior["analysis_run_id"],
        prior_analysis_result=prior,
    )

    assert result["stage"] == "analysis_review_complete"
    assert "unknown or expired" not in " ".join(result["validation_errors"])


def test_analysis_registry_enforces_context_and_total_byte_limits(monkeypatch):
    import ah_disclosure.services.analysis_registry as registry

    monkeypatch.setattr(registry, "_MAX_CONTEXT_BYTES", 64)
    monkeypatch.setattr(registry, "_MAX_REGISTRY_BYTES", 128)
    monkeypatch.setattr(registry, "_MAX_EVIDENCE_TEXT_BYTES", 64)
    with registry._LOCK:
        registry._RUNS.clear()
        registry._TOTAL_BYTES = 0

    run_ids = [
        registry.register_analysis_context(
            {"claim": {f"evidence-{index}"}},
            {f"evidence-{index}": "数" * 200},
            context_fingerprint=f"fingerprint-{index}",
        )
        for index in range(3)
    ]

    assert registry._TOTAL_BYTES <= registry._MAX_REGISTRY_BYTES
    assert len(registry._RUNS) <= 2
    latest = registry.get_analysis_context(run_ids[-1])
    assert latest is not None
    assert len(next(iter(latest[1].values())).encode("utf-8")) <= 64


def test_page_expansion_respects_zero_page_budget(monkeypatch, tmp_path):
    _seed_document(monkeypatch, tmp_path)
    plan = {
        "claims": [
            {"claim_id": "amount", "question": "金额", "search_queries": ["营业收入"]}
        ]
    }
    prior = execute_llm_analysis_plan("金额", plan, document_id="doc1", reconcile=False)

    result = continue_llm_analysis(
        "金额",
        plan,
        {
            "claims": [
                {
                    "claim_id": "amount",
                    "status": "partial",
                    "evidence_ids": ["amount:e1"],
                    "expand_pages": [4],
                }
            ]
        },
        document_id="doc1",
        max_pages_per_claim=0,
        reconcile=False,
        prior_analysis_id=prior["analysis_run_id"],
    )

    assert result["stage"] == "analysis_complete_with_gaps"
    assert "blocked by max_pages_per_claim=0" in " ".join(result["validation_errors"])


def test_follow_up_registry_keeps_all_claims_for_cross_claim_calculation(
    monkeypatch, tmp_path
):
    _seed_document(monkeypatch, tmp_path)
    plan = {
        "claims": [
            {"claim_id": "left", "question": "左值", "search_queries": ["营业收入"]},
            {"claim_id": "right", "question": "右值", "search_queries": ["营业收入"]},
        ]
    }
    prior = execute_llm_analysis_plan("合计", plan, document_id="doc1", reconcile=False)
    follow_up = continue_llm_analysis(
        "合计",
        plan,
        {
            "claims": [
                {"claim_id": "left", "status": "sufficient", "evidence_ids": ["left:e1"]},
                {
                    "claim_id": "right",
                    "status": "partial",
                    "evidence_ids": ["right:e1"],
                    "follow_up_queries": ["人民币万元"],
                },
            ]
        },
        document_id="doc1",
        reconcile=False,
        prior_analysis_id=prior["analysis_run_id"],
    )
    assert {item["claim_id"] for item in follow_up["claim_results"]} == {"left", "right"}

    completed = continue_llm_analysis(
        "合计",
        plan,
        {
            "claims": [
                {"claim_id": "left", "status": "sufficient", "evidence_ids": ["left:e1"]},
                {"claim_id": "right", "status": "sufficient", "evidence_ids": ["right:e1"]},
            ],
            "calculations": [
                {
                    "calculation_id": "cross_claim_total",
                    "expression": "left_value + right_value",
                    "variables": [
                        {"name": "left_value", "value": 123456, "evidence_id": "left:e1"},
                        {"name": "right_value", "value": 123456, "evidence_id": "right:e1"},
                    ],
                    "expected_value": 246912,
                }
            ],
        },
        document_id="doc1",
        reconcile=False,
        prior_analysis_id=follow_up["analysis_run_id"],
        current_round=2,
    )

    assert completed["stage"] == "analysis_review_complete"
    assert completed["calculation_summary"]["status"] == "verified"


def test_evidence_packet_includes_bounded_table_structure(monkeypatch, tmp_path):
    _seed_document(monkeypatch, tmp_path)
    structure_path = tmp_path / "table.json"
    structure_path.write_text(
        json.dumps(
            {
                "header_depth": 2,
                "confidence": 0.9,
                "column_paths": [["2025", "金额"], ["2024", "金额"]],
                "raw_rows": [["2025", "2024"], ["金额", "金额"], [123, 100]],
                "row_count": 3,
                "column_count": 2,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    SQLiteStore().replace_document_tables(
        "doc1",
        [
            {
                "page_no": 4,
                "table_index": 1,
                "table_path": str(tmp_path / "table.csv"),
                "structure_path": str(structure_path),
                "quality_flags": ["header_inferred"],
            }
        ],
    )

    result = execute_llm_analysis_plan(
        "收入",
        {"claims": [{"claim_id": "amount", "question": "收入", "search_queries": ["营业收入"]}]},
        document_id="doc1",
        reconcile=False,
    )

    item = result["claim_results"][0]["evidence_packet"]["evidence_items"][0]
    assert item["structured_payload"]["tables"][0]["header_depth"] == 2
    assert item["structured_payload"]["tables"][0]["column_paths"][0] == ["2025", "金额"]
