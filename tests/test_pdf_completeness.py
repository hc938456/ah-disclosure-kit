from __future__ import annotations

from ah_disclosure.models import PdfPage
from ah_disclosure.pdf import completeness


def test_rejects_short_announcement(monkeypatch, tmp_path):
    path = tmp_path / "announcement.pdf"
    path.write_bytes(b"%PDF placeholder")
    monkeypatch.setattr(completeness, "_extract_pdf_text", lambda _path: (2, "Annual report available online"))

    result = completeness.validate_annual_report_pdf(path)

    assert result["complete"] is False
    assert result["status"] == "rejected_short_document"


def test_accepts_traditional_chinese_annual_report(monkeypatch, tmp_path):
    path = tmp_path / "annual.pdf"
    path.write_bytes(b"%PDF placeholder")
    text = "獨立核數師報告 財務報表附註 綜合收益表 財務狀況表"
    monkeypatch.setattr(completeness, "_extract_pdf_text", lambda _path: (188, text))

    result = completeness.validate_annual_report_pdf(path)

    assert result["complete"] is True


def test_accepts_line_broken_financial_statement_notes(monkeypatch, tmp_path):
    path = tmp_path / "annual.pdf"
    path.write_bytes(b"%PDF placeholder")
    text = "审计报告 二、财务报表 资产负债表 利润表 财\n务报表附注" * 100
    pages = [PdfPage(page_no=index, text=text, char_count=len(text)) for index in range(1, 101)]

    result = completeness.validate_annual_report_pages(path, pages)

    assert result["complete"] is True
    assert "notes" in result["matched_sections"]
    assert result["section_match_count"] >= 2


def test_accepts_simplified_chinese_annual_report(monkeypatch, tmp_path):
    path = tmp_path / "annual.pdf"
    path.write_bytes(b"%PDF placeholder")
    text = "独立审计师报告 财务报表附注 合并利润表 资产负债表"
    monkeypatch.setattr(completeness, "_extract_pdf_text", lambda _path: (160, text))

    result = completeness.validate_annual_report_pdf(path)

    assert result["complete"] is True
    assert result["section_match_count"] >= 2


def test_accepts_bank_annual_report_with_plain_income_statement_heading(
    monkeypatch, tmp_path
):
    path = tmp_path / "bank-annual.pdf"
    path.write_bytes(b"%PDF placeholder")
    text = "审计报告 财务报表附注 利润表 资产负债表"
    monkeypatch.setattr(completeness, "_extract_pdf_text", lambda _path: (360, text))

    result = completeness.validate_annual_report_pdf(path)

    assert result["complete"] is True
    assert result["has_audited_financials"] is True


def test_accepts_notes_on_the_financial_statements_heading(monkeypatch, tmp_path):
    path = tmp_path / "annual-report-and-accounts.pdf"
    path.write_bytes(b"%PDF placeholder")
    text = (
        "Independent auditors' report. Notes on the financial statements. "
        "Statement of financial position. Statement of comprehensive income. "
    ) * 1000
    monkeypatch.setattr(completeness, "_extract_pdf_text", lambda _path: (372, text))

    result = completeness.validate_annual_report_pdf(path)

    assert result["complete"] is True
    assert result["has_audited_financials"] is True


def test_accepts_us_gaap_notes_without_the_in_heading(monkeypatch, tmp_path):
    path = tmp_path / "form-20f-annual-report.pdf"
    path.write_bytes(b"%PDF placeholder")
    text = (
        "Independent auditor's report. Notes to Consolidated Financial Statements. "
        "Consolidated Balance Sheets. Consolidated Income Statements. "
    ) * 1000
    monkeypatch.setattr(completeness, "_extract_pdf_text", lambda _path: (374, text))

    result = completeness.validate_annual_report_pdf(path)

    assert result["complete"] is True
    assert result["has_audited_financials"] is True


def test_rejects_long_results_announcement_without_auditor_report(monkeypatch, tmp_path):
    path = tmp_path / "results-announcement.pdf"
    path.write_bytes(b"%PDF placeholder")
    text = ("财务报表 财务报表附注 合并利润表 资产负债表 " * 1000).strip()
    monkeypatch.setattr(completeness, "_extract_pdf_text", lambda _path: (88, text))

    result = completeness.validate_annual_report_pdf(path)

    assert result["complete"] is False
    assert result["status"] == "needs_review_missing_sections"


def test_rejects_short_global_offering_announcement(monkeypatch, tmp_path):
    path = tmp_path / "global-offering-announcement.pdf"
    path.write_bytes(b"%PDF placeholder")
    monkeypatch.setattr(
        completeness,
        "_extract_pdf_text",
        lambda _path: (9, "GLOBAL OFFERING investors should read the Prospectus"),
    )

    result = completeness.validate_prospectus_pdf(path)

    assert result["complete"] is False
    assert result["status"] == "rejected_short_document"


def test_accepts_full_bilingual_prospectus(monkeypatch, tmp_path):
    path = tmp_path / "prospectus.pdf"
    path.write_bytes(b"%PDF placeholder")
    text = "GLOBAL OFFERING RISK FACTORS BUSINESS FINANCIAL INFORMATION ACCOUNTANTS' REPORT"
    monkeypatch.setattr(completeness, "_extract_pdf_text", lambda _path: (632, text))

    result = completeness.validate_prospectus_pdf(path)

    assert result["complete"] is True
    assert result["has_prospectus_structure"] is True


def test_accepts_a_share_business_and_technology_heading(monkeypatch, tmp_path):
    path = tmp_path / "prospectus.pdf"
    path.write_bytes(b"%PDF placeholder")
    text = "招股说明书 风险因素 业务和技术 财务会计信息" * 100
    pages = [PdfPage(page_no=index, text=text, char_count=len(text)) for index in range(1, 101)]

    result = completeness.validate_prospectus_pages(path, pages)

    assert result["complete"] is True
    assert "business" in result["matched_sections"]
