from ah_disclosure.models import PdfPage
from ah_disclosure.pdf.quality import (
    assess_pages,
    normalize_layout_controls,
    text_quality_metrics,
)
from ah_disclosure.pdf.text_extract import _ocr_enabled, _ocr_result_is_better


def test_control_character_gibberish_is_low_quality(monkeypatch):
    text = ("A;B>C?D\x01" * 80) + "\n"
    metrics = text_quality_metrics(text)
    quality = assess_pages([PdfPage(1, text, len(text))])

    assert metrics["garbled_suspect"] is True
    assert quality["garbled_suspect_pages"] == [1]
    assert quality["quality_score"] == 0.0

    monkeypatch.setattr("ah_disclosure.pdf.text_extract.tesseract_available", lambda: True)
    assert _ocr_enabled("auto", text, 50) is True


def test_normal_long_text_does_not_trigger_garbled_detection():
    text = "Revenue is recognised when control transfers to the customer. " * 20

    assert text_quality_metrics(text)["garbled_suspect"] is False


def test_table_layout_controls_do_not_make_readable_text_garbled(monkeypatch):
    text = ("Revenue \x02 subscriptions \x02 Open Platform \x02 US$53,437\n" * 20)

    metrics = text_quality_metrics(text)
    monkeypatch.setattr("ah_disclosure.pdf.text_extract.tesseract_available", lambda: True)

    assert metrics["control_character_ratio"] >= 0.02
    assert metrics["has_readable_structure"] is True
    assert metrics["garbled_suspect"] is False
    assert _ocr_enabled("auto", text, 50, image_coverage=0.0) is False
    assert "\x02" not in normalize_layout_controls(text)


def test_auto_ocr_requires_image_coverage_for_low_text(monkeypatch):
    monkeypatch.setattr("ah_disclosure.pdf.text_extract.tesseract_available", lambda: True)

    assert _ocr_enabled("auto", "minimaxi.com", 50, image_coverage=0.0) is False
    assert _ocr_enabled("auto", "", 50, image_coverage=0.8) is True


def test_ocr_result_must_improve_existing_text():
    readable = "Revenue from subscriptions was US$53.4 million. " * 10

    assert _ocr_result_is_better(readable, "Revenve USS53A", 50) is False
    assert _ocr_result_is_better("", "Revenue from subscriptions was US$53.4 million.", 20)


def test_quality_report_lists_extraction_fallback_and_failed_pages():
    pages = [
        PdfPage(1, "Readable native text " * 20, 400, extraction_method="pymupdf"),
        PdfPage(2, "Readable fallback text " * 20, 440, extraction_method="pypdf_fallback"),
        PdfPage(3, "", 0, extraction_method="failed", extraction_error="broken page"),
    ]

    quality = assess_pages(pages)

    assert quality["extraction_fallback_pages"] == [2]
    assert quality["extraction_failed_pages"] == [3]
    assert quality["extraction_issue_count"] == 2
