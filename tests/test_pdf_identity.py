from ah_disclosure.models import PdfPage
from ah_disclosure.pdf.identity import validate_document_identity


def test_identity_accepts_company_or_stock_code_and_year():
    pages = [
        PdfPage(
            1,
            "POP MART INTERNATIONAL GROUP LIMITED Stock Code: 9992 Annual Report 2025",
            80,
        )
    ]

    result = validate_document_identity(
        pages,
        expected_year=2025,
        expected_company_name="POP MART",
        expected_symbol="09992",
    )

    assert result["passed"] is True
    assert result["year_match"] is True
    assert result["company_match"] is True


def test_identity_rejects_wrong_company_and_symbol():
    pages = [PdfPage(1, "Example Holdings Annual Report 2025 Stock Code: 1234", 65)]

    result = validate_document_identity(
        pages,
        expected_year=2025,
        expected_company_name="POP MART",
        expected_symbol="09992",
    )

    assert result["passed"] is False


def test_short_hk_symbol_does_not_match_incidental_digit():
    pages = [PdfPage(1, "Annual Report 2025, page 5, unrelated issuer", 48)]

    result = validate_document_identity(pages, expected_year=2025, expected_symbol="00005")

    assert result["symbol_match"] is False
    assert result["passed"] is False


def test_hk_symbol_matches_labeled_unpadded_code():
    pages = [PdfPage(1, "Annual Report 2025 Stock Code: 5", 32)]

    result = validate_document_identity(pages, expected_year=2025, expected_symbol="00005")

    assert result["symbol_match"] is True
    assert result["passed"] is True


def test_chinese_legal_suffix_is_removed_for_company_match():
    pages = [PdfPage(1, "中国移动 2025年年度报告", 16)]

    result = validate_document_identity(
        pages, expected_year=2025, expected_company_name="中国移动有限公司"
    )

    assert result["company_tokens"] == ["中国移动"]
    assert result["company_match"] is True
    assert result["passed"] is True
