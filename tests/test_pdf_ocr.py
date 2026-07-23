from pathlib import Path

import fitz
import pytest
from PIL import Image, ImageDraw

from ah_disclosure.pdf.ocr import tesseract_available
from ah_disclosure.pdf.text_extract import extract_pages


@pytest.mark.skipif(not tesseract_available(), reason="Tesseract is not installed")
def test_force_ocr_extracts_image_only_pdf(tmp_path: Path):
    image_path = tmp_path / "page.png"
    pdf_path = tmp_path / "scan.pdf"
    image = Image.new("RGB", (1000, 320), "white")
    draw = ImageDraw.Draw(image)
    draw.text((80, 120), "Revenue OCR 12345", fill="black")
    image.save(image_path)

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(fitz.Rect(50, 50, 545, 215), filename=str(image_path))
    doc.save(pdf_path)
    doc.close()

    pages = extract_pages(pdf_path, ocr="force", ocr_lang="eng")

    assert pages[0].ocr_used is True
    assert "Revenue" in pages[0].text


def test_auto_ocr_extracts_image_dominant_low_text_page(tmp_path: Path, monkeypatch):
    image_path = tmp_path / "scan.png"
    pdf_path = tmp_path / "scan.pdf"
    Image.new("RGB", (1000, 1400), "white").save(image_path)
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(page.rect, filename=str(image_path))
    doc.save(pdf_path)
    doc.close()
    monkeypatch.setattr("ah_disclosure.pdf.text_extract.tesseract_available", lambda: True)
    monkeypatch.setattr(
        "ah_disclosure.pdf.text_extract.ocr_pdf_page",
        lambda *args, **kwargs: {"text": "Revenue from OCR was 12345."},
    )

    pages = extract_pages(pdf_path, ocr="auto", ocr_lang="eng")

    assert pages[0].ocr_used is True
    assert pages[0].text == "Revenue from OCR was 12345."


def test_single_pymupdf_page_failure_falls_back_without_reprocessing_document(
    tmp_path: Path, monkeypatch
):
    pdf_path = tmp_path / "two-pages.pdf"
    doc = fitz.open()
    first = doc.new_page()
    first.insert_text((72, 72), "PDF first page")
    second = doc.new_page()
    second.insert_text((72, 72), "PDF second page")
    doc.save(pdf_path)
    doc.close()

    real_open = fitz.open

    class PageProxy:
        def __init__(self, page, fail=False):
            self._page = page
            self._fail = fail

        def get_text(self, *args, **kwargs):
            if self._fail:
                raise RuntimeError("synthetic page failure")
            return "PyMuPDF first page"

        def __getattr__(self, name):
            return getattr(self._page, name)

    class DocumentProxy:
        def __init__(self, path):
            self._doc = real_open(path)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self._doc.close()

        def __len__(self):
            return len(self._doc)

        def __getitem__(self, index):
            return PageProxy(self._doc[index], fail=index == 1)

    monkeypatch.setattr(fitz, "open", lambda path: DocumentProxy(path))

    pages = extract_pages(pdf_path, ocr="off")

    assert pages[0].text == "PyMuPDF first page"
    assert "PDF second page" in pages[1].text
    assert pages[0].extraction_method == "pymupdf"
    assert pages[1].extraction_method == "pypdf_fallback"
    assert "synthetic page failure" in pages[1].extraction_error
