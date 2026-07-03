from ah_disclosure.clients import akshare_a_client
from ah_disclosure.clients.akshare_a_client import ACompanyClient


def test_a_share_cache_stores_full_rows_and_applies_row_limit_on_read(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    calls = {"count": 0}

    def fake_get_akshare_function(name):
        def fake_func(**params):
            calls["count"] += 1
            return [{"code": "000001", "value": 1}, {"code": "000001", "value": 2}, {"code": "000001", "value": 3}]

        return fake_func

    monkeypatch.setattr(akshare_a_client, "get_akshare_function", fake_get_akshare_function)

    first = ACompanyClient().call_interface("company_profile", "000001", max_rows=1).to_dict()
    second = ACompanyClient().call_interface("company_profile", "000001", max_rows=2).to_dict()

    assert calls["count"] == 1
    assert first["returned_rows"] == 1
    assert first["truncated"] is True
    assert second["returned_rows"] == 2
    assert second["truncated"] is True
    assert second["params"]["cache_hit"] is True
