from pathlib import Path

import fitz
import pytest

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
    first_quality_path = (
        tmp_path
        / "data"
        / "parsed"
        / document_id
        / "quality_report.json"
    )
    first_quality = first_quality_path.read_text(encoding="utf-8")
    first_quality_path.write_text(
        first_quality.replace('  "extraction_fallback_pages": [],\n', "")
        .replace('  "extraction_failed_pages": [],\n', "")
        .replace('  "extraction_issue_count": 0,\n', ""),
        encoding="utf-8",
    )
    cached = ingest_pdf(pdf_path, document_id=document_id, meta=meta)
    assert cached["sqlite_index_reused"] is True
    migrated_quality = first_quality_path.read_text(encoding="utf-8")
    assert '"extraction_fallback_pages": []' in migrated_quality
    assert '"extraction_failed_pages": []' in migrated_quality
    assert '"extraction_issue_count": 0' in migrated_quality
    store = SQLiteStore()
    assert store.get_document_meta(document_id)
    assert store.search_pages("Revenue", document_id, 5)

    store.delete_document_records(document_id)
    assert not store.get_document_meta(document_id)
    assert not store.search_pages("Revenue", document_id, 5)

    rebuilt = ingest_pdf(pdf_path, document_id=document_id, meta=meta)
    assert rebuilt["sqlite_index_reused"] is False
    assert store.get_document_meta(document_id)
    assert store.search_pages("Revenue", document_id, 5)

    ingest_pdf(pdf_path, document_id=document_id, meta=meta, write_markdown=True)
    saved_meta = store.get_document_meta(document_id)
    assert saved_meta["markdown_path"]
    assert Path(saved_meta["markdown_path"]).exists()


def test_ingest_rebuilds_pages_when_pdf_hash_changes(tmp_path, monkeypatch):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    pdf_path = tmp_path / "sample.pdf"
    _sample_pdf(pdf_path)
    document_id = "TMP_0002_2025_annual_report_EN_SAMPLE"

    first = ingest_pdf(pdf_path, document_id=document_id)

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 72), "Changed PDF content")
    doc.save(pdf_path)
    doc.close()
    second = ingest_pdf(pdf_path, document_id=document_id)

    assert first["sha256"] != second["sha256"]
    rows = SQLiteStore().search_pages("Changed", document_id, 5)
    assert rows


def test_ingest_rebuilds_corrupt_pages_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    pdf_path = tmp_path / "sample.pdf"
    _sample_pdf(pdf_path)
    document_id = "TMP_0003_2025_annual_report_EN_SAMPLE"

    first = ingest_pdf(pdf_path, document_id=document_id)
    Path(first["pages_jsonl_path"]).write_text("not-json\n", encoding="utf-8")
    second = ingest_pdf(pdf_path, document_id=document_id)

    assert second["cache_status"] == "corrupt_cache"
    assert second["reingested"] is True
    assert SQLiteStore().search_pages("Revenue", document_id, 5)


def test_ingest_cache_builds_newly_requested_enhancements(tmp_path, monkeypatch):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    pdf_path = tmp_path / "sample.pdf"
    _sample_pdf(pdf_path)
    document_id = "TMP_0004_2025_annual_report_EN_SAMPLE"

    first = ingest_pdf(pdf_path, document_id=document_id)
    assert first["ingested"] is True

    table_path = tmp_path / "data" / "parsed" / document_id / "tables" / "page_1_table_1.csv"

    def fake_extract_tables(*args, **kwargs):
        table_path.parent.mkdir(parents=True, exist_ok=True)
        table_path.write_text("item,amount\nrevenue,10\n", encoding="utf-8")
        return [{"page_no": 1, "table_index": 1, "table_path": str(table_path)}]

    monkeypatch.setattr("ah_disclosure.pdf.ingest.extract_tables", fake_extract_tables)
    enhanced = ingest_pdf(
        pdf_path,
        document_id=document_id,
        extract_tables_opt=True,
        build_vector_index_opt=True,
    )

    assert enhanced["ingest_cache_hit"] is True
    assert enhanced["ingested"] is False
    assert enhanced["cache_enhanced"] is True
    assert set(enhanced["enhancements_built"]) == {"tables", "vector_manifest"}
    assert Path(enhanced["vector_index_path"]).exists()

    repeated = ingest_pdf(
        pdf_path,
        document_id=document_id,
        extract_tables_opt=True,
        build_vector_index_opt=True,
    )
    assert repeated["cache_enhanced"] is False
    assert repeated["enhancements_built"] == []


@pytest.mark.parametrize("document_id", ["..", "../outside", r"..\outside", "C:/outside"])
def test_ingest_rejects_unsafe_document_id(tmp_path, monkeypatch, document_id):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    pdf_path = tmp_path / "sample.pdf"
    _sample_pdf(pdf_path)

    with pytest.raises(ValueError, match="document_id"):
        ingest_pdf(pdf_path, document_id=document_id)

    assert not (tmp_path / "outside").exists()
