from __future__ import annotations

from pathlib import Path

from ah_disclosure.models import PdfPage
from ah_disclosure.pdf.ocr import ocr_pdf_page, tesseract_available


def _ocr_enabled(ocr: str, text: str, min_chars: int) -> bool:
    mode = str(ocr or "auto").strip().lower()
    if mode in {"0", "false", "no", "none", "off", "disabled"}:
        return False
    if mode in {"1", "true", "yes", "force", "always"}:
        return True
    return len((text or "").strip()) < min_chars and tesseract_available()


def _page_quality(text: str) -> float:
    return min(1.0, len(text.strip()) / 800.0) if text.strip() else 0.0


def extract_pages(
    path: str | Path,
    max_pages: int | None = None,
    ocr: str = "auto",
    ocr_lang: str = "chi_sim+eng",
    ocr_min_chars: int = 50,
) -> list[PdfPage]:
    pdf_path = Path(path).expanduser().resolve()
    if pdf_path.suffix.lower() != ".pdf":
        text = pdf_path.read_text(encoding="utf-8", errors="ignore")
        return [PdfPage(1, text, len(text), False, 1.0)]
    try:
        import fitz  # PyMuPDF

        pages: list[PdfPage] = []
        with fitz.open(pdf_path) as doc:
            n = len(doc) if max_pages is None else min(len(doc), max_pages)
            for idx in range(n):
                text = doc[idx].get_text("text") or ""
                ocr_used = False
                if _ocr_enabled(ocr, text, ocr_min_chars):
                    ocr_result = ocr_pdf_page(pdf_path, idx + 1, lang=ocr_lang)
                    if ocr_result.get("text"):
                        text = str(ocr_result["text"])
                        ocr_used = True
                pages.append(PdfPage(idx + 1, text, len(text), ocr_used, _page_quality(text)))
        return pages
    except Exception:
        pass
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        n = len(reader.pages) if max_pages is None else min(len(reader.pages), max_pages)
        pages = []
        for idx in range(n):
            text = reader.pages[idx].extract_text() or ""
            pages.append(PdfPage(idx + 1, text, len(text), False, _page_quality(text)))
        return pages
    except Exception as exc:
        return [PdfPage(1, f"[PDF text extraction failed: {exc}]", 0, False, 0.0)]
