from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def validate_document_id(value: Any) -> str:
    """Validate an ID before using it as a single filesystem path component."""
    document_id = str(value or "")
    if not document_id:
        raise ValueError("document_id must not be empty")
    if document_id != document_id.strip() or document_id.endswith("."):
        raise ValueError("document_id must not have unsafe leading or trailing characters")
    if document_id in {".", ".."}:
        raise ValueError("document_id must not be a relative path segment")
    if "/" in document_id or "\\" in document_id:
        raise ValueError("document_id must not contain path separators")
    if Path(document_id).is_absolute() or re.match(r"^[A-Za-z]:", document_id):
        raise ValueError("document_id must not be an absolute path")
    if re.search(r'[<>:"|?*\x00-\x1f]', document_id):
        raise ValueError("document_id contains characters unsafe for filesystem paths")
    return document_id


def safe_document_path(parent: Path, document_id: Any) -> Path:
    """Build a child path from a validated document ID.

    This helper is intentionally reusable by ingest and cleanup code.
    """
    validated = validate_document_id(document_id)
    resolved_parent = parent.resolve()
    candidate = (resolved_parent / validated).resolve()
    if candidate == resolved_parent or candidate.parent != resolved_parent:
        raise ValueError("document_id does not resolve to a direct child path")
    return candidate


def safe_name(value: Any, fallback: str = "document", max_length: int = 120) -> str:
    text = re.sub(r"[\\/:*?\"<>|\r\n\t]+", "_", str(value or "")).strip(" ._")
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"_+", "_", text)
    return (text or fallback)[:max_length]


def safe_slug(value: Any, fallback: str = "document", max_length: int = 80) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "_", text).strip("_")
    text = re.sub(r"_+", "_", text)
    return (text or fallback)[:max_length]


def infer_language(title: Any = None, document_language: Any = None) -> str:
    if document_language:
        text = str(document_language).strip().upper()
        if text in {"ZH", "CN", "CHS", "CHT", "SC", "TC"}:
            return "ZH"
        if text in {"EN", "ENG"}:
            return "EN"
    return "ZH" if re.search(r"[\u4e00-\u9fff]", str(title or "")) else "EN"


def company_short_name(meta: dict[str, Any], fallback_title: str = "document") -> str:
    explicit = meta.get("company_short_name") or meta.get("short_name")
    if explicit:
        return safe_name(explicit, fallback="company", max_length=40)

    market = str(meta.get("market") or "").upper()
    name = str(meta.get("company_name") or "").strip()
    if not name or name.isdigit():
        name = str(meta.get("issuer") or meta.get("title") or fallback_title).strip()

    if market.startswith("A"):
        for suffix in ["股份有限公司", "有限责任公司", "有限公司", "集团股份", "集团"]:
            name = name.replace(suffix, "")
        match = re.search(r"[\u4e00-\u9fffA-Za-z0-9\-]+", name)
        return safe_name(match.group(0) if match else name, fallback="company", max_length=40)

    name = re.sub(r"\b(HOLDINGS?|GROUP|LIMITED|LTD|INC|CORPORATION|CORP|COMPANY|CO)\b\.?", "", name, flags=re.I)
    name = re.sub(r"\s+", "_", name).strip("_ .")
    return safe_name(name, fallback="company", max_length=40)


def normalize_document_type(document_type: Any = None, title: Any = None) -> str:
    text = f"{document_type or ''} {title or ''}".lower()
    if "annual report" in text or "年度报告" in text or "年报" in text:
        return "annual_report"
    if "interim" in text or "半年度" in text or "半年报" in text:
        return "interim_report"
    if "quarter" in text or "季度" in text or "季报" in text:
        return "quarterly_report"
    if "prospectus" in text or "招股" in text or "global offering" in text:
        return "prospectus"
    if "offering" in text or "募集说明书" in text:
        return "offering_document"
    return safe_slug(document_type or "filing", max_length=40)


def infer_report_year(title: Any = None, publish_time: Any = None, explicit_year: Any = None) -> str:
    if explicit_year:
        return str(explicit_year)
    title_text = str(title or "")
    matches = re.findall(r"(?:19|20)\d{2}", title_text)
    if matches:
        return matches[0]
    publish_text = str(publish_time or "")
    match = re.search(r"(?:19|20)\d{2}", publish_text)
    return match.group(0) if match else "undated"


def build_document_id(meta: dict[str, Any], fallback_title: str = "document") -> str:
    market = safe_slug(meta.get("market") or "M", max_length=8).upper()
    symbol = safe_slug(meta.get("symbol") or "UNKNOWN", max_length=16).upper()
    year = infer_report_year(meta.get("title"), meta.get("publish_time"), meta.get("report_year"))
    doc_type = normalize_document_type(meta.get("document_type"), meta.get("title"))
    language = infer_language(meta.get("title"), meta.get("language") or meta.get("document_language"))
    short_name = company_short_name(meta, fallback_title=fallback_title)
    return safe_name("_".join([market, symbol, year, doc_type, language, short_name]), max_length=140)


def build_pdf_filename(meta: dict[str, Any], fallback_title: str = "document") -> str:
    return f"{build_document_id(meta, fallback_title=fallback_title)}.pdf"
