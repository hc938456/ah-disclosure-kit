from ah_disclosure.services import prospectus_service


def test_prospectus_download_only_skips_ingest(monkeypatch, tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")
    calls = {"ingest": 0}

    def fake_download_file(*args, **kwargs):
        return {"path": str(pdf_path), "url": args[0], "existed": False}

    def fake_ingest_pdf(*args, **kwargs):
        calls["ingest"] += 1
        return {"document_id": "doc"}

    monkeypatch.setattr(prospectus_service, "download_file", fake_download_file)
    monkeypatch.setattr(prospectus_service, "ingest_pdf", fake_ingest_pdf)
    monkeypatch.setattr(prospectus_service, "extract_pages", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        prospectus_service,
        "validate_prospectus_pages",
        lambda *args, **kwargs: {"complete": True, "status": "complete"},
    )
    monkeypatch.setattr(
        prospectus_service,
        "move_staged_candidate",
        lambda downloaded, *args, **kwargs: downloaded,
    )

    result = prospectus_service.download_and_ingest_prospectus(
        "https://example.com/sample.pdf",
        title="Sample Prospectus",
        ingest=False,
    )

    assert "download" in result
    assert "ingest" not in result
    assert calls["ingest"] == 0


def test_incomplete_prospectus_is_not_ingested(monkeypatch, tmp_path):
    pdf_path = tmp_path / "announcement.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")
    calls = {"ingest": 0}
    monkeypatch.setattr(
        prospectus_service,
        "download_file",
        lambda *args, **kwargs: {"path": str(pdf_path), "url": args[0], "existed": False},
    )
    monkeypatch.setattr(
        prospectus_service,
        "validate_prospectus_pages",
        lambda *args, **kwargs: {"complete": False, "status": "rejected_short_document"},
    )
    monkeypatch.setattr(prospectus_service, "extract_pages", lambda *args, **kwargs: [])
    monkeypatch.setattr(prospectus_service, "discard_staged_candidate", lambda *args: True)
    monkeypatch.setattr(
        prospectus_service,
        "ingest_pdf",
        lambda *args, **kwargs: calls.update(ingest=calls["ingest"] + 1),
    )

    result = prospectus_service.download_and_ingest_prospectus(
        "https://example.com/announcement.pdf",
        title="Global Offering",
        ingest=True,
    )

    assert result["ok"] is False
    assert result["document_validation"]["status"] == "rejected_short_document"
    assert "ingest" not in result
    assert calls["ingest"] == 0
