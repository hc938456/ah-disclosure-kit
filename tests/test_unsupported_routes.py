from ah_disclosure.services.dossier_service import build_company_dossier
from ah_disclosure.services.evidence_service import get_evidence_packet


def test_unsupported_hk_ipo_list_evidence_packet_stops_early():
    packet = get_evidence_packet("2026年至今港股新增IPO上市公司list")

    assert packet["route"] == "unsupported_hk_ipo_annual_list"
    assert packet["unsupported"] is True
    assert packet["evidence_items"] == []


def test_unsupported_hk_ipo_list_dossier_does_not_fetch_default_data(monkeypatch):
    def fail_fetch(*args, **kwargs):
        raise AssertionError("default structured fetch should not run")

    monkeypatch.setattr("ah_disclosure.services.dossier_service.get_company_profile", fail_fetch)
    monkeypatch.setattr("ah_disclosure.services.dossier_service.get_financial_indicators", fail_fetch)
    monkeypatch.setattr("ah_disclosure.services.dossier_service.get_dividends", fail_fetch)

    dossier = build_company_dossier("H", "00700", "2026年至今港股新增IPO上市公司list")

    assert dossier["unsupported"] is True
    assert dossier["route"] == "unsupported_hk_ipo_annual_list"
