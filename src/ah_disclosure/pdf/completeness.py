from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ah_disclosure.models import PdfPage
from ah_disclosure.pdf.quality import text_quality_metrics


SECTION_PATTERNS: dict[str, tuple[str, ...]] = {
    "auditor_report": (
        r"auditor(?:s|[’']s)?\s+report",
        r"independent\s+auditors?[’'`s]*\s+report",
        r"independent\s+auditor.{0,6}report",
        r"report\s+of\s+the\s+independent\s+auditors?",
        r"auditors?\s+report",
        r"獨立核數師報告",
        r"独立核数师报告",
        r"獨立審計師報告",
        r"独立审计师报告",
        r"核數師報告",
        r"核数师报告",
        r"審計報告",
        r"审计报告",
    ),
    "financial_statements": (
        r"(?:consolidated\s+)?financial\s+statements",
        r"財務報表",
        r"财务报表",
        r"財務報告",
        r"财务报告",
    ),
    "notes": (
        r"notes?\s+to\s+(?:the\s+)?(?:consolidated\s+)?financial\s+(?:statements|accounts)",
        r"notes?\s+on\s+(?:the\s+)?(?:consolidated\s+)?financial\s+(?:statements|accounts)",
        r"財務(?:報表|報告)附註",
        r"财务(?:报表|报告)附注",
        r"財\s*務(?:報\s*表|報\s*告)\s*附\s*註",
        r"财\s*务(?:报\s*表|报\s*告)\s*附\s*注",
        r"(?:合併|合并)?財\s*務\s*報\s*表.{0,12}註\s*釋",
        r"(?:合併|合并)?财\s*务\s*报\s*表.{0,12}注\s*释",
        r"會計報表附註",
        r"会计报表附注",
    ),
    "financial_position": (
        r"statement\s+of\s+financial\s+position",
        r"balance\s+sheet",
        r"財務狀況表",
        r"财务状况表",
        r"資產負債表",
        r"资产负债表",
    ),
    "profit_or_loss": (
        r"statement\s+of\s+(?:profit\s+or\s+loss|comprehensive\s+income)",
        r"income\s+statement",
        r"綜合收益表",
        r"综合收益表",
        r"合併利潤表",
        r"合并利润表",
        r"利潤表",
        r"利润表",
        r"損益表",
        r"损益表",
    ),
}

PROSPECTUS_PATTERNS: dict[str, tuple[str, ...]] = {
    "offering_title": (
        r"\bprospectus\b",
        r"\bglobal\s+offering\b",
        r"招股章程",
        r"招股說明書",
        r"招股说明书",
        r"全球發售",
        r"全球发售",
    ),
    "risk_factors": (r"risk\s+factors", r"風險因素", r"风险因素"),
    "business": (
        r"\bbusiness\b",
        r"業務",
        r"业务与技术",
        r"業務與技術",
        r"业务和技术",
        r"業務和技術",
    ),
    "financial_information": (
        r"financial\s+information",
        r"財務資料",
        r"财务资料",
        r"財務會計資料",
        r"财务会计信息",
    ),
    "accountants_report": (
        r"accountants?[’'`s]*\s+report",
        r"report\s+of\s+the\s+reporting\s+accountants?",
        r"會計師報告",
        r"会计师报告",
        r"申報會計師報告",
        r"申报会计师报告",
    ),
}


def _extract_pdf_text(path: Path) -> tuple[int, str]:
    try:
        import fitz
    except ImportError as exc:  # pragma: no cover - depends on optional PDF extra
        raise RuntimeError("PDF completeness checks require pymupdf. Install ah-disclosure-kit[pdf].") from exc

    text_parts: list[str] = []
    with fitz.open(path) as document:
        page_count = document.page_count
        for page in document:
            text_parts.append(page.get_text("text"))
    return page_count, "\n".join(text_parts)


def _annual_report_result(
    pdf_path: Path,
    page_count: int,
    text: str,
) -> dict[str, Any]:
    normalized = re.sub(r"\s+", " ", text).casefold()
    matched_sections = [
        section
        for section, patterns in SECTION_PATTERNS.items()
        if any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in patterns)
    ]
    file_size = pdf_path.stat().st_size
    extracted_chars = len(normalized.strip())
    section_set = set(matched_sections)
    has_core_financials = {
        "notes",
        "financial_position",
        "profit_or_loss",
    }.issubset(section_set)
    has_audited_financials = "auditor_report" in section_set and has_core_financials

    if page_count <= 5:
        status = "rejected_short_document"
        complete = False
    elif page_count < 30:
        status = "needs_review_too_few_pages"
        complete = False
    elif has_audited_financials:
        status = "complete"
        complete = True
    elif page_count >= 60 and extracted_chars < page_count * 100:
        status = "needs_ocr"
        complete = None
    else:
        status = "needs_review_missing_sections"
        complete = False

    return {
        "path": str(pdf_path),
        "complete": complete,
        "status": status,
        "page_count": page_count,
        "file_size_bytes": file_size,
        "extracted_chars": extracted_chars,
        "matched_sections": matched_sections,
        "section_match_count": len(matched_sections),
        "has_audited_financials": has_audited_financials,
        "text_quality": text_quality_metrics(text),
    }


def validate_annual_report_pdf(path: str | Path) -> dict[str, Any]:
    pdf_path = Path(path).expanduser().resolve()
    page_count, text = _extract_pdf_text(pdf_path)
    return _annual_report_result(pdf_path, page_count, text)


def validate_annual_report_pages(path: str | Path, pages: list[PdfPage]) -> dict[str, Any]:
    pdf_path = Path(path).expanduser().resolve()
    return _annual_report_result(pdf_path, len(pages), "\n".join(page.text for page in pages))


def _prospectus_result(pdf_path: Path, page_count: int, text: str) -> dict[str, Any]:
    normalized = re.sub(r"\s+", " ", text).casefold()
    matched_sections = [
        section
        for section, patterns in PROSPECTUS_PATTERNS.items()
        if any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in patterns)
    ]
    section_set = set(matched_sections)
    substantive_sections = section_set - {"offering_title"}
    extracted_chars = len(normalized.strip())
    has_prospectus_structure = (
        "offering_title" in section_set
        and "risk_factors" in section_set
        and len(substantive_sections) >= 3
    )

    if page_count <= 15:
        status = "rejected_short_document"
        complete = False
    elif page_count < 50:
        status = "needs_review_too_few_pages"
        complete = False
    elif has_prospectus_structure:
        status = "complete"
        complete = True
    elif page_count >= 60 and extracted_chars < page_count * 100:
        status = "needs_ocr"
        complete = None
    else:
        status = "needs_review_missing_sections"
        complete = False

    return {
        "path": str(pdf_path),
        "complete": complete,
        "status": status,
        "page_count": page_count,
        "file_size_bytes": pdf_path.stat().st_size,
        "extracted_chars": extracted_chars,
        "matched_sections": matched_sections,
        "section_match_count": len(matched_sections),
        "has_prospectus_structure": has_prospectus_structure,
        "text_quality": text_quality_metrics(text),
    }


def validate_prospectus_pdf(path: str | Path) -> dict[str, Any]:
    pdf_path = Path(path).expanduser().resolve()
    page_count, text = _extract_pdf_text(pdf_path)
    return _prospectus_result(pdf_path, page_count, text)


def validate_prospectus_pages(path: str | Path, pages: list[PdfPage]) -> dict[str, Any]:
    pdf_path = Path(path).expanduser().resolve()
    return _prospectus_result(pdf_path, len(pages), "\n".join(page.text for page in pages))
