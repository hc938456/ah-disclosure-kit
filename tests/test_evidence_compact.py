from ah_disclosure.services.evidence_service import get_evidence_packet
from ah_disclosure.services.local_search_service import LocalSearchService
from ah_disclosure.storage.sqlite_store import SQLiteStore


def test_planned_evidence_packet_uses_compact_plan_by_default(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    store = SQLiteStore()
    store.upsert_document({"document_id": "doc1", "title": "Doc 1"})
    store.upsert_page("doc1", 1, "management discussion and analysis revenue net profit")

    packet = get_evidence_packet(
        "Revenue net profit",
        document_id="doc1",
        strategy="financial_analysis",
        include_structured_data=False,
    )
    debug_packet = get_evidence_packet(
        "Revenue net profit",
        document_id="doc1",
        strategy="financial_analysis",
        include_structured_data=False,
        include_retrieval_plan=True,
    )

    assert "search_query_count" in packet["retrieval_plan"]
    assert "search_queries" not in packet["retrieval_plan"]
    assert "search_queries" in debug_packet["retrieval_plan"]


def test_default_evidence_strategy_auto_selects_accounting_policy(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    store = SQLiteStore()
    store.upsert_document({"document_id": "doc1", "title": "Doc 1"})
    store.upsert_page("doc1", 1, "Revenue recognition is described in significant accounting policies.")

    packet = get_evidence_packet(
        "收入确认政策",
        document_id="doc1",
        include_structured_data=False,
    )

    assert packet["strategy"] == "accounting_policy"


def test_auto_strategy_prioritizes_accounting_policy_when_financial_terms_overlap(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    store = SQLiteStore()
    store.upsert_document({"document_id": "doc1", "title": "Doc 1"})
    store.upsert_page("doc1", 1, "Profit recognition is described in accounting policies.")

    packet = get_evidence_packet(
        "利润确认政策",
        document_id="doc1",
        include_structured_data=False,
    )

    assert packet["strategy"] == "accounting_policy"


def test_auto_strategy_keeps_fpa_driver_questions_financial(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    store = SQLiteStore()
    store.upsert_document({"document_id": "doc1", "title": "Doc 1"})
    store.upsert_page("doc1", 1, "Management discussion and analysis revenue driver margin.")

    packet = get_evidence_packet(
        "FP&A收入驱动分析",
        document_id="doc1",
        include_structured_data=False,
    )

    assert packet["strategy"] == "financial_analysis"


def test_structured_payload_tokens_are_included(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    store = SQLiteStore()
    store.upsert_document({"document_id": "doc1", "title": "Doc 1"})
    store.upsert_page("doc1", 1, "Revenue and net profit.")
    structured = {"rows": [{"metric": "revenue", "value": "x" * 900}]}

    packet = LocalSearchService().evidence_packet(
        "revenue",
        document_id="doc1",
        structured_data=structured,
        strategy="basic",
    )

    structured_tokens = packet["evidence_items"][0]["token_estimate"]
    assert packet["token_estimate"] >= structured_tokens
