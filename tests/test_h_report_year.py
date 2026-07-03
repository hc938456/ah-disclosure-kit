from ah_disclosure.services import disclosure_service


def test_h_annual_report_year_must_match(monkeypatch):
    rows = [
        {
            "market": "H",
            "symbol": "00700",
            "title": "2024 Annual Report",
            "detail_url": "https://example.com/2024.pdf",
            "pdf_url": "https://example.com/2024.pdf",
        }
    ]

    monkeypatch.setattr(disclosure_service, "search_h_filings", lambda *args, **kwargs: rows)

    assert disclosure_service.search_h_annual_report("00700", report_year=2025) == []
    result = disclosure_service.download_and_ingest_h_report("00700", report_year=2025)
    assert result["ok"] is False
    assert "2025" in result["error"]
