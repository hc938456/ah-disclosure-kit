from ah_disclosure.clients import akshare_h_client
from ah_disclosure.clients.akshare_h_client import HCompanyClient


def test_h_akshare_result_is_cached(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    calls = {"count": 0}

    def fake_func(**params):
        calls["count"] += 1
        return [{"指标": "收入", "2025": 123}, {"指标": "净利润", "2025": 45}]

    monkeypatch.setattr(akshare_h_client, "get_akshare_function", lambda name: fake_func)

    first = HCompanyClient().call_interface("financial_statement", "00700", max_rows=1, statement="利润表").to_dict()
    second = HCompanyClient().call_interface("financial_statement", "00700", statement="利润表").to_dict()

    assert calls["count"] == 1
    assert len(first["rows"]) == 1
    assert len(second["rows"]) == 2
    assert second["params"]["cache_hit"] is True
