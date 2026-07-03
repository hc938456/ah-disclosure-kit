from ah_disclosure.services import disclosure_service


def test_h_filing_language_is_passed_to_hkex_client(monkeypatch):
    calls = {}

    class FakeHkexClient:
        def search_filings(self, stock_id, hk_code=None, title_keyword="", max_rows=20, lang="EN"):
            calls["lang"] = lang
            calls["title_keyword"] = title_keyword
            return []

    monkeypatch.setattr(
        disclosure_service,
        "resolve_hkex_stock_id",
        lambda *args, **kwargs: {"hkex_stock_id": "12345", "symbol": "00700"},
    )
    monkeypatch.setattr(disclosure_service, "HkexClient", FakeHkexClient)

    disclosure_service.search_h_filings("00700", title_keyword="年報", lang="ZH")

    assert calls["lang"] == "ZH"
    assert calls["title_keyword"] == "年報"
