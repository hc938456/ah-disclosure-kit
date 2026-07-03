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

    result = prospectus_service.download_and_ingest_prospectus(
        "https://example.com/sample.pdf",
        title="Sample Prospectus",
        ingest=False,
    )

    assert "download" in result
    assert "ingest" not in result
    assert calls["ingest"] == 0
