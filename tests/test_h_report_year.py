from ah_disclosure.services import disclosure_service


def test_h_annual_report_year_must_match(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
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


def test_h_annual_report_year_matches_traditional_chinese_title():
    assert disclosure_service._matches_h_annual_report_year(
        {"title": "2025年年報"}, 2025
    )
    assert disclosure_service._matches_h_annual_report_year(
        {"title": "2025年度報告"}, 2025
    )
    assert disclosure_service._matches_h_annual_report_year(
        {"title": "二零二五年度報告"}, 2025
    )
    assert disclosure_service._matches_h_annual_report_year(
        {"title": "二〇二五年年報"}, 2025
    )


def test_h_annual_report_year_rejects_interim_report():
    assert not disclosure_service._matches_h_annual_report_year(
        {"title": "2025年中期報告"}, 2025
    )


def test_h_annual_report_merges_unfiltered_title_variants(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))

    def fake_search(*args, title_keyword="", **kwargs):
        if title_keyword:
            return [
                {
                    "title": "2025 Annual Report and Accounts",
                    "pdf_url": "https://example.com/two-page-notice.pdf",
                }
            ]
        return [
            {
                "title": "Annual Report and Accounts 2025 (with employee share plans)",
                "pdf_url": "https://example.com/full-report.pdf",
            }
        ]

    monkeypatch.setattr(disclosure_service, "search_h_filings", fake_search)

    rows = disclosure_service.search_h_annual_report("00005", report_year=2025)

    assert {row["pdf_url"] for row in rows} == {
        "https://example.com/two-page-notice.pdf",
        "https://example.com/full-report.pdf",
    }


def test_h_annual_report_skips_broad_search_for_large_exact_result(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    calls = []

    def fake_search(*args, title_keyword="", **kwargs):
        calls.append(title_keyword)
        if not title_keyword:
            raise AssertionError("broad search should not run")
        return [
            {
                "title": "2025 Annual Report",
                "pdf_url": "https://example.com/full-report.pdf",
                "file_size_label": "12MB",
            }
        ]

    monkeypatch.setattr(disclosure_service, "search_h_filings", fake_search)

    rows = disclosure_service.search_h_annual_report("00883", report_year=2025)

    assert [row["pdf_url"] for row in rows] == ["https://example.com/full-report.pdf"]
    assert calls == ["Annual Report"]


def test_h_annual_report_keeps_broad_fallback_for_small_exact_result(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    calls = []

    def fake_search(*args, title_keyword="", **kwargs):
        calls.append(title_keyword)
        if title_keyword:
            return [
                {
                    "title": "2025 Annual Report",
                    "pdf_url": "https://example.com/two-page-notice.pdf",
                    "file_size_label": "158KB",
                }
            ]
        return [
            {
                "title": "Annual Report and Accounts 2025 (with employee share plans)",
                "pdf_url": "https://example.com/full-report.pdf",
                "file_size_label": "8MB",
            }
        ]

    monkeypatch.setattr(disclosure_service, "search_h_filings", fake_search)

    rows = disclosure_service.search_h_annual_report("00005", report_year=2025)

    assert {row["pdf_url"] for row in rows} == {
        "https://example.com/two-page-notice.pdf",
        "https://example.com/full-report.pdf",
    }
    assert calls == ["Annual Report", ""]


def test_h_report_download_forwards_explicit_hkex_stock_id(monkeypatch):
    captured = {}

    def fake_ensure(*args, **kwargs):
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(
        "ah_disclosure.services.filing_pipeline.ensure_filing_evidence",
        fake_ensure,
    )

    result = disclosure_service.download_and_ingest_h_report(
        "00883", report_year=2025, hkex_stock_id="12345", ingest=False
    )

    assert result["ok"] is True
    assert captured["hkex_stock_id"] == "12345"


def test_uncertain_cached_title_result_requires_broad_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))

    def fake_search(*args, title_keyword="", offline=False, **kwargs):
        if title_keyword:
            return [
                {
                    "title": "2025 Annual Report",
                    "pdf_url": "https://example.com/two-page-notice.pdf",
                    "file_size_label": "158KB",
                }
            ]
        if offline:
            raise RuntimeError("Offline source cache miss")
        return []

    monkeypatch.setattr(disclosure_service, "search_h_filings", fake_search)

    try:
        disclosure_service.search_h_annual_report(
            "00005", report_year=2025, offline=True
        )
    except RuntimeError as exc:
        assert "cache miss" in str(exc)
    else:
        raise AssertionError("uncertain partial cache should not be treated as complete")
