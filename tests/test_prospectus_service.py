from ah_disclosure.services import prospectus_service


def test_h_prospectus_requires_symbol_or_hkex_stock_id():
    rows = prospectus_service.search_prospectus("H", company_keyword="美团")

    assert rows[0]["error"] == "H prospectus search requires symbol or hkex_stock_id."
    assert "03690" in rows[0]["hint"]


def test_h_prospectus_searches_multiple_listing_keywords(monkeypatch):
    calls = []

    def fake_search_h_filings(symbol, hkex_stock_id=None, title_keyword="", max_rows=20, verify=True, lang="EN"):
        calls.append(title_keyword)
        if title_keyword == "Global Offering":
            return [{"title": "GLOBAL OFFERING", "pdf_url": "https://example.com/meituan.pdf"}]
        return []

    monkeypatch.setattr(prospectus_service, "search_h_filings", fake_search_h_filings)

    rows = prospectus_service.search_prospectus("H", symbol="03690", max_rows=3)

    assert rows == [{"title": "GLOBAL OFFERING", "pdf_url": "https://example.com/meituan.pdf"}]
    assert "Global Offering" in calls
    assert "Prospectus" in calls
