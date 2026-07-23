from __future__ import annotations

from pathlib import Path

import pytest

from ah_disclosure.core.naming import safe_document_path, validate_document_id
from ah_disclosure.services.cleanup_service import (
    _is_within,
    _remove_dir,
    cleanup_document,
    reconcile_local_documents,
)
from ah_disclosure.storage.sqlite_store import SQLiteStore


@pytest.mark.parametrize(
    "document_id",
    ["..", ".", "../escape", r"..\escape", "/absolute", r"C:\absolute", "bad:name"],
)
def test_document_id_rejects_paths(document_id: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        validate_document_id(document_id)
    with pytest.raises(ValueError):
        safe_document_path(tmp_path, document_id)


def test_safe_document_path_accepts_one_component(tmp_path: Path) -> None:
    assert safe_document_path(tmp_path, "A_000001_2025") == (
        tmp_path / "A_000001_2025"
    ).resolve()


def test_is_within_excludes_root_itself(tmp_path: Path) -> None:
    assert not _is_within(tmp_path, tmp_path)
    assert _is_within(tmp_path / "child", tmp_path)
    result = _remove_dir(tmp_path, tmp_path, dry_run=False)
    assert result["skipped"] is True
    assert tmp_path.exists()


def _indexed_document(store: SQLiteStore, document_id: str, pdf_path: Path) -> None:
    store.upsert_document(
        {
            "document_id": document_id,
            "title": document_id,
            "local_pdf_path": str(pdf_path),
        }
    )


def test_cleanup_rejects_unsafe_document_id_before_deleting(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(data_dir))
    sentinel = data_dir / "sentinel.txt"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text("keep", encoding="utf-8")

    with pytest.raises(ValueError):
        cleanup_document("..")

    assert sentinel.exists()


def test_cleanup_keeps_pdf_referenced_by_another_document(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(data_dir))
    pdf_path = data_dir / "raw" / "shared.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"pdf")
    store = SQLiteStore()
    _indexed_document(store, "doc-1", pdf_path)
    _indexed_document(store, "doc-2", pdf_path)

    result = cleanup_document("doc-1", delete_parsed=False)

    assert pdf_path.exists()
    assert result["actions"][0]["skipped"] is True
    assert result["actions"][0]["referenced_by"] == ["doc-2"]
    assert not store.get_document_meta("doc-1")
    assert store.get_document_meta("doc-2")


def test_cleanup_does_not_delete_files_when_database_cleanup_fails(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(data_dir))
    pdf_path = data_dir / "raw" / "doc.pdf"
    parsed_dir = data_dir / "parsed" / "doc-1"
    pdf_path.parent.mkdir(parents=True)
    parsed_dir.mkdir(parents=True)
    pdf_path.write_bytes(b"pdf")
    (parsed_dir / "pages.jsonl").write_text("{}\n", encoding="utf-8")
    store = SQLiteStore()
    _indexed_document(store, "doc-1", pdf_path)

    def fail_delete(self, document_id: str):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(SQLiteStore, "delete_document_records", fail_delete)

    with pytest.raises(RuntimeError, match="database unavailable"):
        cleanup_document("doc-1")

    assert pdf_path.exists()
    assert parsed_dir.exists()


def test_reconcile_reads_all_documents_without_limit(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(data_dir))
    store = SQLiteStore()
    pdf_path = data_dir / "raw" / "doc.pdf"
    parsed_dir = data_dir / "parsed" / "doc-1"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    parsed_dir.mkdir(parents=True)
    pdf_path.write_bytes(b"pdf")
    (parsed_dir / "pages.jsonl").write_text("{}\n", encoding="utf-8")
    _indexed_document(store, "doc-1", pdf_path)

    def forbidden_limited_read(self, limit: int = 100):
        raise AssertionError("reconcile must not use a capped list_documents query")

    monkeypatch.setattr(SQLiteStore, "list_documents", forbidden_limited_read)

    result = reconcile_local_documents(dry_run=False, scan_raw=False)

    assert result["orphan_parsed_count"] == 0
    assert parsed_dir.exists()
