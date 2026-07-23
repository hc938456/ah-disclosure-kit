from ah_disclosure.services import disclosure_service, filing_pipeline


def test_default_a_annual_report_download_uses_validated_pipeline(monkeypatch):
    captured = {}

    def fake_ensure(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return {"ok": True, "validated_pipeline": True}

    monkeypatch.setattr(filing_pipeline, "ensure_filing_evidence", fake_ensure)

    result = disclosure_service.download_and_ingest_a_report(
        "600519", report_year=2025, ingest=False
    )

    assert result["validated_pipeline"] is True
    assert captured["args"][1:4] == ("A", "600519", "annual_report")
    assert captured["kwargs"]["report_year"] == 2025
    assert captured["kwargs"]["language"] == "ZH"
    assert captured["kwargs"]["ingest_if_missing"] is False
