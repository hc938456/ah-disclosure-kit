from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from ah_disclosure.core.file_utils import normalized_path_key
from ah_disclosure.core.naming import safe_document_path, validate_document_id
from ah_disclosure.core.paths import get_data_paths
from ah_disclosure.storage.sqlite_store import SQLiteStore


def _is_within(path: Path, parent: Path) -> bool:
    try:
        resolved_path = path.resolve()
        resolved_parent = parent.resolve()
        resolved_path.relative_to(resolved_parent)
        return resolved_path != resolved_parent
    except ValueError:
        return False


def _all_documents(store: SQLiteStore) -> list[dict[str, Any]]:
    """Read the complete document index without a cleanup-dangerous row cap."""
    with store.connection() as conn:
        rows = conn.execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()
    return [dict(row) for row in rows]


def _other_pdf_references(store: SQLiteStore, document_id: str, local_pdf_path: str) -> list[str]:
    target_key = normalized_path_key(local_pdf_path)
    with store.connection() as conn:
        rows = conn.execute(
            "SELECT 'document' AS reference_type, document_id, local_pdf_path FROM documents "
            "WHERE local_pdf_path IS NOT NULL "
            "UNION ALL "
            "SELECT 'filing_source' AS reference_type, document_id, local_pdf_path FROM filing_sources "
            "WHERE local_pdf_path IS NOT NULL"
        ).fetchall()
    references: list[str] = []
    for index, row in enumerate(rows):
        row_document_id = str(row["document_id"] or "")
        if row_document_id == document_id or normalized_path_key(row["local_pdf_path"]) != target_key:
            continue
        label = row_document_id or f"filing_source:{index}"
        if label not in references:
            references.append(label)
    return references


def _remove_file(path: Path, root: Path, dry_run: bool) -> dict[str, Any]:
    item = {"path": str(path), "exists": path.exists(), "deleted": False, "skipped": False}
    if not _is_within(path, root):
        item["skipped"] = True
        item["reason"] = "outside data directory"
        return item
    if path.exists() and not dry_run:
        path.unlink()
        item["deleted"] = True
    return item


def _remove_dir(path: Path, root: Path, dry_run: bool) -> dict[str, Any]:
    item = {"path": str(path), "exists": path.exists(), "deleted": False, "skipped": False}
    if not _is_within(path, root):
        item["skipped"] = True
        item["reason"] = "outside data directory"
        return item
    if path.exists() and not dry_run:
        shutil.rmtree(path)
        item["deleted"] = True
    return item


def cleanup_document(document_id: str, delete_pdf: bool = True, delete_parsed: bool = True, dry_run: bool = False) -> dict[str, Any]:
    document_id = validate_document_id(document_id)
    paths = get_data_paths()
    store = SQLiteStore()
    meta = store.get_document_meta(document_id)
    parsed_dir = safe_document_path(paths.parsed, document_id)
    actions: list[dict[str, Any]] = []

    pdf_path = Path(meta["local_pdf_path"]) if delete_pdf and meta.get("local_pdf_path") else None
    shared_by = _other_pdf_references(store, document_id, str(pdf_path)) if pdf_path else []

    # Commit the reversible database cleanup before deleting files. If SQLite
    # fails, no filesystem deletion has taken place.
    sqlite_counts = {} if dry_run else store.delete_document_records(document_id)

    if pdf_path:
        if shared_by:
            actions.append({
                "path": str(pdf_path),
                "exists": pdf_path.exists(),
                "deleted": False,
                "skipped": True,
                "reason": "pdf is referenced by other documents",
                "referenced_by": shared_by,
            })
        else:
            actions.append(_remove_file(pdf_path, paths.root, dry_run))
    if delete_parsed:
        actions.append(_remove_dir(parsed_dir, paths.root, dry_run))

    return {
        "ok": True,
        "document_id": document_id,
        "dry_run": dry_run,
        "meta_found": bool(meta),
        "actions": actions,
        "sqlite": sqlite_counts,
    }


def cleanup_company(
    market: str,
    symbol: str,
    delete_pdfs: bool = True,
    delete_parsed: bool = True,
    delete_company_cache: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    store = SQLiteStore()
    documents = store.list_documents_by_company(market, symbol)
    document_results = [
        cleanup_document(row["document_id"], delete_pdf=delete_pdfs, delete_parsed=delete_parsed, dry_run=dry_run)
        for row in documents
    ]
    company_sqlite = {} if dry_run or not delete_company_cache else store.delete_company_records(market, symbol)
    return {
        "ok": True,
        "market": market,
        "symbol": symbol,
        "dry_run": dry_run,
        "documents_found": len(documents),
        "documents": document_results,
        "company_sqlite": company_sqlite,
    }


def reconcile_local_documents(
    dry_run: bool = False,
    scan_raw: bool = True,
    remove_orphan_parsed: bool = True,
) -> dict[str, Any]:
    paths = get_data_paths()
    store = SQLiteStore()
    stale: list[dict[str, Any]] = []
    indexed_rows = _all_documents(store)
    for row in indexed_rows:
        document_id = row.get("document_id")
        if not document_id:
            continue
        local_pdf = Path(row["local_pdf_path"]) if row.get("local_pdf_path") else None
        try:
            parsed_dir = safe_document_path(paths.parsed, document_id)
        except ValueError as exc:
            stale.append({
                "ok": False,
                "document_id": str(document_id),
                "dry_run": dry_run,
                "meta_found": True,
                "actions": [{
                    "path": "",
                    "exists": False,
                    "deleted": False,
                    "skipped": True,
                    "reason": str(exc),
                }],
                "sqlite": {},
            })
            continue
        pages_jsonl = parsed_dir / "pages.jsonl"
        if (local_pdf and not local_pdf.exists()) or not parsed_dir.exists() or not pages_jsonl.exists():
            stale.append(cleanup_document(document_id, delete_pdf=False, delete_parsed=not pages_jsonl.exists(), dry_run=dry_run))

    current_rows = _all_documents(store)
    indexed_document_ids = {str(row.get("document_id")) for row in current_rows if row.get("document_id")}
    indexed_pdf_paths = {
        normalized_path_key(row["local_pdf_path"])
        for row in current_rows
        if row.get("local_pdf_path")
    }

    raw_missing_index: list[dict[str, Any]] = []
    if scan_raw:
        for pdf_path in paths.raw.rglob("*.pdf"):
            resolved = normalized_path_key(pdf_path)
            if resolved not in indexed_pdf_paths:
                raw_missing_index.append({"path": str(pdf_path), "reason": "raw pdf has no SQLite document record"})

    orphan_parsed: list[dict[str, Any]] = []
    for parsed_dir in paths.parsed.iterdir():
        if not parsed_dir.is_dir() or parsed_dir.name in indexed_document_ids:
            continue
        item = _remove_dir(parsed_dir, paths.root, dry_run) if remove_orphan_parsed else {
            "path": str(parsed_dir),
            "exists": True,
            "deleted": False,
            "skipped": True,
            "reason": "orphan parsed directory; remove_orphan_parsed is false",
        }
        orphan_parsed.append(item)

    return {
        "ok": True,
        "dry_run": dry_run,
        "scan_raw": scan_raw,
        "remove_orphan_parsed": remove_orphan_parsed,
        "stale_count": len(stale),
        "raw_missing_index_count": len(raw_missing_index),
        "orphan_parsed_count": len(orphan_parsed),
        "stale": stale,
        "raw_missing_index": raw_missing_index,
        "orphan_parsed": orphan_parsed,
    }
