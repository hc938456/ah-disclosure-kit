from scripts.run_qa_acceptance import _claim_plan, _evaluate_case


def test_claim_plan_preserves_worker_fields_and_claim_document_scope():
    case = {
        "document_ids": ["doc-a", "doc-h"],
        "claims": [
            {
                "claim_id": "a_only",
                "question": "A evidence",
                "queries": ["query"],
                "document_ids": ["doc-a"],
                "depends_on_claim_ids": ["seed"],
                "review_role": "cross_document_reviewer",
                "worker_preference": "parallel_worker",
            }
        ],
    }

    claim = _claim_plan(case)["claims"][0]

    assert claim["filters"]["document_ids"] == ["doc-a"]
    assert claim["depends_on_claim_ids"] == ["seed"]
    assert claim["review_role"] == "cross_document_reviewer"
    assert claim["worker_preference"] == "parallel_worker"


def test_evaluate_case_checks_required_documents_per_claim():
    case = {
        "case_id": "cross_doc",
        "category": "cross_document",
        "document_ids": ["doc-a", "doc-h"],
        "require_all_documents": True,
        "claims": [
            {
                "claim_id": "a_and_h",
                "question": "compare",
                "queries": ["revenue"],
                "expected_groups": [["revenue"]],
                "require_documents": ["doc-a", "doc-h"],
            },
            {
                "claim_id": "h_only",
                "question": "H evidence",
                "queries": ["cash"],
                "expected_groups": [["cash"]],
            },
        ],
    }
    payload = {
        "stage": "evidence_review_required",
        "analysis_run_id": "run",
        "claim_results": [
            {
                "claim_id": "a_and_h",
                "evidence_packet": {
                    "evidence_items": [
                        {"document_id": "doc-a", "page_no": 1, "text": "revenue"}
                    ]
                },
            },
            {
                "claim_id": "h_only",
                "evidence_packet": {
                    "evidence_items": [
                        {"document_id": "doc-h", "page_no": 2, "text": "cash"}
                    ]
                },
            },
        ],
    }

    result = _evaluate_case(case, payload, 0.1)

    assert result["status"] == "failed"
    assert any(
        "a_and_h: required documents missing: ['doc-h']" in failure
        for failure in result["failures"]
    )
