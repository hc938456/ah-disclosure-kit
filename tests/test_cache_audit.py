import json
from pathlib import Path

from ah_disclosure.services import cache_audit_service
from ah_disclosure.services.cache_audit_service import (
    _load_indexed_pages,
    audit_local_pdf_cache,
)


def test_cache_audit_is_read_only_and_reports_duplicates(monkeypatch, tmp_path: Path):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(data_dir))
    raw_dir = data_dir / "raw" / "hkex"
    raw_dir.mkdir(parents=True)
    first = raw_dir / "H_00941_2025_annual_report_ZH.pdf"
    second = raw_dir / "H_00941_2025_annual_report_ZH_deadbeef.pdf"
    first.write_bytes(b"same-pdf-content")
    second.write_bytes(b"same-pdf-content")
    staged = data_dir / "staging" / "downloads" / "run-1" / "candidate.pdf"
    staged.parent.mkdir(parents=True)
    staged.write_bytes(b"candidate")

    result = audit_local_pdf_cache(scan_content=False)

    assert result["read_only"] is True
    assert result["summary"]["raw_pdf_count"] == 2
    assert result["summary"]["duplicate_hash_group_count"] == 1
    assert result["summary"]["duplicate_logical_name_group_count"] == 1
    assert result["summary"]["unreferenced_raw_pdf_count"] == 2
    assert result["summary"]["staged_download_count"] == 1
    assert first.exists() and second.exists() and staged.exists()


def test_cache_audit_reuses_pages_only_when_hash_and_page_count_match(tmp_path: Path):
    pages_path = tmp_path / "pages.jsonl"
    pages_path.write_text(
        "\n".join(
            json.dumps({"page_no": page_no, "text": f"page {page_no}"})
            for page_no in (1, 2)
        ),
        encoding="utf-8",
    )
    row = {
        "sha256": "expected-hash",
        "page_count": 2,
        "pages_jsonl_path": str(pages_path),
    }

    pages = _load_indexed_pages(row, "expected-hash")

    assert pages is not None
    assert [page.page_no for page in pages] == [1, 2]
    assert _load_indexed_pages(row, "different-hash") is None
    assert _load_indexed_pages({**row, "page_count": 3}, "expected-hash") is None


def test_default_cache_audit_hashes_only_same_size_candidates(monkeypatch, tmp_path: Path):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(data_dir))
    raw_dir = data_dir / "raw" / "cninfo"
    raw_dir.mkdir(parents=True)
    unique = raw_dir / "unique.pdf"
    first_candidate = raw_dir / "first.pdf"
    second_candidate = raw_dir / "second.pdf"
    unique.write_bytes(b"x")
    first_candidate.write_bytes(b"ab")
    second_candidate.write_bytes(b"cd")
    hashed: list[Path] = []

    def fake_hash(path):
        value = Path(path)
        hashed.append(value)
        return value.read_bytes().hex()

    monkeypatch.setattr(cache_audit_service, "file_sha256", fake_hash)

    result = audit_local_pdf_cache(scan_content=False)

    assert set(hashed) == {first_candidate, second_candidate}
    assert result["summary"]["hashed_pdf_count"] == 2
    assert result["summary"]["duplicate_hash_group_count"] == 0

    hashed.clear()
    full_result = audit_local_pdf_cache(scan_content=True)

    assert set(hashed) == {unique, first_candidate, second_candidate}
    assert full_result["summary"]["hashed_pdf_count"] == 3
