from __future__ import annotations

import json
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from ah_disclosure.core.file_utils import normalized_path_key
from ah_disclosure.core.paths import get_data_paths
from ah_disclosure.models import PdfPage
from ah_disclosure.pdf.completeness import (
    validate_annual_report_pages,
    validate_annual_report_pdf,
    validate_prospectus_pages,
    validate_prospectus_pdf,
)
from ah_disclosure.pdf.downloader import file_sha256
from ah_disclosure.storage.sqlite_store import SQLiteStore


def _path_key(value: str | Path) -> str:
    return normalized_path_key(value)


def _logical_pdf_key(path: Path) -> str:
    # A hash suffix is added only when two different files request the same stable name.
    stem = re.sub(r"_[0-9a-f]{8}$", "", path.stem, flags=re.IGNORECASE)
    return f"{path.parent.name.casefold()}|{stem.casefold()}"


def _group_duplicates(files: list[Path], key_func) -> list[dict[str, Any]]:
    groups: dict[str, list[Path]] = defaultdict(list)
    for path in files:
        groups[key_func(path)].append(path)
    return [
        {"key": key, "count": len(paths), "paths": [str(path) for path in paths]}
        for key, paths in sorted(groups.items())
        if len(paths) > 1
    ]


def _hash_targets(files: list[Path], scan_content: bool) -> list[Path]:
    if scan_content:
        return files
    size_groups: dict[int, list[Path]] = defaultdict(list)
    for path in files:
        size_groups[path.stat().st_size].append(path)
    return [path for paths in size_groups.values() if len(paths) > 1 for path in paths]


def _load_indexed_pages(
    row: dict[str, Any] | None,
    expected_sha256: str,
) -> list[PdfPage] | None:
    if not row or str(row.get("sha256") or "") != expected_sha256:
        return None
    pages_path = Path(str(row.get("pages_jsonl_path") or ""))
    if not pages_path.is_file():
        return None
    pages: list[PdfPage] = []
    try:
        with pages_path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                item = json.loads(line)
                page_no = int(item.get("page_no") or 0)
                if page_no <= 0:
                    return None
                text = str(item.get("text") or "")
                pages.append(
                    PdfPage(
                        page_no=page_no,
                        text=text,
                        char_count=int(item.get("char_count") or len(text)),
                        ocr_used=bool(item.get("ocr_used")),
                        quality_score=item.get("quality_score"),
                        section_title=item.get("section_title"),
                        extraction_method=item.get("extraction_method"),
                        extraction_error=item.get("extraction_error"),
                    )
                )
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None
    expected_page_count = int(row.get("page_count") or 0)
    if not pages or expected_page_count <= 0 or len(pages) != expected_page_count:
        return None
    return pages


def _validate_known_document(
    path: Path,
    pages: list[PdfPage] | None = None,
) -> dict[str, Any] | None:
    name = path.name.casefold()
    if "annual_report" in name:
        if pages is not None:
            return validate_annual_report_pages(path, pages)
        return validate_annual_report_pdf(path)
    if "prospectus" in name or "global_offering" in name:
        if pages is not None:
            return validate_prospectus_pages(path, pages)
        return validate_prospectus_pdf(path)
    return None


def audit_local_pdf_cache(scan_content: bool = False) -> dict[str, Any]:
    """Audit local PDFs without changing or deleting any file."""
    paths = get_data_paths()
    store = SQLiteStore()
    raw_files = sorted(path for path in paths.raw.rglob("*.pdf") if path.is_file())
    indexed_rows = store.list_documents(limit=100000)
    indexed_paths = {
        _path_key(row["local_pdf_path"])
        for row in indexed_rows
        if row.get("local_pdf_path")
    }
    indexed_rows_by_path = {
        _path_key(row["local_pdf_path"]): row
        for row in indexed_rows
        if row.get("local_pdf_path")
    }
    with store.connection() as conn:
        source_rows = conn.execute(
            "SELECT local_pdf_path FROM filing_sources WHERE local_pdf_path IS NOT NULL"
        ).fetchall()
    source_paths = {_path_key(row["local_pdf_path"]) for row in source_rows}
    referenced_paths = indexed_paths | source_paths

    hash_targets = _hash_targets(raw_files, scan_content)
    hash_workers = min(4, len(hash_targets))
    if hash_workers > 1:
        with ThreadPoolExecutor(max_workers=hash_workers) as pool:
            hashes = dict(
                zip(hash_targets, pool.map(file_sha256, hash_targets), strict=True)
            )
    else:
        hashes = {path: file_sha256(path) for path in hash_targets}
    duplicate_hashes = _group_duplicates(hash_targets, lambda path: hashes[path])
    duplicate_logical_names = _group_duplicates(raw_files, _logical_pdf_key)
    unreferenced = [str(path) for path in raw_files if _path_key(path) not in referenced_paths]
    missing_indexed = sorted(
        str(Path(row["local_pdf_path"]))
        for row in indexed_rows
        if row.get("local_pdf_path") and not Path(row["local_pdf_path"]).exists()
    )
    staged_downloads = sorted(str(path) for path in paths.staging_downloads.rglob("*.pdf"))
    review_dir = paths.staging / "review"
    staged_reviews = sorted(str(path) for path in review_dir.rglob("*.pdf")) if review_dir.exists() else []

    content_issues: list[dict[str, Any]] = []
    validated_count = 0
    content_index_reused_count = 0
    content_pdf_scanned_count = 0
    if scan_content:
        for path in raw_files:
            try:
                pages = _load_indexed_pages(
                    indexed_rows_by_path.get(_path_key(path)),
                    hashes[path],
                )
                result = _validate_known_document(path, pages)
            except Exception as exc:
                content_issues.append({"path": str(path), "status": "validation_error", "error": str(exc)})
                continue
            if result is None:
                continue
            validated_count += 1
            if pages is None:
                content_pdf_scanned_count += 1
            else:
                content_index_reused_count += 1
            if result.get("complete") is not True or (result.get("text_quality") or {}).get(
                "garbled_suspect"
            ):
                content_issues.append(result)

    return {
        "ok": True,
        "read_only": True,
        "scan_content": scan_content,
        "summary": {
            "raw_pdf_count": len(raw_files),
            "hash_workers": hash_workers,
            "hashed_pdf_count": len(hash_targets),
            "indexed_document_count": len(indexed_rows),
            "duplicate_hash_group_count": len(duplicate_hashes),
            "duplicate_logical_name_group_count": len(duplicate_logical_names),
            "unreferenced_raw_pdf_count": len(unreferenced),
            "missing_indexed_pdf_count": len(missing_indexed),
            "staged_download_count": len(staged_downloads),
            "review_candidate_count": len(staged_reviews),
            "content_validated_count": validated_count,
            "content_index_reused_count": content_index_reused_count,
            "content_pdf_scanned_count": content_pdf_scanned_count,
            "content_issue_count": len(content_issues),
        },
        "duplicate_hashes": duplicate_hashes,
        "duplicate_logical_names": duplicate_logical_names,
        "unreferenced_raw_pdfs": unreferenced,
        "missing_indexed_pdfs": missing_indexed,
        "staged_downloads": staged_downloads,
        "review_candidates": staged_reviews,
        "content_issues": content_issues,
    }
