from __future__ import annotations

from ah_disclosure.clients import cninfo_client
from ah_disclosure.clients.cninfo_client import CninfoClient, _pdf_url


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_cninfo_urls_use_https():
    assert cninfo_client.CNINFO_BASE.startswith("https://")
    assert _pdf_url("finalpage/2026-01-01/example.pdf") == (
        "https://static.cninfo.com.cn/finalpage/2026-01-01/example.pdf"
    )
    assert _pdf_url("http://static.cninfo.com.cn/example.pdf") == (
        "https://static.cninfo.com.cn/example.pdf"
    )


def test_cninfo_missing_symbol_uses_top_search_fallback(monkeypatch):
    saved = {}
    monkeypatch.setattr(cninfo_client, "_read_org_map_cache", lambda: {})
    monkeypatch.setattr(cninfo_client, "_write_org_map_cache", lambda mapping: saved.update(mapping))
    client = CninfoClient()
    monkeypatch.setattr(
        client.session,
        "get",
        lambda *args, **kwargs: _Response({"stockList": [{"code": "600519", "orgId": "gssz0000531"}]}),
    )
    monkeypatch.setattr(
        client.session,
        "post",
        lambda *args, **kwargs: _Response([{"code": "300750", "orgId": "GD165627"}]),
    )

    assert client.lookup_stock_org_id("300750") == "GD165627"
    assert saved["300750"] == "GD165627"
