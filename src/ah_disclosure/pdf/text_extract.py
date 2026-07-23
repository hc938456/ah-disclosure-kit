from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
from typing import Any

from ah_disclosure.core.logging import get_logger
from ah_disclosure.models import PdfPage
from ah_disclosure.pdf.ocr import ocr_pdf_page, tesseract_available
from ah_disclosure.pdf.quality import normalize_layout_controls, text_quality_metrics


logger = get_logger(__name__)


def _ocr_enabled(
    ocr: str,
    text: str,
    min_chars: int,
    image_coverage: float | None = None,
    quality_metrics: dict[str, Any] | None = None,
) -> bool:
    mode = str(ocr or "auto").strip().lower()
    if mode in {"0", "false", "no", "none", "off", "disabled"}:
        return False
    if mode in {"1", "true", "yes", "force", "always"}:
        return True
    low_text = len((text or "").strip()) < min_chars
    metrics = quality_metrics if quality_metrics is not None else text_quality_metrics(text)
    garbled = bool(metrics.get("garbled_suspect"))
    if low_text and image_coverage is not None and image_coverage < 0.1:
        low_text = False
    return (low_text or garbled) and tesseract_available()


def _page_image_coverage(page: Any) -> float:
    try:
        page_area = max(float(page.rect.width * page.rect.height), 1.0)
        image_area = 0.0
        for image in page.get_images(full=True):
            for rect in page.get_image_rects(image[0]):
                image_area += max(float(rect.width), 0.0) * max(float(rect.height), 0.0)
        return min(image_area / page_area, 1.0)
    except Exception:
        # A low-text page with unreadable image metadata is safer to OCR than skip.
        return 1.0


def _ocr_result_is_better(original: str, candidate: str, min_chars: int) -> bool:
    original_text = normalize_layout_controls(original).strip()
    candidate_text = normalize_layout_controls(candidate).strip()
    if not candidate_text:
        return False
    candidate_metrics = text_quality_metrics(candidate_text)
    if candidate_metrics["garbled_suspect"]:
        return False
    if not original_text:
        return len(candidate_text) >= min(min_chars, 20)
    original_metrics = text_quality_metrics(original)
    if original_metrics["garbled_suspect"]:
        return (
            candidate_metrics["readable_word_count"]
            > original_metrics["readable_word_count"]
        )
    if len(original_text) < min_chars:
        return len(candidate_text) >= max(min_chars, len(original_text) * 2)
    return False


def _page_quality(text: str) -> float:
    if not text.strip():
        return 0.0
    metrics = text_quality_metrics(text)
    if metrics["garbled_suspect"]:
        return 0.0
    return min(1.0, len(text.strip()) / 800.0)


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
        return [
            PdfPage(
                1,
                text,
                len(text),
                False,
                1.0,
                extraction_method="text",
            )
        ]
    try:
        import fitz  # PyMuPDF

        pages: list[PdfPage] = []
        fallback_reader: Any = None
        with ExitStack() as stack:
            doc = stack.enter_context(fitz.open(pdf_path))
            n = len(doc) if max_pages is None else min(len(doc), max_pages)
            for idx in range(n):
                try:
                    page = doc[idx]
                    raw_text = page.get_text("text") or ""
                    text = normalize_layout_controls(raw_text)
                    ocr_used = False
                    mode = str(ocr or "auto").strip().lower()
                    disabled = mode in {"0", "false", "no", "none", "off", "disabled"}
                    forced = mode in {"force", "always", "1", "true", "yes"}
                    metrics = text_quality_metrics(raw_text)
                    needs_auto_check = (
                        len(raw_text.strip()) < ocr_min_chars
                        or metrics["garbled_suspect"]
                    )
                    image_coverage = (
                        _page_image_coverage(page)
                        if not disabled and not forced and needs_auto_check
                        else None
                    )
                    if _ocr_enabled(
                        ocr,
                        raw_text,
                        ocr_min_chars,
                        image_coverage,
                        quality_metrics=metrics,
                    ):
                        try:
                            ocr_result = ocr_pdf_page(pdf_path, idx + 1, lang=ocr_lang)
                        except Exception as exc:
                            logger.warning(
                                "OCR failed for %s page %s; native text retained: %s",
                                pdf_path,
                                idx + 1,
                                exc,
                            )
                            ocr_result = {}
                        if ocr_result.get("text"):
                            ocr_text = normalize_layout_controls(str(ocr_result["text"]))
                            if forced or _ocr_result_is_better(
                                raw_text, ocr_text, ocr_min_chars
                            ):
                                text = ocr_text
                                ocr_used = True
                    pages.append(
                        PdfPage(
                            idx + 1,
                            text,
                            len(text),
                            ocr_used,
                            _page_quality(text),
                            extraction_method="ocr" if ocr_used else "pymupdf",
                        )
                    )
                except Exception as exc:
                    logger.warning(
                        "PyMuPDF text extraction failed for %s page %s; using pypdf for this page: %s",
                        pdf_path,
                        idx + 1,
                        exc,
                    )
                    try:
                        if fallback_reader is None:
                            from pypdf import PdfReader

                            fallback_stream = stack.enter_context(pdf_path.open("rb"))
                            fallback_reader = PdfReader(fallback_stream)
                        fallback_text = normalize_layout_controls(
                            fallback_reader.pages[idx].extract_text() or ""
                        )
                        pages.append(
                            PdfPage(
                                idx + 1,
                                fallback_text,
                                len(fallback_text),
                                False,
                                _page_quality(fallback_text),
                                extraction_method="pypdf_fallback",
                                extraction_error=str(exc),
                            )
                        )
                    except Exception as fallback_exc:
                        logger.error(
                            "All text extraction failed for %s page %s: %s",
                            pdf_path,
                            idx + 1,
                            fallback_exc,
                        )
                        pages.append(
                            PdfPage(
                                idx + 1,
                                f"[PDF page {idx + 1} text extraction failed: {fallback_exc}]",
                                0,
                                False,
                                0.0,
                                extraction_method="failed",
                                extraction_error=(
                                    f"PyMuPDF: {exc}; pypdf: {fallback_exc}"
                                ),
                            )
                        )
        return pages
    except Exception:
        pass
    try:
        from pypdf import PdfReader

        with pdf_path.open("rb") as stream:
            reader = PdfReader(stream)
            n = len(reader.pages) if max_pages is None else min(len(reader.pages), max_pages)
            pages = []
            for idx in range(n):
                text = normalize_layout_controls(reader.pages[idx].extract_text() or "")
                pages.append(
                    PdfPage(
                        idx + 1,
                        text,
                        len(text),
                        False,
                        _page_quality(text),
                        extraction_method="pypdf",
                    )
                )
        return pages
    except Exception as exc:
        return [
            PdfPage(
                1,
                f"[PDF text extraction failed: {exc}]",
                0,
                False,
                0.0,
                extraction_method="failed",
                extraction_error=str(exc),
            )
        ]
