from __future__ import annotations

from ah_disclosure.models import PdfPage


def assess_pages(pages: list[PdfPage]) -> dict:
    char_count = sum(len(page.text or "") for page in pages)
    empty_pages = sum(1 for page in pages if len((page.text or "").strip()) < 50)
    avg_chars = char_count / len(pages) if pages else 0
    scanned_suspect_pages = [page.page_no for page in pages if len((page.text or "").strip()) < 50]
    return {
        "page_count": len(pages),
        "char_count": char_count,
        "avg_chars_per_page": avg_chars,
        "empty_or_low_text_pages": empty_pages,
        "scanned_suspect_pages": scanned_suspect_pages,
        "quality_score": min(1.0, avg_chars / 800.0) if pages else 0.0,
    }
