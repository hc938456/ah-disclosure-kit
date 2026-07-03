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
