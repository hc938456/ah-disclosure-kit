from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


def _clean(value: Any) -> Any:
    try:
        if value != value:
            return None
    except Exception:
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    return value


def serializable_dict(obj: Any) -> dict[str, Any]:
    return _clean(asdict(obj))


@dataclass(slots=True)
class CompanyIdentity:
    market: str
    symbol: str
    name: str | None = None
    exchange: str | None = None
    cninfo_org_id: str | None = None
    hkex_stock_id: str | None = None
    aliases: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return serializable_dict(self)


@dataclass(slots=True)
class FilingRecord:
    market: str
    symbol: str
    company_name: str
    title: str
    publish_time: str
    document_type: str | None = None
    source: str = ""
    detail_url: str | None = None
    pdf_url: str | None = None
    raw_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return serializable_dict(self)


@dataclass(slots=True)
class ProspectusRecord:
    market: str
    company_name: str
    symbol: str | None = None
    board: str | None = None
    stage: str | None = None
    document_type: str = ""
    title: str = ""
    publish_date: str | None = None
    status: str | None = None
    sponsor: str | None = None
    law_firm: str | None = None
    accounting_firm: str | None = None
    source: str = ""
    source_url: str | None = None
    pdf_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return serializable_dict(self)


@dataclass(slots=True)
class CompanyDataResult:
    market: str
    symbol: str
    data_type: str
    interface: str
    source: str
    fetched_at: str
    rows: list[dict[str, Any]]
    columns: list[str]
    params: dict[str, Any] = field(default_factory=dict)
    total_rows: int | None = None
    returned_rows: int | None = None
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return serializable_dict(self)


@dataclass(slots=True)
class PdfPage:
    page_no: int
    text: str
    char_count: int
    ocr_used: bool = False
    quality_score: float | None = None
    section_title: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return serializable_dict(self)


@dataclass(slots=True)
class PdfIngestResult:
    document_id: str
    pdf_path: str
    meta_path: str
    pages_jsonl_path: str
    full_text_path: str | None
    markdown_path: str | None
    page_count: int
    char_count: int
    md5: str
    sha256: str
    sqlite_path: str | None = None
    fts_enabled: bool = False
    vector_index_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return serializable_dict(self)


@dataclass(slots=True)
class EvidenceItem:
    source_type: str
    document_id: str | None = None
    market: str | None = None
    symbol: str | None = None
    company_name: str | None = None
    page_no: int | None = None
    section_title: str | None = None
    text: str | None = None
    table_path: str | None = None
    structured_payload: dict[str, Any] | None = None
    source_url: str | None = None
    local_pdf_path: str | None = None
    score: float | None = None
    token_estimate: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return serializable_dict(self)


@dataclass(slots=True)
class EvidencePacket:
    query: str
    route: str
    market: str | None = None
    symbol: str | None = None
    company_name: str | None = None
    evidence_items: list[EvidenceItem] = field(default_factory=list)
    token_estimate: int = 0
    max_chars: int = 12000
    truncated: bool = False
    generated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return serializable_dict(self)
