from ah_disclosure.identity.resolver import resolve_company
from ah_disclosure.models import EvidencePacket
from ah_disclosure.services.query_router import route_query


def test_resolve_a():
    result = resolve_company("600519")
    data = result.to_dict() if hasattr(result, "to_dict") else result
    assert data["market"] == "A"


def test_resolve_h():
    result = resolve_company("00700")
    data = result.to_dict() if hasattr(result, "to_dict") else result
    assert data["market"] == "H"
    assert data["symbol"] == "00700"


def test_evidence_packet():
    assert EvidencePacket(query="q", route="local").to_dict()["query"] == "q"


def test_query_router():
    assert route_query("查公司资料")["route"] == "structured_profile"
    assert route_query("腾讯2025年收入和净利润")["route"] == "structured_financials"
