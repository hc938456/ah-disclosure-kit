from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any


def tesseract_available() -> bool:
    import shutil

    return shutil.which("tesseract") is not None


def _safe_image_to_string(image_path: Path, lang: str) -> tuple[str, str]:
    import pytesseract

    try:
        return pytesseract.image_to_string(str(image_path), lang=lang), lang
    except Exception:
        if lang != "eng" and "+" in lang:
            return pytesseract.image_to_string(str(image_path), lang="eng"), "eng"
        raise


def ocr_pdf_page(pdf_path: str | Path, page_no: int, lang: str = "chi_sim+eng", dpi: int = 200) -> dict[str, Any]:
    """OCR one PDF page locally with Tesseract."""
    result: dict[str, Any] = {
        "pdf_path": str(pdf_path),
        "page_no": page_no,
        "lang": lang,
        "available": tesseract_available(),
        "text": "",
        "error": None,
    }
    if not result["available"]:
        result["error"] = "tesseract executable not found"
        return result
    try:
        import fitz

        with fitz.open(Path(pdf_path).expanduser().resolve()) as doc:
            if page_no < 1 or page_no > len(doc):
                result["error"] = f"page_no out of range: {page_no}"
                return result
            page = doc[page_no - 1]
            matrix = fitz.Matrix(dpi / 72, dpi / 72)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            with tempfile.TemporaryDirectory() as tmp_dir:
                image_path = Path(tmp_dir) / f"page_{page_no}.png"
                pix.save(image_path)
                text, used_lang = _safe_image_to_string(image_path, lang)
        result["text"] = text or ""
        result["lang"] = used_lang
        return result
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result


# Backward-compatible alias for earlier drafts/tests.
def ocr_pdf_page_stub(pdf_path: str | Path, page_no: int, lang: str = "chi_sim+eng") -> dict[str, Any]:
    return ocr_pdf_page(pdf_path, page_no, lang=lang)
