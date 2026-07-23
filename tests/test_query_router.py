from ah_disclosure.services.query_router import route_query


def test_accounting_policy_question_uses_local_evidence_before_financials():
    route = route_query("招商证券年报里的收入确认政策")

    assert route["route"] == "local_document_evidence"
    assert route["llm_required"] is True


def test_plain_revenue_profit_question_still_uses_structured_financials():
    route = route_query("腾讯2025年收入和净利润")

    assert route["route"] == "structured_financials"
    assert route["llm_required"] is False


def test_revenue_model_question_uses_annual_report_evidence():
    route = route_query("这家公司有几种收入模式，主要收入来源和业务分部是什么")

    assert route["route"] == "local_document_evidence"
    assert route["llm_required"] is True


def test_prospectus_question_wins_over_accounting_keyword():
    route = route_query("美团招股书里的会计师是谁")

    assert route["route"] == "prospectus_search_download_ingest"
    assert route["llm_required"] is False


def test_download_financial_report_uses_filing_route():
    route = route_query("下载阿里巴巴24年财报H股")

    assert route["route"] == "filing_search_download_ingest"
    assert route["llm_required"] is False


def test_hk_ipo_annual_list_is_explicitly_unsupported():
    route = route_query("2026年至今港股新增IPO上市公司list")

    assert route["route"] == "unsupported_hk_ipo_annual_list"
    assert route["llm_required"] is True


def test_single_company_hk_ipo_prospectus_is_not_unsupported():
    route = route_query("美团港股IPO招股书")

    assert route["route"] == "prospectus_search_download_ingest"
    assert route["llm_required"] is False
