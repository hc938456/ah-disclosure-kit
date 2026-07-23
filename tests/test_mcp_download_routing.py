from ah_disclosure import mcp_server


def test_annual_report_download_uses_validated_pipeline(monkeypatch):
    captured = {}

    def fake_ensure(**kwargs):
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(mcp_server, "ensure_filing_evidence", fake_ensure)
    record = {
        "market": "H",
        "symbol": "00941",
        "document_type": "annual_report",
        "report_year": 2025,
        "title": "China Mobile Annual Report 2025",
        "pdf_url": "https://example.test/report.pdf",
    }

    result = mcp_server.download_and_ingest_filing(record, ingest=True)

    assert result["ok"] is True
    assert result["validated_pipeline"] is True
    assert captured["document_type"] == "annual_report"
    assert captured["report_year"] == 2025
    assert captured["ingest_if_missing"] is True
