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


def test_company_info_uses_a_direct_bounded_request(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "rc": 0,
                "data": {
                    "f43": 11.28,
                    "f57": "000001",
                    "f58": "平安银行",
                },
            }

    def fake_get(url, *, params, timeout):
        captured.update({"url": url, "params": params, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr(akshare_a_client.requests, "get", fake_get)

    result = ACompanyClient().call_interface("company_info", "000001").to_dict()

    assert captured["url"] == "https://push2delay.eastmoney.com/api/qt/stock/get"
    assert captured["timeout"] == 20
    assert captured["params"]["secid"] == "0.000001"
    assert result["source"] == "Eastmoney direct"
    assert result["rows"] == [
        {"item": "最新", "value": 11.28},
        {"item": "股票代码", "value": "000001"},
        {"item": "股票简称", "value": "平安银行"},
    ]


def test_top_float_shareholders_filters_at_source(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "success": True,
                "result": {
                    "data": [
                        {
                            "HOLDER_NAME": "测试股东",
                            "HOLDER_TYPE": "基金",
                            "SECURITY_CODE": "600519",
                            "SECURITY_NAME_ABBR": "贵州茅台",
                            "END_DATE": "2025-03-31 00:00:00",
                            "HOLD_NUM": 100,
                            "XZCHANGE": 10,
                            "CHANGE_RATIO": 0.1,
                            "HOLDNUM_CHANGE_NAME": "增加",
                            "HOLDER_MARKET_CAP": 200,
                            "UPDATE_DATE": "2025-04-30 00:00:00",
                        }
                    ]
                },
            }

    def fake_get(url, *, params, timeout):
        captured.update({"url": url, "params": params, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr(akshare_a_client.requests, "get", fake_get)

    result = ACompanyClient().call_interface(
        "top_float_shareholders",
        "600519",
        date="20250331",
    ).to_dict()

    assert captured["timeout"] == 20
    assert captured["params"]["pageSize"] == "100"
    assert captured["params"]["filter"] == (
        "(END_DATE='2025-03-31')(SECURITY_CODE=\"600519\")"
    )
    assert result["total_rows"] == 1
    assert result["source"] == "Eastmoney direct"
    assert result["rows"][0]["股票代码"] == "600519"
    assert result["rows"][0]["报告期"] == "2025-03-31"


def test_top_float_shareholders_defaults_to_latest_period(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "success": True,
                "result": {
                    "data": [
                        {
                            "HOLDER_NAME": "最新股东",
                            "SECURITY_CODE": "600519",
                            "END_DATE": "2025-06-30 00:00:00",
                        },
                        {
                            "HOLDER_NAME": "旧期股东",
                            "SECURITY_CODE": "600519",
                            "END_DATE": "2025-03-31 00:00:00",
                        },
                    ]
                },
            }

    def fake_get(url, *, params, timeout):
        captured.update({"url": url, "params": params, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr(akshare_a_client.requests, "get", fake_get)

    result = ACompanyClient().call_interface(
        "top_float_shareholders",
        "600519",
    ).to_dict()

    assert captured["params"]["filter"] == '(SECURITY_CODE="600519")'
    assert result["total_rows"] == 1
    assert result["rows"][0]["股东名称"] == "最新股东"
    assert result["rows"][0]["报告期"] == "2025-06-30"
