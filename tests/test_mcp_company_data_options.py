from ah_disclosure import mcp_server


def test_financial_indicator_tool_forwards_a_share_start_year(monkeypatch):
    captured = {}

    def fake_get_financial_indicators(market, symbol, **params):
        captured.update({"market": market, "symbol": symbol, **params})
        return {"ok": True}

    monkeypatch.setattr(
        mcp_server,
        "get_financial_indicators",
        fake_get_financial_indicators,
    )

    result = mcp_server.get_financial_indicators_tool(
        "A",
        "600519",
        max_rows=20,
        start_year="2025",
    )

    assert result == {"ok": True}
    assert captured == {
        "market": "A",
        "symbol": "600519",
        "max_rows": 20,
        "start_year": "2025",
    }


def test_shareholder_tool_forwards_top_holder_date(monkeypatch):
    captured = {}

    def fake_get_shareholders(market, symbol, **params):
        captured.update({"market": market, "symbol": symbol, **params})
        return {"ok": True}

    monkeypatch.setattr(mcp_server, "get_shareholders", fake_get_shareholders)

    result = mcp_server.get_shareholders_tool(
        "A",
        "600519",
        data_type="top_float_shareholders",
        max_rows=10,
        date="20250331",
    )

    assert result == {"ok": True}
    assert captured == {
        "market": "A",
        "symbol": "600519",
        "data_type": "top_float_shareholders",
        "max_rows": 10,
        "date": "20250331",
    }
