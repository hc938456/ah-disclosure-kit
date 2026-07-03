from ah_disclosure import mcp_server


def test_mcp_ingest_exposes_ocr_and_overwrite(monkeypatch):
    calls = {}

    def fake_ingest_pdf(*args, **kwargs):
        calls["args"] = args
        calls["kwargs"] = kwargs
        return {"ok": True}

    monkeypatch.setattr(mcp_server, "_ingest_pdf", fake_ingest_pdf)

    result = mcp_server.ingest_pdf_tool(
        "scan.pdf",
        document_id="scan_doc",
        ocr="force",
        ocr_lang="eng",
        overwrite=True,
    )

    assert result["ok"] is True
    assert calls["kwargs"]["ocr"] == "force"
    assert calls["kwargs"]["ocr_lang"] == "eng"
    assert calls["kwargs"]["overwrite"] is True
