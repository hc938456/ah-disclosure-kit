from ah_disclosure.services import prospectus_service


def test_h_prospectus_requires_symbol_or_hkex_stock_id():
    rows = prospectus_service.search_prospectus("H", company_keyword="美团")

    assert rows[0]["error"] == "H prospectus search requires symbol or hkex_stock_id."
    assert "03690" in rows[0]["hint"]


def test_h_prospectus_stops_after_high_confidence_listing_keyword(monkeypatch):
    calls = []

    def fake_search_h_filings(
        symbol,
        hkex_stock_id=None,
        title_keyword="",
        max_rows=20,
        verify=True,
        lang="EN",
        **kwargs,
    ):
        calls.append(title_keyword)
        if title_keyword == "Global Offering":
            return [{"title": "GLOBAL OFFERING", "pdf_url": "https://example.com/meituan.pdf"}]
        return []

    monkeypatch.setattr(prospectus_service, "search_h_filings", fake_search_h_filings)

    rows = prospectus_service.search_prospectus("H", symbol="03690", max_rows=3)

    assert rows == [{"title": "GLOBAL OFFERING", "pdf_url": "https://example.com/meituan.pdf"}]
    assert calls == ["Global Offering"]


def test_h_prospectus_uses_traditional_chinese_keyword_first(monkeypatch):
    calls = []

    def fake_search_h_filings(symbol, title_keyword="", **kwargs):
        calls.append(title_keyword)
        if title_keyword == "全球發售":
            return [
                {
                    "title": "全球發售",
                    "category": "上市文件 - [發售以供認購]",
                    "pdf_url": "https://example.com/prospectus_c.pdf",
                },
                {
                    "title": "全球發售",
                    "category": "公告及通告 - [正式通告]",
                    "pdf_url": "https://example.com/formal-notice_c.pdf",
                },
            ]
        return []

    monkeypatch.setattr(prospectus_service, "search_h_filings", fake_search_h_filings)

    rows = prospectus_service.search_h_prospectus(
        symbol="02475", lang="ZH", max_rows=5
    )

    assert calls == ["全球發售"]
    assert rows[0]["pdf_url"].endswith("prospectus_c.pdf")
    assert rows[1]["pdf_url"].endswith("formal-notice_c.pdf")


def test_h_prospectus_finds_introduction_listing_package(monkeypatch):
    calls = []

    def fake_search_h_filings(symbol, title_keyword="", **kwargs):
        calls.append(title_keyword)
        if title_keyword == "Introduction":
            return [
                {
                    "title": "LISTING BY WAY OF INTRODUCTION",
                    "category": "Listing Documents - [Introduction]",
                    "detail_url": "https://www1.hkexnews.hk/example/listing.htm",
                }
            ]
        return []

    monkeypatch.setattr(prospectus_service, "search_h_filings", fake_search_h_filings)

    rows = prospectus_service.search_h_prospectus(symbol="09866", max_rows=5)

    assert "Introduction" in calls
    assert rows[0]["detail_url"].endswith("listing.htm")


def test_historical_h_prospectus_queries_only_historical_category(monkeypatch):
    categories = []

    def fake_search_h_filings(symbol, title_keyword="", category="0", **kwargs):
        categories.append(category)
        if category == "1" and title_keyword == "Offering":
            return [
                {
                    "title": "OFFERING OF CLASS A SHARES",
                    "category": "Listing Documents - [Offer for Subscription]",
                    "pdf_url": "https://example.com/aquila.pdf",
                }
            ]
        return []

    monkeypatch.setattr(prospectus_service, "search_h_filings", fake_search_h_filings)

    rows = prospectus_service.search_h_prospectus(symbol="07836", max_rows=5)

    assert categories
    assert set(categories) == {"1"}
    assert rows[0]["pdf_url"].endswith("aquila.pdf")


def test_a_prospectus_falls_back_to_ipo_registry_with_company_name(monkeypatch):
    monkeypatch.setattr(
        prospectus_service,
        "search_a_listed_company_prospectus",
        lambda *args, **kwargs: [],
    )
    captured = {}

    def fake_ipo(**kwargs):
        captured.update(kwargs)
        return [{"title": "锦波生物 招股说明书", "pdf_url": "https://example.com/ipo.pdf"}]

    monkeypatch.setattr(prospectus_service, "search_a_ipo_prospectus", fake_ipo)

    rows = prospectus_service.search_prospectus(
        "A", symbol="832982", company_keyword="锦波生物"
    )

    assert rows[0]["pdf_url"].endswith("ipo.pdf")
    assert captured["symbol"] == "832982"
    assert captured["board"] == "bj"


def test_a_ipo_publish_date_is_normalized_for_document_naming(monkeypatch):
    class Record:
        def to_dict(self):
            return {
                "title": "测试公司 招股说明书",
                "publish_date": "2023-07-27 00:00:00",
            }

    monkeypatch.setattr(
        prospectus_service.EastmoneyIpoClient,
        "search_ipo_prospectus",
        lambda *args, **kwargs: [Record()],
    )

    rows = prospectus_service.search_a_ipo_prospectus(company_keyword="测试公司")

    assert rows[0]["publish_time"] == "2023-07-27 00:00:00"


def test_a_offering_search_reports_source_errors_when_all_categories_fail(monkeypatch):
    monkeypatch.setattr(
        prospectus_service,
        "search_a_filings",
        lambda **kwargs: (_ for _ in ()).throw(TimeoutError("CNINFO timeout")),
    )

    rows = prospectus_service.search_a_offering_documents("000001")

    assert rows
    assert rows[0]["source"] == "CNINFO"
    assert rows[0]["category"] == "可转债"
    assert "TimeoutError" in rows[0]["error"]
