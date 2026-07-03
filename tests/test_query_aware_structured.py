from ah_disclosure.services import dossier_service, evidence_service


def test_financial_evidence_packet_uses_income_statement(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    calls = {"income": 0}

    def fake_financials(market, symbol, statement="all", **params):
        calls["income"] += 1
        return {"market": market, "symbol": symbol, "statement": statement, "rows": [{"收入": 123, "净利润": 45}]}

    monkeypatch.setattr(evidence_service, "get_financial_statements", fake_financials)

    packet = evidence_service.get_evidence_packet("腾讯2025年收入和净利润", market="H", symbol="00700")
    payload = packet["evidence_items"][0]["structured_payload"]

    assert calls["income"] == 1
    assert "income_statement" in payload
    assert payload["income_statement"]["statement"] == "income"


def test_financial_evidence_packet_uses_requested_statement(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    calls = []

    def fake_financials(market, symbol, statement="all", **params):
        calls.append(statement)
        return {"market": market, "symbol": symbol, "statement": statement, "rows": []}

    monkeypatch.setattr(evidence_service, "get_financial_statements", fake_financials)

    balance_packet = evidence_service.get_evidence_packet("腾讯资产负债表", market="H", symbol="00700")
    cashflow_packet = evidence_service.get_evidence_packet("腾讯现金流量表", market="H", symbol="00700")

    balance_payload = balance_packet["evidence_items"][0]["structured_payload"]
    cashflow_payload = cashflow_packet["evidence_items"][0]["structured_payload"]
    assert calls == ["balance", "cashflow"]
    assert balance_payload["balance_sheet"]["statement"] == "balance"
    assert cashflow_payload["cashflow_statement"]["statement"] == "cashflow"


def test_dossier_is_query_aware_for_financial_question(monkeypatch):
    calls = {"income": 0, "indicators": 0, "dividends": 0}

    def fake_financials(market, symbol, **params):
        calls["income"] += 1
        return {"rows": [{"收入": 123}]}

    def fake_indicators(market, symbol, **params):
        calls["indicators"] += 1
        return {"rows": [{"ROE": 1.2}]}

    def fake_dividends(market, symbol, **params):
        calls["dividends"] += 1
        return {"rows": [{"dividend": 1}]}

    monkeypatch.setattr(dossier_service, "get_financial_statements", fake_financials)
    monkeypatch.setattr(dossier_service, "get_financial_indicators", fake_indicators)
    monkeypatch.setattr(dossier_service, "get_dividends", fake_dividends)
    monkeypatch.setattr(dossier_service, "get_evidence_packet", lambda *args, **kwargs: {"evidence_items": []})

    dossier = dossier_service.build_company_dossier("H", "00700", "腾讯2025年收入和净利润")

    assert "income_statement" in dossier
    assert "financial_indicators" in dossier
    assert "dividends" not in dossier
    assert calls == {"income": 1, "indicators": 1, "dividends": 0}


def test_dossier_uses_requested_financial_statement(monkeypatch):
    calls = []

    def fake_financials(market, symbol, **params):
        calls.append(params.get("statement"))
        return {"rows": []}

    monkeypatch.setattr(dossier_service, "get_financial_statements", fake_financials)
    monkeypatch.setattr(dossier_service, "get_financial_indicators", lambda *args, **kwargs: {"rows": []})
    monkeypatch.setattr(dossier_service, "get_evidence_packet", lambda *args, **kwargs: {"evidence_items": []})

    dossier = dossier_service.build_company_dossier("H", "00700", "腾讯现金流量表")

    assert "cashflow_statement" in dossier
    assert "income_statement" not in dossier
    assert calls == ["cashflow"]
