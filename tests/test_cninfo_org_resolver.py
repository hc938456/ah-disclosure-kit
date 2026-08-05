from __future__ import annotations

import pytest
import requests

from ah_disclosure.clients import cninfo_client
from ah_disclosure.clients.cninfo_client import (
    CninfoClient,
    CninfoLookupTimeoutError,
    _pdf_url,
)


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class _InvalidJsonResponse(_Response):
    def json(self):
        raise ValueError("not json")


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


def test_cninfo_request_timeout_becomes_bounded_lookup_error(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        cninfo_client,
        "_read_org_map_cache",
        lambda: {"300502": "9900029344"},
    )
    client = CninfoClient(timeout=0.25, lookup_budget=1.0)

    def fail(*args, **kwargs):
        captured["timeout"] = kwargs["timeout"]
        raise requests.Timeout("upstream stalled")

    monkeypatch.setattr(client.session, "post", fail)

    with pytest.raises(CninfoLookupTimeoutError) as captured_error:
        client.search_filings(symbol="300502", max_rows=30)

    assert captured["timeout"] <= 0.25
    assert captured_error.value.code == "cninfo_source_lookup_timeout"
    assert captured_error.value.operation == "announcement query"


def test_cninfo_proxy_failure_becomes_actionable_source_error(monkeypatch):
    monkeypatch.setattr(
        cninfo_client,
        "_read_org_map_cache",
        lambda: {"300502": "9900029344"},
    )
    client = CninfoClient(timeout=0.25, lookup_budget=1.0)

    def fail_proxy(*args, **kwargs):
        raise requests.exceptions.ProxyError("local proxy unavailable")

    monkeypatch.setattr(client.session, "post", fail_proxy)

    with pytest.raises(cninfo_client.CninfoSourceLookupError) as captured_error:
        client.search_filings(symbol="300502", max_rows=30)

    assert not isinstance(captured_error.value, CninfoLookupTimeoutError)
    assert captured_error.value.code == "cninfo_source_lookup_error"
    assert "Check network and proxy availability" in str(captured_error.value)
    assert "local proxy unavailable" not in str(captured_error.value)


def test_cninfo_invalid_json_becomes_actionable_source_error(monkeypatch):
    monkeypatch.setattr(
        cninfo_client,
        "_read_org_map_cache",
        lambda: {"300502": "9900029344"},
    )
    client = CninfoClient(timeout=0.25, lookup_budget=1.0)
    monkeypatch.setattr(
        client.session,
        "post",
        lambda *args, **kwargs: _InvalidJsonResponse(None),
    )

    with pytest.raises(cninfo_client.CninfoSourceLookupError, match="invalid JSON"):
        client.search_filings(symbol="300502", max_rows=30)


def test_cninfo_lookup_budget_stops_sequential_pages(monkeypatch):
    clock = iter([0.0, 0.2, 0.4, 1.1])
    monkeypatch.setattr(cninfo_client.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(
        cninfo_client,
        "_read_org_map_cache",
        lambda: {"300502": "9900029344"},
    )
    calls = {"count": 0}
    client = CninfoClient(timeout=0.8, lookup_budget=1.0)

    def respond(*args, **kwargs):
        calls["count"] += 1
        return _Response({"totalAnnouncement": 5, "announcements": []})

    monkeypatch.setattr(client.session, "post", respond)

    with pytest.raises(CninfoLookupTimeoutError, match="internal budget"):
        client.search_filings(
            symbol="300502",
            max_rows=5,
            page_size=1,
            max_pages=5,
        )

    assert calls["count"] == 1
