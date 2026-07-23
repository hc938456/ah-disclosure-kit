from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from ah_disclosure.core.file_utils import replace_file_with_retry
from ah_disclosure.core.naming import build_document_id, validate_document_id
from ah_disclosure.core.paths import get_data_paths
from ah_disclosure.core.time_utils import now_iso
from ah_disclosure.models import PdfIngestResult, PdfPage
from ah_disclosure.pdf.downloader import file_hashes
from ah_disclosure.pdf.markdown import pdf_to_markdown
from ah_disclosure.pdf.quality import assess_pages
from ah_disclosure.pdf.table_extract import extract_tables
from ah_disclosure.pdf.text_extract import extract_pages
from ah_disclosure.pdf.vector_index import build_vector_index
from ah_disclosure.storage.jsonl_store import write_jsonl
from ah_disclosure.storage.sqlite_store import SQLiteStore


def _pages_to_full_text(pages: list[PdfPage]) -> str:
    return "\n\n".join(f"<!-- page: {page.page_no} -->\n{page.text}" for page in pages)


def _pages_to_plain_markdown(pages: list[PdfPage], title: str | None = None) -> str:
    header = f"# {title}\n\n" if title else ""
    body = "".join(f"\n\n<!-- page: {page.page_no} -->\n\n{page.text}" for page in pages).strip()
    return f"{header}{body}\n"


def _read_pages_jsonl(path: Path) -> list[PdfPage]:
    pages: list[PdfPage] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            pages.append(
                PdfPage(
                    page_no=int(row.get("page_no") or 0),
                    text=row.get("text") or "",
                    char_count=int(row.get("char_count") or len(row.get("text") or "")),
                    ocr_used=bool(row.get("ocr_used")),
                    quality_score=row.get("quality_score"),
                    section_title=row.get("section_title"),
                    extraction_method=row.get("extraction_method"),
                    extraction_error=row.get("extraction_error"),
                )
            )
    return pages


def _write_json_atomic(path: Path, payload: Any) -> None:
    tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    replace_file_with_retry(tmp, path)


def _write_optional_text_outputs(
    pdf_path: Path,
    pages: list[PdfPage],
    title: str | None,
    text_path: Path,
    markdown_path: Path,
    write_full_text: bool,
    write_markdown: bool,
    layout_mode: str,
) -> tuple[str | None, str | None]:
    full_text_path = None
    markdown_path_value = None
    if write_full_text:
        text_path.write_text(_pages_to_full_text(pages), encoding="utf-8")
        full_text_path = str(text_path)
    if write_markdown:
        if layout_mode in {"layout", "pymupdf4llm"}:
            markdown = pdf_to_markdown(pdf_path, pages, title=title)
        else:
            markdown = _pages_to_plain_markdown(pages, title=title)
        markdown_path.write_text(markdown, encoding="utf-8")
        markdown_path_value = str(markdown_path)
    return full_text_path, markdown_path_value


def _merge_meta(old: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    merged = {**old}
    for key, value in meta.items():
        if value not in (None, ""):
            merged[key] = value
    return merged


_TABLE_KEYWORDS = (
    "募集资金",
    "前五大客户",
    "主营构成",
    "主营",
    "分部收入",
    "分部",
    "资产负债表",
    "利润表",
    "现金流量表",
)


def _should_extract_tables(mode: str, option: bool | str, pages: list[PdfPage]) -> bool:
    if mode == "full" or option is True:
        return True
    return option == "auto" and any(
        keyword in page.text for page in pages for keyword in _TABLE_KEYWORDS
    )


def _table_candidate_pages(pages: list[PdfPage]) -> list[int] | None:
    candidates = [
        page.page_no
        for page in pages
        if any(keyword in page.text for keyword in _TABLE_KEYWORDS)
    ]
    return candidates or None


def _table_extraction_state(results: list[dict[str, Any]], requested: bool) -> dict[str, Any]:
    failed = any(bool(item.get("error")) for item in results)
    return {
        "requested": requested,
        "status": "failed" if failed else ("completed" if requested else "not_requested"),
        "result_count": sum(1 for item in results if not item.get("error")),
        "attempted_at": now_iso() if requested else None,
    }


def _sync_sqlite_index(
    store: SQLiteStore,
    document_id: str,
    pdf_path: Path,
    meta: dict[str, Any],
    pages: list[PdfPage],
    meta_path: Path,
    pages_path: Path,
    full_text_path: str | None,
    markdown_path: str | None,
    md5: str,
    sha256: str,
    table_results: list[dict[str, Any]] | None = None,
    replace_page_index: bool = True,
) -> None:
    store.upsert_document(
        {
            "document_id": document_id,
            "market": meta.get("market"),
            "symbol": meta.get("symbol"),
            "company_name": meta.get("company_name"),
            "document_type": meta.get("document_type"),
            "report_year": meta.get("report_year"),
            "title": meta.get("title") or pdf_path.name,
            "publish_time": meta.get("publish_time"),
            "source": meta.get("source"),
            "detail_url": meta.get("detail_url"),
            "pdf_url": meta.get("pdf_url"),
            "local_pdf_path": str(pdf_path),
            "meta_path": str(meta_path),
            "pages_jsonl_path": str(pages_path),
            "markdown_path": markdown_path,
            "full_text_path": full_text_path,
            "md5": md5,
            "sha256": sha256,
            "page_count": len(pages),
        }
    )
    if replace_page_index:
        store.replace_pages(document_id, pages)
        store.replace_document_tables(document_id, table_results or [])


def ingest_pdf(
    pdf_path: str | Path,
    document_id: str | None = None,
    meta: dict[str, Any] | None = None,
    mode: str = "auto",
    extract_tables_opt: bool | str = False,
    ocr: str = "auto",
    ocr_lang: str = "chi_sim+eng",
    build_vector_index_opt: bool = False,
    layout_mode: str = "auto",
    write_full_text: bool = False,
    write_markdown: bool = False,
    overwrite: bool = False,
    pre_extracted_pages: list[PdfPage] | None = None,
    precomputed_md5: str | None = None,
    precomputed_sha256: str | None = None,
) -> dict[str, Any]:
    path = Path(pdf_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    meta = meta or {}
    if precomputed_md5 and precomputed_sha256:
        md5, sha = precomputed_md5, precomputed_sha256
    else:
        md5, sha = file_hashes(path)
    document_id = validate_document_id(
        document_id or build_document_id(meta, fallback_title=path.stem)
    )
    paths = get_data_paths()
    out_dir = paths.parsed_document_dir(document_id)
    meta_path = out_dir / "meta.json"
    pages_path = out_dir / "pages.jsonl"
    text_path = out_dir / "full_text.txt"
    markdown_path = out_dir / "document.md"
    quality_path = out_dir / "quality_report.json"
    write_full_text = write_full_text or mode == "full"
    write_markdown = write_markdown or mode == "full"

    cache_status = "forced_overwrite" if overwrite else "miss"
    cached_meta: dict[str, Any] | None = None
    cached_pages: list[PdfPage] | None = None
    if pages_path.exists() and meta_path.exists() and not overwrite:
        try:
            cached_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            cache_status = "corrupt_cache"
        else:
            cached_sha = str(cached_meta.get("sha256") or "")
            if not cached_sha:
                cache_status = "stale_missing_hash"
            elif cached_sha != sha:
                cache_status = "stale_hash_mismatch"
            else:
                cache_status = "hit"

    if cache_status == "hit":
        try:
            cached_pages = _read_pages_jsonl(pages_path)
        except Exception:
            cache_status = "corrupt_cache"

    if cache_status == "hit" and cached_meta is not None and cached_pages is not None:
        old = cached_meta
        old = _merge_meta(old, meta)
        pages = cached_pages
        try:
            cached_quality = json.loads(quality_path.read_text(encoding="utf-8"))
            if not isinstance(cached_quality, dict):
                cached_quality = {}
        except (OSError, ValueError):
            cached_quality = {}
        quality_schema_changed = False
        quality_defaults: dict[str, Any] = {
            "extraction_fallback_pages": [
                page.page_no
                for page in pages
                if page.extraction_method == "pypdf_fallback"
            ],
            "extraction_failed_pages": [
                page.page_no for page in pages if page.extraction_method == "failed"
            ],
        }
        quality_defaults["extraction_issue_count"] = (
            len(quality_defaults["extraction_fallback_pages"])
            + len(quality_defaults["extraction_failed_pages"])
        )
        for key, value in quality_defaults.items():
            if key not in cached_quality:
                cached_quality[key] = value
                quality_schema_changed = True
        if quality_schema_changed:
            _write_json_atomic(quality_path, cached_quality)
        old["quality_report_path"] = str(quality_path)
        old["quality"] = cached_quality
        enhancements_built: list[str] = []
        if write_full_text or write_markdown:
            full_text_path, markdown_path_value = _write_optional_text_outputs(
                path,
                pages,
                old.get("title") or meta.get("title"),
                text_path,
                markdown_path,
                write_full_text and not text_path.exists(),
                write_markdown and not markdown_path.exists(),
                layout_mode,
            )
            if full_text_path:
                old["full_text_path"] = full_text_path
                enhancements_built.append("full_text")
            if markdown_path_value:
                old["markdown_path"] = markdown_path_value
                enhancements_built.append("markdown")

        should_extract_tables = _should_extract_tables(mode, extract_tables_opt, pages)
        cached_tables = old.get("tables")
        cached_table_results = cached_tables if isinstance(cached_tables, list) else []
        old_table_state = old.get("table_extraction")
        table_completed = (
            isinstance(old_table_state, dict)
            and old_table_state.get("status") == "completed"
        ) or bool(
            cached_table_results
            and not any(item.get("error") for item in cached_table_results)
        )
        if should_extract_tables and not table_completed:
            cached_table_results = extract_tables(
                path,
                out_dir / "tables",
                pages=_table_candidate_pages(pages),
            )
            old["tables"] = cached_table_results
            old["extract_tables"] = True
            old["table_extraction"] = _table_extraction_state(cached_table_results, True)
            enhancements_built.append(
                "tables_failed"
                if old["table_extraction"]["status"] == "failed"
                else "tables"
            )

        vector_path = old.get("vector_index_path")
        vector_requested = build_vector_index_opt or mode == "full"
        vector_exists = bool(vector_path and Path(str(vector_path)).exists())
        if vector_requested and not vector_exists:
            vector = build_vector_index(document_id, pages, paths.index / "vector_store")
            vector_path = vector.get("vector_index_path")
            old["vector_index_path"] = vector_path
            enhancements_built.append("vector_manifest")
        full_text_path = str(text_path) if text_path.exists() else old.get("full_text_path")
        markdown_path_value = str(markdown_path) if markdown_path.exists() else old.get("markdown_path")
        old.update(
            {
                "document_id": document_id,
                "local_pdf_path": str(path),
                "meta_path": str(meta_path),
                "pages_jsonl_path": str(pages_path),
                "full_text_path": full_text_path if full_text_path and Path(full_text_path).exists() else None,
                "markdown_path": markdown_path_value if markdown_path_value and Path(markdown_path_value).exists() else None,
                "md5": md5,
                "sha256": sha,
                "page_count": int(old.get("page_count") or len(pages)),
                "char_count": int(old.get("char_count") or sum(page.char_count for page in pages)),
                "text_outputs": {
                    "full_text": bool(full_text_path and Path(full_text_path).exists()),
                    "markdown": bool(markdown_path_value and Path(markdown_path_value).exists()),
                    "layout_mode": layout_mode,
                    "default_policy": "core index only; full_text.txt and document.md are optional",
                },
                "sqlite_synced_at": now_iso(),
            }
        )
        _write_json_atomic(meta_path, old)
        store = SQLiteStore()
        sqlite_index_reused = store.document_index_is_consistent(
            document_id,
            sha,
            len(pages),
        )
        _sync_sqlite_index(
            store,
            document_id,
            path,
            old,
            pages,
            meta_path,
            pages_path,
            old.get("full_text_path"),
            old.get("markdown_path"),
            md5,
            sha,
            cached_table_results,
            replace_page_index=not sqlite_index_reused,
        )
        store.log_ingest(
            document_id,
            str(path),
            "ok_cached_index_reused" if sqlite_index_reused else "ok_cached_index_rebuilt",
        )
        result = PdfIngestResult(
            document_id=document_id,
            pdf_path=str(path),
            meta_path=str(meta_path),
            pages_jsonl_path=str(pages_path),
            full_text_path=old.get("full_text_path"),
            markdown_path=old.get("markdown_path"),
            page_count=int(old.get("page_count") or len(pages)),
            char_count=int(old.get("char_count") or sum(page.char_count for page in pages)),
            md5=md5,
            sha256=sha,
            sqlite_path=str(paths.sqlite_path),
            fts_enabled=True,
            vector_index_path=old.get("vector_index_path"),
        )
        payload = result.to_dict()
        payload.update(
            {
                "cache_status": "hit",
                "ingest_cache_hit": True,
                "ingested": False,
                "reingested": False,
                "sqlite_index_reused": sqlite_index_reused,
                "cache_enhanced": bool(enhancements_built),
                "enhancements_built": enhancements_built,
            }
        )
        return payload

    pages = pre_extracted_pages or extract_pages(path, ocr=ocr, ocr_lang=ocr_lang)
    quality = assess_pages(pages)
    write_jsonl(pages_path, [page.to_dict() for page in pages])
    full_text_path, markdown_path_value = _write_optional_text_outputs(
        path,
        pages,
        meta.get("title"),
        text_path,
        markdown_path,
        write_full_text,
        write_markdown,
        layout_mode,
    )

    should_extract_tables = _should_extract_tables(mode, extract_tables_opt, pages)
    table_results: list[dict[str, Any]] = []
    if should_extract_tables:
        table_results = extract_tables(
            path,
            out_dir / "tables",
            pages=_table_candidate_pages(pages),
        )

    vector_path = None
    if build_vector_index_opt or mode == "full":
        vector = build_vector_index(document_id, pages, paths.index / "vector_store")
        vector_path = vector.get("vector_index_path")

    _write_json_atomic(quality_path, quality)
    meta_full = {
        **meta,
        "document_id": document_id,
        "local_pdf_path": str(path),
        "meta_path": str(meta_path),
        "pages_jsonl_path": str(pages_path),
        "full_text_path": full_text_path,
        "markdown_path": markdown_path_value,
        "quality_report_path": str(quality_path),
        "md5": md5,
        "sha256": sha,
        "page_count": len(pages),
        "char_count": quality["char_count"],
        "quality": quality,
        "tables": table_results,
        "table_extraction": _table_extraction_state(table_results, should_extract_tables),
        "vector_index_path": vector_path,
        "ingest_mode": mode,
        "extract_tables": should_extract_tables,
        "ocr_mode": ocr,
        "ocr_lang": ocr_lang,
        "ocr_pages": [page.page_no for page in pages if page.ocr_used],
        "layout_mode": layout_mode,
        "text_outputs": {
            "full_text": bool(full_text_path),
            "markdown": bool(markdown_path_value),
            "default_policy": "core index only; full_text.txt and document.md are optional",
        },
        "ingested_at": now_iso(),
    }
    _write_json_atomic(meta_path, meta_full)

    store = SQLiteStore()
    _sync_sqlite_index(
        store,
        document_id,
        path,
        meta_full,
        pages,
        meta_path,
        pages_path,
        full_text_path,
        markdown_path_value,
        md5,
        sha,
        table_results,
    )
    store.log_ingest(document_id, str(path), "ok")

    payload = PdfIngestResult(
        document_id=document_id,
        pdf_path=str(path),
        meta_path=str(meta_path),
        pages_jsonl_path=str(pages_path),
        full_text_path=full_text_path,
        markdown_path=markdown_path_value,
        page_count=len(pages),
        char_count=quality["char_count"],
        md5=md5,
        sha256=sha,
        sqlite_path=str(paths.sqlite_path),
        fts_enabled=True,
        vector_index_path=vector_path,
    ).to_dict()
    payload.update(
        {
            "cache_status": cache_status,
            "ingest_cache_hit": False,
            "ingested": True,
            "reingested": cache_status
            in {"stale_hash_mismatch", "stale_missing_hash", "corrupt_cache", "forced_overwrite"},
        }
    )
    return payload
