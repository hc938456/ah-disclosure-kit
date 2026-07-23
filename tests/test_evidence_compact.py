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


def test_auto_strategy_uses_bilingual_business_segment_queries(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(data_dir))
    parsed_dir = data_dir / "parsed" / "doc1"
    parsed_dir.mkdir(parents=True)
    (parsed_dir / "pages.jsonl").write_text("", encoding="utf-8")
    pdf_path = data_dir / "raw" / "doc1.pdf"
    pdf_path.parent.mkdir(parents=True)
    pdf_path.write_bytes(b"%PDF placeholder")
    store = SQLiteStore()
    store.upsert_document(
        {"document_id": "doc1", "title": "Doc 1", "local_pdf_path": str(pdf_path)}
    )
    store.upsert_page("doc1", 8, "主营业务分产品：运输服务、仓储服务及其他服务。")

    packet = get_evidence_packet(
        "这家公司有几种收入模式，主要收入来源和业务分部是什么",
        document_id="doc1",
        include_structured_data=False,
    )

    assert packet["strategy"] == "financial_analysis"
    assert packet["evidence_items"][0]["page_no"] == 8


def test_auto_strategy_supports_traditional_chinese_filing_terms(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(data_dir))
    parsed_dir = data_dir / "parsed" / "doc1"
    parsed_dir.mkdir(parents=True)
    (parsed_dir / "pages.jsonl").write_text("", encoding="utf-8")
    pdf_path = data_dir / "raw" / "doc1.pdf"
    pdf_path.parent.mkdir(parents=True)
    pdf_path.write_bytes(b"%PDF placeholder")
    store = SQLiteStore()
    store.upsert_document(
        {"document_id": "doc1", "title": "Doc 1", "local_pdf_path": str(pdf_path)}
    )
    store.upsert_page("doc1", 9, "收入分拆及主要產品及服務詳情如下。")

    packet = get_evidence_packet(
        "公司的收入模式及業務分部",
        document_id="doc1",
        include_structured_data=False,
    )

    assert packet["strategy"] == "financial_analysis"
    assert packet["evidence_items"][0]["page_no"] == 9


def test_financial_queries_do_not_contain_company_specific_terms(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(data_dir))
    parsed_dir = data_dir / "parsed" / "doc1"
    parsed_dir.mkdir(parents=True)
    (parsed_dir / "pages.jsonl").write_text("", encoding="utf-8")
    pdf_path = data_dir / "raw" / "doc1.pdf"
    pdf_path.parent.mkdir(parents=True)
    pdf_path.write_bytes(b"%PDF placeholder")
    store = SQLiteStore()
    store.upsert_document(
        {"document_id": "doc1", "title": "Doc 1", "local_pdf_path": str(pdf_path)}
    )
    store.upsert_page("doc1", 4, "Reportable segments and disaggregation of revenue.")

    packet = get_evidence_packet(
        "revenue model and reportable segments",
        document_id="doc1",
        include_structured_data=False,
        include_retrieval_plan=True,
    )
    queries = [item["query"].casefold() for item in packet["retrieval_plan"]["search_queries"]]

    assert packet["strategy"] == "financial_analysis"
    assert "core local commerce" not in queries
    assert "reportable segments" in queries
    assert "expenses by nature" not in queries
    assert "cost of revenues" not in queries


def test_financial_evidence_reserves_a_slot_for_the_exact_user_query(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    store = SQLiteStore()
    store.upsert_document({"document_id": "doc1", "title": "Doc 1"})
    store.upsert_page("doc1", 1, "主营业务分产品：产品概览。")
    store.upsert_page("doc1", 2, "营业收入分产品：业务介绍。")
    store.upsert_page(
        "doc1",
        20,
        "2023年度 传输类产品 144471.46 音视频类产品 94987.60 充电类产品 155718.17",
    )

    packet = get_evidence_packet(
        "2023年度 传输类产品 音视频类产品 充电类产品",
        document_id="doc1",
        include_structured_data=False,
        strategy="financial_analysis",
        max_pages=2,
        reconcile=False,
    )

    assert packet["evidence_items"][0]["page_no"] == 20
    assert "user_query" in packet["evidence_items"][0]["section_title"]


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
