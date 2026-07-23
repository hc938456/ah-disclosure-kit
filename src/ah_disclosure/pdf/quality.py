from __future__ import annotations

import re

from ah_disclosure.models import PdfPage

PDF_LAYOUT_CONTROLS = "\x02"
PDF_LAYOUT_CONTROL_TRANSLATION = {ord(char): " " for char in PDF_LAYOUT_CONTROLS}
READABLE_WORD_THRESHOLD = 8


def normalize_layout_controls(text: str) -> str:
    """Replace known PDF table-layout markers without hiding real encoding failures."""
    return str(text or "").translate(PDF_LAYOUT_CONTROL_TRANSLATION)


def _bounded_readable_word_count(text: str) -> int:
    count = 0
    for _ in re.finditer(r"[A-Za-z]{2,}|[\u4e00-\u9fff]{2,}", text):
        count += 1
        if count >= READABLE_WORD_THRESHOLD:
            break
    return count


def text_quality_metrics(text: str) -> dict:
    body = str(text or "")
    meaningful_count = 0
    control_count = 0
    for char in body:
        if not char.isspace():
            meaningful_count += 1
        if ord(char) < 32 and char not in "\n\r\t":
            control_count += 1
    control_ratio = control_count / max(1, meaningful_count)
    control_suspect = meaningful_count >= 100 and control_ratio >= 0.02
    if control_suspect or meaningful_count < 100:
        readable_word_count = _bounded_readable_word_count(normalize_layout_controls(body))
    else:
        readable_word_count = READABLE_WORD_THRESHOLD
    has_readable_structure = readable_word_count >= READABLE_WORD_THRESHOLD
    return {
        "control_character_count": control_count,
        "control_character_ratio": control_ratio,
        "readable_word_count": readable_word_count,
        "has_readable_structure": has_readable_structure,
        "garbled_suspect": (
            control_suspect
            and not has_readable_structure
        ),
    }


def assess_pages(pages: list[PdfPage]) -> dict:
    char_count = sum(len(page.text or "") for page in pages)
    empty_pages = sum(1 for page in pages if len((page.text or "").strip()) < 50)
    avg_chars = char_count / len(pages) if pages else 0
    scanned_suspect_pages = [page.page_no for page in pages if len((page.text or "").strip()) < 50]
    garbled_suspect_pages = [
        page.page_no for page in pages if text_quality_metrics(page.text).get("garbled_suspect")
    ]
    extraction_fallback_pages = [
        page.page_no
        for page in pages
        if page.extraction_method == "pypdf_fallback"
    ]
    extraction_failed_pages = [
        page.page_no for page in pages if page.extraction_method == "failed"
    ]
    return {
        "page_count": len(pages),
        "char_count": char_count,
        "avg_chars_per_page": avg_chars,
        "empty_or_low_text_pages": empty_pages,
        "scanned_suspect_pages": scanned_suspect_pages,
        "garbled_suspect_pages": garbled_suspect_pages,
        "extraction_fallback_pages": extraction_fallback_pages,
        "extraction_failed_pages": extraction_failed_pages,
        "extraction_issue_count": len(extraction_fallback_pages)
        + len(extraction_failed_pages),
        "garbled_page_ratio": len(garbled_suspect_pages) / max(1, len(pages)),
        "quality_score": (
            min(1.0, avg_chars / 800.0) * (1 - len(garbled_suspect_pages) / max(1, len(pages)))
            if pages
            else 0.0
        ),
    }
