from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ah_disclosure.core.naming import build_document_id
from ah_disclosure.core.paths import get_data_paths
from ah_disclosure.core.time_utils import now_iso
from ah_disclosure.models import PdfIngestResult, PdfPage
from ah_disclosure.pdf.downloader import file_md5, file_sha256
from ah_disclosure.pdf.markdown import pdf_to_markdown
from ah_disclosure.pdf.quality import assess_pages
from ah_disclosure.pdf.table_extract import extract_tables
from ah_disclosure.pdf.text_extract import extract_pages
from ah_disclosure.pdf.vector_index import build_vector_index
from ah_disclosure.storage.jsonl_store import write_jsonl
from ah_disclosure.storage.sqlite_store import SQLiteStore


def safe_document_id(text: str) -> str:
    value = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", str(text)).strip("_")
    return (value or "document")[:140]


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
                )
            )
    return pages


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
) -> dict[str, Any]:
    path = Path(pdf_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    meta = meta or {}
    md5 = file_md5(path)
    sha = file_sha256(path)
    document_id = document_id or build_document_id(meta, fallback_title=path.stem)
    paths = get_data_paths()
    out_dir = paths.parsed_document_dir(document_id)
    meta_path = out_dir / "meta.json"
    pages_path = out_dir / "pages.jsonl"
    text_path = out_dir / "full_text.txt"
    markdown_path = out_dir / "document.md"
    quality_path = out_dir / "quality_report.json"
    write_full_text = write_full_text or mode == "full"
    write_markdown = write_markdown or mode == "full"

    if pages_path.exists() and meta_path.exists() and not overwrite:
        old = json.loads(meta_path.read_text(encoding="utf-8"))
        old = _merge_meta(old, meta)
        pages = _read_pages_jsonl(pages_path)
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
            if markdown_path_value:
                old["markdown_path"] = markdown_path_value
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
        meta_path.write_text(json.dumps(old, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        store = SQLiteStore()
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
            old.get("tables") or [],
        )
        store.log_ingest(document_id, str(path), "ok_cached")
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
        return result.to_dict()

    pages = extract_pages(path, ocr=ocr, ocr_lang=ocr_lang)
    quality = assess_pages(pages)
    write_jsonl(pages_path, [page.to_dict() for page in pages])
    all_text = "\n\n".join(page.text for page in pages)
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

    should_extract_tables = (
        mode == "full"
        or extract_tables_opt is True
        or (
            extract_tables_opt == "auto"
            and any(keyword in all_text for keyword in ["募集资金", "前五大客户", "主营构成", "分部收入", "资产负债表", "利润表", "现金流量表"])
        )
    )
    table_results: list[dict[str, Any]] = []
    if should_extract_tables:
        candidate_pages = [
            page.page_no
            for page in pages
            if any(keyword in page.text for keyword in ["募集资金", "前五大客户", "主营", "分部", "资产负债表", "利润表", "现金流量表"])
        ] or None
        table_results = extract_tables(path, out_dir / "tables", pages=candidate_pages)

    vector_path = None
    if build_vector_index_opt or mode == "full":
        vector = build_vector_index(document_id, pages, paths.index / "vector_store")
        vector_path = vector.get("vector_index_path")

    quality_path.write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8")
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
    meta_path.write_text(json.dumps(meta_full, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

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

    return PdfIngestResult(
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
