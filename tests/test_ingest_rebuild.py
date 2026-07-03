from pathlib import Path

import fitz

from ah_disclosure.pdf.ingest import ingest_pdf
from ah_disclosure.storage.sqlite_store import SQLiteStore


def _sample_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 72), "Revenue recognition sample\nNet profit sample")
    doc.save(path)
    doc.close()


def test_ingest_rebuilds_sqlite_from_existing_pages(tmp_path, monkeypatch):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    pdf_path = tmp_path / "sample.pdf"
    _sample_pdf(pdf_path)
    document_id = "TMP_0001_2025_annual_report_EN_SAMPLE"
    meta = {"market": "T", "symbol": "0001", "title": "2025 Annual Report"}

    ingest_pdf(pdf_path, document_id=document_id, meta=meta)
    store = SQLiteStore()
    assert store.get_document_meta(document_id)
    assert store.search_pages("Revenue", document_id, 5)

    store.delete_document_records(document_id)
    assert not store.get_document_meta(document_id)
    assert not store.search_pages("Revenue", document_id, 5)

    ingest_pdf(pdf_path, document_id=document_id, meta=meta)
    assert store.get_document_meta(document_id)
    assert store.search_pages("Revenue", document_id, 5)

    ingest_pdf(pdf_path, document_id=document_id, meta=meta, write_markdown=True)
    saved_meta = store.get_document_meta(document_id)
    assert saved_meta["markdown_path"]
    assert Path(saved_meta["markdown_path"]).exists()
